"""Uçtan uca akış: veritabanını güncelle, modeli kur (ya da önbellekten yükle), ilanları değerlendir."""
import hashlib
import json
import lzma
import shutil
from pathlib import Path

from .degerlendirme import Piyasa
from .model import FiyatModeli
from .okuyucu import dosya_oku
from .veritabani import HAM, KOK, aktif_ilanlar, kur

MODEL_SURUM = "6"
MODEL_YOLU = KOK / "veri" / "model.pkl"
ADAYLAR = KOK / "veri" / "adaylar"


def _parmak_izi(conn):
    dosyalar = [r[0] for r in conn.execute("SELECT ad FROM dosya ORDER BY ad")]
    return hashlib.sha1((MODEL_SURUM + "|" + "|".join(dosyalar)).encode()).hexdigest()


def fiyat_penceresi(conn):
    """Son görüntüdeki filtrelerden kategori başına fiyat aralığı."""
    r = conn.execute("SELECT kapsamlar FROM goruntu ORDER BY tarih DESC LIMIT 1").fetchone()
    if r is None:
        return {}
    pencere = {}
    for k in json.loads(r[0]):
        lo, hi = k.get("min_fiyat"), k.get("max_fiyat")
        if not lo or not hi:
            continue
        a, b = pencere.get(k["kategori"], (lo, hi))
        pencere[k["kategori"]] = (min(a, lo), max(b, hi))
    return pencere


def piyasa_hazirla(sessiz=False, yeniden_kur=False):
    conn, _ = kur(yeniden=yeniden_kur, sessiz=sessiz)
    satirlar = aktif_ilanlar(conn)
    iz = _parmak_izi(conn)
    model = None
    if MODEL_YOLU.exists() and not yeniden_kur:
        try:
            m = FiyatModeli.yukle(MODEL_YOLU)
            if getattr(m, "parmak_izi", None) == iz:
                model = m
        except Exception:
            model = None
    if model is None:
        if not sessiz:
            print(f"  Fiyat modeli kuruluyor ({len(satirlar)} ilan)...")
        temiz = [r for r in satirlar if r.get("yil") and r.get("km") is not None and r.get("fiyat")]
        model = FiyatModeli().kur(temiz, pencere=fiyat_penceresi(conn))
        model.parmak_izi = iz
        model.kaydet(MODEL_YOLU)
    return Piyasa(satirlar, model), conn


def _tekille(sonuclar):
    """Aynı aracın tekrar ilanlarını (aynı model, yıl, km, fiyat) teke indirir."""
    gorulen, cikti = set(), []
    for s in sonuclar:
        k = (s["marka"], s["seri"], s["model"], s["yil"], s["km"], s["fiyat"])
        if k in gorulen:
            continue
        gorulen.add(k)
        cikti.append(s)
    return cikti


def piyasa_firsatlari(piyasa):
    sonuclar = [piyasa.degerlendir(r) for r in piyasa.satirlar]
    sonuclar.sort(key=lambda s: -s["puan"])
    return _tekille(sonuclar)


def aday_dosyasini_sakla(yol):
    """Değerlendirilen dosyanın sıkıştırılmış kopyasını veri/adaylar/ altına koyar."""
    yol = Path(yol)
    ADAYLAR.mkdir(parents=True, exist_ok=True)
    hedef = ADAYLAR / (yol.name if yol.name.endswith(".xz") else yol.name + ".xz")
    if not hedef.exists():
        if yol.name.endswith(".xz"):
            shutil.copy(yol, hedef)
        else:
            with open(yol, "rb") as i, lzma.open(hedef, "wb", preset=6) as o:
                shutil.copyfileobj(i, o)
    return hedef


def referansa_ekle(yollar):
    """Yeni piyasa taramasını veri/ham/ altına (sıkıştırılmış) koyar. Veritabanına işleme piyasa_hazirla'da olur."""
    eklenen = []
    HAM.mkdir(parents=True, exist_ok=True)
    for yol in yollar:
        yol = Path(yol)
        if sahibinden_mi(yol):
            print(f"  ! {yol.name}: sahibinden dosyası referans piyasaya eklenmez (arabam temel alınır). "
                  f"Değerlendirmek için: python3 firsat.py degerlendir {yol}")
            continue
        ad = yol.name
        # yükleme önekini (ör. '615a613a-') at: arabam-ilanlar-... ile başlasın
        if "arabam-" in ad and not ad.startswith("arabam-"):
            ad = ad[ad.index("arabam-"):]
        hedef = HAM / (ad if ad.endswith(".xz") else ad + ".xz")
        if hedef.exists():
            print(f"  = {hedef.name} zaten var, atlandı")
            continue
        if yol.name.endswith(".xz"):
            shutil.copy(yol, hedef)
        else:
            with open(yol, "rb") as i, lzma.open(hedef, "wb", preset=6) as o:
                shutil.copyfileobj(i, o)
        eklenen.append(hedef)
    return eklenen


def adaylari_degerlendir(piyasa, yollar):
    """Aday dosyalarını (arabam ya da sahibinden; detaylı ya da genel tarama) referans piyasaya göre puanlar.
    Adaylar veritabanına EKLENMEZ. (sonuçlar, bilgi) döner; bilgi: kaynaklar, türler, eşleşme sayıları."""
    from collections import Counter
    from .eslestir import Eslestirici
    sonuclar, bilgi = [], {"kaynak": set(), "tur": set(), "eslesme": Counter(), "okunamayan": 0}
    eslestirici = None
    for yol in yollar:
        meta, satirlar = dosya_oku(yol)
        bilgi["kaynak"].add(meta["kaynak"])
        bilgi["tur"].add(meta["tur"])
        for r in satirlar:
            if not (r.get("fiyat") and r.get("yil") and r.get("km") is not None and r.get("marka")):
                bilgi["okunamayan"] += 1
                continue
            if r.get("kaynak") == "sahibinden":
                eslestirici = eslestirici or Eslestirici(piyasa.satirlar)
                eslestirici.eslestir(r)
                bilgi["eslesme"][r["eslesme"]] += 1
            sonuclar.append(piyasa.degerlendir(r))
    sonuclar.sort(key=lambda s: -s["puan"])
    return _tekille(sonuclar), bilgi


def sahibinden_mi(yol):
    """Dosya sahibinden taraması mı? (sahibinden dosyaları referans veritabanına eklenmez)"""
    try:
        meta, satirlar = dosya_oku(yol)
    except Exception:
        return False
    return meta["kaynak"] == "sahibinden"
