"""Her ilan için satıcıya sorulacak kısa, kopyalanabilir sorular.

Sorular ilanın verisine göre seçilir: açıklamadaki riskler, boyalı/değişen parçalar, tramer, km,
şanzıman tipi, yakıt, garanti, satıcı tipi. En fazla ~7 soru; sonda her zaman ekspertiz/borç ve son fiyat.
"""

CIFT_KAVRAMALI = ("DSG", "DCT", "EDC", "Powershift", "DDCT", "e-DCS6", "eDCS6", "e-DCT6", "7G-DCT", "S-Tronic")

RISK_SORUSU = {
    "airbag": "Açıklamada airbag işleminden söz ediliyor: hangi olayda açıldı, orijinal parçayla mı değişti, servis faturası var mı?",
    "engelli": "Araç engelli/ÖTV muafiyetiyle mi alındı? Devirde ÖTV ödenmesi gerekiyor mu, normal noter satışı yapılabiliyor mu?",
    "kiralik": "Araç kiralık, filo ya da ticari olarak kullanıldı mı?",
    "yabanci": "Araç yurt dışından mı getirildi? Gümrük ve ruhsat işlemleri tamamlandı mı?",
    "motor": "Motor ya da şanzımanda hangi işlem yapıldı, ne zaman ve nerede? Faturası var mı?",
    "yapisal": "Şasi, podye veya direklerde işlem var mı? Güncel ekspertiz raporunu paylaşabilir misiniz?",
    "manuel": "Vites otomatik mi, manuel mi? İlanda iki farklı bilgi var.",
    "form_degisen": "Açıklamada değişen parça geçiyor ama ilan formunda görünmüyor: tam boya-değişen durumu nedir?",
    "form_boya": "Açıklamada boyalı parça geçiyor ama ilan formunda görünmüyor: hangi parçalar boyalı?",
    "lpg_sonradan": "LPG ruhsata işli mi? Hangi marka, ne zaman takıldı?",
    "dolandiricilik": "Aracı yerinde görüp kendi seçeceğim ekspertize götürebilir miyim? (Görmeden kapora göndermiyorum.)",
    "kaza": "Aracın geçirdiği kaza nasıl oldu, hangi parçalar onarıldı? Kaza fotoğrafı var mı?",
    "pert": "Araçta pert, sel veya ağır hasar kaydı var mı?",
    "agir_hasar": "Ağır hasar kaydı var mı? Varsa hangi olaydan?",
    "km": "Kilometre orijinal mi? Servis kayıtlarındaki km'leri paylaşabilir misiniz?",
}


def _parca_yazi(liste, adet=4):
    liste = [p.lower() for p in liste]
    if len(liste) > adet:
        return ", ".join(liste[:adet]) + f" ve {len(liste) - adet} parça daha"
    return ", ".join(liste)


def _tl(n):
    return f"{int(round(n)):,}".replace(",", ".") + " TL"


def sorular(s, en_fazla=7):
    risk = []
    gorulen = set()
    for kod, _, _ in s.get("riskler") or []:
        if kod in RISK_SORUSU and kod not in gorulen:
            gorulen.add(kod)
            risk.append(RISK_SORUSU[kod])
    if s.get("firsat", 0) > 0.15:
        risk.append("Fiyat benzerlerine göre epey uygun: aracın bilmem gereken bir durumu ya da acil satış nedeni var mı?")
    if s.get("pesinat_gecer") and s.get("firsat", 0) > 0.06:
        risk.append("İlandaki fiyat tam nakit satış fiyatı mı? Kredili ya da senetli satışta fiyat farklı mı?")

    hasar = []
    p = s.get("parcalar") or {}
    if s.get("liste_satiri"):
        hasar.append("Boya-değişen durumu ve hasar kaydı (tramer) nedir? Güncel ekspertiz raporu var mı?")
    elif s.get("boya_bilinmiyor"):
        hasar.append("Boya-değişen durumu nedir? Güncel ekspertiz raporunu paylaşabilir misiniz?")
    else:
        if p.get("degisen"):
            hasar.append(f"{_parca_yazi(p['degisen']).capitalize()} neden değişti? Orijinal parça mı, yan sanayi mi? Kaza fotoğrafı var mı?")
        boyali = list(p.get("boya") or []) + list(p.get("lokal") or [])
        if boyali:
            hasar.append(f"{_parca_yazi(boyali).capitalize()} neden boyandı: çizik/sürtme mi, kaza mı?")
    if not s.get("liste_satiri"):
        if s.get("tramer_durum") == "tutar" and s.get("tramer_tl"):
            hasar.append(f"{_tl(s['tramer_tl'])} hasar kaydı hangi olaydan? Hangi parçalar onarıldı ya da değişti?")
        elif s.get("tramer_durum") == "belirsiz":
            hasar.append("Hasar kaydı (tramer) var mı, varsa tutarı ne? Şasi numarasını paylaşırsanız sorgulayabilirim.")

    bakim = ["Son bakım ne zaman ve kaç km'de yapıldı, yetkili serviste mi? Servis kaydı ya da faturası var mı?"]
    km = s.get("km") or 0
    if km >= 80_000:
        bakim.append("Ağır bakımı (triger/zincir, şanzıman yağı, balata, disk) yapıldı mı?")
    if s.get("vites") == "Yarı Otomatik" or (s.get("sanziman") or "") in CIFT_KAVRAMALI:
        bakim.append("Şanzımanda kalkışta titreme ya da vuruntu var mı? Kavrama veya mekatronik işlemi yapıldı mı?")
    if s.get("yakit") in ("Hibrit", "Elektrik"):
        bakim.append("Batarya sağlık raporu (SOH) alabilir miyim? Batarya garantisi ne zamana kadar?")
    elif s.get("garanti") == 1:
        bakim.append("Garanti hangi tarihe kadar devam ediyor?")
    if s.get("kimden") == "Sahibinden":
        bakim.append("Araç sizin adınıza mı kayıtlı, kaçıncı sahibisiniz?")
    if s.get("yakit") == "LPG & benzin" and "lpg_sonradan" not in gorulen:
        bakim.append("LPG ruhsata işli mi, hangi marka?")

    kapanis = ["Borç, haciz ya da rehin var mı? Aracı kendi seçeceğim ekspertize götürebilir miyim?",
               "Nakit alımda son fiyatınız nedir?"]
    govde = (risk + hasar + bakim)[: max(1, en_fazla - len(kapanis))]
    return govde + kapanis


def mesaj(s, liste=None):
    liste = liste or sorular(s)
    site = "sahibinden'deki" if "sahibinden.com" in (s.get("url") or "") else "arabam.com'daki"
    arac = f"{s.get('yil')} {s.get('marka')} {s.get('seri')} {s.get('model')}".strip()
    satirlar = [f"Merhaba, {site} {arac} ilanınız (ilan no {s.get('ilan_id')}) için yazıyorum. Birkaç sorum olacak:"]
    satirlar += [f"{i}. {q}" for i, q in enumerate(liste, 1)]
    satirlar.append("Şimdiden teşekkür ederim.")
    return "\n".join(satirlar)
