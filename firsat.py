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


def _kaydet(sonuclar, ad, baslik, alt_baslik, piyasa, mod):
    RAPORLAR.mkdir(exist_ok=True)
    html_yol = RAPORLAR / f"{ad}.html"
    json_yol = RAPORLAR / f"{ad}.json"
    rapor.yaz(sonuclar, html_yol, baslik=baslik, alt_baslik=alt_baslik, piyasa=piyasa, mod=mod)
    with open(json_yol, "w", encoding="utf-8") as f:
        json.dump([rapor.kayit(s) for s in sonuclar], f, ensure_ascii=False, indent=1, default=str)
    # Claude'un okuması için: notu olmayan en iyi adayların açıklamaları (telefonlar maskeli, depoya girmez)
    notlar = rapor.notlari_yukle()
    satirlar = []
    for i, s in enumerate(sonuclar[:100], 1):
        if s["ilan_id"] in notlar:
            continue
        aciklama = re.sub(r"\s+", " ", s.get("aciklama") or "")
        aciklama = re.sub(r"(\+?90)?\s?0?\s?5\d{2}[\s\d]{7,12}", "[tel]", aciklama)
        satirlar.append(f"#{i} [{s['ilan_id']}] {s['puan']} {s['karar']} | {s['marka']} {s['seri']} {s['model']} {s['yil']} "
                        f"{s['km']} km | {s['fiyat']:,} TL, piyasa ~{s['adil']:,.0f} (%{s['firsat']*100:.1f}) | "
                        f"{s['n_boya']} boya {s['n_degisen']} değişen {s['n_lokal']} lokal, tramer {s['tramer_durum']} "
                        f"{s.get('tramer_tl') or ''} | {s['kimden']} {s['sehir']} | riskler: {', '.join(k for k, _, _ in s['riskler'])}"
                        f"\n   BAŞLIK: {s['baslik']}\n   AÇIKLAMA: {aciklama[:600]}\n")
    inceleme = RAPORLAR / f"{ad}-inceleme.txt"
    inceleme.write_text("\n".join(satirlar), encoding="utf-8")
    print(f"\n  HTML : {html_yol.relative_to(KOK)}\n  JSON : {json_yol.relative_to(KOK)}")
    print(f"  Okunacak (notu olmayan) {len(satirlar)} aday: {inceleme.relative_to(KOK)}")


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
    d = alt.add_parser("degerlendir")
    d.add_argument("dosyalar", nargs="+")
    d.add_argument("--ad", default=None, help="rapor dosya adı (varsayılan: aday-<tarih>)")
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
    elif a.komut == "degerlendir":
        for y in a.dosyalar:
            analiz.aday_dosyasini_sakla(y)
        sonuclar = analiz.adaylari_degerlendir(piyasa, a.dosyalar)
        _ozet_yaz(sonuclar, 30)
        ad = a.ad or f"aday-{date.today().isoformat()}"
        _kaydet(sonuclar, ad, "Aday Değerlendirmesi",
                f"{len(sonuclar)} ilan, {len(piyasa.satirlar):,} ilanlık piyasaya göre puanlandı".replace(",", "."),
                piyasa, "aday")


if __name__ == "__main__":
    sys.exit(main())
