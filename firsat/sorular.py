"""Satıcıya sorulacak kısa sorular: her biri tek cümle, gerçek bir alıcının mesajda yazacağı gibi.

Claude notu üçüncü öğe olarak elle yazılmış sorular içeriyorsa (`veri/notlar.json`: [karar, görüş, [sorular]])
rapor onları kullanır; yoksa buradaki kurallar ilanın verisinden en fazla 3 soru seçer (önce riskler, sonra
hasar/tramer, sonra şanzıman/bakım, en sonda pazarlık).
"""

CIFT_KAVRAMALI = ("DSG", "DCT", "EDC", "Powershift", "DDCT", "e-DCS6", "eDCS6", "e-DCT6", "7G-DCT", "S-Tronic")
CVT = ("X-tronic", "Xtronic", "CVT", "Multidrive", "Multidrive S", "e-CVT")

RISK_SORUSU = {
    "airbag": "Airbag hangi olayda açıldı, orijinal parçayla mı değişti?",
    "engelli": "Araç engelli raporuyla mı alındı, devirde ÖTV çıkar mı?",
    "kiralik": "Araç kiralık ya da filo aracı olarak mı kullanıldı?",
    "kiralik_firma": "Kiralama firmasından mı çıktı, kaç kişi kullandı?",
    "yabanci": "Araç yurt dışından mı geldi, ruhsat işlemleri tamamen bitti mi?",
    "motor": "Motorda ya da şanzımanda tam olarak ne yapıldı, faturası var mı?",
    "yapisal": "Şasi, podye ya da direklerde herhangi bir işlem var mı?",
    "manuel": "Vites otomatik mi manuel mi, ilanda ikisi de geçiyor?",
    "form_degisen": "Formda değişen görünmüyor ama açıklamada geçiyor, hangi parça değişti?",
    "form_boya": "Formda boya görünmüyor ama açıklamada geçiyor, tam olarak hangi parçalar boyalı?",
    "lpg_sonradan": "LPG ruhsata işli mi, hangi marka ve ne zaman takıldı?",
    "dolandiricilik": "Aracı yerinde görüp kendi seçtiğim ekspertize götürebilir miyim?",
    "kaza": "Kaza nasıl oldu, hangi taraftan vurdu?",
    "pert": "Pert, sel ya da ağır hasar kaydı var mı?",
    "agir_hasar": "Ağır hasar kaydı hangi olaydan?",
    "km": "Kilometre servis kayıtlarıyla tutuyor mu?",
}


def _tl(n):
    return f"{int(round(n)):,}".replace(",", ".") + " TL"


def _parcalar(liste):
    liste = [p.lower() for p in liste]
    if len(liste) == 1:
        return liste[0]
    if len(liste) <= 3:
        return ", ".join(liste[:-1]) + " ve " + liste[-1]
    return f"{len(liste)} parça"


def sorular(s, en_fazla=3):
    """İlan için en fazla `en_fazla` tek cümlelik soru."""
    q, gorulen = [], set()
    for kod, _, _ in s.get("riskler") or []:
        if kod in RISK_SORUSU and kod not in gorulen:
            gorulen.add(kod)
            q.append(RISK_SORUSU[kod])
    if s.get("pesinat_gecer") and s.get("firsat", 0) > 0.06:
        q.append("İlandaki fiyat tamamen nakit fiyatı mı, peşin ödersem ne olur?")

    p = s.get("parcalar") or {}
    if s.get("liste_satiri") or s.get("boya_bilinmiyor"):
        q.append("Boya değişen var mı, tramer kaydı ne kadar?")
    else:
        if p.get("degisen"):
            q.append(f"{_parcalar(p['degisen']).capitalize()} neden değişti, orijinal parça mı takıldı?")
        boyali = list(p.get("boya") or []) + list(p.get("lokal") or [])
        if boyali and "form_boya" not in gorulen:
            q.append(f"{_parcalar(boyali).capitalize()} neden boyandı, çizik mi vuruk mu?")
        if s.get("tramer_durum") == "tutar" and s.get("tramer_tl"):
            q.append(f"{_tl(s['tramer_tl'])} hasar kaydı neyden, hangi parçalar yapıldı?")
        elif s.get("tramer_durum") == "belirsiz":
            q.append("Tramer kaydı var mı, varsa ne kadar?")

    km = s.get("km") or 0
    sanziman = s.get("sanziman") or ""
    model = s.get("model") or ""
    if s.get("yakit") in ("Hibrit", "Elektrik"):
        q.append("Batarya sağlık raporu alabilir miyim?")
    if "PureTech" in model and km >= 50_000:
        q.append("Triger kayışı (yağ içindeki) kontrol edildi ya da değişti mi?")
    if sanziman in CVT and km >= 80_000:
        q.append("Şanzıman yağı hiç değişti mi?")
    elif s.get("vites") == "Yarı Otomatik" or sanziman in CIFT_KAVRAMALI:
        q.append("Şanzımanda kalkışta titreme ya da vuruntu var mı?")
    if km >= 100_000:
        q.append("Ağır bakımı yapıldı mı, triger ne zaman değişti?")
    if s.get("kimden") == "Sahibinden":
        q.append("Kaçıncı sahibisiniz, neden satıyorsunuz?")
    if (s.get("ilan_gun") or 0) >= 60:
        q.append("İlan uzun süredir yayında, nakit son rakamınız ne?")
    if len(q) < 2:
        q.append("Nakit alırsam son rakam ne olur?")
    return q[:en_fazla]
