import time
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

# Binance API ile bağlantı kurmak için API anahtarı ve gizli anahtarı kullanıcıdan al
api_key = input("API Anahtarınızı Girin: ")
api_secret = input("API Gizli Anahtarınızı Girin: ")

# Binance API Client bağlantısı kur ve otomatik zaman senkronizasyonu etkinleştir
client = Client(api_key, api_secret)
client.API_URL = 'https://api.binance.com'
client.ping()  # Bağlantı testi

# Sunucu zamanını senkronize et
client.futures_time()  # Spot işlem zaman senkronizasyonu yapılır
client.get_server_time()  # API talepleri için sunucu zamanı alınır

# Kullanıcıdan işlem çiftini ve alım miktarını al
symbol = input("İşlem çifti (örn. BTCUSDT): ").upper()  # Örneğin BTCUSDT
quantity = float(input("Alım miktarı (örn. 0.001): "))
profit_percentage = float(input("Kar hedefi yüzdesi (örn. 1): ")) / 100
loss_percentage = float(input("Zarar durdurma yüzdesi (örn. 2): ")) / 100
order_type = input("Emir türü (MARKET veya LIMIT): ").upper()

# Eğer LIMIT seçildiyse limit fiyatını al
if order_type == "LIMIT":
    limit_price = float(input("Limit fiyatını girin: "))

# Üst üste en fazla 5 zarar
max_loss_count = 5
current_loss_count = 0

# entry_price tanımla
entry_price = None

# Alım işlemi
try:
    if order_type == "MARKET":
        print("Piyasa emriyle alım yapılıyor...")
        order = client.order_market_buy(symbol=symbol, quantity=quantity)
        entry_price = float(order['fills'][0]['price'])  # Gerçekleşen fiyat
        print(f"Alım işlemi başarılı: {entry_price} fiyatından alındı.")
    
    elif order_type == "LIMIT":
        print(f"Limit emriyle {limit_price} fiyatından alım yapılıyor...")
        order = client.order_limit_buy(symbol=symbol, quantity=quantity, price=str(limit_price))
        
        # Limit emrinin tamamlanmasını beklemek için döngü
        while True:
            order_status = client.get_order(symbol=symbol, orderId=order['orderId'])
            if order_status['status'] == 'FILLED':
                print("Limit emri gerçekleşti.")
                fills = client.get_my_trades(symbol=symbol)
                entry_price = float(fills[-1]['price'])  # En son gerçekleşen fiyatı al
                print(f"Limit emri başarılı: {entry_price} fiyatından alındı.")
                break
            else:
                print("Limit emri henüz dolmadı, bekleniyor...")
                time.sleep(5)  # 5 saniye bekle ve tekrar dene

except BinanceAPIException as e:
    print(f"Binance API hatası: {e}")
except BinanceOrderException as e:
    print(f"Emir işlemi hatası: {e}")
except Exception as e:
    print(f"Beklenmeyen bir hata oluştu: {e}")

# Kar ve zarar hedeflerini belirle
if entry_price:  # entry_price tanımlanmışsa devam et
    target_profit_price = entry_price * (1 + profit_percentage)
    stop_loss_price = entry_price * (1 - loss_percentage)

    # Döngüyle fiyatları izleme ve satış kararı verme
    while current_loss_count < max_loss_count:
        try:
            # Mevcut fiyatı al
            current_price = float(client.get_symbol_ticker(symbol=symbol)['price'])
            print(f"Mevcut fiyat: {current_price}")

            # Kar hedefi yakalandı mı?
            if current_price >= target_profit_price:
                print("Kar hedefi yakalandı, satış yapılıyor...")
                client.order_market_sell(symbol=symbol, quantity=quantity)
                break

            # Zarar durdurma tetiklendi mi?
            elif current_price <= stop_loss_price:
                print("Zarar durdurma tetiklendi, satış yapılıyor...")
                client.order_market_sell(symbol=symbol, quantity=quantity)
                current_loss_count += 1
                if current_loss_count >= max_loss_count:
                    print("Maksimum zarar sayısına ulaşıldı, işlemler durduruluyor...")
                    break
                else:
                    print(f"Zararlı işlem. Toplam zarar sayısı: {current_loss_count}")
                    # Tekrar alım yap
                    order = client.order_market_buy(symbol=symbol, quantity=quantity)
                    entry_price = float(order['fills'][0]['price'])
                    target_profit_price = entry_price * (1 + profit_percentage)
                    stop_loss_price = entry_price * (1 - loss_percentage)

            # Fiyatları kontrol etmek için belirli bir süre bekle
            time.sleep(5)  # Her 5 saniyede bir fiyat kontrol edilir
        except BinanceAPIException as e:
            print(f"API hatası: {e}")
        except Exception as e:
            print(f"Hata: {e}")

    print("Bot işlemi sona erdi.")
else:
    print("Alım emri gerçekleşmedi, işlem yapılamıyor.")
