"""arabam.com detaylı ilan JSON'larını (eklentinin 'coklu' çıktısı) ortak satır biçimine çevirir."""
import gzip
import json
import lzma
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .metin import form_celiskileri, olumlular, riskler, sade, tramer_metinden

AYLAR = {"ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6, "temmuz": 7,
         "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12}
PARCALAR = ["Motor Kaputu", "Tavan", "Arka Kaput", "Ön Tampon", "Arka Tampon",
            "Sol Ön Çamurluk", "Sağ Ön Çamurluk", "Sol Arka Çamurluk", "Sağ Arka Çamurluk",
            "Sol Ön Kapı", "Sağ Ön Kapı", "Sol Arka Kapı", "Sağ Arka Kapı"]
TAMPONLAR = {"Ön Tampon", "Arka Tampon"}


def ac(yol):
    yol = str(yol)
    if yol.endswith(".xz"):
        return lzma.open(yol, "rt", encoding="utf-8")
    if yol.endswith(".gz"):
        return gzip.open(yol, "rt", encoding="utf-8")
    return open(yol, encoding="utf-8")


def sayi(s):
    if s is None:
        return None
    r = re.sub(r"\D", "", str(s))
    return int(r) if r else None


def aralik_orta(s):
    """'101 - 125 HP' -> 113, '130 HP' -> 130."""
    if not s:
        return None
    n = [int(x) for x in re.findall(r"\d+", str(s).replace(".", ""))]
    if not n:
        return None
    return round(sum(n[:2]) / len(n[:2]))


def tarih_tr(s):
    m = re.match(r"(\d{1,2})\s+(\S+)\s+(\d{4})", sade(s))
    if not m or m.group(2) not in AYLAR:
        return None
    return date(int(m.group(3)), AYLAR[m.group(2)], int(m.group(1)))


def motor_anahtari(model, yakit):
    """'1.0 TCe Icon' -> '1.0 tce'; motor hacmi yoksa ilk kelime. Yakıt eklenir (hibrit/benzin ayrımı)."""
    tok = sade(model).replace("-", " ").split()
    if not tok:
        return sade(yakit)
    if re.match(r"^\d[.,]\d+$", tok[0]):
        anahtar = " ".join(tok[:2])
    else:
        anahtar = tok[0]
    return f"{anahtar} | {sade(yakit)}"


def filtre_kapsami(url):
    """Filtre adresinden kapsam: kategori, fiyat ve yıl/km sınırları."""
    u = urlparse(url)
    q = parse_qs(u.query)
    kategori = "suv" if "arazi-suv" in u.path else "otomobil"

    def ilk(k, tip=int):
        v = q.get(k)
        return tip(v[0]) if v else None
    return {"kategori": kategori, "min_fiyat": ilk("minPrice"), "max_fiyat": ilk("maxPrice"),
            "min_yil": ilk("minYear"), "max_km": ilk("maxkm"), "url": url}


def hasar_ozet(bd):
    p = (bd or {}).get("parcalar") or {}
    lokal = p.get("Lokal boyalı") or p.get("Lokal Boyalı") or []
    boya = p.get("Boyalı") or []
    degisen = p.get("Değişmiş") or p.get("Değişen") or []
    belirsiz = p.get("Belirtilmemiş") or []
    orjinal = p.get("Orjinal") or p.get("Orijinal") or []
    tumu_bilinmiyor = not p or (len(belirsiz) >= 12 and not (lokal or boya or degisen)) or \
        (not orjinal and not lokal and not boya and not degisen)
    return {
        "n_lokal": len(lokal), "n_boya": len(boya), "n_degisen": len(degisen), "n_belirsiz": len(belirsiz),
        "boya_bilinmiyor": int(tumu_bilinmiyor),
        "tampon_lokal": sum(1 for x in lokal if x in TAMPONLAR),
        "tampon_boya": sum(1 for x in boya if x in TAMPONLAR),
        "tampon_degisen": sum(1 for x in degisen if x in TAMPONLAR),
        "tavan_boya": int("Tavan" in boya or "Tavan" in lokal),
        "tavan_degisen": int("Tavan" in degisen),
        "kaput_degisen": int("Motor Kaputu" in degisen),
        "parcalar": {"lokal": lokal, "boya": boya, "degisen": degisen, "belirsiz": belirsiz},
    }


def tramer_ozet(bd, metin_sade):
    t = sade((bd or {}).get("tramer"))
    durum, tutar, kaynak = None, None, None
    if "yok" in t:
        durum, tutar, kaynak = "yok", 0, "ilan"
    elif re.search(r"\d", t):
        tutar = sayi(t)
        durum, kaynak = ("yok" if tutar == 0 else "tutar"), "ilan"
    if durum is None:
        d, x = tramer_metinden(metin_sade)
        if d:
            durum, tutar, kaynak = d, x, "aciklama"
    if durum is None:
        durum = "belirsiz"
    return {"tramer_durum": durum, "tramer_tl": tutar, "tramer_kaynak": kaynak}


def satir(x, kategori=None, kaynak="arabam"):
    g = x.get("genel_bilgiler") or {}
    a = x.get("arac_bilgileri") or {}
    bd = x.get("boya_degisen_tramer") or {}
    aciklama = x.get("aciklama") or ""
    baslik = g.get("baslik") or ""
    t = sade(baslik + " . " + aciklama)
    hp = sayi(a.get("Motor Gücü (Motor ve Performans)")) or aralik_orta(a.get("Motor gücü"))
    garanti = a.get("Garanti durumu")
    agir = sade(bd.get("agir_hasar") or a.get("Ağır hasar kaydı"))
    donanim = x.get("donanim") or {}
    donanim_duz = {d for v in donanim.values() for d in (v or [])} if isinstance(donanim, dict) else set()
    r = {
        "ilan_id": str(g.get("ilan_id")), "kaynak": kaynak, "url": g.get("url"), "baslik": baslik,
        "fiyat": sayi(g.get("fiyat")), "sehir": g.get("sehir"), "ilce": g.get("ilce"),
        "ilan_tarihi": (tarih_tr(g.get("ilan_tarihi")) or None), "kimden": g.get("kimden") or "Bilinmiyor",
        "foto": g.get("fotograf_sayisi"), "kategori": kategori or ("suv" if a.get("Kasa tipi") in ("SUV", "Crossover", "Pick-Up") else "otomobil"),
        "marka": (a.get("Marka") or "").strip(), "seri": (a.get("Seri") or "").strip(),
        "model": (a.get("Model") or "").strip(), "yil": sayi(a.get("Yıl")), "km": sayi(a.get("Kilometre")),
        "vites": a.get("Vites tipi"), "yakit": a.get("Yakıt tipi"), "kasa": a.get("Kasa tipi"),
        "renk": a.get("Renk"), "cekis": a.get("Çekiş"), "sanziman": a.get("Şanzıman"),
        "hp": hp, "cc": sayi(a.get("Motor hacmi")), "segment": a.get("Sınıfı"),
        "garanti": 1 if garanti == "Garantisi var" else (0 if garanti == "Garantisi yok" else None),
        "agir_hasar": "yok" if "yok" in agir else ("var" if agir in ("evet", "var") or "kayitli" in agir else None),
        "cam_tavan": int(bool(donanim_duz & {"Cam tavan", "Sunroof"})),
        "aciklama": aciklama,
    }
    r["motor"] = motor_anahtari(r["model"], r["yakit"])
    r.update(hasar_ozet(bd))
    r.update(tramer_ozet(bd, t))
    r["riskler"] = [x for x in riskler(t) + form_celiskileri(t, baslik, r)
                    if not (x[0] == "lpg_sonradan" and "LPG" in (r.get("yakit") or ""))]
    r["olumlu"] = olumlular(t)
    r["pesinat_gecer"] = int(bool(re.search(r"pesinat|kapora|\bsenet", t)))
    return r


def dosya_oku(yol):
    """(meta, satırlar) döner. meta: toplanma zamanı, filtre kapsamları."""
    with ac(yol) as f:
        d = json.load(f)
    meta = d.get("meta") or {}
    kategori = {}
    kapsamlar = []
    for fl in meta.get("filtreler") or []:
        k = filtre_kapsami(fl.get("filtre_url") or "")
        k["tamam"] = fl.get("durum") == "tamamlandı"
        k["sitede"], k["basarili"] = fl.get("sitedeki_ilan_sayisi"), fl.get("basarili_ilan")
        kapsamlar.append(k)
        for i in fl.get("ilan_idleri") or []:
            kategori[str(i)] = k["kategori"]
    if not kapsamlar and meta.get("filtre_url"):
        kapsamlar.append(filtre_kapsami(meta["filtre_url"]))
    toplanma = meta.get("toplanma_tarihi")
    try:
        toplanma = datetime.fromisoformat(toplanma).replace(tzinfo=None)
    except Exception:
        toplanma = datetime.fromtimestamp(Path(yol).stat().st_mtime)
    satirlar = []
    for x in d.get("ilanlar") or []:
        iid = str((x.get("genel_bilgiler") or {}).get("ilan_id"))
        satirlar.append(satir(x, kategori.get(iid)))
    return {"toplanma": toplanma, "kapsamlar": kapsamlar, "kaynak": meta.get("kaynak", "arabam.com"),
            "ilan_sayisi": len(satirlar)}, satirlar
