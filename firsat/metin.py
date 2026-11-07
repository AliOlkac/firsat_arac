"""Açıklama metninden bilgi çıkarma: tramer tutarı, risk bayrakları, olumlu ifadeler."""
import re

_TR = str.maketrans("çğıöşüâîûÇĞİIÖŞÜÂÎÛ", "cgiosuaiucgiiosuaiu")


def sade(s):
    """Türkçe karakterleri sadeleştirir, küçük harfe çevirir, boşlukları teke indirir (satır sonu -> ' | ')."""
    s = (s or "").translate(_TR).lower()
    s = re.sub(r"\s*\n\s*", " | ", s)
    return re.sub(r"[ \t\r\f\v]+", " ", s).strip()


_OLUMSUZ = re.compile(r"^.{0,8}?\b(degil|degildir|yok|yoktur|olmayan|olmamistir|bulunmamaktadir|bulunmuyor|mevcut degil)\b")


# Galeri kalıp cümleleri: "firmamız ağır hasarlı, pert kayıtlı araç alım satımı yapmaz" gibi.
_KALIP = re.compile(r"yapma|yapilma|yapmaz|yer alma|yer verme|satma|satilma|almay|almaz|alinma|kabul etm|bulunma|"
                    r"\basla\b|degil|taahhut|islemsiz|yoktur|\byok\b|hatasiz|olmayan|kesinlikle|iade|ticaret|"
                    r"portfoy|firmamiz|tarafimiz|\baraclar|garantisi|garantili|sorgula|sozlesme|sayilir|kapsam|\balim\b|alim ?satim|"
                    r"kabul edem|kabul edil|takas|teklif etme|almiyoruz|satmiyoruz|almamaktayiz|satmamaktayiz")
_RISK_KELIME = re.compile(r"pert|agir hasar|km (oynan|dusur)|kilometre(si)? (oynan|dusur|degis)|airbag|sase|sasi|podye|hurda|"
                          r"\bsel\b|selden|cekme belge")
_BENIM = re.compile(r"aracim|aracimiz|aracta|aracin |aracimizda")
_KENDI = re.compile(r"\b(aracim\w*|aracimiz\w*|arac|aracin|bu arac\w*)\b")
_GENEL = re.compile(r"araclar|firmamiz|tarafimiz|portfoy|ticaret|alim ?satim|kabul|yapmay|yapmaz|almiyor|satmiyor|almay|satmay")
_CUMLE_SONU = re.compile(r"[.!?;|•✅▪►✔➤*]|-{2,}|_{2,}|━")


def _cumle(t, bas, son):
    i = max((m.end() for m in _CUMLE_SONU.finditer(t, max(0, bas - 160), bas)), default=max(0, bas - 160))
    m = _CUMLE_SONU.search(t, son)
    return t[i: m.start() if m else min(len(t), son + 160)]


def _olumsuz_mu(t, bas, son, kalip=True):
    """'airbag açmış değil' ya da galeri kalıp cümlesi ise ifade risk sayılmaz."""
    if _OLUMSUZ.match(t[son:son + 30]):
        return True
    c = _cumle(t, bas, son)
    # "ağır hasarlı, pert, km'si düşürülmüş, airbag işlemli araçlar..." gibi liste: aracın kendisinden söz etmiyorsa kalıptır
    if len({m.group(0)[:4] for m in _RISK_KELIME.finditer(c)}) >= 3 and not _BENIM.search(c):
        return True
    if kalip and _KALIP.search(c):
        # "araç ağır hasarlıdır, masrafı yoktur" gibi aracın kendisine dair cümle kalıp sayılmaz
        return not (_KENDI.search(c) and not _GENEL.search(c))
    return False


# (kod, açıklama, puan cezası, desen, galeri kalıbı kontrolü). Açıklamadaki bu ifadeler puanı düşürür.
RISKLER = [
    ("pert", "Açıklamada pert/hurda/çekme belgeli/sel/yangın ifadesi", 35,
     r"\bpert\b|\bhurda\b|cekme belge|\bselden\b|sel hasar|sel bask|\bsel\W{0,2}su\b|su baskin|su basmas|selzede|"
     r"yangin hasar|\byanmis\b", True),
    ("agir_hasar", "Açıklamada ağır hasar kaydı ifadesi", 35,
     r"agir hasar kayitli|agir hasarli|agir hasar kaydi (var|mevcut|bulunmakta)|agir hasar (cikmakta|cikiyor|cikar|gorun|gozuk|var)",
     True),
    ("engelli", "Engelli/ÖTV muafiyetli araç: devirde ÖTV ödenmesi ya da yalnızca engelliye satış gerekebilir", 30,
     r"\bengelli(den|ye|lere|ler)?\b|engelli raporlu|otv (muaf|istisna|indirimli)|otvsiz|otv siz", False),
    ("yapisal", "Şasi/podye/direk/tavan işlemi ifadesi", 15,
     r"(sasi|sase|sasesi|sasisi|sasede|saside|saseye|sasiye) (hasar|duzelt|kesme|islemli|islem gor|islem var|degis|cekil)|"
     r"podye (hasar|degis|islemli|islem gor|duzelt|kaynak)|"
     r"direk (degis|hasar|islemli|islem gor|kaynak)|tavan (degisen|degismis|degisti|kesme)", True),
    ("motor", "Motor/şanzıman işlemi ya da arıza ifadesi", 14,
     r"motor (revizyon|rektifiye|yenilen|yenilendi|degisti|degismis|degisimi|degistiril\w*|arizali|arizasi)|motor indi|sandik motor|"
     r"sanziman (degisti|degismis|degismistir|arizali|arizasi|revizyon|yenilendi)|vites (arizali|kutusu degis)", False),
    ("airbag", "Airbag açmış/değişmiş: ciddi kaza geçmişi", 18,
     r"(airbag|airbeg|airbaq|egirbe|eirbe|eyirbe|ayrbag|erbag|erbeg|hava yastig)\w*\W{0,3}(\w+\W+){0,3}?"
     r"(acti|acmis|acmistir|acilmis|patladi|patlamis|patlak|degis\w*|yenilen\w*|onarim\w*|onaril\w*|tamir\w*|islemli\w*|islem gor\w*)", False),
    ("km", "KM düzeltme ya da km'si belirsiz ifadesi", 12,
     r"km (dusur|oynan|duzelt|geri al)|km si belirsiz|km belirsiz", True),
    ("yabanci", "Yurt dışından getirilmiş / yabancı plaka: ikinci elde satışı zor", 14,
     r"yabanci plaka|mavi plaka|gumrukte|gumruk islem|turistik plaka|yurt ?disindan (getir|gel|al)|"
     r"yurt ?disi (gorev|cikisli|araci)|turk plakaya|turk plakasina", False),
    ("dolandiricilik", "Satıcı yurt dışında / sadece WhatsApp: kapora dolandırıcılığı kalıbı, aracı görmeden para gönderme", 25,
     r"yurt ?disindayim|yurt ?disinda (yasiyorum|oldugum|bulundugum)|sadece (whatsapp|wp|mesaj)|whatsapp (uzerinden|tan) ulas|"
     r"kargo ile teslim|kapora (gonder|yatir)|cekici ile (gonder|teslim)", False),
    ("lpg_sonradan", "Açıklamada LPG geçiyor: LPG'li araçların ikinci el talebi düşüktür", 5,
     r"\blpg\b|\blpgli\b|\blpg li\b", False),
    ("kiralik", "Kiralık/filo/taksi/ticari kullanım geçmişi olabilir", 10,
     r"kiralik|rent ?a ?car|\bfilo\b|\btaksi\b|ticari plaka|ticari kayit|ticariye|ticari olarak kullan|\bhizmet araci", True),
    ("mekatronik", "Mekatronik/şanzıman beyni değişimi yapılmış", 3, r"mekatronik|sanziman beyni", False),
    ("kaza", "Açıklamada aracın kaza geçirdiği yazıyor", 10,
     r"kazaya karis\w*|kaza gecir\w*|kaza yapmis|kaza yapti|kazasi (var|mevcut|olmustur)|kazasi fotograf\w*|"
     r"kaza (resmi|fotograf)\w*|darbe al\w*|carpisma sonucu", False),
    ("hasar_genel", "Açıklamada hasar/kaza/onarım geçiyor (okunmalı)", 4,
     r"\bkazali\b|\bkaza (yap|gec)|\bhasarli\b|\bgocuk\b|\bezik\b|\bcizik\b|\brotus\b|\brotuslu\b", True),
]
RISKLER = [(k, a, c, re.compile(d), kl) for k, a, c, d, kl in RISKLER]

# Formdaki bilgiyle çelişen ifadeler (form "boyasız / otomatik" derken açıklama başka şey söylüyorsa)
PARCA = r"(kapi|kapisi|kapilar|kapilari|camurluk|camurlugu|kaput|kaputu|tampon|tamponu|bagaj|tavan|panel|marspiyel|on uc parca|uc parca|kapagi|gogus|gogsu|kapi saclari)"
DEGISEN_METIN = re.compile(PARCA + r"\w*\W{1,3}(\w+\W+){0,4}?(degismis|degismistir|degisti|degistirilmis|degistirilmistir|"
                           r"degistirmis|degistirmistir|degisimi|degisim olmus|degisen)\b")
BOYA_METIN = re.compile(PARCA + r"\w*\W{1,3}(\w+\W+){0,3}?(boyali|boyalidir|boyanmis|boyanmistir|boya var|boya mevcut|"
                        r"lokal boya|lokal boyali|lokal boyalidir)\b")
MANUEL = re.compile(r"\bmanuel\b(?!\W{0,2}(klima|mod|gecis|vites modu|kullanim|katlan|ayar|koltuk|el fren|park|perde|"
                    r"bagaj|direksiyon|ayna|sunroof|tavan|kontrol|secenek|olarak da|vites secimi|vites degis|f1))")


def form_celiskileri(t, baslik, r):
    """Form ile açıklama çelişiyorsa risk listesi döner."""
    cikti = []
    if r.get("vites") in ("Otomatik", "Yarı Otomatik"):
        metin = sade(baslik) + " . " + t
        for m in MANUEL.finditer(metin):
            if not _OLUMSUZ.match(metin[m.end():m.end() + 30]) and "otomatik" not in metin[max(0, m.start() - 25): m.end() + 25]:
                cikti.append(("manuel", "Başlık/açıklamada 'manuel' geçiyor: vites manuel olabilir, manuelin piyasa değeri belirgin düşüktür", 22))
                break
    if not r.get("n_degisen"):
        for m in DEGISEN_METIN.finditer(t):
            if not _olumsuz_mu(t, m.start(), m.end(), kalip=False):
                sadece_tampon = m.group(1).startswith("tampon")
                cikti.append(("form_degisen", "Açıklamada değişen parça yazıyor ama ilan formunda değişen yok: ekspertizle doğrula",
                              3 if sadece_tampon else 9))
                break
    if not r.get("n_boya") and not r.get("n_lokal"):
        for m in BOYA_METIN.finditer(t):
            if not _olumsuz_mu(t, m.start(), m.end(), kalip=False):
                cikti.append(("form_boya", "Açıklamada boyalı parça yazıyor ama ilan formunda boya yok", 4))
                break
    return cikti


PESINAT = re.compile(r"pesinat|kapora|\bsenet")

OLUMLU = [
    ("ilk_sahip", "İlk/tek sahibinden", re.compile(r"ilk sahib|tek sahib|ilk elden|birinci el")),
    ("servis", "Yetkili servis bakımlı", re.compile(r"(yetkili )?servis bakimli|bakimlari (yetkili )?servis|yetkili serviste")),
    ("garaj", "Garaj arabası / az kullanılmış", re.compile(r"garaj arabasi|az kullanilmis")),
    ("acil", "Satıcı acele ediyor (pazarlık şansı)", re.compile(r"\bacil\b|acil satilik|ihtiyactan|borctan")),
    ("fatura", "Faturalı / galeriden ilk el", re.compile(r"faturali|fatura (ile|li)")),
]

TRAMER_YOK = re.compile(
    r"tramer(siz| kaydi yok| kaydi bulunmamakta| yok| yoktur| 0 ?(tl)?\b| bulunmamakta| sifir)|"
    r"hasar kaydi (yok|bulunmamakta)|hasar kayitsiz|sifir tramer|\b0 tramer|tramer kaydi yoktur|degisen ve tramer yok|"
    r"boya ?(,|ve)? ?degisen ?(,|ve)? ?tramer yok")
TRAMER_ANAHTAR = re.compile(r"tramer|hasar kaydi|hasar kayit")


def _tutar(ham, carpani):
    deger = int(re.sub(r"[.,\s]", "", ham))
    if carpani in ("bin", "k") and deger < 10_000:
        deger *= 1000
    return deger


def tramer_metinden(t):
    """Sade metinden tramer bilgisi. (durum, tutar) döner: ('yok',0) | ('tutar',x) | (None,None)."""
    if not TRAMER_ANAHTAR.search(t):
        return None, None
    adaylar = []
    # "tramer 45.000 tl", "hasar kaydı: 120 bin"
    for m in re.finditer(r"(tramer|hasar kaydi|hasar kayit)(\w*)", t):
        if "siz" in m.group(2):                          # tramersiz / hasar kayıtsız
            continue
        pencere = t[m.end(): m.end() + 45]
        for n in re.finditer(r"(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(bin|k\b)?\s*(tl|lira|₺)?(\s*(km|adet|parca|kalem|kez|kayit))?", pencere):
            if n.start() > 32:
                break
            if n.group(4):                                   # "30.000 km", "2 adet"
                continue
            deger = _tutar(n.group(1), n.group(2))
            if 1990 <= deger <= 2030 and not n.group(3):   # yıl
                continue
            if deger < 1000 and not n.group(2):              # "2 parça", "3 boya", tarih parçası
                continue
            adaylar.append(deger)
            break
    # "45 bin tl tramer", "1 milyon 200 bin hasar kaydı"
    for m in re.finditer(r"(?:(\d+)\s*milyon\s*)?(\d{1,3}(?:[.,]\d{3})*|\d+)\s*(bin|k\b|tl|₺)\s*(tl\s*)?(lik\s*)?"
                         r"(normal\s*)?(tramer|hasar kaydi|hasar kayit)", t):
        deger = int(m.group(1) or 0) * 1_000_000 + _tutar(m.group(2), m.group(3))
        adaylar.append(deger)
    adaylar = [a for a in adaylar if 1000 <= a <= 3_000_000]
    if adaylar:
        return "tutar", max(adaylar)
    if TRAMER_YOK.search(t):
        return "yok", 0
    return None, None


def riskler(t):
    """Sade metindeki risk bayrakları: [(kod, açıklama, ceza), ...]."""
    bulunan = []
    for kod, aciklama, ceza, desen, kalip in RISKLER:
        for m in desen.finditer(t):
            if not _olumsuz_mu(t, m.start(), m.end(), kalip):
                bulunan.append((kod, aciklama, ceza))
                break
    return bulunan


def olumlular(t):
    return [(kod, aciklama) for kod, aciklama, desen in OLUMLU if desen.search(t)]
