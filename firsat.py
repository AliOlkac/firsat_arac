#!/usr/bin/env python3
"""Fırsat Araç: arabam.com piyasasına göre piyasanın altındaki, satması kolay araçları bulur.

Komutlar
  python3 firsat.py durum                      veritabanı ve model özeti
  python3 firsat.py ekle DOSYA.json [...]      yeni piyasa taramasını referans veritabanına ekler
  python3 firsat.py piyasa [--n 150]           referans piyasanın tamamındaki en iyi fırsatlar -> HTML
  python3 firsat.py degerlendir DOSYA.json     yeni gelen ilanları referansa göre puanlar -> HTML
  python3 firsat.py kur                        veritabanını ve modeli ham dosyalardan sıfırdan kurar
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from firsat import analiz, rapor
from firsat.veritabani import KOK

RAPORLAR = KOK / "raporlar"


def _kaydet(sonuclar, ad, baslik, alt_baslik, piyasa, mod, ek_meta=None):
    RAPORLAR.mkdir(exist_ok=True)
    html_yol = RAPORLAR / f"{ad}.html"
    json_yol = RAPORLAR / f"{ad}.json"
    rapor.yaz(sonuclar, html_yol, baslik=baslik, alt_baslik=alt_baslik, piyasa=piyasa, mod=mod, ek_meta=ek_meta)
    notlar_ = rapor.notlari_yukle()
    with open(json_yol, "w", encoding="utf-8") as f:
        json.dump([rapor.kayit(s, notlar_, mod) for s in sonuclar], f, ensure_ascii=False, indent=1, default=str)
    # Claude'un okuması için: notu olmayan en iyi adayların açıklamaları (telefonlar maskeli, depoya girmez)
    notlar = rapor.notlari_yukle()
    satirlar = []
    for i, s in enumerate(sonuclar[:100], 1):
        if s["ilan_id"] in notlar:
            continue
        aciklama = re.sub(r"\s+", " ", s.get("aciklama") or "")
        aciklama = re.sub(r"(\+?90)?\s?0?\s?5\d{2}[\s\d]{7,12}", "[tel]", aciklama)
        satirlar.append(f"#{i} [{s['ilan_id']}] {s['puan_hizli'] if mod == 'hizli' else s['puan']} {s['karar']} | {s['marka']} {s['seri']} {s['model']} {s['yil']} "
                        f"{s['km']} km | {s['fiyat']:,} TL, piyasa ~{s['adil']:,.0f} (%{s['firsat']*100:.1f}) | "
                        f"{s['n_boya']} boya {s['n_degisen']} değişen {s['n_lokal']} lokal, tramer {s['tramer_durum']} "
                        f"{s.get('tramer_tl') or ''} | {s['kimden']} {s['sehir']} | riskler: {', '.join(k for k, _, _ in s['riskler'])}"
                        f"\n   BAŞLIK: {s['baslik']}\n   AÇIKLAMA: {aciklama[:600]}\n")
    inceleme = RAPORLAR / f"{ad}-inceleme.txt"
    inceleme.write_text("\n".join(satirlar), encoding="utf-8")
    print(f"\n  HTML : {html_yol.relative_to(KOK)}\n  JSON : {json_yol.relative_to(KOK)}")
    print(f"  Okunacak (notu olmayan) {len(satirlar)} aday: {inceleme.relative_to(KOK)}")


def _link(url):
    """Eklenti virgül içeren adresleri ilan adresi saymıyor (2026-11-08: 300 linkten 7'si toplanmadı); virgülü kodla."""
    return url.replace(",", "%2C")


def _ozet_yaz(sonuclar, n=15):
    print(f"\n  {'#':>3} {'Puan':>5} {'Karar':7} {'Fırsat':>7}  Araç")
    for i, s in enumerate(sonuclar[:n], 1):
        print(f"  {i:>3} {s['puan']:5.1f} {s['karar']:7} {s['firsat']*100:6.1f}%  {s['marka']} {s['seri']} {s['model']} "
              f"{s['yil']} | {s['km']:,} km | {s['fiyat']:,} TL (piyasa ~{s['adil']:,.0f})".replace(",", "."))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = ap.add_subparsers(dest="komut", required=True)
    alt.add_parser("durum")
    alt.add_parser("kur")
    e = alt.add_parser("ekle")
    e.add_argument("dosyalar", nargs="+")
    p = alt.add_parser("piyasa")
    p.add_argument("--n", type=int, default=150, help="rapora girecek en fazla ilan")
    p.add_argument("--min-puan", type=float, default=60)
    h = alt.add_parser("hizli", help="yarın satsam en kârlı olacaklar (hızlı al-sat)")
    h.add_argument("--n", type=int, default=150)
    h.add_argument("--min-puan", type=float, default=60)
    d = alt.add_parser("degerlendir")
    d.add_argument("dosyalar", nargs="+")
    d.add_argument("--ad", default=None, help="rapor dosya adı (varsayılan: aday-<tarih>)")
    d.add_argument("--n", type=int, default=250, help="genel taramada detaylı taramaya önerilecek ilan sayısı")
    a = ap.parse_args()

    if a.komut == "kur":
        analiz.piyasa_hazirla(yeniden_kur=True)
        return
    if a.komut == "ekle":
        eklenen = analiz.referansa_ekle(a.dosyalar)
        print(f"  {len(eklenen)} dosya referansa eklendi")
        analiz.piyasa_hazirla()
        return
    piyasa, conn = analiz.piyasa_hazirla()
    m = piyasa.model
    if a.komut == "durum":
        n = conn.execute("SELECT COUNT(*), SUM(durum='aktif'), SUM(durum='kayboldu') FROM ilan").fetchone()
        g = conn.execute("SELECT tarih, ilan_sayisi FROM goruntu ORDER BY tarih").fetchall()
        print(f"  İlan: {n[0]} (aktif {n[1]}, kaybolan {n[2]})")
        print(f"  Görüntüler: " + ", ".join(f"{t} ({k})" for t, k in g))
        print(f"  Model: {len(m.kolonlar)} sütun, tipik sapma ±%{m.sigma*100:.1f}, fiyat penceresi "
              + ", ".join(f"{k}: {round(2.718281828**lo/1e6, 2)}-{round(2.718281828**hi/1e6, 2)} M" for k, (lo, hi) in m.pencere.items()))
        for k, v in m.katsayi_ozeti().items():
            print(f"    {k:34s} {v*100:+5.1f}%")
        return
    bugun = piyasa.bugun[:10]
    if a.komut == "piyasa":
        sonuclar = [s for s in analiz.piyasa_firsatlari(piyasa) if s["puan"] >= a.min_puan][: a.n]
        _ozet_yaz(sonuclar)
        _kaydet(sonuclar, f"piyasa-firsatlari-{bugun}", "Fırsat Araç Listesi",
                f"arabam.com piyasası, {bugun} — {len(piyasa.satirlar):,} ilan tarandı".replace(",", "."), piyasa, "piyasa")
    elif a.komut == "hizli":
        tum = [piyasa.degerlendir(r) for r in piyasa.satirlar]
        tum = analiz._tekille(sorted(tum, key=lambda s: -s["puan_hizli"]))
        ek = {"n_karli": sum(s["net_yarin"] > 0 for s in tum), "n_karli_100": sum(s["net_yarin"] > 100_000 for s in tum)}
        sonuclar = [s for s in tum if s["net_yarin"] > 0 and s["puan_hizli"] >= a.min_puan][: a.n]
        print(f"\n  Yarın satılsa kâr eden: {ek['n_karli']} ilan (100 bin TL üstü: {ek['n_karli_100']})")
        print(f"\n  {'#':>3} {'Puan':>5}  {'Net kâr':>10}  Araç")
        for i, s in enumerate(sonuclar[:15], 1):
            print(f"  {i:>3} {s['puan_hizli']:5.1f}  {s['net_yarin']:>10,.0f}  {s['marka']} {s['seri']} {s['model']} {s['yil']} | "
                  f"{s['km']:,} km | {s['fiyat']:,} TL".replace(",", "."))
        _kaydet(sonuclar, f"hizli-al-sat-{bugun}", "Hızlı Al-Sat Listesi",
                f"arabam.com piyasası, {bugun}", piyasa, "hizli", ek)
    elif a.komut == "degerlendir":
        for y in a.dosyalar:
            analiz.aday_dosyasini_sakla(y)
        sonuclar, bilgi = analiz.adaylari_degerlendir(piyasa, a.dosyalar)
        sahibinden = "sahibinden" in bilgi["kaynak"]
        pazar = "pazar" in bilgi["tur"]
        if bilgi["eslesme"]:
            print("  arabam eşleşmesi: " + ", ".join(f"{k} {v}" for k, v in bilgi["eslesme"].most_common()))
        if pazar:
            # genel tarama: detaylı taramaya değecekleri seç (kâr potansiyeline göre)
            from firsat import ayarlar as A
            sonuclar.sort(key=lambda s: -s["puan_hizli"])
            # daha önce detaylı taranmış ve fiyatı düşmemiş ilanları tekrar önerme
            onceki = analiz.onceki_detaylar()
            tekrar = [s for s in sonuclar if s["ilan_id"] in onceki and onceki[s["ilan_id"]] and s["fiyat"] >= onceki[s["ilan_id"]]]
            if tekrar:
                ids = {s["ilan_id"] for s in tekrar}
                sonuclar = [s for s in sonuclar if s["ilan_id"] not in ids]
                print(f"  Daha önce detaylı taranmış, fiyatı düşmemiş {len(tekrar)} ilan listeden çıkarıldı")
            # referans piyasanın kapsamadığı yıl/km (ör. sahibinden SUV sayfası yıl-km filtresini uygulamıyor)
            kapsam = {}
            for r in piyasa.satirlar:
                lo, hi = kapsam.get(r["kategori"], (9999, 0))
                kapsam[r["kategori"]] = (min(lo, r["yil"]), max(hi, r["km"]))
            dis = [s for s in sonuclar if s["yil"] < kapsam.get(s["kategori"], (0, 10**9))[0]
                   or s["km"] > kapsam.get(s["kategori"], (0, 10**9))[1]]
            if dis:
                ids = {s["ilan_id"] for s in dis}
                sonuclar = [s for s in sonuclar if s["ilan_id"] not in ids]
                print(f"  Referansın kapsamadığı yıl/km: {len(dis)} ilan çıkarıldı")
            if not sahibinden:
                # aynı araç sahibinden'de zaten önerildi ya da detaylı tarandıysa arabam'dan tekrar önerme
                bilinen = analiz.sahibinden_bilinen_araclar()
                cift = [s for s in sonuclar if analiz.ayni_arac_var(bilinen, s)]
                if cift:
                    ids = {s["ilan_id"] for s in cift}
                    sonuclar = [s for s in sonuclar if s["ilan_id"] not in ids]
                    print(f"  sahibinden'de de ilanda olan (zaten önerilmiş/taranmış) {len(cift)} araç çıkarıldı")
            sonuclar = [s for s in sonuclar if s["firsat"] * s["guven"] >= (A.ONELEME_TEMIZ_ESIK if not (s["n_boya"] or s["n_degisen"])
                                                                 else A.ONELEME_BOYALI_ESIK)
                        and s.get("agir_hasar") != "var"
                        and not any(c >= 15 or k in ("lpg_sonradan", "manuel", "kiralik", "kiralik_firma") for k, _, c in s["riskler"])][: a.n]
        _ozet_yaz(sonuclar, 30)
        site_adi = "Sahibinden" if sahibinden else "Aday"
        ad = a.ad or f"{'sahibinden-on-eleme' if pazar else ('sahibinden' if sahibinden else 'aday')}-{date.today().isoformat()}"
        baslik = "Sahibinden Ön Eleme" if pazar else f"{site_adi} Fırsatları"
        _kaydet(sonuclar, ad, baslik,
                f"{len(sonuclar)} ilan, {len(piyasa.satirlar):,} ilanlık arabam piyasasına göre puanlandı".replace(",", "."),
                piyasa, "aday")
        if pazar:
            (RAPORLAR / f"{ad}-linkler.txt").write_text("\n".join(_link(s["url"]) for s in sonuclar if s.get("url")) + "\n", encoding="utf-8")
            (RAPORLAR / f"{ad}-ilan-numaralari.txt").write_text(",".join(s["ilan_id"] for s in sonuclar) + "\n", encoding="utf-8")
            print(f"  Detaylı taranacak {len(sonuclar)} ilan: raporlar/{ad}-linkler.txt ve -ilan-numaralari.txt")
            # Sohbete yapıştırmak için tek blok: eklenti link listesini sayfadan bağımsız topluyor (adres_listesi)
            print("\n===== LİNKLER (sohbete aynen yapıştır) =====")
            print("\n".join(_link(s_["url"]) for s_ in sonuclar if s_.get("url")))


if __name__ == "__main__":
    sys.exit(main())
