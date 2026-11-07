# Fırsat Araç

arabam.com piyasasını referans alıp **piyasanın altında fiyatlanmış, temiz ve 1-2 yıl sonra satarken baş ağrıtmayacak** araçları bulan sistem. Çıktı, 100 üzerinden puanla sıralanmış bir HTML listedir. İlana ve boya şemasına tıklayınca arabam.com ilanı açılır.

> "Arabayı alırken başkasına alıyormuş gibi al, satarken başın ağrımasın."

## Nasıl çalışır?

Yapay zekâ modeli eğitmek gerekmiyor. Sistem üç katmandan oluşuyor:

1. **Piyasa veritabanı** (`veri/piyasa.db`): Gönderdiğin tüm arabam.com taramaları tek bir SQLite veritabanında birleşir. Aynı ilan iki kez sayılmaz. Her yeni taramada fiyat değişiklikleri ve listeden kaybolan (muhtemelen satılan) ilanlar kaydedilir.
2. **Fiyat modeli** (`firsat/model.py`): Bir istatistik modeli (makine öğrenmesi, hiyerarşik ridge regresyon). 27 bin ilandan 20-30 saniyede öğrenir: marka > seri > motor > paket, yıl, km, boya/değişen, tramer, renk, satıcı tipi. Modelin görmediği ilanlarda ortalama hata **±%2,8**.
   - Referans tarama 1,25-2,0 M TL aralığında olduğu için model "kesik regresyon" kullanır. Sıradan regresyon bu aralığın kenarındaki araçları yanlışlıkla ucuz ya da pahalı gösterirdi.
   - Her ilanın piyasa değeri, o ilan hesaba katılmadan tahmin edilir. Böylece ilan kendi fiyatını "doğrulamaz".
3. **Claude incelemesi** (`veri/notlar.json`): En iyi adayların ilan açıklamalarını Claude tek tek okur. Rakamların göstermediği tuzakları işaretler: başlıkta "manuel" yazıp otomatik listelenmiş araç, "airbag değişmiş", "sel-su" tramer kaydı, açıklamada değişen parça yazıp formda "boyasız" görünen ilan, "yurt dışındayım, WhatsApp'tan yazın" dolandırıcılık kalıbı gibi.

## Puan (100)

| Bileşen | Puan | Ne ölçer |
|---|---|---|
| Fiyat avantajı | 45 | Aynı özellikteki araçların piyasa değerine göre ucuzluk. %12 ve üstü tam puan alır. Emsali az olan modellerde puan kısılır. |
| Kondisyon | 20 | Boya, değişen, tavan/kaput işlemi, tramer tutarı, boş bırakılmış ekspertiz bilgisi |
| Satılabilirlik | 20 | Marka/seri talebi, ilan derinliği, renk, satış anındaki km, yakıt tipi |
| Değer koruma | 15 | 18 ay ve ~26 bin km sonra bugünkü parayla tahmini değer |

Açıklamadaki riskler (pert, ağır hasar, airbag, şasi, engelli/ÖTV, kaza, dolandırıcılık kalıbı) puandan düşülür. Claude'un notu da puanı etkiler: AL +3, Dikkat −15, Ele ise ilanı listeden çıkarır.

**Kararlar:** AL / Güçlü aday (≥78), İncele (65-78), Dikkat (risk işareti), Pas (<65).

**Hızlı al-sat puanı** ("yarın satsam"): net kâr 55, satış hızı 25, kondisyon 20. Net kâr = piyasa değerinin bireysel satıcı seviyesinde %3 altına (hızlı satış) satış − ilan fiyatı − noter/ekspertiz/ilan/temizlik masrafı. Alışta pazarlık yapılmadığı varsayılır; pazarlık ek kârdır.

## Kullanım

Her şeyi Claude çalıştırır. Dosyayı sohbete ekleyip ne istediğini söylemen yeterli. Elle çalıştırmak istersen:

```bash
python3 firsat.py ekle arabam-ilanlar-coklu-....json      # yeni piyasa taramasını referansa ekler
python3 firsat.py piyasa --n 150                         # tüm piyasadaki en iyi fırsatlar -> raporlar/*.html
python3 firsat.py hizli --n 150                          # yarın satsam en kârlı olacaklar (hızlı al-sat)
python3 firsat.py degerlendir yeni-ilanlar.json          # gönderdiğin ilanları piyasaya göre puanlar
python3 firsat.py durum                                  # veritabanı ve model özeti
python3 firsat.py kur                                    # her şeyi ham dosyalardan sıfırdan kurar
```

Gereksinim: Python 3.10+ ve `numpy`.

## Klasörler

```
firsat.py            komut satırı
firsat/              okuyucu, metin analizi, veritabanı, fiyat modeli, puanlama, HTML rapor
veri/ham/            referans piyasa taramaları (.json.xz, sıkıştırılmış ham dosyalar; asıl kaynak)
veri/adaylar/        değerlendirilmek üzere gönderilen ilan dosyaları
veri/notlar.json     Claude'un ilan bazında notları
raporlar/            HTML ve JSON raporlar
```

`veri/piyasa.db` ve `veri/model.pkl` depoya girmez, ham dosyalardan otomatik kurulur.

## Daha iyi sonuç için tarama önerileri

- **Haftalık tara.** Aynı filtrelerle her hafta tarama gelirse sistem hangi ilanların kaybolduğunu (satıldığını) ve fiyat düşüşlerini görür. Böylece hangi modelin kaç günde satıldığını ve gerçek satış iskontosunu öğrenmeye başlar. Şu an tek bir gün var.
- **Fiyat penceresini biraz genişlet.** Örneğin 1,0-2,5 M TL. Pencerenin kenarındaki araçların tahmini daha sağlam olur. Senin bütçen 1,25-2,0 M TL ise rapor yine o aralığı gösterir.
- **Aday dosyaları aynı formatta gelsin.** Eklentinin arabam çoklu çıktısı doğrudan okunuyor. sahibinden dosyası gelirse ona da okuyucu eklenir.

## Sınırlar

- Fiyatlar ilan fiyatıdır, gerçek satış fiyatı değildir. Pazarlık payı iki tarafta da vardır.
- 18 ay hesabı enflasyon hariçtir (reel). TL bazında satış fiyatı daha yüksek görünecektir.
- Ekspertiz, tramer (hasar kaydı) ve borç/haciz sorgusu olmadan hiçbir araç alınmamalı.
- Yatırım tavsiyesi değildir.
