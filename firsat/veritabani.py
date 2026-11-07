"""Piyasa veritabanı (SQLite). Kaynak gerçek: veri/ham/*.json.xz dosyaları; veritabanı onlardan yeniden kurulabilir.

Tablolar
  goruntu       bir toplama günü (aynı gün gelen dosyalar tek görüntüdür) ve kapsadığı filtreler
  dosya         işlenmiş ham dosyalar (aynı dosya ikinci kez işlenmez)
  ilan          her ilanın son hali + ilk/son görülme, ilk/son fiyat, durum (aktif / kayboldu)
  fiyat_gecmisi ilan başına görüntü tarihindeki fiyat
"""
import json
import sqlite3
from datetime import timedelta
from pathlib import Path

from .okuyucu import dosya_oku

KOK = Path(__file__).resolve().parent.parent
HAM = KOK / "veri" / "ham"
DB_YOLU = KOK / "veri" / "piyasa.db"

ALANLAR = ["kaynak", "url", "baslik", "sehir", "ilce", "ilan_tarihi", "kimden", "foto", "kategori", "marka", "seri",
           "model", "motor", "yil", "km", "vites", "yakit", "kasa", "renk", "cekis", "sanziman", "hp", "cc", "segment",
           "garanti", "agir_hasar", "cam_tavan", "n_lokal", "n_boya", "n_degisen", "n_belirsiz", "boya_bilinmiyor",
           "tampon_lokal", "tampon_boya", "tampon_degisen", "tavan_boya", "tavan_degisen", "kaput_degisen",
           "tramer_durum", "tramer_tl", "tramer_kaynak", "pesinat_gecer", "aciklama"]
JSON_ALANLAR = ["parcalar", "riskler", "olumlu"]

SEMA = f"""
CREATE TABLE IF NOT EXISTS goruntu (tarih TEXT PRIMARY KEY, kapsamlar TEXT, ilan_sayisi INTEGER);
CREATE TABLE IF NOT EXISTS dosya (ad TEXT PRIMARY KEY, toplanma TEXT, goruntu TEXT, ilan_sayisi INTEGER);
CREATE TABLE IF NOT EXISTS ilan (
  ilan_id TEXT PRIMARY KEY, {", ".join(a + " " for a in ALANLAR + JSON_ALANLAR)},
  ilk_gorulme TEXT, son_gorulme TEXT, ilk_fiyat INTEGER, son_fiyat INTEGER, fiyat_degisim_sayisi INTEGER DEFAULT 0,
  durum TEXT DEFAULT 'aktif', kaybolma_tarihi TEXT);
CREATE TABLE IF NOT EXISTS fiyat_gecmisi (ilan_id TEXT, tarih TEXT, fiyat INTEGER, PRIMARY KEY (ilan_id, tarih));
CREATE INDEX IF NOT EXISTS ix_ilan_seri ON ilan (marka, seri);
"""


def baglan(yol=DB_YOLU):
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(yol))
    conn.row_factory = sqlite3.Row
    conn.executescript(SEMA)
    return conn


def _kapsiyor_mu(k, r):
    """Bu filtre bu ilanı (son fiyatıyla) görmeliydi mi?"""
    if not k.get("tamam", True) or k["kategori"] != r["kategori"]:
        return False
    f = r["son_fiyat"]
    if k.get("min_fiyat") and f < k["min_fiyat"]:
        return False
    if k.get("max_fiyat") and f > k["max_fiyat"]:
        return False
    if k.get("min_yil") and (r["yil"] or 0) < k["min_yil"]:
        return False
    if k.get("max_km") and (r["km"] or 0) > k["max_km"]:
        return False
    return True


def dosya_isle(conn, yol, sessiz=False):
    """Bir ham dosyayı veritabanına işler. Özet sözlüğü döner."""
    ad = Path(yol).name
    if conn.execute("SELECT 1 FROM dosya WHERE ad=?", (ad,)).fetchone():
        return {"dosya": ad, "atlandi": "zaten işlenmiş"}
    meta, satirlar = dosya_oku(yol)
    tarih = meta["toplanma"].date().isoformat()
    son = conn.execute("SELECT MAX(tarih) FROM goruntu").fetchone()[0]
    if son and tarih < son:
        # Eski görüntü: fiyat geçmişine eklenir ama ilanların son halini ve durumunu değiştirmez.
        eski = True
    else:
        eski = False
    yeni, guncel, fiyat_degisen = 0, 0, 0
    for r in satirlar:
        if not r["fiyat"] or not r["ilan_id"]:
            continue
        conn.execute("INSERT OR IGNORE INTO fiyat_gecmisi VALUES (?,?,?)", (r["ilan_id"], tarih, r["fiyat"]))
        mevcut = conn.execute("SELECT son_fiyat, son_gorulme, ilk_gorulme FROM ilan WHERE ilan_id=?",
                              (r["ilan_id"],)).fetchone()
        degerler = [r[a] if a != "ilan_tarihi" else (r[a].isoformat() if r[a] else None) for a in ALANLAR]
        degerler += [json.dumps(r[a], ensure_ascii=False) for a in JSON_ALANLAR]
        if mevcut is None:
            conn.execute(f"INSERT INTO ilan (ilan_id, {', '.join(ALANLAR + JSON_ALANLAR)}, ilk_gorulme, son_gorulme, "
                         f"ilk_fiyat, son_fiyat) VALUES ({', '.join('?' * (len(ALANLAR) + len(JSON_ALANLAR) + 5))})",
                         [r["ilan_id"]] + degerler + [tarih, tarih, r["fiyat"], r["fiyat"]])
            yeni += 1
        elif not eski and tarih >= mevcut["son_gorulme"]:
            degisti = int(mevcut["son_fiyat"] != r["fiyat"])
            fiyat_degisen += degisti
            conn.execute(f"UPDATE ilan SET {', '.join(a + '=?' for a in ALANLAR + JSON_ALANLAR)}, son_gorulme=?, "
                         f"son_fiyat=?, fiyat_degisim_sayisi=fiyat_degisim_sayisi+?, durum='aktif', kaybolma_tarihi=NULL "
                         f"WHERE ilan_id=?", degerler + [tarih, r["fiyat"], degisti, r["ilan_id"]])
            guncel += 1
        elif tarih < mevcut["ilk_gorulme"]:
            conn.execute("UPDATE ilan SET ilk_gorulme=?, ilk_fiyat=? WHERE ilan_id=?", (tarih, r["fiyat"], r["ilan_id"]))
    # Görüntü kaydı (aynı gün birden çok dosya kapsamları birleştirir)
    g = conn.execute("SELECT kapsamlar, ilan_sayisi FROM goruntu WHERE tarih=?", (tarih,)).fetchone()
    kapsamlar = (json.loads(g["kapsamlar"]) if g else []) + meta["kapsamlar"]
    conn.execute("INSERT OR REPLACE INTO goruntu VALUES (?,?,?)",
                 (tarih, json.dumps(kapsamlar, ensure_ascii=False), (g["ilan_sayisi"] if g else 0) + len(satirlar)))
    conn.execute("INSERT INTO dosya VALUES (?,?,?,?)", (ad, meta["toplanma"].isoformat(), tarih, len(satirlar)))
    conn.commit()
    return {"dosya": ad, "goruntu": tarih, "ilan": len(satirlar), "yeni": yeni, "guncellenen": guncel,
            "fiyat_degisen": fiyat_degisen, "eski_goruntu": eski}


def kaybolanlari_isaretle(conn):
    """Son görüntünün kapsadığı ama o görüntüde görünmeyen aktif ilanları 'kayboldu' yapar (muhtemelen satıldı)."""
    son = conn.execute("SELECT tarih, kapsamlar FROM goruntu ORDER BY tarih DESC LIMIT 1").fetchone()
    if son is None:
        return 0
    kapsamlar = json.loads(son["kapsamlar"])
    sayi = 0
    for r in conn.execute("SELECT ilan_id, kategori, son_fiyat, yil, km FROM ilan WHERE durum='aktif' AND son_gorulme<?",
                          (son["tarih"],)).fetchall():
        if any(_kapsiyor_mu(k, r) for k in kapsamlar):
            conn.execute("UPDATE ilan SET durum='kayboldu', kaybolma_tarihi=? WHERE ilan_id=?", (son["tarih"], r["ilan_id"]))
            sayi += 1
    conn.commit()
    return sayi


def ham_dosyalar():
    """Ham dosyalar, toplanma sırasına göre (dosya adındaki tarih-saat)."""
    return sorted(HAM.glob("*.json*"), key=lambda p: p.name.split("coklu-")[-1] if "coklu-" in p.name else p.name)


def kur(yeniden=False, sessiz=False):
    """Veritabanını ham dosyalardan kurar ya da eksik dosyaları işler."""
    if yeniden and DB_YOLU.exists():
        DB_YOLU.unlink()
    conn = baglan()
    ozetler = []
    for f in ham_dosyalar():
        o = dosya_isle(conn, f)
        if "atlandi" not in o:
            ozetler.append(o)
            if not sessiz:
                print(f"  + {o['dosya']}: {o['ilan']} ilan, {o['yeni']} yeni, {o['fiyat_degisen']} fiyat değişimi")
    k = kaybolanlari_isaretle(conn) if ozetler else 0
    if ozetler and not sessiz:
        print(f"  Kaybolan (muhtemelen satıldı) olarak işaretlenen: {k}")
    return conn, ozetler


def aktif_ilanlar(conn, gun=21):
    """Model için: son görüntüden en çok `gun` gün önce görülmüş aktif ilanlar."""
    son = conn.execute("SELECT MAX(tarih) FROM goruntu").fetchone()[0]
    if son is None:
        return []
    from datetime import date
    sinir = (date.fromisoformat(son) - timedelta(days=gun)).isoformat()
    return [satir_sozluk(r) for r in conn.execute(
        "SELECT * FROM ilan WHERE durum='aktif' AND son_gorulme>=?", (sinir,))]


def satir_sozluk(r):
    d = dict(r)
    for a in JSON_ALANLAR:
        d[a] = json.loads(d[a]) if d.get(a) else ([] if a != "parcalar" else {})
    d["fiyat"] = d.get("son_fiyat") or d.get("fiyat")
    return d
