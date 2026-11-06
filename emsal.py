#!/usr/bin/env python3
"""Emsal karşılaştırma ve fırsat taraması.

Girdi : eklentiden gelen detaylı tarama JSON'ları (bir ya da birden fazla)
Çıktı : cikti/firsatlar.csv      tüm ilanlar, fırsat yüzdesine göre sıralı
        cikti/incele.txt         en iyi adaylar (link + neden + okunacak notlar)
        cikti/model_ozeti.txt    her grubun modeli: ilan sayısı, hata payı, katsayılar

Kullanım:
    python3 emsal.py data/*.json
    python3 emsal.py data/vw.json --en-az 8 --ust 60

Yöntem (kısaca):
 1. Her ilanın fiyatı, hasar cezası geri eklenerek "temiz araç fiyatı"na çevrilir.
 2. Grup başına (marka, seri, yakıt) log(temiz fiyat) ~ yıl + km + paket regresyonu kurulur,
    uç değerler atılıp yeniden uydurulur.
 3. Beklenen fiyat = temiz tahmin x (1 - hasar cezası) - tramer cezası.
 4. Fırsat % = (beklenen - ilan fiyatı) / beklenen.
Hasar cezaları aşağıdaki tablodadır; elindeki veriyle kalibre edildikçe güncelle.
"""
import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

# --- Hasar ceza tablosu (temiz araç fiyatına oranla) -----------------------
CEZA_LOKAL_BOYA = 0.010      # parça başı
CEZA_BOYA = 0.020            # parça başı
CEZA_DEGISEN = 0.040         # parça başı
CEZA_KRITIK = 0.080          # tavan / direk / podye / şasi boyalı ya da değişen (ek)
CEZA_AGIR_HASAR = 0.120      # "Ağır Hasar Kayıtlı: Evet"
TRAMER_ORANI = 0.40          # açıklamadaki tramer tutarının fiyata yansıyan kısmı
KRITIK_PARCA = re.compile(r"tavan|direk|podye|şasi|sasi", re.I)

SUPHELI_ESIK = 0.35          # bundan büyük "fırsat" önce şüpheli sayılır
MIN_GRUP = 25                # regresyon için gereken en az ilan

AYLAR = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7,
         "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}

POZITIF = re.compile(r"acil|borç|borc|yurt\s?dışı|yurtdisi|taşınma|tasinma|ihtiyaçtan|sahibinden acil", re.I)
NEGATIF = re.compile(r"hasarlı|hasarli|\bpert\b|ağır hasar|agir hasar|ağir hasar|kaporta|motor arıza|şanzıman arıza|"
                     r"çalışmıyor|yürümez|km garantisi yok|ekspertiz yok|\bçıkma|\bçikma|rötuş|rotus|çizik|göçük|gocuk", re.I)
TRAMERSIZ = re.compile(r"tramersiz|tramer yok|tramer kayd[ıi] yok|hasar kayd[ıi] yok|hasarsız|hasarsiz|"
                       r"hatasız|hatasiz|sıfır tramer|0 tramer", re.I)
TRAMER_ANAHTAR = re.compile(r"tramer|hasar\s*kayd[ıi]|hasar\s*kay[ıi]t", re.I)


def sayi(s):
    if s is None:
        return None
    r = re.sub(r"\D", "", str(s))
    return int(r) if r else None


def tarih(s):
    m = re.match(r"(\d{1,2})\s+(\w+)\s+(\d{4})", (s or "").strip().lower())
    if not m or m.group(2) not in AYLAR:
        return None
    return datetime(int(m.group(3)), AYLAR[m.group(2)], int(m.group(1)))


def tramer_tutari(metin):
    """Açıklamadan tramer/hasar kaydı tutarı (TL) çıkarır. Bulamazsa None."""
    t = metin.lower()
    en_iyi = None
    for m in re.finditer(r"tramer|hasar\s*kayd[ıi]|hasar\s*kay[ıi]t", t):
        pencere = t[m.end(): m.end() + 40]
        # "tramer yok / sıfır / 0" gibi ifadeler tutar sayılmaz
        if re.match(r"\W{0,6}(yok|sıfır|sifir|0\b|bulunmamaktadır|bulunmuyor)", pencere):
            continue
        n = re.search(r"(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(bin|k\b)?\s*(tl|₺|lira)?", pencere)
        if not n:
            continue
        ham, bin_, tl = n.group(1), n.group(2), n.group(3)
        deger = int(re.sub(r"[.,]", "", ham))
        if bin_:
            deger *= 1000 if deger < 1000 else 1
        if 2000 <= deger <= 2100 and not tl:   # muhtemelen yıl
            continue
        if deger < 1500 and not bin_:          # "2 parça", "3 boya" vb.
            continue
        if deger > 2_000_000:
            continue
        en_iyi = max(en_iyi or 0, deger)
    return en_iyi


def oku(dosyalar):
    ilanlar, toplanma = {}, None
    for f in dosyalar:
        d = json.load(open(f, encoding="utf-8"))
        toplanma = toplanma or tarih_iso(d.get("meta", {}).get("toplanma_tarihi"))
        for x in d.get("ilanlar", []):
            ilanlar[x["genel_bilgiler"]["ilan_id"]] = x   # tekrarlarda sonuncu kazanır
    return list(ilanlar.values()), toplanma or datetime.now()


def tarih_iso(s):
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except Exception:
        return None


def satir(x, bugun):
    g, a = x["genel_bilgiler"], x.get("arac_bilgileri") or {}
    bd = x.get("boya_degisen_tramer") or {}
    p = bd.get("parcalar")
    metin = ((g.get("baslik") or "") + " . " + (x.get("aciklama") or ""))
    lokal = len((p or {}).get("Lokal Boyalı", []))
    boyali = len((p or {}).get("Boyalı", []))
    degisen = len((p or {}).get("Değişen", []))
    kritik = sum(1 for k in ("Lokal Boyalı", "Boyalı", "Değişen")
                 for n in (p or {}).get(k, []) if KRITIK_PARCA.search(n))
    tutar = tramer_tutari(metin)
    ilan_t = tarih(g.get("ilan_tarihi"))
    return dict(
        id=g["ilan_id"], url=g.get("url"), baslik=g.get("baslik"),
        marka=a.get("Marka"), seri=a.get("Seri"), paket=(a.get("Model") or "").strip(),
        yakit=a.get("Yakıt / Motor Tipi"), yil=sayi(a.get("Yıl")), km=sayi(a.get("KM")),
        fiyat=sayi(g.get("fiyat")), sehir=g.get("sehir"), kimden=g.get("kimden"),
        satici=g.get("satici"), foto=g.get("fotograf_sayisi"),
        ilan_yasi=(bugun - ilan_t).days if ilan_t else None,
        lokal=lokal, boyali=boyali, degisen=degisen, kritik=kritik,
        parca_yok=p is None, agir=(bd.get("agir_hasar") == "Evet"),
        tramer_tutar=tutar,
        tramer_belirsiz=bool(TRAMER_ANAHTAR.search(metin)) and not TRAMERSIZ.search(metin) and tutar is None,
        tramersiz_yazili=bool(TRAMERSIZ.search(metin)),
        pozitif=sorted({m.lower() for m in POZITIF.findall(metin)}),
        negatif=sorted({m.lower() for m in NEGATIF.findall(metin)}),
    )


def ceza_orani(r):
    c = (r["lokal"] * CEZA_LOKAL_BOYA + r["boyali"] * CEZA_BOYA + r["degisen"] * CEZA_DEGISEN
         + (CEZA_KRITIK if r["kritik"] else 0) + (CEZA_AGIR_HASAR if r["agir"] else 0))
    return min(c, 0.6)


def tasarim(rows, yillar, paketler):
    A = []
    for r in rows:
        A.append([1.0] + [float(r["yil"] == y) for y in yillar[1:]] + [r["km"] / 10000.0]
                 + [float(r["paket_k"] == p) for p in paketler[1:]])
    return np.array(A, float)


def grup_modeli(rows):
    """Bir grubun log-fiyat modelini kurar. (beta, yillar, paketler, sd, n) döner."""
    for r in rows:
        r["paket_k"] = r["paket"]
    sayac = defaultdict(int)
    for r in rows:
        sayac[r["paket"]] += 1
    for r in rows:
        if sayac[r["paket"]] < 5:
            r["paket_k"] = "diger"
    yillar = sorted({r["yil"] for r in rows})
    paketler = sorted({r["paket_k"] for r in rows})
    y_all = np.array([np.log(r["temiz"]) for r in rows])
    A_all = tasarim(rows, yillar, paketler)
    kullan = np.ones(len(rows), bool)
    for _ in range(3):
        beta = np.linalg.lstsq(A_all[kullan] + 0.0, y_all[kullan], rcond=None)[0]
        res = y_all - A_all @ beta
        sd = res[kullan].std() or 1e-6
        yeni = (res > -2.0 * sd) & (res < 2.5 * sd)
        if (yeni == kullan).all():
            break
        kullan = yeni
    return beta, yillar, paketler, float(res[kullan].std()), int(kullan.sum())


def tahmin(beta, yillar, paketler, r):
    r = dict(r)
    r["paket_k"] = r["paket"] if r["paket"] in paketler else "diger"
    if r["yil"] not in yillar or r["paket_k"] not in paketler:
        return None
    return float(np.exp((tasarim([r], yillar, paketler) @ beta)[0]))


def analiz(rows, en_az):
    for r in rows:
        r["ceza"] = ceza_orani(r)
        tr_tl = (r["tramer_tutar"] or 0) * TRAMER_ORANI
        r["tramer_ceza_tl"] = tr_tl
        r["temiz"] = max((r["fiyat"] + tr_tl) / (1 - r["ceza"]), 1)
    gruplar = defaultdict(list)
    for r in rows:
        gruplar[(r["marka"], r["seri"], r["yakit"])].append(r)
    ozet = []
    for k, v in sorted(gruplar.items(), key=lambda kv: -len(kv[1])):
        if len(v) < MIN_GRUP:
            for r in v:
                r.update(beklenen=None, temiz_tahmin=None, firsat=None, guven="yetersiz emsal", grup_n=len(v), sd=None)
            ozet.append(f"{k}: {len(v)} ilan (< {MIN_GRUP}) -> fiyat modeli kurulmadı")
            continue
        beta, yillar, paketler, sd, n = grup_modeli(v)
        ozet.append(f"{k}: {len(v)} ilan, modelde {n}, hata payı ±%{sd*100:.1f}, "
                    f"km etkisi {np.expm1(beta[len(yillar)])*100:+.1f}% / 10 bin km")
        for r in v:
            temiz_t = tahmin(beta, yillar, paketler, r)
            if temiz_t is None:
                r.update(beklenen=None, temiz_tahmin=None, firsat=None, guven="yıl/paket modelde yok", grup_n=len(v), sd=sd)
                continue
            beklenen = temiz_t * (1 - r["ceza"]) - r["tramer_ceza_tl"]
            r.update(temiz_tahmin=temiz_t, beklenen=beklenen, firsat=(beklenen - r["fiyat"]) / beklenen,
                     grup_n=len(v), sd=sd,
                     guven="yüksek" if len(v) >= 150 and sd < 0.05 else "orta" if len(v) >= 50 else "düşük")
    return ozet


def nedenler(r):
    n = []
    if r["parca_yok"]:
        n.append("boya/değişen bilgisi yok")
    if r["tramer_belirsiz"]:
        n.append("açıklamada tramer geçiyor, tutar okunamadı -> OKU")
    if r["tramer_tutar"]:
        n.append(f"açıklamadaki tramer ~{r['tramer_tutar']:,} TL".replace(",", "."))
    if r["agir"]:
        n.append("AĞIR HASAR KAYITLI")
    if r["kritik"]:
        n.append("tavan/direk/podye/şasi boyalı ya da değişen")
    if r["negatif"]:
        n.append("açıklamada: " + ", ".join(r["negatif"]))
    if r["pozitif"]:
        n.append("satıcı acelesi: " + ", ".join(r["pozitif"]))
    if r["firsat"] is not None and r["firsat"] > SUPHELI_ESIK:
        n.append("ÇOK UCUZ: dolandırıcılık/gizli hasar olabilir, önce doğrula")
    if r["ilan_yasi"] is not None and r["ilan_yasi"] >= 30:
        n.append(f"{r['ilan_yasi']} gündür yayında (pazarlık payı)")
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dosyalar", nargs="+")
    ap.add_argument("--en-az", type=float, default=8.0, help="aday için en düşük fırsat %% (varsayılan 8)")
    ap.add_argument("--ust", type=int, default=50, help="incele.txt'e yazılacak en fazla aday")
    ap.add_argument("--cikti", default="cikti")
    a = ap.parse_args()

    ham, bugun = oku(a.dosyalar)
    rows = [r for r in (satir(x, bugun) for x in ham) if r["fiyat"] and r["yil"] and r["km"] is not None]
    print(f"{len(ham)} ilan okundu, {len(rows)} ilan analize girdi")
    ozet = analiz(rows, a.en_az)

    out = Path(a.cikti)
    out.mkdir(exist_ok=True)
    (out / "model_ozeti.txt").write_text("\n".join(ozet) + "\n", encoding="utf-8")

    sirali = sorted(rows, key=lambda r: -(r["firsat"] if r["firsat"] is not None else -9))
    alanlar = ["id", "marka", "seri", "paket", "yil", "km", "fiyat", "beklenen", "firsat", "guven", "grup_n",
               "lokal", "boyali", "degisen", "agir", "tramer_tutar", "kimden", "sehir", "ilan_yasi", "url"]
    with open(out / "firsatlar.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, alanlar, extrasaction="ignore")
        w.writeheader()
        for r in sirali:
            r = dict(r)
            if r["beklenen"] is not None:
                r["beklenen"] = round(r["beklenen"])
                r["firsat"] = round(r["firsat"], 4)
            w.writerow(r)

    adaylar = [r for r in sirali if r["firsat"] is not None and r["firsat"] * 100 >= a.en_az][: a.ust]
    satirlar = []
    for i, r in enumerate(adaylar, 1):
        satirlar.append(
            f"{i}. %{r['firsat']*100:.1f} fırsat | {r['marka']} {r['seri']} {r['paket']} {r['yil']} | "
            f"{r['km']:,} km | ilan {r['fiyat']:,} TL | beklenen {r['beklenen']:,.0f} TL | güven: {r['guven']}".replace(",", ".")
        )
        satirlar.append(f"   {r['url']}")
        for n in nedenler(r):
            satirlar.append(f"   - {n}")
        satirlar.append("")
    (out / "incele.txt").write_text("\n".join(satirlar) + "\n", encoding="utf-8")

    print("\n".join(ozet))
    print(f"\n%{a.en_az:g} üzeri aday: {len([r for r in rows if r['firsat'] is not None and r['firsat']*100 >= a.en_az])}"
          f" (incele.txt'e ilk {len(adaylar)} yazıldı)")
    print(f"Çıktılar: {out}/firsatlar.csv, {out}/incele.txt, {out}/model_ozeti.txt")


if __name__ == "__main__":
    main()
