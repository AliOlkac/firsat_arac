"""Fiyat modeli: log(fiyat) için hiyerarşik ridge regresyon (marka > seri > motor > paket, seri x yıl, seri x km).

Neden bu model?
  * 27 bin ilanın çoğu seride az örnek var; ridge küçük grupları üst gruba (seri, marka) doğru büzer.
  * Her katsayı okunabilir: "2 boyalı parça fiyatı %x düşürüyor" gibi.
  * Saniyeler içinde yeniden kurulur, ek kütüphane gerektirmez (yalnızca numpy).

Kesik regresyon: referans tarama yalnızca belli bir fiyat aralığını (ör. 1.25-2.0 M TL) içeriyor.
Aralığın kenarına yakın gruplarda ucuz (ya da pahalı) emsaller listede olmadığı için sıradan regresyon
ortalamayı pencerenin içine doğru çeker ve yıl/km etkilerini olduğundan küçük gösterir. Bu yüzden model,
gözlemlerin [alt, üst] arasına düştüğü bilinen kesik normal olabilirlik ile (ridge cezalı) kurulur.
"""
import math
import pickle
from collections import Counter, defaultdict

import numpy as np

KM_DUGUM = (0, 30_000, 60_000, 100_000, 140_000)
# Ön dağılım ölçekleri (log fiyat cinsinden beklenen etki büyüklüğü). ceza = sigma^2 / tau^2
TAU = {"marka": 0.30, "seri": 0.25, "motor": 0.10, "model": 0.06, "yil": 0.40, "seriyil": 0.045, "motoryil": 0.03,
       "seriyas": 0.10, "serikm": 0.06, "kasa": 0.06, "yakit": 0.08, "vites": 0.05, "sanz": 0.05, "cekis": 0.06,
       "renk": 0.03, "kimden": 0.05, "garanti": 0.04, "kategori": 0.05}
SIGMA0 = 0.07
POPULER_RENK = {"Beyaz", "Gri", "Siyah", "Füme", "Gri (Gümüş)", "Gri (Metalik)", "Gri (Titanyum)", "Gümüş"}


def renk_grubu(renk):
    if not renk:
        return "bilinmiyor"
    if renk in POPULER_RENK:
        return renk if renk in ("Beyaz", "Siyah") else "gri"
    return renk.split(" (")[0]


def ozellikler(r, ref_yil, kimden=None):
    """İlanın model özellikleri: [(sütun adı, değer), ...]. kimden verilirse satıcı tipi onunla değiştirilir."""
    seri = f"{r['marka']}|{r['seri']}"
    motor = f"{seri}|{r['motor']}"
    yas = ref_yil - (r["yil"] or ref_yil)
    km = min(max(r["km"] or 0, 0), 400_000)
    f = [("marka:" + r["marka"], 1.0), ("seri:" + seri, 1.0), ("motor:" + motor, 1.0),
         ("model:" + f"{seri}|{r['model']}", 1.0), ("yil:%d" % r["yil"], 1.0), ("seriyil:%s|%d" % (seri, r["yil"]), 1.0),
         ("motoryil:%s|%d" % (motor, r["yil"]), 1.0),
         ("kasa:%s" % r.get("kasa"), 1.0), ("yakit:%s" % r.get("yakit"), 1.0), ("vites:%s" % r.get("vites"), 1.0),
         ("sanz:%s" % (r.get("sanziman") or "-"), 1.0), ("cekis:%s" % r.get("cekis"), 1.0),
         ("renk:" + renk_grubu(r.get("renk")), 1.0), ("kimden:" + (kimden or r.get("kimden") or "?"), 1.0),
         ("garanti:%s" % r.get("garanti"), 1.0), ("kategori:%s" % r.get("kategori"), 1.0),
         ("seriyas:" + seri, yas / 5.0), ("serikm:" + seri, km / 100_000)]
    for d in KM_DUGUM:
        f.append(("n:km%d" % (d // 1000), max(0, km - d) / 100_000))
    f.append(("n:hp", math.log(r["hp"] / 120.0)) if r.get("hp") else ("n:hp_yok", 1.0))
    tl, tb, td = r.get("tampon_lokal", 0), r.get("tampon_boya", 0), r.get("tampon_degisen", 0)
    f += [("n:lokal", r["n_lokal"] - tl), ("n:lokal_tampon", tl), ("n:boya", r["n_boya"] - tb), ("n:boya_tampon", tb),
          ("n:degisen", r["n_degisen"] - td), ("n:degisen_tampon", td), ("n:tavan_boya", r["tavan_boya"]),
          ("n:tavan_degisen", r["tavan_degisen"]), ("n:kaput_degisen", r["kaput_degisen"]),
          ("n:boya_bilinmiyor", r["boya_bilinmiyor"]),
          ("n:kismi_belirsiz", float(r["n_belirsiz"] > 0 and not r["boya_bilinmiyor"])),
          ("n:tramer_yok", float(r["tramer_durum"] == "yok")), ("n:tramer_belirsiz", float(r["tramer_durum"] == "belirsiz")),
          ("n:tramer_log", math.log1p((r.get("tramer_tl") or 0) / 10_000)),
          ("n:agir_bilinmiyor", float(r.get("agir_hasar") is None)), ("n:cam_tavan", float(r.get("cam_tavan") or 0))]
    return [(a, v) for a, v in f if v != 0.0]


def _tur(ad):
    return "n" if ad.startswith("n:") else ad.split(":", 1)[0]


_ERF = np.frompyfunc(math.erf, 1, 1)


def _Phi(x):
    return 0.5 * (1.0 + _ERF(x / math.sqrt(2.0)).astype(float))


def _phi(x):
    return np.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def kesik_kayma(mu, s, a, b):
    """E[y | a<y<b] - mu  (kesik normalde ortalamanın kayması), vektörel."""
    al = np.clip((a - mu) / s, -8.0, 8.0)
    be = np.clip((b - mu) / s, -8.0, 8.0)
    z = np.maximum(_Phi(be) - _Phi(al), 1e-12)
    return s * (_phi(al) - _phi(be)) / z


class FiyatModeli:
    def __init__(self, tau_carpan=1.0):
        self.tau_carpan = tau_carpan

    # ---- kurulum -------------------------------------------------------
    def _sutunlar(self, satir_ozellik):
        sayac = Counter(a for f in satir_ozellik for a, _ in f)
        esik = {"motoryil": 6, "seriyil": 3}
        self.kolonlar = ["_sabit"] + sorted(a for a, n in sayac.items() if n >= esik.get(_tur(a), 1))
        self.idx = {a: i for i, a in enumerate(self.kolonlar)}
        ceza = np.zeros(len(self.kolonlar))
        for a, i in self.idx.items():
            t = _tur(a)
            if a == "_sabit":
                continue
            ceza[i] = 1e-3 if t == "n" else SIGMA0 ** 2 / (TAU[t] * self.tau_carpan) ** 2
        self.ceza = ceza

    def _seyrek(self, ozellik_listesi):
        I, V = [], []
        for f in ozellik_listesi:
            ii, vv = [0], [1.0]
            for a, v in f:
                j = self.idx.get(a)
                if j is not None:
                    ii.append(j)
                    vv.append(v)
            I.append(np.array(ii))
            V.append(np.array(vv))
        return I, V

    def _normal(self, I, V, y, secim):
        n = len(self.kolonlar)
        pi, pv, xi, xv = [], [], [], []
        for k in np.nonzero(secim)[0]:
            ii, vv = I[k], V[k]
            pi.append((ii[:, None] * n + ii[None, :]).ravel())
            pv.append(np.outer(vv, vv).ravel())
            xi.append(ii)
            xv.append(vv * y[k])
        XtX = np.bincount(np.concatenate(pi), weights=np.concatenate(pv), minlength=n * n).reshape(n, n)
        Xty = np.bincount(np.concatenate(xi), weights=np.concatenate(xv), minlength=n)
        return XtX, Xty

    def _coz(self, XtX, Xty):
        A = XtX + np.diag(self.ceza)
        return np.linalg.solve(A, Xty)

    @staticmethod
    def _tahmin_seyrek(b, I, V):
        return np.array([float(b[ii] @ vv) for ii, vv in zip(I, V)])

    def _duz(self, I, V):
        R = np.concatenate([np.full(len(ii), k) for k, ii in enumerate(I)])
        return R, np.concatenate(I), np.concatenate(V)

    def _kesik_coz(self, XtX, secim, y, duz, b0, s):
        """Kesik normal olabilirlik (ridge cezalı) için sabit nokta yinelemesi:
        b = (X'X + P)^-1 X'(y - kayma(mu)),  mu = Xb. Kayma: gözlenen ortalama ile gerçek ortalama farkı."""
        R, C, V = duz
        n, N = len(self.kolonlar), len(y)
        Ainv = np.linalg.inv(XtX + np.diag(self.ceza))
        w = secim.astype(float)
        b = b0.copy()
        mu = np.bincount(R, weights=b[C] * V, minlength=N)
        for _ in range(60):
            yadj = y - kesik_kayma(mu, s, self.alt, self.ust)
            Xty = np.bincount(C, weights=V * (yadj * w)[R], minlength=n)
            b_yeni = Ainv @ Xty
            fark = np.max(np.abs(b_yeni - b))
            b = b_yeni
            mu = np.bincount(R, weights=b[C] * V, minlength=N)
            if fark < 2e-5:
                break
        return b, mu

    def kur(self, satirlar, kat=5, tohum=7, pencere=None):
        """Modeli kurar; her ilan için kendisi hariç tutularak (out-of-fold) tahmin de üretir.
        pencere: {kategori: (alt_fiyat, ust_fiyat)} referans taramanın fiyat aralığı (yoksa verideki en düşük/yüksek)."""
        self.ref_yil = max(r["yil"] for r in satirlar)
        fiyat = np.array([r["fiyat"] for r in satirlar], float)
        # Fiyat penceresi kategori başına (ör. otomobil ve SUV taraması farklı aralıklarda olabilir)
        pencere = pencere or {}
        self.pencere = {}
        for kg in {r.get("kategori") for r in satirlar}:
            f = fiyat[[r.get("kategori") == kg for r in satirlar]]
            lo, hi = pencere.get(kg, (None, None))
            self.pencere[kg] = (math.log(min(lo or f.min(), f.min())) - 0.002, math.log(max(hi or f.max(), f.max())) + 0.002)
        self.alt = np.array([self.pencere[r.get("kategori")][0] for r in satirlar])
        self.ust = np.array([self.pencere[r.get("kategori")][1] for r in satirlar])
        y = np.log(fiyat)
        oz = [ozellikler(r, self.ref_yil) for r in satirlar]
        self._sutunlar(oz)
        I, V = self._seyrek(oz)
        duz = self._duz(I, V)
        R, C, Vv = duz
        tum = np.ones(len(y), bool)
        XtX, Xty = self._normal(I, V, y, tum)
        # 1) sıradan ridge: başlangıç ve dağılım genişliği (pencerenin ortasından)
        b = self._coz(XtX, Xty)
        m0 = np.bincount(R, weights=b[C] * Vv, minlength=len(y))
        e0 = y - m0
        orta = (m0 > self.alt + 0.12) & (m0 < self.ust - 0.12)
        self.sigma = float(1.4826 * np.median(np.abs(e0[orta] - np.median(e0[orta])))) * 1.1
        # 2) kesik regresyon + uç değer temizliği
        icerde = tum
        for tur in range(2):
            b, mu = self._kesik_coz(XtX, icerde, y, duz, b, self.sigma)
            beklenen = mu + kesik_kayma(mu, self.sigma, self.alt, self.ust)   # gözlenen fiyatın beklenen değeri
            artik = y - beklenen
            mad = 1.4826 * np.median(np.abs(artik[icerde] - np.median(artik[icerde])))
            yeni = np.abs(artik - np.median(artik[icerde])) <= 3.5 * mad
            if tur == 1 or (yeni == icerde).all():
                break
            icerde = yeni
            XtX, _ = self._normal(I, V, y, icerde)
        self.b = b
        self.icerde = icerde
        # 3) out-of-fold tahmin: her ilan, kendisinin olmadığı modelle tahmin edilir
        rng = np.random.default_rng(tohum)
        kat_no = rng.integers(0, kat, len(y))
        oof = np.zeros(len(y))
        for k in range(kat):
            secim = icerde & (kat_no != k)
            XtXk, _ = self._normal(I, V, y, icerde & (kat_no == k))
            _, mu_k = self._kesik_coz(XtX - XtXk, secim, y, duz, b, self.sigma)
            oof[kat_no == k] = mu_k[kat_no == k]
        self.oof = oof
        self.y = y
        artik = y - (oof + kesik_kayma(oof, self.sigma, self.alt, self.ust))
        self._seri_istatistik(satirlar, artik, icerde)
        self._yil_egrileri(satirlar)
        return self

    def _seri_istatistik(self, satirlar, artik, icerde):
        g = defaultdict(list)
        for r, e, ok in zip(satirlar, artik, icerde):
            if ok:
                g[f"{r['marka']}|{r['seri']}"].append(e)
        self.seri_sapma = {}
        for s, e in g.items():
            e = np.array(e)
            # az örnekli seride genel sapmaya doğru büz
            n = len(e)
            ss = float(1.4826 * np.median(np.abs(e - np.median(e)))) if n >= 5 else self.sigma
            self.seri_sapma[s] = (n * ss + 20 * self.sigma) / (n + 20)
        self.sayilar = {
            "seri": Counter(f"{r['marka']}|{r['seri']}" for r in satirlar),
            "model": Counter(f"{r['marka']}|{r['seri']}|{r['model']}" for r in satirlar),
            "motoryil": Counter(f"{r['marka']}|{r['seri']}|{r['motor']}|{r['yil']}" for r in satirlar),
            "seriyil": Counter(f"{r['marka']}|{r['seri']}|{r['yil']}" for r in satirlar),
        }

    def _k(self, ad):
        i = self.idx.get(ad)
        return float(self.b[i]) if i is not None else 0.0

    def _yil_egrileri(self, satirlar):
        """Her seri için yıl -> log değer eğrisi (genel yıl etkisi + seri sapması + seri yaş eğimi)."""
        yillar = sorted({r["yil"] for r in satirlar})
        self.yillar = yillar
        genel = {y: self._k("yil:%d" % y) for y in yillar}
        self.genel_yil = genel
        seri_yillar = defaultdict(set)
        for r in satirlar:
            seri_yillar[f"{r['marka']}|{r['seri']}"].add(r["yil"])
        self.seri_yillar = {s: sorted(v) for s, v in seri_yillar.items()}

    def yil_degeri(self, seri, yil):
        """Serinin `yil` model aracının (diğer her şey sabitken) log değeri. Veri dışı yıllar için doğrusal uzatma."""
        egim_s = self._k("seriyas:" + seri) / 5.0

        def ic(y):
            return self.genel_yil.get(y, 0.0) + self._k("seriyil:%s|%d" % (seri, y)) + egim_s * (self.ref_yil - y)
        mevcut = self.seri_yillar.get(seri) or self.yillar
        lo, hi = min(mevcut), max(mevcut)
        if lo <= yil <= hi and yil in self.genel_yil:
            return ic(yil)
        # yıllık değişim: serinin gözlenen yıllarındaki ortalama eğim (en az 2 yıl), yoksa genel eğim
        if hi > lo:
            egim = (ic(hi) - ic(lo)) / (hi - lo)
        else:
            gy = self.yillar
            egim = (self.genel_yil[gy[-1]] - self.genel_yil[gy[0]]) / max(1, gy[-1] - gy[0]) - egim_s
        egim = min(max(egim, 0.02), 0.20)
        if yil < lo:
            return ic(lo) - egim * (lo - yil)
        return ic(hi) + egim * (yil - hi)

    def km_degeri(self, seri, km):
        km = min(max(km, 0), 400_000)
        v = sum(self._k("n:km%d" % (d // 1000)) * max(0, km - d) / 100_000 for d in KM_DUGUM)
        return v + self._k("serikm:" + seri) * km / 100_000

    # ---- tahmin ----------------------------------------------------------
    def log_tahmin(self, r, kimden=None):
        lp = float(self.b[0])
        for a, v in ozellikler(r, self.ref_yil, kimden):
            i = self.idx.get(a)
            if i is not None:
                lp += float(self.b[i]) * v
            elif a.startswith("yil:"):
                # eğitimde olmayan model yılı: genel yıl eğrisinden uzat
                seri = f"{r['marka']}|{r['seri']}"
                # seri yaş eğimi zaten eklendi; eğrinin geri kalanı (genel yıl + seri sapması) eklenir
                lp += self.yil_degeri(seri, r["yil"]) - self._k("seriyas:" + seri) / 5.0 * (self.ref_yil - r["yil"]) \
                    - self._k("seriyil:%s|%d" % (seri, r["yil"]))
        return lp

    def penceredeki_konum(self, lp, kategori=None):
        """Tahminin referans fiyat penceresine göre konumu (sigma cinsinden); >0 pencerenin üstü, <0 altı."""
        alt, ust = self.pencere.get(kategori) or (min(v[0] for v in self.pencere.values()),
                                                  max(v[1] for v in self.pencere.values()))
        if lp > ust:
            return (lp - ust) / self.sigma
        if lp < alt:
            return (lp - alt) / self.sigma
        return 0.0

    def pencerede_mi(self, fiyat, kategori=None, pay=0.05):
        alt, ust = self.pencere.get(kategori) or (min(v[0] for v in self.pencere.values()),
                                                  max(v[1] for v in self.pencere.values()))
        return alt - pay <= math.log(fiyat) <= ust + pay

    def gelecek_orani(self, r, ay=18, yillik_km=17_500):
        """`ay` ay sonra aynı aracın bugünkü TL ile değer oranı (reel değer değişimi)."""
        seri = f"{r['marka']}|{r['seri']}"
        h = ay / 12.0
        y0 = r["yil"]
        alt_yil = math.floor(y0 - h)
        w = (y0 - h) - alt_yil
        yil_simdi = self.yil_degeri(seri, y0)
        yil_sonra = (1 - w) * self.yil_degeri(seri, alt_yil) + w * self.yil_degeri(seri, alt_yil + 1)
        km0 = r["km"] or 0
        dkm = self.km_degeri(seri, km0 + h * yillik_km) - self.km_degeri(seri, km0)
        # garanti bitebilir: garantili aracın primi yarıya iner varsayımı
        garanti = -0.5 * self._k("garanti:1") if r.get("garanti") == 1 else 0.0
        return math.exp(yil_sonra - yil_simdi + dkm + garanti)

    def katsayi_ozeti(self):
        ad = {"n:lokal": "1 lokal boyalı parça", "n:boya": "1 boyalı parça", "n:degisen": "1 değişen parça",
              "n:lokal_tampon": "1 lokal boyalı tampon", "n:boya_tampon": "1 boyalı tampon",
              "n:degisen_tampon": "1 değişen tampon", "n:tavan_boya": "tavan boyalı (ek)",
              "n:tavan_degisen": "tavan değişen (ek)", "n:kaput_degisen": "motor kaputu değişen (ek)",
              "n:boya_bilinmiyor": "boya bilgisi yok", "n:tramer_yok": "tramer yok (belirtilmiş)",
              "n:tramer_belirsiz": "tramer belirtilmemiş", "n:tramer_log": "tramer log(1+TL/10bin) başına",
              "n:cam_tavan": "cam tavan", "kimden:Galeriden": "galeriden (sahibine göre)",
              "kimden:Yetkili Bayiden": "yetkili bayiden", "kimden:Sahibinden": "sahibinden",
              "garanti:1": "garantisi var"}
        return {v: math.expm1(self._k(k)) for k, v in ad.items()}

    def kaydet(self, yol):
        with open(yol, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def yukle(yol):
        with open(yol, "rb") as f:
            return pickle.load(f)
