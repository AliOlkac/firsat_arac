"""Genel (A = referans) tarama linklerini üretir.

Kullanım:  python3 linkler/filtre_ayarlari.py
Çıktı:     linkler/genel_tarama_linkleri.md  (tablo)
           linkler/genel_tarama_linkleri.txt (her satırda bir link, toplu tarama için)
"""
from pathlib import Path

# --- Ortak filtreler -------------------------------------------------------
KM_MAX = 130_000
FIYAT_MIN = 1_200_000
FIYAT_MAX = 2_000_000
VITES_YOLU = "otomatik,yari-otomatik"  # DSG/EDC/CVT'lerin çoğu "yarı otomatik" listelenir
SEDAN_KASA = "a8=250"  # sahibinden 'Kasa tipi: Sedan' (hatchback'i olan modellerde kullanılır)

# Boyasız + Değişensiz + Ağır hasar kayıtlı: Hayır parametreleri.
# Sitede bu 3 filtreyi bir kez elle seçip linkteki ek kısmı buraya yaz, örn:
# EK_PARAMETRELER = "a1234=5678&a9999=1"
EK_PARAMETRELER = "unpaintedParts=true&unchangingTracks=true&a116445=1263354"

# --- Marka -> minimum yıl (kalite/segmente göre) ---------------------------
MIN_YIL = {
    "mercedes-benz": 2017, "bmw": 2017, "audi": 2017, "volvo": 2017,
    "volkswagen": 2018, "skoda": 2018, "toyota": 2018, "honda": 2018,
    "mini": 2018, "seat": 2019, "cupra": 2020,
    "ford": 2019, "hyundai": 2019, "kia": 2019, "nissan": 2019, "peugeot": 2019,
    "renault": 2021,
}

# (marka, model slug, tip, sedan filtresi?)  tip: "oto" = otomobil, "suv" = arazi-suv-pickup
MODELLER = [
    # Premium
    ("audi", "a3", "oto", True), ("audi", "a4", "oto", False), ("audi", "a6", "oto", False),
    ("audi", "q2", "suv", False), ("audi", "q3", "suv", False), ("audi", "q5", "suv", False),
    ("bmw", "3-serisi", "oto", False), ("bmw", "5-serisi", "oto", False),
    ("bmw", "x1", "suv", False), ("bmw", "x2", "suv", False), ("bmw", "x3", "suv", False),
    ("mercedes-benz", "a-serisi", "oto", True), ("mercedes-benz", "c-serisi", "oto", True),
    ("mercedes-benz", "cla", "oto", False), ("mercedes-benz", "e-serisi", "oto", True),
    ("mercedes-benz", "gla", "suv", False), ("mercedes-benz", "glc", "suv", False),
    ("volvo", "s60", "oto", False), ("volvo", "s90", "oto", False),
    ("volvo", "xc40", "suv", False), ("volvo", "xc60", "suv", False),
    ("mini", "countryman", "suv", False),
    # Orta segment
    ("volkswagen", "passat", "oto", False), ("volkswagen", "jetta", "oto", False),
    ("volkswagen", "tiguan", "suv", False), ("volkswagen", "t-roc", "suv", False),
    ("volkswagen", "t-cross", "suv", False), ("volkswagen", "taigo", "suv", False),
    ("skoda", "octavia", "oto", False), ("skoda", "superb", "oto", False),
    ("skoda", "kamiq", "suv", False), ("skoda", "karoq", "suv", False), ("skoda", "kodiaq", "suv", False),
    ("seat", "ateca", "suv", False), ("seat", "arona", "suv", False),
    ("cupra", "formentor", "suv", False), ("cupra", "ateca", "suv", False),
    ("toyota", "corolla", "oto", True), ("toyota", "c-hr", "suv", False), ("toyota", "rav4", "suv", False),
    ("honda", "civic", "oto", True), ("honda", "hr-v", "suv", False), ("honda", "cr-v", "suv", False),
    ("ford", "focus", "oto", True), ("ford", "puma", "suv", False), ("ford", "kuga", "suv", False),
    ("hyundai", "elantra", "oto", False), ("hyundai", "bayon", "suv", False),
    ("hyundai", "kona", "suv", False), ("hyundai", "tucson", "suv", False),
    ("kia", "cerato", "oto", False), ("kia", "stonic", "suv", False),
    ("kia", "xceed", "suv", False), ("kia", "niro", "suv", False), ("kia", "sportage", "suv", False),
    ("nissan", "juke", "suv", False), ("nissan", "qashqai", "suv", False), ("nissan", "x-trail", "suv", False),
    ("peugeot", "408", "oto", False), ("peugeot", "508", "oto", False),
    ("peugeot", "2008", "suv", False), ("peugeot", "3008", "suv", False), ("peugeot", "5008", "suv", False),
    ("renault", "megane", "oto", True), ("renault", "taliant", "oto", False),
    ("renault", "captur", "suv", False), ("renault", "austral", "suv", False),
]


def link(marka, model, tip, sedan):
    on_ek = "arazi-suv-pickup-" if tip == "suv" else ""
    q = [f"a5_min={MIN_YIL[marka]}", f"a4_max={KM_MAX}",
         f"price_min={FIYAT_MIN}", f"price_max={FIYAT_MAX}"]
    if sedan:
        q.append(SEDAN_KASA)
    if EK_PARAMETRELER:
        q.append(EK_PARAMETRELER)
    return f"https://www.sahibinden.com/{on_ek}{marka}-{model}/{VITES_YOLU}?" + "&".join(q)


def main():
    klasor = Path(__file__).parent
    satirlar = ["# Genel Tarama (A – Referans) Linkleri", "",
                f"Ortak: otomatik + yarı otomatik, ≤{KM_MAX:,} km, {FIYAT_MIN:,}–{FIYAT_MAX:,} TL".replace(",", "."),
                "", "| # | Marka | Model | Tip | Min yıl | Link |", "|---|---|---|---|---|---|"]
    linkler = []
    for i, (marka, model, tip, sedan) in enumerate(MODELLER, 1):
        u = link(marka, model, tip, sedan)
        linkler.append(u)
        tip_ad = "SUV" if tip == "suv" else ("Sedan" if sedan else "Otomobil")
        satirlar.append(f"| {i} | {marka} | {model} | {tip_ad} | {MIN_YIL[marka]} | [aç]({u}) |")
    (klasor / "genel_tarama_linkleri.md").write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    (klasor / "genel_tarama_linkleri.txt").write_text("\n".join(linkler) + "\n", encoding="utf-8")
    print(f"{len(linkler)} link üretildi")


if __name__ == "__main__":
    main()
