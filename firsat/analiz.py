"""Uçtan uca akış: veritabanını güncelle, modeli kur (ya da önbellekten yükle), ilanları değerlendir."""
import hashlib
import json
import lzma
import math
import shutil
from pathlib import Path

from .degerlendirme import Piyasa
from .model import FiyatModeli
from .okuyucu import dosya_oku
from .veritabani import HAM, KOK, aktif_ilanlar, kur

MODEL_SURUM = "15"
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
    ad = yol.name
    for on in ("sahibinden-", "arabam-"):          # yükleme önekini (ör. '838a3f94-') at
        if on in ad and not ad.startswith(on):
            ad = ad[ad.index(on):]
            break
    hedef = ADAYLAR / (ad if ad.endswith(".xz") else ad + ".xz")
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


DUZELTME_BUZME = 20        # grup başına bu kadar ilan olana kadar düzeltme sıfıra doğru büzülür
DUZELTME_TAVAN = 0.08


def sahibinden_duzeltmesi(piyasa, eslestirici, sessiz=False):
    """sahibinden genel taramalarından (veri/adaylar/*pazar*) seri ve motor bazında site farkı.

    Aynı araç sahibinden'de arabam'dan farklı seviyede listelenebilir (ör. Golf eTSI ~%5 ucuz). Bu fark
    düzeltilmezse o serinin bütün ilanları "fırsat" görünür. Yalnızca boyasız/değişensiz, paket ya da motor
    düzeyinde eşleşen satırlar kullanılır; medyan log fark örnek sayısına göre sıfıra büzülür.
    Dönüş: {(marka, seri, motor): d, (marka, seri): d}; d < 0 ise sahibinden daha ucuz."""
    import statistics as st
    from collections import defaultdict
    gorulen = {}
    for yol in sorted(ADAYLAR.glob("*pazar*.json*")):
        try:
            _, satirlar = dosya_oku(yol)
        except Exception:
            continue
        for r in satirlar:
            if r.get("fiyat") and r.get("yil") and r.get("km") is not None and r.get("marka"):
                gorulen[r["ilan_id"]] = r            # sonraki tarama öncekinin yerine geçer
    seri, motor = defaultdict(list), defaultdict(list)
    for r in gorulen.values():
        r = dict(r)
        eslestirici.eslestir(r)
        if r["eslesme"] not in ("paket", "motor") or r["n_boya"] or r["n_degisen"]:
            continue
        fark = math.log(r["fiyat"]) - piyasa.model.log_tahmin(r)
        if abs(fark) > 0.35:                         # yanlış eşleşme / peşinat fiyatı gibi uç değerler
            continue
        seri[(r["marka"], r["seri"])].append(fark)
        motor[(r["marka"], r["seri"], r["motor"])].append(fark)
    k = DUZELTME_BUZME
    sinirla = lambda d: max(-DUZELTME_TAVAN, min(DUZELTME_TAVAN, d))
    sonuc = {}
    for s, v in seri.items():
        sonuc[s] = sinirla(len(v) / (len(v) + k) * st.median(v))
    for m, v in motor.items():
        ds = sonuc.get(m[:2], 0.0)
        sonuc[m] = sinirla(ds + len(v) / (len(v) + k) * (st.median(v) - ds))
    if not sessiz:
        print(f"  sahibinden site farkı: {len(gorulen)} genel tarama ilanından {len(seri)} seri / {len(motor)} motor")
    return sonuc


def adaylari_degerlendir(piyasa, yollar):
    """Aday dosyalarını (arabam ya da sahibinden; detaylı ya da genel tarama) referans piyasaya göre puanlar.
    Adaylar veritabanına EKLENMEZ. (sonuçlar, bilgi) döner; bilgi: kaynaklar, türler, eşleşme sayıları."""
    from collections import Counter
    from .eslestir import Eslestirici
    sonuclar, bilgi = [], {"kaynak": set(), "tur": set(), "eslesme": Counter(), "okunamayan": 0}
    eslestirici, duzeltme = None, None
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
                if duzeltme is None:
                    duzeltme = sahibinden_duzeltmesi(piyasa, eslestirici)
                eslestirici.eslestir(r)
                bilgi["eslesme"][r["eslesme"]] += 1
                if r["eslesme"] in ("paket", "motor", "seri"):
                    r["site_duzeltme"] = duzeltme.get((r["marka"], r["seri"], r.get("motor")),
                                                      duzeltme.get((r["marka"], r["seri"]), 0.0))
            sonuclar.append(piyasa.degerlendir(r))
    sonuclar.sort(key=lambda s: -s["puan"])
    return _tekille(sonuclar), bilgi


def onceki_detaylar():
    """Daha önce detaylı taranmış sahibinden ve arabam ilanları: {ilan_id: fiyat} (veri/adaylar/*-ilanlar-*)."""
    from .okuyucu import sayi
    fiyatlar = {}
    yollar = sorted(ADAYLAR.glob("sahibinden-ilanlar-*.json*")) + sorted(ADAYLAR.glob("arabam-ilanlar-*.json*"))
    for yol in sorted(yollar, key=lambda y: y.name.split("-ilanlar-")[1]):   # tarih sırası: son görülen fiyat kalır
        try:
            with lzma.open(yol) if yol.suffix == ".xz" else open(yol, "rb") as f:
                d = json.load(f)
        except Exception:
            continue
        for x in d.get("ilanlar") or []:
            g = x.get("genel_bilgiler") or {}
            if g.get("ilan_id") and g.get("fiyat"):
                fiyatlar[str(g["ilan_id"])] = sayi(g["fiyat"])
    return fiyatlar


def sahibinden_bilinen_araclar():
    """Önceki sahibinden raporlarındaki (ön eleme + detay) araçlar: {(marka, seri, model, yil): [(km, fiyat), ...]}.
    Aynı araç arabam'da da ilandaysa iki kez taranmasın diye kullanılır."""
    from collections import defaultdict
    raporlar = KOK / "raporlar"
    bilinen = defaultdict(list)
    for yol in sorted(raporlar.glob("sahibinden-*.json")):
        try:
            for x in json.load(open(yol, encoding="utf-8")):
                if x.get("km") is not None and x.get("fiyat"):
                    bilinen[(x.get("marka"), x.get("seri"), x.get("model"), x.get("yil"))].append((x["km"], x["fiyat"]))
        except Exception:
            continue
    return bilinen


def ayni_arac_var(bilinen, r, km_tol=600, fiyat_tol=0.025):
    """r'nin (arabam ilanı) sahibinden'de aynı marka/seri/yıl, ~aynı km ve ~aynı fiyatla görülüp görülmediği."""
    for km, fiyat in bilinen.get((r["marka"], r["seri"], r["model"], r["yil"]), ()):
        if abs(km - r["km"]) <= km_tol and abs(fiyat - r["fiyat"]) <= fiyat_tol * r["fiyat"]:
            return True
    return False


def sahibinden_mi(yol):
    """Dosya sahibinden taraması mı? (sahibinden dosyaları referans veritabanına eklenmez)"""
    try:
        meta, satirlar = dosya_oku(yol)
    except Exception:
        return False
    return meta["kaynak"] == "sahibinden"
