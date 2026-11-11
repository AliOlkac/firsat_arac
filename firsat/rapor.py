"""HTML rapor: puanlı fırsat listesi (tek dosya, çevrimdışı açılır)."""
import json
from datetime import date
from pathlib import Path

from .degerlendirme import hasar_kisa
from .sorular import sorular as soru_uret

from .veritabani import KOK

NOT_YOLU = KOK / "veri" / "notlar.json"
CLAUDE_DUZELTME = {"AL": 3.0, "İNCELE": 0.0, "DİKKAT": -15.0}


def notlari_yukle():
    try:
        d = json.loads(NOT_YOLU.read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if not k.startswith("_")}
    except Exception:
        return {}


def kayit(s, notlar=None, mod="piyasa"):
    notlar = notlar if notlar is not None else notlari_yukle()
    c = notlar.get(s["ilan_id"])
    duzeltme = CLAUDE_DUZELTME.get(c[0], 0.0) if c else 0.0
    return {
        "id": s["ilan_id"], "url": s["url"], "baslik": s["baslik"], "marka": s["marka"], "seri": s["seri"],
        "model": s["model"], "yil": s["yil"], "km": s["km"], "fiyat": s["fiyat"], "adil": round(s["adil"]),
        "firsat": round(s["firsat"], 4), "guven": round(s["guven"], 2), "puan": s["puan"],
        "son_puan": round(max(0.0, min(100.0, (s["puan_hizli"] if mod == "hizli" else s["puan"]) + duzeltme)), 1),
        "karar": s["karar_hizli"] if mod == "hizli" else s["karar"], "claude": c[:2] if c else None,
        "sorular": list(c[2]) if c and len(c) > 2 else soru_uret(s),
        "p": ([round(s["p_kar"], 1), round(s["p_kondisyon"], 1), round(s["p_hiz"], 1), 0.0,
               round(s["ceza"], 1), round(s["bonus"], 1), duzeltme] if mod == "hizli" else
              [round(s["p_fiyat"], 1), round(s["p_kondisyon"], 1), round(s["p_satis"], 1),
               round(s["p_deger"], 1), round(s["ceza"], 1), round(s["bonus"], 1), duzeltme]),
        "net_yarin": round(s["net_yarin"]), "net_yarin_oran": round(s["net_yarin_oran"], 4),
        "satis_yarin": round(s["satis_yarin"]), "pazarlik": round(s["pazarlik"]), "masraf": round(s["masraf"]),
        "kimden": s["kimden"], "sehir": s["sehir"], "renk": s.get("renk"), "yakit": s.get("yakit"),
        "vites": s.get("vites"), "sanziman": s.get("sanziman"), "kasa": s.get("kasa"), "kategori": s.get("kategori"),
        "hp": s.get("hp"), "garanti": s.get("garanti"),
        "tramer": [s["tramer_durum"], s.get("tramer_tl"), s.get("tramer_kaynak")],
        "hasar": hasar_kisa(s), "parcalar": s.get("parcalar") or {}, "boya_bilinmiyor": s.get("boya_bilinmiyor"),
        "n_boya": s["n_boya"], "n_degisen": s["n_degisen"], "n_lokal": s["n_lokal"],
        "notlar": s["notlar"], "uyarilar": s["uyarilar"], "satis18": round(s["satis_18ay"]),
        "net18": round(s["net_18ay"]), "net18_oran": round(s["net_18ay_oran"], 4),
        "gelecek": round(s["gelecek_oran"], 4), "emsal": s["emsal_listesi"],
        "emsal_fiyat": round(s["emsal_fiyat"]) if s.get("emsal_fiyat") else None,
        "ilan_gun": s.get("ilan_gun"), "n_benzer": s["n_benzer"],
        "eslesme": s.get("eslesme"), "kaynak_adi": s.get("kaynak_adi"),
        "site": "sahibinden" if "sahibinden.com" in (s.get("url") or "") else "arabam",
    }


def yaz(sonuclar, yol, baslik, alt_baslik, piyasa, mod="piyasa", ek_meta=None):
    notlar = notlari_yukle()
    kayitlar = [kayit(s, notlar, mod) for s in sonuclar]
    m = piyasa.model
    okunan = sum(1 for k in kayitlar if k["claude"])
    meta = {
        "baslik": baslik, "alt_baslik": alt_baslik, "mod": mod, "tarih": piyasa.bugun[:10],
        "taranan": len(piyasa.satirlar), "sigma": round(m.sigma * 100, 1), "okunan": okunan,
        "uretim": date.today().isoformat(), **(ek_meta or {}),
    }
    veri = json.dumps(kayitlar, ensure_ascii=False, separators=(",", ":"))
    html = SABLON.replace("/*META*/null", json.dumps(meta, ensure_ascii=False)).replace("/*VERI*/[]", veri)
    html = html.replace("{{BASLIK}}", baslik)
    Path(yol).write_text(html, encoding="utf-8")
    return yol


SABLON = r"""<title>{{BASLIK}}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Barlow:wght@400;500;600&display=swap">
<style>
/* Düzen: ilan kartlarından oluşan tek sütunlu sıralı liste; her kartta puan halkası, araç bilgisi, fiyat bloğu ve boya şeması.
   Kimlik: Türkiye plakasının mavi şeridi vurgu rengi; boya şeması renkleri ekspertiz raporlarındaki sarı/turuncu/kırmızı. */
:root {
  --zemin: #eef1f5; --kart: #ffffff; --murekkep: #132030; --soluk: #5a6879; --cizgi: #d6dde6; --ince: #e8edf2;
  --vurgu: #2347a6; --vurgu-yumusak: #e3e9f8; --vurgu-ustu: #ffffff;
  --iyi: #17804a; --iyi-z: #ddf2e5; --orta: #a8690f; --orta-z: #fbefd9; --kotu: #bf3a28; --kotu-z: #fbe4e0;
  --orj: #dfe5ec; --lokal: #efc84a; --boya: #ee8a2a; --degisen: #d23a2e; --belirsiz: #f6f8fa;
  --f-baslik: "Barlow Condensed", "Arial Narrow", "Roboto Condensed", sans-serif;
  --f-govde: "Barlow", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --golge: 0 1px 2px rgba(19, 32, 48, .06), 0 2px 10px rgba(19, 32, 48, .05);
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --zemin: #0e141b; --kart: #161f29; --murekkep: #e4eaf1; --soluk: #9aa8b8; --cizgi: #2b3746; --ince: #1d2733;
  --vurgu: #86a6ff; --vurgu-yumusak: #1c2740; --vurgu-ustu: #0e141b;
  --iyi: #4cc27f; --iyi-z: #133022; --orta: #e3ab4e; --orta-z: #34280f; --kotu: #ff6f5e; --kotu-z: #3a1a16;
  --orj: #2f3b49; --lokal: #e6c04a; --boya: #f29a44; --degisen: #ff5e51; --belirsiz: #1b2430;
  --golge: 0 1px 2px rgba(0, 0, 0, .3); color-scheme: dark; } }
:root[data-theme="dark"] {
  --zemin: #0e141b; --kart: #161f29; --murekkep: #e4eaf1; --soluk: #9aa8b8; --cizgi: #2b3746; --ince: #1d2733;
  --vurgu: #86a6ff; --vurgu-yumusak: #1c2740; --vurgu-ustu: #0e141b;
  --iyi: #4cc27f; --iyi-z: #133022; --orta: #e3ab4e; --orta-z: #34280f; --kotu: #ff6f5e; --kotu-z: #3a1a16;
  --orj: #2f3b49; --lokal: #e6c04a; --boya: #f29a44; --degisen: #ff5e51; --belirsiz: #1b2430;
  --golge: 0 1px 2px rgba(0, 0, 0, .3); color-scheme: dark; }
* { box-sizing: border-box; }
body { background: var(--zemin); color: var(--murekkep); font-family: var(--f-govde); font-size: 15px; line-height: 1.45;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px); z-index: 10; background: var(--zemin); }
.sar { max-width: 1120px; margin: 0 auto; }
a { color: var(--vurgu); }
a:focus-visible, button:focus-visible, select:focus-visible, input:focus-visible, summary:focus-visible { outline: 2px solid var(--vurgu); outline-offset: 2px; }
.sayi { font-variant-numeric: tabular-nums; }

header.ust { padding-block: 28px 18px; display: grid; gap: 14px; }
.kasa-serit { display: inline-flex; align-items: stretch; border: 1.5px solid var(--murekkep); border-radius: 5px; overflow: hidden;
  font-family: var(--f-baslik); font-weight: 600; letter-spacing: .06em; font-size: 13px; width: fit-content; }
.kasa-serit b { background: var(--vurgu); color: #fff; padding: 2px 7px; font-weight: 700; }
.kasa-serit span { padding: 2px 10px; text-transform: uppercase; }
h1 { font-family: var(--f-baslik); font-weight: 700; font-size: clamp(34px, 6vw, 54px); line-height: 1; margin: 0; letter-spacing: -.01em; text-wrap: balance; }
.ozet { margin: 0; color: var(--soluk); max-width: 68ch; font-size: 16px; }
.istat { display: flex; flex-wrap: wrap; gap: 10px 28px; margin-top: 4px; }
.istat div { display: grid; }
.istat b { font-family: var(--f-baslik); font-size: 28px; font-weight: 600; line-height: 1.05; }
.istat small { color: var(--soluk); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }

details.yontem { background: var(--kart); border: 1px solid var(--cizgi); border-radius: 10px; padding: 0 16px; margin-bottom: 14px; }
details.yontem summary { cursor: pointer; padding-block: 12px; font-weight: 600; }
.yontem-ic { display: grid; gap: 12px; padding-bottom: 16px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.yontem-ic section { min-width: 0; }
.yontem-ic h3 { font-family: var(--f-baslik); font-size: 18px; margin: 0 0 4px; font-weight: 600; }
.yontem-ic p, .yontem-ic li { margin: 0; color: var(--soluk); font-size: 14px; }
.yontem-ic ul { margin: 0; padding-left: 18px; }

.filtre { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 5; background: var(--zemin); padding-block: 10px;
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center; border-bottom: 1px solid var(--cizgi); }
.filtre input[type=search], .filtre select { font: inherit; font-size: 14px; color: var(--murekkep); background: var(--kart);
  border: 1px solid var(--cizgi); border-radius: 8px; padding: 7px 10px; min-width: 0; }
.filtre input[type=search] { flex: 1 1 180px; }
.cip { font: inherit; font-size: 13px; border: 1px solid var(--cizgi); background: var(--kart); color: var(--murekkep);
  border-radius: 999px; padding: 6px 12px; cursor: pointer; }
.cip[aria-pressed="true"] { background: var(--murekkep); color: var(--zemin); border-color: var(--murekkep); }
.sonuc-sayi { color: var(--soluk); font-size: 13px; margin-left: auto; }

#liste { display: grid; gap: 12px; padding-block: 14px 8px; }
.ilan { background: var(--kart); border: 1px solid var(--cizgi); border-radius: 12px; box-shadow: var(--golge);
  display: grid; grid-template-columns: 76px minmax(0, 1fr) 210px 104px; gap: 4px 18px; padding: 14px 16px; align-items: start; }
.sira { display: grid; justify-items: center; gap: 4px; }
.sira small { font-family: var(--f-baslik); color: var(--soluk); font-size: 14px; }
.halka { --p: 0; --r: var(--soluk); width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center;
  background: conic-gradient(var(--r) calc(var(--p) * 1%), var(--ince) 0); }
.halka span { width: 50px; height: 50px; border-radius: 50%; background: var(--kart); display: grid; place-items: center;
  font-family: var(--f-baslik); font-weight: 700; font-size: 24px; }
.govde { min-width: 0; display: grid; gap: 6px; }
.govde h2 { font-family: var(--f-baslik); font-weight: 600; font-size: 22px; line-height: 1.1; margin: 0; text-wrap: balance; }
.govde h2 a { color: inherit; text-decoration: none; }
.govde h2 a:hover { text-decoration: underline; text-decoration-color: var(--vurgu); }
.govde h2 em { font-style: normal; color: var(--soluk); font-weight: 500; }
.etiketler { display: flex; flex-wrap: wrap; gap: 4px 12px; color: var(--soluk); font-size: 13.5px; }
.etiketler span { white-space: nowrap; }
.karar { display: inline-flex; gap: 6px; align-items: baseline; font-size: 12px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .05em; padding: 2px 8px; border-radius: 5px; width: fit-content; }
.k-AL, .k-GÜÇLÜ { background: var(--iyi-z); color: var(--iyi); }
.k-İNCELE { background: var(--vurgu-yumusak); color: var(--vurgu); }
.k-DİKKAT, .k-ELE { background: var(--kotu-z); color: var(--kotu); }
.k-PAS { background: var(--ince); color: var(--soluk); }
.claude { font-size: 14px; margin: 0; }
.claude b { font-weight: 600; }
.claude.yok { color: var(--soluk); font-size: 13px; }
.fiyat { display: grid; gap: 2px; justify-items: end; text-align: right; }
.fiyat .ana { font-family: var(--f-baslik); font-size: 26px; font-weight: 700; line-height: 1; }
.fiyat .piyasa { color: var(--soluk); font-size: 13px; }
.fark { font-weight: 600; font-size: 14px; }
.fark.arti { color: var(--iyi); } .fark.eksi { color: var(--kotu); }
.sonra { font-size: 12.5px; color: var(--soluk); }
.git { display: inline-flex; align-items: center; gap: 6px; margin-top: 8px; padding: 7px 14px; border-radius: 8px;
  background: var(--vurgu); color: var(--vurgu-ustu); font-weight: 600; font-size: 14px; text-decoration: none; white-space: nowrap; }
.git:hover { filter: brightness(1.08); text-decoration: underline; }
.git small { font-weight: 500; opacity: .8; font-size: 12px; }
.butonlar { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
.gorus { grid-column: 2 / -1; margin: 0; padding: 10px 14px; border-radius: 8px; background: var(--zemin);
  border-left: 3px solid var(--soluk); font-size: 14.5px; line-height: 1.5; }
.gorus b { display: block; font-size: 11.5px; letter-spacing: .06em; text-transform: uppercase; color: var(--soluk); margin-bottom: 2px; }
.gorus p { margin: 0; }
.gorus b + ul { margin-top: 0; }
.gorus p + b { margin-top: 10px; }
.sor { margin: 0; padding-left: 18px; display: grid; gap: 3px; }
.sor li::marker { color: var(--soluk); }
.gorus.g-AL { border-left-color: var(--iyi); } .gorus.g-İNCELE { border-left-color: var(--vurgu); }
.gorus.g-DİKKAT { border-left-color: var(--kotu); }
.okunmayan { display: flex; justify-content: center; margin: 18px 0 6px; }
.detay-ic section.genis { grid-column: 1 / -1; }
.sema { display: grid; justify-items: center; gap: 3px; text-decoration: none; color: var(--soluk); font-size: 12px; text-align: center; }
.sema svg { width: 54px; height: auto; display: block; }
.sema:hover svg { filter: drop-shadow(0 0 2px var(--vurgu)); }
.sema .tr { color: var(--murekkep); font-weight: 500; }
.detay { grid-column: 2 / -1; }
.detay summary { cursor: pointer; color: var(--vurgu); font-size: 13.5px; font-weight: 600; width: fit-content; }
.detay-ic { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px 22px; padding-top: 10px; }
.detay-ic section { min-width: 0; }
.detay-ic h4 { margin: 0 0 6px; font-family: var(--f-baslik); font-size: 16px; font-weight: 600; letter-spacing: .02em; }
.cubuk { display: grid; grid-template-columns: 112px 1fr 48px; gap: 8px; align-items: center; font-size: 13px; margin-bottom: 4px; }
.cubuk i { display: block; height: 7px; border-radius: 4px; background: var(--ince); overflow: hidden; }
.cubuk i b { display: block; height: 100%; background: var(--vurgu); }
.cubuk.ceza i b { background: var(--kotu); }
.cubuk span:last-child { text-align: right; font-variant-numeric: tabular-nums; color: var(--soluk); }
.hesap { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.hesap td { padding: 3px 0; border-bottom: 1px dashed var(--ince); }
.hesap td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
.hesap tr.top td { font-weight: 600; border-bottom: none; }
.emsal { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 13px; }
.emsal li { display: flex; justify-content: space-between; gap: 10px; }
.emsal li span:last-child { font-variant-numeric: tabular-nums; white-space: nowrap; }
.maddeler { margin: 0; padding-left: 18px; font-size: 13.5px; color: var(--soluk); }
.maddeler li.u { color: var(--kotu); }
.bos { padding: 40px 0; text-align: center; color: var(--soluk); }
#elenen { margin-block: 18px; background: var(--kart); border: 1px solid var(--cizgi); border-radius: 10px; padding: 0 16px; }
#elenen summary { cursor: pointer; padding-block: 12px; font-weight: 600; }
#elenen ul { margin: 0; padding: 0 0 14px 18px; display: grid; gap: 6px; font-size: 14px; }
#elenen li span { color: var(--soluk); }
footer { color: var(--soluk); font-size: 13px; padding-block: 18px 36px; max-width: 75ch; }
.gosterge { display: flex; gap: 10px; flex-wrap: wrap; font-size: 12px; color: var(--soluk); align-items: center; }
.gosterge i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: -1px; }
@media (max-width: 860px) {
  .butonlar { justify-content: flex-start; }
  .ilan { grid-template-columns: 64px minmax(0, 1fr) 76px; }
  .fiyat { grid-column: 2 / 3; justify-items: start; text-align: left; grid-row: 2; }
  .sema { grid-column: 3; grid-row: 1 / 3; }
  .detay { grid-column: 1 / -1; }
  .halka { width: 56px; height: 56px; } .halka span { width: 44px; height: 44px; font-size: 21px; }
}
@media (max-width: 480px) {
  .ilan { grid-template-columns: 56px minmax(0, 1fr); padding: 12px; gap: 6px 12px; }
  .sema { grid-column: 1; grid-row: 2 / 4; align-self: start; }
  .sema svg { width: 44px; }
  .fiyat { grid-column: 2; grid-row: 2; }
  .govde h2 { font-size: 20px; }
  .sonuc-sayi { margin-left: 0; width: 100%; }
}
@media (prefers-reduced-motion: no-preference) { .ilan { transition: border-color .15s; } .ilan:hover { border-color: var(--vurgu); } }
</style>

<div class="sar">
  <header class="ust">
    <div class="kasa-serit"><b>TR</b><span id="ust-etiket">arabam.com</span></div>
    <h1 id="baslik">{{BASLIK}}</h1>
    <p class="ozet" id="ozet"></p>
    <div class="istat" id="istat"></div>
  </header>

  <details class="yontem" id="yontem-hizli" hidden>
    <summary>Hızlı al-sat puanı nasıl hesaplanıyor?</summary>
    <div class="yontem-ic">
      <section><h3>Yarın satsan hesabı</h3><p>Alış: ilan fiyatı (pazarlıksız, temkinli). Satış: aracın piyasa değeri, bireysel satıcı fiyat seviyesinde, hızlı satmak için %3 altına fiyatlanmış. Noter, ekspertiz, ilan ve temizlik masrafı (~15 bin TL + %0,2) düşülür. Kalan tutar net kârdır. Pazarlıkla alırsan kâr artar.</p></section>
      <section><h3>Kâr potansiyeli · 55</h3><p>Masraflar düştükten sonraki net kâr oranı; tahmin güveni düşükse (emsali az model, fiyat penceresi dışı) kısılır. %9 ve üstü net kâr tam puan alır. Piyasanın %20'den fazla altındaki ilanlar dolandırıcılık ya da gizli hasar şüphesiyle kırpılır.</p></section>
      <section><h3>Satış hızı · 25</h3><p>Marka ve serinin ikinci el talebi, piyasadaki ilan derinliği, renk, km, yakıt tipi ve fiyat bandı (ucuz bantta alıcı çok). Yarın satmak istiyorsan araç aranan bir araç olmalı.</p></section>
      <section><h3>Kondisyon · 20</h3><p>Boyasız, değişensiz, tramersiz araç hem kolay hem pazarlıksız satılır. Değişen, boya, tavan/kaput işlemi ve tramer puan düşürür.</p></section>
      <section><h3>Kararlar</h3><ul><li><b>AL / Güçlü aday</b>: puan ≥ 78, belirgin risk yok</li><li><b>İncele</b>: 65-78 ya da sorulacak bilgi var</li><li><b>Dikkat</b>: hasar/airbag/tramer/dolandırıcılık işareti</li><li><b>Claude notu</b>: açıklama tek tek okundu; AL +3, Dikkat −15, Ele: listeden çıkarıldı</li></ul></section>
      <section><h3>Sınırlar</h3><p>Fiyatlar ilan fiyatıdır; ilan fiyatından alıp ilan fiyatından satmak garanti değildir. Kâr, aracın gerçekten tahmin edilen değerde satılmasına bağlıdır. Ekspertiz ve tramer sorgusu olmadan alma. Yatırım tavsiyesi değildir.</p></section>
    </div>
  </details>

  <details class="yontem" id="yontem-normal">
    <summary>Puan nasıl hesaplanıyor?</summary>
    <div class="yontem-ic">
      <section><h3>Fiyat avantajı · 45</h3><p>İlan fiyatı, aynı marka-seri-motor-paket, yıl, km, boya/değişen, tramer, renk ve satıcı tipindeki araçların piyasa değeriyle karşılaştırılır. Piyasa değeri 27 bin ilanlık veriden kurulan istatistik modelden gelir; aracın kendisi hesaba katılmaz. %12 ve üstü ucuzluk tam puan alır. Emsali az olan modellerde puan kısılır.</p></section>
      <section><h3>Kondisyon · 20</h3><p>Boyasız, değişensiz, tramersiz araç tam puan alır. Lokal boya, boya, değişen, tavan ve kaput işlemi, tramer tutarı ve boş bırakılmış ekspertiz bilgisi puan düşürür. "Başkasına alıyormuş gibi al" ilkesi burada.</p></section>
      <section><h3>Satılabilirlik · 20</h3><p>Markanın ve serinin Türkiye'de ikinci el talebi, piyasadaki ilan derinliği, renk (beyaz/gri/siyah kolay satılır), satış anındaki km ve yakıt tipi.</p></section>
      <section><h3>Değer koruma · 15</h3><p>18 ay ve ~26 bin km sonra aracın bugünkü parayla ne kadar edeceği, aynı serinin bir-iki yaş büyük ve daha çok km'li ilanlarından hesaplanır (enflasyon hariç, reel).</p></section>
      <section><h3>Kararlar</h3><ul><li><b>AL / Güçlü aday</b>: puan ≥ 78, belirgin risk yok</li><li><b>İncele</b>: 65-78 ya da sorulacak bilgi var</li><li><b>Dikkat</b>: hasar/airbag/tramer/dolandırıcılık işareti</li><li><b>Claude notu</b>: ilan açıklaması tek tek okundu; AL +3, Dikkat −15, Ele: listeden çıkarıldı</li></ul></section>
      <section><h3>Sınırlar</h3><p>Fiyatlar ilan fiyatıdır, satış fiyatı değildir. Referans tarama 1,25-2,0 M TL aralığında; bu aralığın dışındaki tahminler daha belirsizdir. Ekspertiz ve tramer sorgusu olmadan hiçbir araç alınmamalı. Yatırım tavsiyesi değildir.</p></section>
    </div>
  </details>

  <div class="filtre" role="search">
    <input type="search" id="ara" placeholder="Marka, model, şehir ara…" aria-label="Ara">
    <select id="kat" aria-label="Kategori"><option value="">Tüm kasalar</option><option value="otomobil">Otomobil</option><option value="suv">SUV / Pikap</option></select>
    <select id="fiyat" aria-label="En yüksek fiyat"><option value="">Her fiyat</option><option value="1400000">≤ 1,4 M</option><option value="1600000">≤ 1,6 M</option><option value="1800000">≤ 1,8 M</option><option value="2000000">≤ 2,0 M</option></select>
    <select id="sirala" aria-label="Sıralama"><option value="puan">Sırala: puan</option><option value="firsat">Sırala: ucuzluk %</option><option value="net">Sırala: 18 ay sonucu</option><option value="fiyat">Sırala: fiyat</option><option value="km">Sırala: km</option></select>
    <button class="cip" id="c-al" aria-pressed="false" type="button">Sadece AL / Güçlü</button>
    <button class="cip" id="c-temiz" aria-pressed="false" type="button">Boyasız</button>
    <button class="cip" id="c-sahibi" aria-pressed="false" type="button">Sahibinden</button>
    <button class="cip" id="c-dikkat" aria-pressed="true" type="button">Dikkat işaretlileri göster</button>
    <span class="sonuc-sayi" id="sayi"></span>
  </div>

  <main id="liste" aria-live="polite"></main>
  <details id="elenen" hidden><summary id="elenen-baslik"></summary><ul id="elenen-liste"></ul></details>

  <footer>
    <div class="gosterge"><span><i style="background:var(--orj)"></i>orijinal</span><span><i style="background:var(--lokal)"></i>lokal boyalı</span><span><i style="background:var(--boya)"></i>boyalı</span><span><i style="background:var(--degisen)"></i>değişen</span><span><i style="background:var(--belirsiz);border:1px dashed var(--soluk)"></i>belirtilmemiş</span></div>
    <p id="alt-not"></p>
  </footer>
</div>

<script>
const META = /*META*/null;
const VERI = /*VERI*/[];
const HIZLI = META.mod === "hizli";
const TL = n => n == null ? "–" : Math.round(n).toLocaleString("tr-TR") + " TL";
const KM = n => n == null ? "–" : n.toLocaleString("tr-TR") + " km";
const YUZDE = (x, d = 1) => (x * 100).toLocaleString("tr-TR", { minimumFractionDigits: d, maximumFractionDigits: d });
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Üstten görünüm boya şeması: ön taraf yukarıda, sürücü (sol) tarafı solda
const PARCA = {
  "Ön Tampon": [12, 2, 36, 7], "Motor Kaputu": [16, 11, 28, 24], "Sol Ön Çamurluk": [4, 11, 10, 24], "Sağ Ön Çamurluk": [46, 11, 10, 24],
  "Sol Ön Kapı": [4, 37, 10, 23], "Sağ Ön Kapı": [46, 37, 10, 23], "Tavan": [16, 37, 28, 46], "Sol Arka Kapı": [4, 62, 10, 21],
  "Sağ Arka Kapı": [46, 62, 10, 21], "Sol Arka Çamurluk": [4, 85, 10, 21], "Sağ Arka Çamurluk": [46, 85, 10, 21],
  "Arka Kaput": [16, 85, 28, 21], "Arka Tampon": [12, 108, 36, 7] };
function sema(r) {
  const p = r.parcalar || {}, durum = {};
  for (const n of p.belirsiz || []) durum[n] = "belirsiz";
  for (const n of p.lokal || []) durum[n] = "lokal";
  for (const n of p.boya || []) durum[n] = "boya";
  for (const n of p.degisen || []) durum[n] = "degisen";
  const renk = { belirsiz: "var(--belirsiz)", lokal: "var(--lokal)", boya: "var(--boya)", degisen: "var(--degisen)" };
  let s = `<svg viewBox="0 0 60 117" role="img" aria-label="Boya-değişen şeması: ${esc(r.hasar)}">`;
  for (const [ad, [x, y, w, h]] of Object.entries(PARCA)) {
    const d = r.boya_bilinmiyor ? "belirsiz" : durum[ad];
    const kesik = d === "belirsiz" ? ' stroke-dasharray="2 1.5"' : "";
    s += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="2.5" fill="${d ? renk[d] : "var(--orj)"}" stroke="var(--soluk)" stroke-opacity=".45" stroke-width=".7"${kesik}><title>${esc(ad)}: ${d ? { belirsiz: "belirtilmemiş", lokal: "lokal boyalı", boya: "boyalı", degisen: "değişen" }[d] : "orijinal"}</title></rect>`;
  }
  return s + "</svg>";
}
function tramerYazi(t) {
  const [d, tl] = t;
  if (d === "yok") return "tramer yok";
  if (d === "tutar") return "tramer " + TL(tl);
  return "tramer belirtilmemiş";
}
function puanRenk(p) { return p >= 85 ? "var(--iyi)" : p >= 78 ? "var(--iyi)" : p >= 65 ? "var(--orta)" : "var(--soluk)"; }
function kararEtiket(r) {
  if (r.claude) return { k: r.claude[0], y: { AL: "Claude: AL", "İNCELE": "Claude: incele", "DİKKAT": "Claude: dikkat", ELE: "Claude: ele" }[r.claude[0]] };
  return { k: r.karar, y: { "GÜÇLÜ": "Güçlü aday", "İNCELE": "İncele", "DİKKAT": "Dikkat", PAS: "Pas" }[r.karar] };
}
function kart(r, i) {
  const ke = kararEtiket(r);
  const fark = r.adil - r.fiyat;
  const cub = (ad, v, max, ceza) => `<div class="cubuk${ceza ? " ceza" : ""}"><span>${ad}</span><i><b style="width:${Math.max(0, Math.min(100, Math.abs(v) / max * 100))}%"></b></i><span>${ceza ? "−" : ""}${Math.abs(v).toLocaleString("tr-TR", { maximumFractionDigits: 1 })}</span></div>`;
  const [pf, pk, ps, pd, ceza, bonus, cdz] = r.p;
  const emsal = (r.emsal || []).map(e => `<li><a href="${esc(e.url)}" target="_blank" rel="noopener">${e.yil} · ${esc(e.model)} · ${KM(e.km)} · ${esc(e.hasar)}</a><span>${TL(e.fiyat)}</span></li>`).join("");
  const maddeler = [...(r.uyarilar || []).map(u => `<li class="u">${esc(u)}</li>`), ...(r.notlar || []).map(n => `<li>${esc(n)}</li>`)].join("");
  const masraf = r.satis18 - r.fiyat - r.net18;
  const etiket = [r.yil, KM(r.km), r.yakit, r.vites === "Yarı Otomatik" ? (r.sanziman || "yarı otomatik") : (r.sanziman || r.vites), r.renk, r.sehir, r.kimden,
    r.ilan_gun != null ? `${r.ilan_gun} gündür yayında` : null, r.garanti === 1 ? "garantili" : null].filter(Boolean);
  return `<article class="ilan" id="i${esc(r.id)}">
    <div class="sira"><div class="halka" style="--p:${r.son_puan};--r:${puanRenk(r.son_puan)}"><span class="sayi">${Math.round(r.son_puan)}</span></div><small>#${i + 1}</small></div>
    <div class="govde">
      <h2><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.marka)} ${esc(r.seri)} <em>${esc(r.model)}</em></a></h2>
      <div class="etiketler">${etiket.map(e => `<span>${esc(e)}</span>`).join("")}</div>
      <span class="karar k-${esc(ke.k)}">${esc(ke.y)}</span>
      ${r.claude ? "" : `<p class="claude yok">Açıklama Claude tarafından okunmadı; otomatik değerlendirme.</p>`}
    </div>
    <div class="fiyat">
      <span class="ana sayi">${TL(r.fiyat)}</span>
      <span class="piyasa">piyasa değeri ~${TL(r.adil)}</span>
      <span class="fark ${fark >= 0 ? "arti" : "eksi"} sayi">${fark >= 0 ? "%" + YUZDE(r.firsat) + " ucuz · " + TL(fark) : "%" + YUZDE(-r.firsat) + " pahalı"}</span>
      ${HIZLI ? `<span class="sonra sayi"><b class="fark ${r.net_yarin >= 0 ? "arti" : "eksi"}">Yarın satsan net: ${r.net_yarin >= 0 ? "+" : ""}${TL(r.net_yarin)}</b></span>`
              : `${META.mod === "aday" ? `<span class="sonra sayi">Yarın satsan net: ${r.net_yarin >= 0 ? "+" : ""}${TL(r.net_yarin)}</span>` : ""}<span class="sonra sayi">18 ay sonra (reel): ${r.net18 >= 0 ? "+" : ""}${TL(r.net18)}</span>`}
      <div class="butonlar"><a class="git" href="${esc(r.url)}" target="_blank" rel="noopener">İlana git ↗ <small>${esc(r.site === "arabam" ? "arabam" : "sahibinden")} #${esc(r.id)}</small></a></div>
    </div>
    <a class="sema" href="${esc(r.url)}" target="_blank" rel="noopener" title="İlanı aç">${sema(r)}<span class="tr">${esc(r.hasar)}</span><span>${esc(tramerYazi(r.tramer))}</span></a>
    <details class="detay"><summary>${HIZLI ? "Puan dökümü, kâr hesabı ve emsaller" : "Puan dökümü, 18 ay hesabı ve emsaller"}</summary><div class="detay-ic">
      <section><h4>Puan ${r.son_puan.toLocaleString("tr-TR")} / 100</h4>
        ${HIZLI ? cub("Kâr potansiyeli", pf, 55) + cub("Satış hızı", ps, 25) + cub("Kondisyon", pk, 20)
                : cub("Fiyat avantajı", pf, 45) + cub("Kondisyon", pk, 20) + cub("Satılabilirlik", ps, 20) + cub("Değer koruma", pd, 15)}
        ${ceza ? cub("Açıklama riski", ceza, 40, true) : ""}${cdz < 0 ? cub("Claude düzeltmesi", cdz, 40, true) : ""}
        <p class="sonra">Tahmin güveni: %${Math.round(r.guven * 100)} · aynı motor ve yılda ${r.n_benzer} ilan${r.site === "sahibinden" && r.kaynak_adi ? ` · sahibinden adı: ${esc(r.kaynak_adi)} (arabam eşleşmesi: ${esc(r.eslesme || "-")})` : ""}</p></section>
      ${HIZLI ? `<section><h4>Yarın satsan</h4><table class="hesap">
        <tr><td>Alış (ilan fiyatı, pazarlıksız)</td><td>${TL(r.fiyat)}</td></tr>
        <tr><td>Piyasa değeri</td><td>${TL(r.adil)}</td></tr>
        <tr><td>Hızlı satış fiyatı (bireysel, %3 altı)</td><td>${TL(r.satis_yarin)}</td></tr>
        <tr><td>Noter, ekspertiz, ilan, temizlik</td><td>−${TL(r.masraf)}</td></tr>
        <tr class="top"><td>Net kâr</td><td>${r.net_yarin >= 0 ? "+" : ""}${TL(r.net_yarin)} (%${YUZDE(r.net_yarin_oran)})</td></tr></table>
        <p class="sonra">Pazarlıkla alırsan (${esc(r.kimden)} için tipik ~${TL(r.pazarlik)}) kâr o kadar artar.</p></section>` : ""}
      <section${HIZLI ? " hidden" : ""}><h4>18 ay sonra (bugünkü parayla)</h4><table class="hesap">
        <tr><td>Alış (ilan fiyatı)</td><td>${TL(r.fiyat)}</td></tr>
        <tr><td>Bugünkü piyasa değeri</td><td>${TL(r.adil)}</td></tr>
        <tr><td>18 ay, +26 bin km sonra satış</td><td>${TL(r.satis18)}</td></tr>
        <tr><td>Noter, ekspertiz, ilan masrafı</td><td>−${TL(masraf)}</td></tr>
        <tr class="top"><td>Sonuç (enflasyon hariç)</td><td>${r.net18 >= 0 ? "+" : ""}${TL(r.net18)}</td></tr></table>
        <p class="sonra">TL bazında satış fiyatı enflasyonla daha yüksek görünür; burada reel değer kaybı gösterilir.</p></section>
      <section><h4>Benzer ilanlar</h4>${emsal ? `<ul class="emsal">${emsal}</ul>${r.emsal_fiyat ? `<p class="sonra">Bu araca göre uyarlanmış emsal medyanı: ${TL(r.emsal_fiyat)}</p>` : ""}` : `<p class="sonra">Yakın emsal bulunamadı (aynı motor, ±1 yıl, ±35 bin km).</p>`}</section>
      ${maddeler ? `<section><h4>Sistem notları</h4><ul class="maddeler">${maddeler}</ul></section>` : ""}
    </div></details>
    ${r.claude || (r.sorular || []).length ? `<div class="gorus g-${esc(r.claude ? r.claude[0] : "yok")}">
      ${r.claude ? `<b>Görüşüm</b><p>${esc(r.claude[1])}</p>` : ""}
      ${(r.sorular || []).length ? `<b>Satıcıya sorarım</b><ul class="sor">${r.sorular.map(q => `<li>${esc(q)}</li>`).join("")}</ul>` : ""}
    </div>` : ""}
  </article>`;
}

const durum = { ara: "", kat: "", fiyat: "", sirala: "puan", al: false, temiz: false, sahibi: false, dikkat: true, hepsi: false };
try { Object.assign(durum, JSON.parse(localStorage.getItem("firsat-filtre") || "{}")); } catch (e) {}
const ANA = VERI.filter(r => !(r.claude && r.claude[0] === "ELE"));
// Aday raporunda varsayılan olarak yalnız açıklaması okunup görüş yazılan ilanlar gösterilir
const OKUNAN_VAR = META.mod === "aday" && ANA.filter(r => r.claude).length >= 10;
const ELENEN = VERI.filter(r => r.claude && r.claude[0] === "ELE");

function ciz() {
  const q = durum.ara.trim().toLocaleLowerCase("tr-TR");
  let l = ANA.filter(r => {
    if (OKUNAN_VAR && !durum.hepsi && !r.claude) return false;
    if (q && !`${r.marka} ${r.seri} ${r.model} ${r.sehir} ${r.yil}`.toLocaleLowerCase("tr-TR").includes(q)) return false;
    if (durum.kat && r.kategori !== durum.kat) return false;
    if (durum.fiyat && r.fiyat > +durum.fiyat) return false;
    const k = r.claude ? r.claude[0] : r.karar;
    if (durum.al && !(k === "AL" || k === "GÜÇLÜ")) return false;
    if (!durum.dikkat && k === "DİKKAT") return false;
    if (durum.temiz && (r.n_boya || r.n_degisen || r.n_lokal || r.boya_bilinmiyor)) return false;
    if (durum.sahibi && r.kimden !== "Sahibinden") return false;
    return true;
  });
  const anahtar = { puan: r => -r.son_puan, firsat: r => -r.firsat, net: r => -(HIZLI ? r.net_yarin : r.net18), fiyat: r => r.fiyat, km: r => r.km }[durum.sirala];
  l.sort((a, b) => anahtar(a) - anahtar(b));
  const liste = document.getElementById("liste");
  const okunmayan = OKUNAN_VAR ? ANA.filter(r => !r.claude).length : 0;
  liste.innerHTML = (l.length ? l.map(kart).join("") : `<p class="bos">Bu filtrelere uyan ilan yok. Filtreleri gevşet.</p>`)
    + (okunmayan ? `<div class="okunmayan"><button class="cip" type="button" id="hepsi">${durum.hepsi ? "Yalnız görüş yazdıklarımı göster" : `Açıklaması okunmayan ${okunmayan} ilanı da göster (otomatik puan)`}</button></div>` : "");
  const hb = document.getElementById("hepsi");
  if (hb) hb.onclick = () => { durum.hepsi = !durum.hepsi; ciz(); };
  document.getElementById("sayi").textContent = `${l.length} / ${ANA.length} ilan`;
  try { localStorage.setItem("firsat-filtre", JSON.stringify(durum)); } catch (e) {}
}


function kur() {
  const tarih = new Date(META.tarih + "T12:00:00").toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric" });
  document.getElementById("ust-etiket").textContent = `arabam.com · ${tarih}`;
  const nAl = ANA.filter(r => (r.claude ? r.claude[0] : r.karar) === "AL" || (!r.claude && r.karar === "GÜÇLÜ")).length;
  if (HIZLI) {
    document.getElementById("yontem-hizli").hidden = false; document.getElementById("yontem-normal").hidden = true;
    document.querySelector('#sirala option[value="net"]').textContent = "Sırala: net kâr (TL)";
  }
  document.getElementById("ozet").textContent = HIZLI
    ? `${META.taranan.toLocaleString("tr-TR")} ilan tarandı. ${META.n_karli.toLocaleString("tr-TR")} tanesi yarın satılsa masraflar düştükten sonra kâr bırakıyor; bunların en sağlam ${ANA.length} tanesi aşağıda. Ölçüt: alış ile hızlı satış fiyatı arasındaki net fark, satış hızı ve kondisyon.`
    : META.mod === "aday"
    ? `${VERI.length} yeni ilan, ${META.taranan.toLocaleString("tr-TR")} ilanlık güncel piyasaya göre puanlandı. Üstte piyasanın altında, temiz ve satması kolay olanlar var.`
    : `${META.taranan.toLocaleString("tr-TR")} ilan tarandı. Piyasanın altında fiyatlanmış, temiz ve 1-2 yıl sonra satarken baş ağrıtmayacak araçlar 100 üzerinden puanlanıp sıralandı.`;
  const ist = HIZLI
    ? [[META.taranan.toLocaleString("tr-TR"), "taranan ilan"], [META.n_karli.toLocaleString("tr-TR"), "yarın satılsa kâr eden"],
       [META.n_karli_100.toLocaleString("tr-TR"), "100 bin TL+ net kâr"], [ANA.length, "listede"], [nAl, "AL / güçlü aday"],
       [META.okunan, "açıklaması okunan"]]
    : [[META.taranan.toLocaleString("tr-TR"), "taranan ilan"], [ANA.length, "listede"], [nAl, "AL / güçlü aday"],
       [META.okunan, "açıklaması okunan"], ["±%" + META.sigma.toLocaleString("tr-TR"), "fiyat modeli hata payı"]];
  document.getElementById("istat").innerHTML = ist.map(([b, s]) => `<div><b class="sayi">${b}</b><small>${s}</small></div>`).join("");
  document.getElementById("alt-not").textContent = `Rapor ${META.uretim} tarihinde üretildi. Fiyatlar ilan fiyatıdır; piyasa değeri istatistiksel tahmindir. Almadan önce ekspertiz, tramer (hasar kaydı) ve borç/haciz sorgusu yaptır. Yatırım tavsiyesi değildir.`;
  if (ELENEN.length) {
    const e = document.getElementById("elenen"); e.hidden = false;
    document.getElementById("elenen-baslik").textContent = `Claude'un açıklamasını okuyup elediği ${ELENEN.length} ilan`;
    document.getElementById("elenen-liste").innerHTML = ELENEN.map(r => `<li><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.marka)} ${esc(r.seri)} ${esc(r.model)} ${r.yil} · ${TL(r.fiyat)}</a> <span>— ${esc(r.claude[1])}</span></li>`).join("");
  }
  const ara = document.getElementById("ara"); ara.value = durum.ara;
  ara.addEventListener("input", () => { durum.ara = ara.value; ciz(); });
  for (const id of ["kat", "fiyat", "sirala"]) {
    const el = document.getElementById(id); el.value = durum[id];
    el.addEventListener("change", () => { durum[id] = el.value; ciz(); });
  }
  for (const [id, k] of [["c-al", "al"], ["c-temiz", "temiz"], ["c-sahibi", "sahibi"], ["c-dikkat", "dikkat"]]) {
    const b = document.getElementById(id); b.setAttribute("aria-pressed", String(!!durum[k]));
    b.addEventListener("click", () => { durum[k] = !durum[k]; b.setAttribute("aria-pressed", String(durum[k])); ciz(); });
  }
  ciz();
}
kur();
</script>
"""
