"""Puanlama ayarları. Değerleri buradan değiştir; kod başka yerde sabit sayı tutmaz."""

ELDE_TUTMA_AY = 18            # "1-2 yıl sonra satarım" -> 18 ay
YILLIK_KM = 17_500            # elde tutarken yapılacak km varsayımı
MASRAF_SABIT = 15_000         # ekspertiz + noter + ilan + temizlik (TL)
MASRAF_ORAN = 0.002           # noter harcı benzeri oransal masraf

# Puan ağırlıkları (toplam 100)
P_FIYAT = 45                  # piyasaya göre ucuzluk
P_KONDISYON = 20              # boya / değişen / tramer
P_SATILABILIRLIK = 20         # talep, renk, km, yakıt
P_DEGER_KORUMA = 15           # 18 ay sonraki reel değer

ESIK_GUCLU = 78              # bu puan ve üstü: güçlü aday
ESIK_INCELE = 65             # bu puan ve üstü: incelenebilir; altı: pas
FIYAT_TAVAN = 0.12            # bu kadar (%12) ucuz olan tam puan alır
SUPHELI_UCUZ = 0.20           # bundan ucuzsa önce doğrulanmalı (dolandırıcılık / gizli hasar / peşinat fiyatı)
DEGER_ALT, DEGER_UST = 0.86, 0.985  # 18 ay sonraki değer oranı: alt -> 0 puan, üst -> tam puan

# Marka bazında ikinci el talebi / satış kolaylığı (Türkiye piyasası, 0-1). Listede yoksa 0.6.
MARKA_TALEP = {
    "Toyota": 1.0, "Honda": 1.0, "Volkswagen": 1.0, "Renault": 1.0, "Fiat": 1.0, "Hyundai": 0.95, "Dacia": 0.95,
    "Skoda": 0.9, "Peugeot": 0.85, "Ford": 0.85, "Opel": 0.8, "Seat": 0.85, "Kia": 0.85, "Nissan": 0.8,
    "Citroen": 0.75, "Audi": 0.9, "BMW": 0.9, "Mercedes - Benz": 0.9, "Cupra": 0.8, "Mini": 0.75, "Volvo": 0.75,
    "Suzuki": 0.75, "Mazda": 0.65, "Jeep": 0.65, "Mitsubishi": 0.6, "Subaru": 0.55, "Alfa Romeo": 0.55,
    "DS Automobiles": 0.5, "KGM SsangYong": 0.5, "Isuzu": 0.55, "TOGG": 0.65, "Lexus": 0.6, "Land Rover": 0.6,
    "Jaguar": 0.5, "Smart": 0.5,
    "Chery": 0.5, "MG": 0.45, "BYD": 0.45, "Jaecoo": 0.4, "Omoda": 0.4, "Skywell": 0.35, "SWM": 0.3, "DFSK": 0.3,
    "Foton": 0.3, "Seres": 0.3, "Nieve": 0.3, "Lynk & Co": 0.4,
}
ELEKTRIK_CARPAN = 0.75        # elektrikli araçlarda ikinci el talebi ve fiyat istikrarı daha düşük

RENK_POPULER = {"Beyaz", "Gri", "Siyah", "Füme", "Gri (Gümüş)", "Gri (Metalik)", "Gri (Titanyum)", "Gümüş", "Gri (Füme)"}
RENK_ZOR = {"Yeşil", "Yeşil (Metalik)", "Turuncu", "Sarı", "Mor", "Pembe", "Kahverengi", "Bej", "Bordo", "Altın",
            "Şampanya", "Turkuaz", "Bronz"}

YAKIT_PUAN = {"Benzin": 1.0, "Hibrit": 1.0, "Dizel": 0.85, "LPG & benzin": 0.55, "Elektrik": 0.35}
SORUNLU_SANZIMAN = {"Powershift": "Ford Powershift şanzımanı kronik arızalarıyla bilinir"}
