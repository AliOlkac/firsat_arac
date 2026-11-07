"""İlanları piyasa modeline göre değerlendirir: adil fiyat, fırsat %, benzer ilanlar, 100 üzerinden puan."""
import math
from collections import defaultdict
from datetime import date

import numpy as np

from . import ayarlar as A
from .model import FiyatModeli


class Piyasa:
    """Referans piyasa: ilanlar + kurulmuş fiyat modeli + emsal arama dizini."""

    def __init__(self, satirlar, model=None):
        self.satirlar = [r for r in satirlar if r.get("yil") and r.get("km") is not None and r.get("fiyat")]
        self.model = model or FiyatModeli().kur(self.satirlar)
        m = self.model
        self.oof = {r["ilan_id"]: float(v) for r, v in zip(self.satirlar, m.oof)}
        self.tam = {r["ilan_id"]: m.log_tahmin(r) for r in self.satirlar}
        self.icerde = {r["ilan_id"]: bool(v) for r, v in zip(self.satirlar, m.icerde)}
        self.dizin = defaultdict(list)
        for r in self.satirlar:
            self.dizin[(r["marka"], r["seri"])].append(r)
        self.seri_sayisi = {k: len(v) for k, v in self.dizin.items()}
        self.bugun = max((r.get("son_gorulme") or "") for r in self.satirlar) or date.today().isoformat()

    # ---- emsaller ----------------------------------------------------------
    def emsaller(self, r, lp_hedef, adet=6):
        """Aynı seri/motor, ±1 yıl, ±35 bin km ilanlar; fiyatları hedef araca göre (km, yıl, hasar, paket) uyarlanır."""
        aday = []
        for c in self.dizin.get((r["marka"], r["seri"]), []):
            if c["ilan_id"] == r["ilan_id"] or not self.icerde.get(c["ilan_id"], True):
                continue
            if c["motor"] != r["motor"] or abs(c["yil"] - r["yil"]) > 1 or abs(c["km"] - r["km"]) > 35_000:
                continue
            uzaklik = (0 if c["model"] == r["model"] else 1.0) + abs(c["yil"] - r["yil"]) * 0.8 \
                + abs(c["km"] - r["km"]) / 25_000 + 0.3 * abs((c["n_boya"] + c["n_degisen"]) - (r["n_boya"] + r["n_degisen"]))
            uyarlanmis = c["fiyat"] * math.exp(lp_hedef - self.tam[c["ilan_id"]])
            aday.append((uzaklik, c, uyarlanmis))
        aday.sort(key=lambda t: t[0])
        return aday[:adet]

    # ---- tek ilan ----------------------------------------------------------
    def degerlendir(self, r):
        m = self.model
        seri = f"{r['marka']}|{r['seri']}"
        referansta = r["ilan_id"] in self.oof
        lp_ham = self.oof[r["ilan_id"]] if referansta else m.log_tahmin(r)
        lp_tam = self.tam.get(r["ilan_id"]) or m.log_tahmin(r)
        lp = lp_ham
        konum = m.penceredeki_konum(lp, r.get("kategori"))        # adil fiyat referans penceresinin dışındaysa tahmin daha belirsiz
        adil = math.exp(lp)
        firsat_model = 1 - r["fiyat"] / adil
        ems = self.emsaller(r, lp_tam)
        ems_fiyat = float(np.median([u for _, _, u in ems])) if len(ems) >= 3 else None
        firsat = firsat_model
        if ems_fiyat and len(ems) >= 4:
            # temkinli: gerçek emsaller aracın ucuz olduğunu desteklemiyorsa fırsatı emsallere göre sınırla
            firsat = min(firsat_model, (1 - r["fiyat"] / ems_fiyat) + 0.03)
        adil = r["fiyat"] / (1 - firsat)

        # güven: emsal yoğunluğu, serinin fiyat tutarlılığı, pencere dışı tahmin
        n_benzer = m.sayilar["motoryil"].get(f"{seri}|{r['motor']}|{r['yil']}", 0)
        sapma = m.seri_sapma.get(seri, m.sigma)
        g1 = min(1.0, n_benzer / 15)
        g2 = min(1.0, m.sigma / sapma)
        g3 = math.exp(-abs(konum) / 2.5)
        g4 = 1.0 if m.pencerede_mi(r["fiyat"], r.get("kategori")) else 0.75
        g0 = min(1.0, self.seri_sayisi.get((r["marka"], r["seri"]), 0) / 30)
        guven = (0.25 + 0.75 * (0.6 * g1 + 0.4 * g2)) * (0.5 + 0.5 * g0) * (0.4 + 0.6 * g3) * g4
        if r.get("eslesme"):          # sahibinden ilanı: arabam adlarına eşleşme kalitesi
            from .eslestir import GUVEN_CARPANI
            guven *= GUVEN_CARPANI.get(r["eslesme"], 0.5)

        # 18 ay sonra: bireysel satış fiyat seviyesinde, bugünkü TL ile
        oran = m.gelecek_orani(r, A.ELDE_TUTMA_AY, A.YILLIK_KM)
        sahibinden_fark = m.log_tahmin(r, kimden="Sahibinden") - m.log_tahmin(r)
        satis = adil * math.exp(sahibinden_fark) * oran
        masraf = A.MASRAF_SABIT + A.MASRAF_ORAN * r["fiyat"]
        net = satis - r["fiyat"] - masraf

        # Yarın satsam: bireysel satıcı olarak, hızlı satmak için piyasanın biraz altına fiyatlayıp
        satis_yarin = adil * math.exp(sahibinden_fark) * (1 - A.HIZLI_SATIS_ISKONTO)
        net_yarin = satis_yarin - r["fiyat"] - masraf
        pazarlik = r["fiyat"] * A.ALIS_PAZARLIK.get(r.get("kimden"), 0.02)

        sonuc = dict(r)
        sonuc.update(satis_yarin=satis_yarin, net_yarin=net_yarin, net_yarin_oran=net_yarin / r["fiyat"],
                     pazarlik=pazarlik, sahibinden_fark=sahibinden_fark, masraf=masraf)
        sonuc.update(adil=adil, firsat=firsat, guven=guven, emsal_fiyat=ems_fiyat, n_benzer=n_benzer,
                     pencere_konum=konum, firsat_model=firsat_model, gelecek_oran=oran, satis_18ay=satis, net_18ay=net,
                     net_18ay_oran=net / r["fiyat"], referansta=referansta,
                     emsal_listesi=[{"ilan_id": c["ilan_id"], "url": c["url"], "model": c["model"], "yil": c["yil"],
                                     "km": c["km"], "fiyat": c["fiyat"], "uyarlanmis": round(u),
                                     "hasar": hasar_kisa(c), "kimden": c["kimden"]} for _, c, u in ems])
        sonuc.update(puanla(sonuc, self))
        return sonuc


def hasar_kisa(r):
    if r.get("boya_bilinmiyor"):
        return "boya bilgisi yok"
    p = []
    if r["n_degisen"]:
        p.append(f"{r['n_degisen']} değişen")
    if r["n_boya"]:
        p.append(f"{r['n_boya']} boyalı")
    if r["n_lokal"]:
        p.append(f"{r['n_lokal']} lokal")
    return ", ".join(p) if p else "boyasız"


def _ilan_gun(r, bugun):
    try:
        return (date.fromisoformat(bugun[:10]) - date.fromisoformat(r["ilan_tarihi"])).days
    except Exception:
        return None


def puanla(s, piyasa):
    """100 üzerinden puan ve bileşenleri. s: degerlendir() sonucu."""
    notlar, uyarilar = [], []
    # A. Fiyat avantajı
    etkin = s["firsat"] * s["guven"]
    p_fiyat = A.P_FIYAT * (min(1.0, max(0.0, etkin) / A.FIYAT_TAVAN) ** 0.85)
    if s["firsat"] > A.SUPHELI_UCUZ:
        uyarilar.append(f"Piyasanın %{s['firsat']*100:.0f} altında: dolandırıcılık, gizli hasar ya da hatalı fiyat olabilir, önce doğrula")
        p_fiyat *= 0.6
    if s.get("pesinat_gecer") and s["firsat"] > 0.08:
        uyarilar.append("Açıklamada peşinat/senet/kapora geçiyor: ilan fiyatı toplam fiyat olmayabilir")
        p_fiyat *= 0.8

    # B. Kondisyon
    tl, tb, td = s["tampon_lokal"], s["tampon_boya"], s["tampon_degisen"]
    kus = (2.5 * (s["n_lokal"] - tl) + 1.0 * tl + 4.0 * (s["n_boya"] - tb) + 1.5 * tb
           + 7.0 * (s["n_degisen"] - td) + 2.5 * td + 5.0 * s["tavan_boya"] + 10.0 * s["tavan_degisen"]
           + 3.0 * s["kaput_degisen"])
    if s["tramer_durum"] == "tutar" and s.get("tramer_tl"):
        kus += min(8.0, 120 * s["tramer_tl"] / s["fiyat"])
    elif s["tramer_durum"] == "belirsiz":
        kus += 2.0
        notlar.append("Tramer tutarı belirtilmemiş: sor / sorgula")
    if s["boya_bilinmiyor"]:
        kus += 7.0
        notlar.append("Boya-değişen bilgisi girilmemiş: ekspertizsiz alma")
    elif s["n_belirsiz"]:
        kus += 1.0
    if s["tavan_degisen"] or s["tavan_boya"]:
        uyarilar.append("Tavan boyalı/değişen: ciddi kaza işareti olabilir")
    p_kondisyon = max(0.0, A.P_KONDISYON - kus) + (1.0 if s.get("garanti") == 1 else 0.0)
    p_kondisyon = min(A.P_KONDISYON, p_kondisyon)

    # C. Satılabilirlik
    talep_marka = A.MARKA_TALEP.get(s["marka"], 0.6) * (A.ELEKTRIK_CARPAN if s["yakit"] == "Elektrik" else 1.0)
    derinlik = math.log1p(piyasa.seri_sayisi.get((s["marka"], s["seri"]), 0)) / math.log1p(1500)
    talep = 0.55 * talep_marka + 0.45 * min(1.0, derinlik)
    renk = s.get("renk") or ""
    p_renk = 3.0 if renk in A.RENK_POPULER else (0.5 if renk in A.RENK_ZOR else 2.0)
    km_satis = (s["km"] or 0) + A.YILLIK_KM * A.ELDE_TUTMA_AY / 12
    p_km = 4.0 if km_satis <= 60_000 else 3.2 if km_satis <= 100_000 else 2.2 if km_satis <= 130_000 else 1.2 if km_satis <= 160_000 else 0.3
    p_yakit = 3.0 * A.YAKIT_PUAN.get(s["yakit"], 0.7)
    if s.get("sanziman") in A.SORUNLU_SANZIMAN:
        p_yakit = max(0.0, p_yakit - 2.0)
        uyarilar.append(A.SORUNLU_SANZIMAN[s["sanziman"]])
    p_satis = 10.0 * talep + p_renk + p_km + p_yakit
    if s["yakit"] == "Elektrik":
        notlar.append("Elektrikli: ikinci elde batarya ve fiyat düşüşü riski")

    # D. Değer koruma (18 ay sonra reel değer oranı)
    p_deger = A.P_DEGER_KORUMA * min(1.0, max(0.0, (s["gelecek_oran"] - A.DEGER_ALT) / (A.DEGER_UST - A.DEGER_ALT)))

    # Açıklama riskleri ve olumlular
    ceza = min(40.0, sum(c for _, _, c in s.get("riskler") or []))
    for _, aciklama, c in s.get("riskler") or []:
        (uyarilar if c >= 10 else notlar).append(aciklama)
    bonus = min(2.0, sum(1.0 for k, _ in (s.get("olumlu") or []) if k in ("ilk_sahip", "servis", "garaj")))
    for k, aciklama in s.get("olumlu") or []:
        notlar.append(aciklama)
    gun = _ilan_gun(s, piyasa.bugun)
    if gun is not None and gun >= 45:
        notlar.append(f"{gun} gündür yayında: pazarlık payı olabilir")
    if s["guven"] < 0.55:
        notlar.append("Emsal az / tahmin belirsiz: fiyatı elle de kontrol et")
    if s.get("eslesme") and s["eslesme"] != "paket":
        notlar.append({"motor": "arabam'da aynı paket yok, aynı motorlu araçlarla karşılaştırıldı",
                       "seri": "arabam'da aynı motor/paket bulunamadı, seri ortalamasıyla karşılaştırıldı",
                       "marka": "arabam'da bu seri yok: fiyat tahmini güvenilmez",
                       "yok": "arabam'da bu marka yok: fiyat tahmini güvenilmez"}[s["eslesme"]])
    if s.get("liste_satiri"):
        notlar.append("Genel tarama satırı: boya-değişen, tramer ve açıklama bilinmiyor; detaylı taramayla doğrula")

    toplam = max(0.0, min(100.0, p_fiyat + p_kondisyon + p_satis + p_deger - ceza + bonus))
    agir_risk = any(c >= 15 for _, _, c in s.get("riskler") or []) or s["firsat"] > A.SUPHELI_UCUZ

    def karar_ver(puan):
        if agir_risk:
            return "DİKKAT"
        return "GÜÇLÜ" if puan >= A.ESIK_GUCLU else "İNCELE" if puan >= A.ESIK_INCELE else "PAS"

    # Hızlı al-sat (yarın satsam) puanı: kâr 55 + satış hızı 25 + kondisyon 20
    etkin_firsat = max(0.0, s["firsat"]) * s["guven"]
    oran_e = math.exp(s["sahibinden_fark"]) * (1 - A.HIZLI_SATIS_ISKONTO) / (1 - etkin_firsat)
    net_e = oran_e - 1 - s["masraf"] / s["fiyat"]
    p_kar = A.PH_KAR * (min(1.0, max(0.0, net_e) / A.HIZLI_KAR_TAVAN) ** 0.85)
    if s["firsat"] > A.SUPHELI_UCUZ:
        p_kar *= 0.6
    if s.get("pesinat_gecer") and s["firsat"] > 0.08:
        p_kar *= 0.8
    km_simdi = s["km"] or 0
    h_km = 5.0 if km_simdi <= 60_000 else 4.0 if km_simdi <= 100_000 else 2.5 if km_simdi <= 130_000 else 1.2
    h_bant = 2.0 if s["fiyat"] <= 1_500_000 else 1.0 if s["fiyat"] <= 1_800_000 else 0.0   # ucuz bantta alıcı çok
    p_hiz = min(A.PH_HIZ, 12.0 * talep + p_renk + h_km + p_yakit + h_bant)
    toplam_h = max(0.0, min(100.0, p_kar + p_hiz + p_kondisyon - ceza + bonus))

    return {"puan": round(toplam, 1), "karar": karar_ver(toplam), "p_fiyat": p_fiyat, "p_kondisyon": p_kondisyon,
            "p_satis": p_satis, "p_deger": p_deger, "ceza": ceza, "bonus": bonus,
            "puan_hizli": round(toplam_h, 1), "karar_hizli": karar_ver(toplam_h), "p_kar": p_kar, "p_hiz": p_hiz,
            "net_etkin_oran": net_e,
            "notlar": notlar, "uyarilar": uyarilar, "ilan_gun": gun, "talep": talep}
