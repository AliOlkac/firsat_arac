# Fırsat Araç — Claude için çalışma talimatı

Kullanıcı Türkçe konuşur; yanıtlar Türkçe. Amaç: arabam.com piyasasına göre **piyasanın altında, temiz, 1-2 yıl sonra zararsız satılabilecek** araçları bulmak ve 100 üzerinden puanlı HTML liste vermek. Eski "arac-emsal" eklenti sistemi bu projede KULLANILMAZ (kullanıcı istemedi); her şey bu depodaki `firsat.py` ile yapılır.

## Kullanıcı dosya gönderdiğinde

Dosyalar genelde `/root/.claude/uploads/...` altına gelir. Önce `meta` bölümüne bak (`toplam_ilan`, `filtreler`).

1. **Geniş piyasa taraması** (çoklu filtre, binlerce ilan, "arabam-ilanlar-coklu-*"): referansa ekle.
   ```bash
   python3 firsat.py ekle <dosya.json> [...]
   python3 firsat.py piyasa --n 150 --min-puan 60
   ```
   Kullanıcı "yarın satsam kârlı olacak / hızlı al-sat / FP" isterse:
   ```bash
   python3 firsat.py hizli --n 150 --min-puan 60
   ```
   Hızlı al-sat puanı: net kâr 55 (alış = ilan fiyatı, satış = piyasa değeri × bireysel seviye × %97, masraf düşülür),
   satış hızı 25, kondisyon 20. 18 ay değer koruması bu puana girmez.
2. **Değerlendirilecek ilanlar** (kullanıcı "bunlara bak / hangilerini alayım" der, genelde yüzlerce ilan):
   ```bash
   python3 firsat.py degerlendir <dosya.json> --ad aday-YYYY-MM-DD
   ```
   Emin değilsen: 3000+ ilan ve fiyat bantlı çoklu filtre ise referans, değilse aday. Gerekirse kullanıcıya sor.
3. **sahibinden dosyaları** (kullanıcı oradan gerçek alınacak araçları arar): arabam piyasası emsal/temel olarak kalır,
   sahibinden ilanları **veritabanına eklenmez** (`ekle` reddeder). Her zaman `degerlendir` ile puanla:
   - **Genel tarama** (`"pazar"` listesi ya da `meta.mod = "pazar_taramasi"`; boya/tramer/açıklama yok):
     `python3 firsat.py degerlendir <dosya.json> --n 250` → kâr potansiyeline göre ön eleme raporu +
     `raporlar/<ad>-linkler.txt` ve `-ilan-numaralari.txt` (kullanıcı bunları detaylı tarar; en fazla 200-300).
     Bu iki txt'yi kullanıcıya dosya olarak da gönder.
   - **Detaylı tarama** (genel_bilgiler + arac_bilgileri + boya_degisen_tramer, sahibinden.com linkli):
     `python3 firsat.py degerlendir <dosya.json>` → tam rapor; ardından Claude incelemesi ve yayın.
   - Model adları `firsat/eslestir.py` ile arabam adlarına eşlenir (paket > motor > seri). Raporda "arabam eşleşmesi"
     yazar; eşleşme seri/marka seviyesindeyse fiyat tahmini zayıftır, buna göre yorumla.
   - İlk gerçek sahibinden dosyası geldiğinde etiket adlarını kontrol et (okuyucu `_al(...)` alternatifleri, `pazar_satiri`).
4. Veritabanı yoksa ilk komut onu `veri/ham/*.json.xz` dosyalarından otomatik kurar (~1 dk). Model `veri/model.pkl` içinde önbelleklenir.

## Claude incelemesi (atlanmaz)

Her rapordan sonra `raporlar/<ad>-inceleme.txt` dosyası notu olmayan en iyi adayların açıklamalarını içerir. Bunları oku ve `veri/notlar.json` dosyasına ekle:

```json
"<ilan_id>": ["AL" | "İNCELE" | "DİKKAT" | "ELE", "Tek-iki cümlelik gerekçe"]
```

Sonra raporu aynı komutla yeniden üret. Okurken özellikle bak:
- Başlıkta/açıklamada **"manuel"** (form otomatik derken) → ELE (manuelin değeri düşük).
- **Airbag** açmış/değişmiş/onarılmış (yazım hataları: eirbeg, egirbec) → ELE.
- **Sel-su, pert, ağır hasar çıkıyor, şasi/podye düzeltme** → ELE.
- Açıklamada **değişen/boyalı parça** yazıp formda boyasız görünen → DİKKAT.
- Yüksek **tramer** (≳150 bin TL), **sandık motor değişimi**, **yurt dışından getirme / Türk plakaya çevirme** → DİKKAT ya da ELE.
- **"Yurt dışındayım, sadece WhatsApp", kapora isteyen** → DİKKAT (dolandırıcılık kalıbı).
- **Paket uyuşmazlığı** (başlık "Touch", form "Icon" gibi) → İNCELE, fırsat küçük olabilir.
- **Peşinat/senet** öne çıkarılmış ve fiyat çok ucuz → fiyatın nakit tam fiyat olduğunu teyit ettir.
- Emsali çok az (serinin piyasada <10 ilanı) ve çok ucuz görünen → güvenme.
Yeni bir kalıp tekrar ediyorsa `firsat/metin.py` içindeki kurallara ekle.

## Satıcıya sorular

Her kartta "Satıcıya sor: kopyala" butonu ve detayda mesaj kutusu var (`firsat/sorular.py`). Sorular ilanın verisinden
üretilir (değişen/boyalı parçalar, tramer, km, çift kavramalı şanzıman, hibrit batarya, garanti, riskler, ucuzluk).
Yeni bir risk kalıbı eklersen `RISK_SORUSU` sözlüğüne de soru ekle.

## Yayınlama ve teslim

- HTML'i Artifact olarak yayınla (kullanıcı telefondan da bakıyor). Güncel piyasa fırsat listesi şu artifact'ta: https://claude.ai/artifact/7hDqWUBJW8KTrzLk3d17H7 — yeni piyasa raporunu `url` ile bu adrese yayınla (önce `read` et). Hızlı al-sat listesi: https://claude.ai/artifact/WDmzJfbKH9a7ojw1r2cNhJ (aynı şekilde güncelle). Aday değerlendirmeleri için yeni artifact açılabilir.
- Kullanıcıya kısa özet ver: kaç ilan tarandı, kaç AL/güçlü aday, ilk 5 araç (fiyat, piyasa değeri, ucuzluk %, Claude notu).
- Değişiklikleri commit edip geliştirme dalına pushla. `veri/piyasa.db`, `veri/model.pkl`, `*-inceleme.txt` depoya girmez.

## Kod haritası

- `firsat/okuyucu.py` arabam detaylı JSON → ortak satır (hasar parçaları, tramer, motor anahtarı, riskler)
- `firsat/metin.py` açıklama analizi: tramer tutarı, risk kalıpları, form çelişkileri, galeri kalıp cümlesi ayıklama
- `firsat/veritabani.py` SQLite: görüntü (tarama günü), ilan, fiyat geçmişi, kaybolan ilan işareti
- `firsat/model.py` hiyerarşik ridge + kesik regresyon (fiyat penceresi), 5 katlı out-of-fold tahmin, yıl/km eğrileri
- `firsat/degerlendirme.py` adil fiyat, emsaller, güven, 18 ay hesabı, 100'lük puan ve karar
- `firsat/ayarlar.py` ağırlıklar, eşikler, marka talep tablosu, masraflar
- `firsat/rapor.py` HTML şablonu (tek dosya) ve JSON kayıt biçimi
- `firsat/sorular.py` satıcıya sorulacak sorular ve kopyalanabilir mesaj
- `firsat/eslestir.py` sahibinden marka/seri/paket adlarını arabam adlarına eşleme

Model sürümünü (`firsat/analiz.py` → `MODEL_SURUM`) özellik/parsing değişikliğinde artır; önbellek yenilenir.
