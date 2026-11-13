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
     `python3 firsat.py degerlendir <dosya.json> --n 250` → çıktının sonundaki "LİNKLER" bölümünü **sohbete düz metin
     olarak, alt alta** yapıştır; linkleri tek tıkla kopyalanabilsin diye bir kod bloğu (```text) içine koy (seri başına bir blok). KULLANICI İSTEĞİ: bu adımda dosya gönderme, artifact/HTML yayınlama, uzun açıklama
     yapma; sadece linkler (birden fazla seri varsa kısa seri başlığıyla ayrılmış, çünkü eklenti seri sayfası başına
     toplar) ve en fazla bir-iki cümle. Tek bir tarama dosyası (çok markalı `/otomobil/...` taraması dahil) gelirse linkler
     tek blokta verilir; kullanıcı link listesini yapıştırınca eklenti (`mod: adres_listesi`) sayfadan bağımsız toplar.
     Çok markalı taramada marka `kategori` alanında, seri boşsa `kumeler[].ilan_idleri` eşlemesinden alınır. Kullanıcı linkleri detaylı tarayıp geri gönderir; fırsat listesi (HTML) o zaman yapılır.
   - **Detaylı tarama** (genel_bilgiler + arac_bilgileri + boya_degisen_tramer, sahibinden.com linkli):
     `python3 firsat.py degerlendir <dosya.json>` → tam rapor; ardından Claude incelemesi ve yayın.
   - Model adları `firsat/eslestir.py` ile arabam adlarına eşlenir (paket > motor > seri). Raporda "arabam eşleşmesi"
     yazar; eşleşme seri/marka seviyesindeyse fiyat tahmini zayıftır, buna göre yorumla.
   - Gerçek biçim (2026-11-07'de doğrulandı): genel taramada `marka`/`seri` null gelir, seri `meta.filtre_url`
     yolundan alınır (`/skoda-octavia/...`); yakıt/kasa/şanzıman yoktur, eşleşen arabam paketinden doldurulur.
     `boyasiz=false` = boyalı (parça sayısı bilinmiyor, 2 parça varsayılır). `boyasiz=null` ama `meta.etiketler`de
     "Boyasız" seçeneği ≥%95 tarandıysa (ör. 858'de 852, durum "eksik") okuyucu null'u boyalı sayar. Detaylı ilan etiketleri: "Yakıt / Motor Tipi",
     "Vites", "KM", "Kasa Tipi", "Motor Gücü", "Motor Hacmi", "Servis Garantisi", "Ağır Hasar Kayıtlı".
   - Detaylı dosya (`meta.mod = "secili_ilanlar"`) içinde ayrıca `pazar`/`kumeler` de bulunur; okuyucu `ilanlar` içindeki
     detaylı kayıtları okur. Eklenti yalnızca o anki filtre sayfasının taramasındaki numaraları toplar
     (`meta.secim.taninmayan_numaralar`): farklı serilerin numaralarını kullanıcıya seri seri ayrı dosyalarda ver ve
     tanınmayan numara varsa kullanıcıya söyle.
   - Ön eleme eşiği (`ayarlar.ONELEME_*`): fırsat × güven ≥ %2,5 (boyasız) / %5 (boyalı); ağır risk bayraklı ilanlar çıkar.
     Başlıkları da oku (engelliden engelliye, peşinat/senet, %20 KDV gibi).
   - **sahibinden site farkı** (`analiz.sahibinden_duzeltmesi`): bazı seriler sahibinden'de arabam'dan farklı seviyede
     listelenir (2026-11-08: Golf eTSI ~%5 ucuz). `veri/adaylar/*pazar*` genel taramalarındaki boyasız ilanlardan seri/motor
     başına medyan fark hesaplanır (20 ilana kadar sıfıra büzülür, ±%8 tavan) ve sahibinden ilanının piyasa değeri bu kadar
     kaydırılır. Genel tarama dosyalarını `veri/adaylar/` içinde tut; yeni taramalar farkı günceller.
   - Eklenti virgül içeren adresleri ilan adresi saymıyor: link listesinde virgül `%2C` olarak yazılır.
   - **arabam detaylı aday dosyası** (`arabam-ilanlar-*` ama ön elemeden gelen yüzlerce ilan): referansa EKLENMEZ,
     `degerlendir` ile puanlanır. Kullanıcı arabam ve sahibinden detaylı dosyalarını birlikte gönderirse tek komutta
     ver: `python3 firsat.py degerlendir <sahibinden.json> <arabam.json> --ad firsat-listesi-YYYY-MM-DD` → tek HTML.
   - **arabam liste taraması** (`meta.mod = "liste_taramasi"`, `arabam-liste-*`): sonuç sayfası satırları, açıklama/boya
     yok; `temiz=true` yalnız sitenin "Boyasız, Değişensiz ve Tramersiz" filtresinde çıkanlar (~%6). Etiketsiz ilan boyalı
     DEMEK DEĞİL (referansta %40 tam temiz): okuyucu 1 boyalı parça varsayar (gözlenen ~%1,7 fiyat farkına denk) ve
     boyalı eşiğini uygular. Referansa EKLENMEZ; `degerlendir` ile ön eleme yapılıp arabam linkleri ayrı blokta verilir.
     sahibinden ön elemesini önce çalıştır: arabam ön elemesi sahibinden raporlarında aynı marka/seri/paket/yıl, ±600 km,
     ±%2,5 fiyatla görülen araçları (iki sitede birden ilanda olan aynı araç) çıkarır (`analiz.ayni_arac_var`).
   - Ön elemede referansın kapsamadığı yıl/km (2018 öncesi, 160 bin km üstü) çıkarılır: sahibinden SUV sayfası
     (`/arazi-suv-pickup/`) URL'deki yıl/km filtresini uygulamıyor. `agir_hasar = "Evet"` ilanlar da çıkarılır.
   - Ön elemede daha önce detaylı taranmış (`veri/adaylar/sahibinden-ilanlar-*` ve `arabam-ilanlar-*`) ve fiyatı düşmemiş ilanlar çıkarılır
     (`analiz.onceki_detaylar`); fiyatı düşenler yeniden önerilir. Detaylı dosyaları `veri/adaylar/` içinde tut.
4. Veritabanı yoksa ilk komut onu `veri/ham/*.json.xz` dosyalarından otomatik kurar (~1 dk). Model `veri/model.pkl` içinde önbelleklenir.

## Claude incelemesi (atlanmaz)

Her rapordan sonra `raporlar/<ad>-inceleme.txt` dosyası notu olmayan en iyi adayların açıklamalarını içerir. Bunları oku ve `veri/notlar.json` dosyasına ekle:

```json
"<ilan_id>": ["AL" | "İNCELE" | "DİKKAT" | "ELE", "Tek-iki cümlelik görüş", ["Tek cümlelik soru", "..."]]
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

## HTML kartları, Claude görüşü ve sorular

KULLANICI İSTEĞİ (2026-11-11): kartlarda uzun satıcı mesajı/kopyala kısmı YOK. Her kartın altında bir kutu var:
**Görüşüm** (`veri/notlar.json` notunun metni, renk = AL/İNCELE/DİKKAT/ELE) ve **Satıcıya sorarım** (1-3 soru).
Notlar araca dair kısa ama somut bir görüş olmalı (kim satıyor, boya/tramer, gerçek ucuzluk, sorulacak şey).
Not biçimi: `"<ilan_id>": [karar, görüş, [soru, ...]]`. Sorular **tek cümle**, gerçek bir alıcının mesajda yazacağı
gibi ve o araca özgü olsun ("45 bin TL'lik kayıt sadece sunroof camı mı?", "Orijinal tampon ve jantlar duruyor mu?",
"Bir yılda 45 bin km yapmış, kiralık mıydı?"). Genel kalıp soru yığma; ELE notlarına soru gerekmez. Elle soru
yazılmamışsa `firsat/sorular.py` veriden en fazla 3 kısa soru üretir (riskler > hasar/tramer > şanzıman/bakım >
pazarlık); yeni risk kalıbı eklersen `RISK_SORUSU`na da tek cümlelik soru ekle. Aday raporunda ≥10 notlu ilan varsa
sayfa varsayılan olarak yalnız notlu ilanları gösterir; "okunmayan ilanları da göster" düğmesi gerisini açar.

## Yayınlama ve teslim

- HTML'i Artifact olarak yayınla (kullanıcı telefondan da bakıyor). Güncel piyasa fırsat listesi şu artifact'ta: https://claude.ai/artifact/7hDqWUBJW8KTrzLk3d17H7 — yeni piyasa raporunu `url` ile bu adrese yayınla (önce `read` et). Hızlı al-sat listesi: https://claude.ai/artifact/WDmzJfbKH9a7ojw1r2cNhJ (aynı şekilde güncelle). Aday değerlendirmeleri için yeni artifact açılabilir (Skoda ön eleme: https://claude.ai/artifact/NzHso4K8PuEKnWjpTUutqV, Superb detay: https://claude.ai/artifact/UVTLnV5xkP5wapgjzabCgf, Octavia detay: https://claude.ai/artifact/LeMYPkFmb98orqSDSimFvC, çok markalı detay 2026-11-08: https://claude.ai/artifact/JN94LgaDuXpqBkojUJksEE, 24 saat detay 2026-11-09: https://claude.ai/artifact/L2SGyMbUt8exBGra5SLpQD, 24 saat detay 2026-11-09 akşam: https://claude.ai/artifact/RZqj7YY76NkirjqXMAgq8f, 24 saat detay 2026-11-11: https://claude.ai/artifact/HW8FUu8X2pcmmFUhKoeNnb, arabam + sahibinden birleşik detay 2026-11-11: https://claude.ai/artifact/VUxqZyf8YZ3uciWhmwoV3Q, birleşik detay 2026-11-12: https://claude.ai/artifact/P2fvojZhDkkg2WGGDhReEe, birleşik detay 2026-11-13: https://claude.ai/artifact/JhWN6WJEkMdFWQ2ccsRMpw, Civic Eco detay 2026-11-13: https://claude.ai/artifact/CkXNau5f3pigdh975jqxZ9).
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
- `firsat/sorular.py` satıcıya sorulacak tek cümlelik sorular (elle yazılmamışsa)
- `firsat/eslestir.py` sahibinden marka/seri/paket adlarını arabam adlarına eşleme

Model sürümünü (`firsat/analiz.py` → `MODEL_SURUM`) özellik/parsing değişikliğinde artır; önbellek yenilenir.
