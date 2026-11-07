"""sahibinden ilanını arabam piyasasındaki marka / seri / paket adlarına eşler.

İki site aynı aracı çoğu zaman aynı adla yazar ("1.3 TCe Icon"), ama marka yazımı ("Mercedes-Benz" /
"Mercedes - Benz"), boşluk-tire farkları ve paket adı ayrıntıları değişebilir. Eşleşme seviyesi:
  paket  aynı paket bulundu (fiyat modeli tam çalışır)
  motor  aynı motor (hacim + motor kodu + yakıt) bulundu, paket farklı/bilinmiyor
  seri   yalnızca seri bulundu (tahmin daha belirsiz)
  marka  seri bulunamadı (tahmin güvenilmez)
"""
import re
from collections import Counter, defaultdict

from .metin import sade

GUVEN_CARPANI = {"paket": 1.0, "motor": 0.9, "seri": 0.7, "marka": 0.4, "yok": 0.3}


def _tok(s):
    return [t for t in re.split(r"[\s\-/_()+]+", sade(s)) if t]


def _marka_n(s):
    return re.sub(r"[^a-z0-9]", "", sade(s))


def _hacim(toklar):
    """'1.3' gibi motor hacmi; '1.3 TCe' -> '1.3'."""
    for t in toklar:
        if re.fullmatch(r"\d[.,]\d{1,2}", t):
            return t.replace(",", ".")
    return None


class Eslestirici:
    def __init__(self, satirlar):
        self.markalar = {}                          # marka_n -> arabam marka adı
        self.seriler = defaultdict(dict)            # marka_n -> {seri_n: seri adı}
        self.modeller = defaultdict(Counter)        # (marka, seri) -> Counter(model)
        self.model_bilgi = {}                       # (marka, seri, model) -> (motor, yakıt, hp)
        hp = defaultdict(list)
        for r in satirlar:
            mn = _marka_n(r["marka"])
            self.markalar[mn] = r["marka"]
            self.seriler[mn][" ".join(_tok(r["seri"]))] = r["seri"]
            self.modeller[(r["marka"], r["seri"])][r["model"]] += 1
            if r.get("hp"):
                hp[(r["marka"], r["seri"], r["model"])].append(r["hp"])
            self.model_bilgi.setdefault((r["marka"], r["seri"], r["model"]), [r["motor"], r.get("yakit"), None])
        for k, v in hp.items():
            v.sort()
            self.model_bilgi[k][2] = v[len(v) // 2]

    def _seri_bul(self, mn, seri, model, baslik):
        adaylar = self.seriler.get(mn) or {}
        sn = " ".join(_tok(seri))
        if sn in adaylar:
            return adaylar[sn]
        sik = sn.replace(" ", "")
        for k, v in adaylar.items():
            if k.replace(" ", "") == sik:
                return v
        # seri adı modelin/başlığın içinde geçiyor mu (en uzun eşleşen)
        havuz = set(_tok(seri) + _tok(model) + _tok(baslik))
        uyan = [(len(k), v) for k, v in adaylar.items() if k and set(k.split()) <= havuz]
        return max(uyan)[1] if uyan else None

    def eslestir(self, r):
        """r'yi yerinde günceller: marka/seri/model/motor arabam adlarına çekilir, 'eslesme' alanı eklenir."""
        mn = _marka_n(r.get("marka"))
        r["kaynak_adi"] = f"{r.get('marka')} {r.get('seri')} {r.get('model')}".strip()
        if mn not in self.markalar:
            # 'Mercedes' / 'Mercedes-Benz' gibi kısmi yazımlar
            uyan = [k for k in self.markalar if k.startswith(mn) or mn.startswith(k)] if mn else []
            if not uyan:
                r["eslesme"] = "yok"
                return r
            mn = max(uyan, key=len)
        r["marka"] = self.markalar[mn]
        seri = self._seri_bul(mn, r.get("seri") or "", r.get("model") or "", r.get("baslik") or "")
        if not seri:
            r["eslesme"] = "marka"
            return r
        r["seri"] = seri
        modeller = self.modeller[(r["marka"], seri)]
        hedef = _tok(r.get("model"))
        hedef_set, hacim = set(hedef), _hacim(hedef)
        en_iyi, en_iyi_puan = None, 0.0
        for m, adet in modeller.items():
            mt = _tok(m)
            ms = set(mt)
            if not ms or not hedef_set:
                continue
            mh = _hacim(mt)
            if hacim and mh and hacim != mh:
                continue
            m_yakit = self.model_bilgi[(r["marka"], seri, m)][1]
            if r.get("yakit") and m_yakit and r["yakit"] != m_yakit:      # benzinli "A 180" dizel "A 180 d" ile eşleşmesin
                continue
            puan = len(ms & hedef_set) / len(ms | hedef_set)
            hp = self.model_bilgi[(r["marka"], seri, m)][2]
            if r.get("hp") and hp and abs(r["hp"] - hp) / hp < 0.1:
                puan += 0.1
            puan += min(adet, 50) / 5000            # eşitlikte yaygın paketi seç
            if puan > en_iyi_puan:
                en_iyi, en_iyi_puan = m, puan
        if en_iyi and en_iyi_puan >= 0.6:
            r["model"] = en_iyi
            r["motor"] = self.model_bilgi[(r["marka"], seri, en_iyi)][0]
            r["eslesme"] = "paket"
            return r
        # motor düzeyi: aynı hacim + motor kodu + yakıt
        if hacim:
            i = next(i for i, t in enumerate(hedef) if t.replace(",", ".") == hacim)
            kod = hedef[i + 1] if i + 1 < len(hedef) else ""
            motorlar = Counter()
            for m, adet in modeller.items():
                motor, yakit, _ = self.model_bilgi[(r["marka"], seri, m)]
                if motor.startswith(f"{hacim} {kod}".strip()) and (not r.get("yakit") or yakit == r["yakit"]):
                    motorlar[motor] += adet
            if motorlar:
                r["motor"] = motorlar.most_common(1)[0][0]
                r["eslesme"] = "motor"
                return r
        # motor hacmi yazmayan adlar ("320i ED Luxury Line"): okuyucunun motor anahtarı aynı mı?
        from .okuyucu import motor_anahtari
        anahtar = motor_anahtari(r.get("model") or "", r.get("yakit"))
        if any(self.model_bilgi[(r["marka"], seri, m)][0] == anahtar for m in modeller):
            r["motor"] = anahtar
            r["eslesme"] = "motor"
            return r
        r["eslesme"] = "seri"
        return r
