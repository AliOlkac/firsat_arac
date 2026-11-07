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


PARCA_ESLE = {"Bagaj Kapağı": "Arka Kaput", "Bagaj Kapagi": "Arka Kaput"}   # sahibinden -> arabam parça adı


def hasar_ozet(bd):
    def _ad(x):            # "Ön Tampon (Mini Onarım / Tamir)" -> "Ön Tampon"
        x = re.sub(r"\s*\(.*?\)\s*$", "", x or "").strip()
        return PARCA_ESLE.get(x, x)
    p = {k: [_ad(x) for x in (v or [])] for k, v in ((bd or {}).get("parcalar") or {}).items()}
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


def _al(a, *anahtarlar):
    """Aynı bilgi arabam ve sahibinden dosyalarında farklı etiketle gelir; ilk dolu olanı döner."""
    for k in anahtarlar:
        if a.get(k) not in (None, ""):
            return a[k]
    return None


def yakit_norm(y):
    """Yakıt adını arabam sözlüğüne çevirir (model bu adlarla eğitildi)."""
    s = sade(y)
    if not s:
        return y
    if "lpg" in s:
        return "LPG & benzin"
    if "hibrit" in s or "hybrid" in s:
        return "Hibrit"
    if "elektrik" in s:
        return "Elektrik"
    if "dizel" in s or "diesel" in s:
        return "Dizel"
    if "benzin" in s:
        return "Benzin"
    return y


def kasa_norm(k):
    s = sade(k)
    if not s:
        return k
    if "hatchback" in s:
        return "Hatchback/3" if "3" in s else "Hatchback/5"
    if "station" in s:
        return "Station wagon"
    if "suv" in s:
        return "SUV"
    return k


def garanti_norm(g):
    s = sade(g)
    if not s:
        return None
    if "var" in s or s in ("evet", "devam ediyor"):
        return 1
    if "yok" in s or s == "hayir":
        return 0
    return None


def site(url):
    return "sahibinden" if "sahibinden.com" in (url or "") else "arabam"


def satir(x, kategori=None, kaynak=None):
    """arabam ya da sahibinden detaylı ilanını ortak satıra çevirir."""
    g = x.get("genel_bilgiler") or {}
    a = x.get("arac_bilgileri") or {}
    bd = x.get("boya_degisen_tramer") or {}
    aciklama = x.get("aciklama") or ""
    baslik = g.get("baslik") or ""
    t = sade(baslik + " . " + aciklama)
    url = g.get("url")
    kaynak = kaynak or site(url)
    hp = sayi(a.get("Motor Gücü (Motor ve Performans)")) or aralik_orta(_al(a, "Motor gücü", "Motor Gücü"))
    agir = sade(bd.get("agir_hasar") or _al(a, "Ağır hasar kaydı", "Ağır Hasar Kayıtlı"))
    donanim = x.get("donanim") or {}
    donanim_duz = {d for v in donanim.values() for d in (v or [])} if isinstance(donanim, dict) else set()
    kasa = kasa_norm(_al(a, "Kasa tipi", "Kasa Tipi"))
    if not kategori:
        kategori = "suv" if ("arazi-suv" in (url or "") or kasa in ("SUV", "Crossover", "Pick-Up")) else "otomobil"
    r = {
        "ilan_id": str(g.get("ilan_id")), "kaynak": kaynak, "url": url, "baslik": baslik,
        "fiyat": sayi(g.get("fiyat")), "sehir": g.get("sehir"), "ilce": g.get("ilce"),
        "ilan_tarihi": (tarih_tr(g.get("ilan_tarihi")) or None), "kimden": g.get("kimden") or "Bilinmiyor",
        "foto": g.get("fotograf_sayisi"), "kategori": kategori,
        "marka": (a.get("Marka") or "").strip(), "seri": (a.get("Seri") or "").strip(),
        "model": (a.get("Model") or "").strip(), "yil": sayi(a.get("Yıl")), "km": sayi(_al(a, "Kilometre", "KM")),
        "vites": _al(a, "Vites tipi", "Vites"), "yakit": yakit_norm(_al(a, "Yakıt tipi", "Yakıt", "Yakıt / Motor Tipi")),
        "kasa": kasa, "renk": a.get("Renk"), "cekis": _al(a, "Çekiş"), "sanziman": a.get("Şanzıman"),
        "hp": hp, "cc": aralik_orta(_al(a, "Motor hacmi", "Motor Hacmi")), "segment": a.get("Sınıfı"),
        "garanti": garanti_norm(_al(a, "Garanti durumu", "Garanti", "Servis Garantisi")),
        "agir_hasar": "yok" if ("yok" in agir or agir == "hayir") else ("var" if agir in ("evet", "var") or "kayitli" in agir else None),
        "cam_tavan": int(bool(donanim_duz & {"Cam tavan", "Sunroof", "Cam Tavan"})),
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


def pazar_satiri(x):
    """sahibinden genel (liste) tarama satırı: açıklama, tramer ve parça adı yoktur."""
    kat = [k.strip() for k in (x.get("kategori") or "").split(">") if k.strip()]
    baslik = x.get("baslik") or ""
    url = x.get("url")
    boyasiz, degisensiz = x.get("boyasiz"), x.get("degisensiz")
    bilinmiyor = boyasiz is None and degisensiz is None
    model = x.get("model") or " ".join(kat[2:])
    r = {
        "ilan_id": str(x.get("ilan_id")), "kaynak": "sahibinden", "url": url, "baslik": baslik,
        "fiyat": sayi(x.get("fiyat")), "sehir": x.get("sehir"), "ilce": x.get("ilce"),
        "ilan_tarihi": tarih_tr(x.get("ilan_tarihi")), "kimden": x.get("kimden") or ("Galeriden" if x.get("magaza") else "Sahibinden"),
        "foto": None, "kategori": "suv" if "arazi-suv" in (url or "") else "otomobil",
        "marka": (x.get("marka") or (kat[0] if kat else "")).strip(), "seri": (x.get("seri") or (kat[1] if len(kat) > 1 else "")).strip(),
        "model": model.strip(), "yil": sayi(x.get("yil")), "km": sayi(x.get("km")),
        "vites": x.get("vites"), "yakit": yakit_norm(x.get("yakit")), "kasa": kasa_norm(x.get("kasa")),
        "renk": x.get("renk") or x.get("Renk"), "cekis": None, "sanziman": None, "hp": None, "cc": None, "segment": None,
        "garanti": None, "agir_hasar": {"Evet": "var", "Hayır": "yok"}.get(x.get("agir_hasar")), "cam_tavan": 0,
        "aciklama": "", "liste_satiri": 1,
        "n_lokal": 0, "n_boya": 0 if boyasiz in (True, None) else 2, "n_degisen": 0 if degisensiz in (True, None) else 1,
        "n_belirsiz": 13 if bilinmiyor else 0, "boya_bilinmiyor": int(bilinmiyor),
        "tampon_lokal": 0, "tampon_boya": 0, "tampon_degisen": 0, "tavan_boya": 0, "tavan_degisen": 0, "kaput_degisen": 0,
        "parcalar": {"lokal": [], "boya": [], "degisen": [], "belirsiz": []},
        "tramer_durum": "belirsiz", "tramer_tl": None, "tramer_kaynak": None,
    }
    r["motor"] = motor_anahtari(r["model"], r["yakit"])
    t = sade(baslik)
    r["riskler"] = riskler(t) + form_celiskileri(t, baslik, r)
    r["olumlu"] = olumlular(t)
    r["pesinat_gecer"] = int(bool(re.search(r"pesinat|kapora|\bsenet", t)))
    return r


def sahibinden_filtre_seri(url):
    """'https://www.sahibinden.com/skoda-octavia/otomatik?...' -> ('skoda', 'octavia', 'otomobil').
    Marka/seri ayrımı kesin değildir ('mercedes-benz-c-serisi' -> 'mercedes', 'benz c serisi'); eşleştirici düzeltir."""
    if not url or "sahibinden.com" not in url:
        return None, None, None
    yol = urlparse(url).path.strip("/").split("/")
    if not yol or not yol[0]:
        return None, None, None
    slug = yol[0]
    kategori = "otomobil"
    for on in ("arazi-suv-pickup-", "arazi-suv-pick-up-", "otomobil-"):
        if slug.startswith(on):
            kategori = "suv" if on.startswith("arazi") else "otomobil"
            slug = slug[len(on):]
    if slug in ("otomobil", "arazi-suv-pickup", "vasita"):
        return None, None, kategori
    parca = slug.split("-")
    return parca[0], " ".join(parca[1:]), kategori


def dosya_oku(yol):
    """(meta, satırlar) döner. meta: toplanma zamanı, filtre kapsamları, kaynak (arabam/sahibinden), tür (detay/pazar)."""
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
    satirlar, tur = [], "detay"
    detayli = any(isinstance(x, dict) and x.get("genel_bilgiler") for x in (d.get("ilanlar") or [])[:5])
    if not detayli and ("pazar" in d or meta.get("mod") == "pazar_taramasi"):
        tur = "pazar"
        gorulen = set()
        marka_slug, seri_slug, kat_slug = sahibinden_filtre_seri(meta.get("filtre_url"))
        for x in d.get("pazar") or d.get("ilanlar") or []:
            if str(x.get("ilan_id")) in gorulen or (x.get("para_birimi") not in (None, "TL")):
                continue
            gorulen.add(str(x.get("ilan_id")))
            if not x.get("marka") and not x.get("kategori") and marka_slug:
                x = dict(x, marka=marka_slug, seri=seri_slug)
            r = pazar_satiri(x)
            if kat_slug:
                r["kategori"] = kat_slug
            satirlar.append(r)
    else:
        for x in d.get("ilanlar") or []:
            g = x.get("genel_bilgiler") or {}
            if g.get("para_birimi") not in (None, "TL"):
                continue
            satirlar.append(satir(x, kategori.get(str(g.get("ilan_id")))))
    kaynak = "sahibinden" if (tur == "pazar" or "sahibinden" in sade(meta.get("kaynak"))
                              or any(r["kaynak"] == "sahibinden" for r in satirlar[:20])) else "arabam"
    return {"toplanma": toplanma, "kapsamlar": kapsamlar, "kaynak": kaynak, "tur": tur,
            "ilan_sayisi": len(satirlar)}, satirlar
