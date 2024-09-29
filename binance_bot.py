import time
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
import logging
from decimal import Decimal, ROUND_DOWN, getcontext

# Decimal hassasiyetini artır
getcontext().prec = 28

# Logging yapılandırması
logging.basicConfig(
    filename='trading_bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def get_api_credentials():
    api_key = input("API Anahtarınızı Girin: ")
    api_secret = input("API Gizli Anahtarınızı Girin: ")
    return api_key, api_secret

def connect_client(api_key, api_secret):
    client = Client(api_key, api_secret)
    try:
        server_time = client.get_server_time()
        logging.info(f"Bağlantı başarılı. Sunucu zamanı: {server_time}")
        print(f"Bağlantı başarılı. Sunucu zamanı: {server_time}")
        return client
    except BinanceAPIException as e:
        logging.error(f"Binance API hatası: {e}")
        print(f"Binance API hatası: {e}")
        exit()
    except Exception as e:
        logging.error(f"Hata: {e}")
        print(f"Hata: {e}")
        exit()

def get_symbol_info(client, symbol):
    try:
        symbol_info = client.get_symbol_info(symbol)
        if not symbol_info:
            raise Exception(f"Symbol bilgisi bulunamadı: {symbol}")
        return symbol_info
    except BinanceAPIException as e:
        logging.error(f"Binance API hatası: {e}")
        print(f"Binance API hatası: {e}")
        exit()
    except Exception as e:
        logging.error(f"Hata: {e}")
        print(f"Hata: {e}")
        exit()

def extract_filters(symbol_info):
    lot_size_filter = next(filter(lambda f: f['filterType'] == 'LOT_SIZE', symbol_info['filters']), None)
    if lot_size_filter:
        min_qty = Decimal(lot_size_filter['minQty'])
        max_qty = Decimal(lot_size_filter['maxQty'])
        step_size = Decimal(lot_size_filter['stepSize'])
        print(f"Min miktar: {min_qty}, Max miktar: {max_qty}, Adım boyutu: {step_size}")
        logging.info(f"Min miktar: {min_qty}, Max miktar: {max_qty}, Adım boyutu: {step_size}")
    else:
        raise Exception(f"LOT_SIZE filtresi bulunamadı: {symbol_info['symbol']}")

    price_filter = next(filter(lambda f: f['filterType'] == 'PRICE_FILTER', symbol_info['filters']), None)
    if price_filter:
        min_price = Decimal(price_filter['minPrice'])
        tick_size = Decimal(price_filter['tickSize'])
        print(f"Minimum fiyat adımı: {tick_size}")
        logging.info(f"Minimum fiyat adımı: {tick_size}")
    else:
        raise Exception(f"PRICE_FILTER bulunamadı: {symbol_info['symbol']}")

    min_notional_filter = next(filter(lambda f: f['filterType'] == 'MIN_NOTIONAL', symbol_info['filters']), None)
    if min_notional_filter:
        min_notional = Decimal(min_notional_filter['minNotional'])
        print(f"Minimum notional değeri: {min_notional}")
        logging.info(f"Minimum notional değeri: {min_notional}")
    else:
        min_notional = Decimal('10')
        print(f"Minimum notional filtresi bulunamadı. Varsayılan değer: {min_notional}")
        logging.info(f"Minimum notional filtresi bulunamadı. Varsayılan değer: {min_notional}")

    return min_qty, max_qty, step_size, min_price, tick_size, min_notional

def round_quantity(quantity, step_size):
    return (quantity / step_size).to_integral_value(rounding=ROUND_DOWN) * step_size

def round_price(price, tick_size):
    tick_decimals = abs(tick_size.as_tuple().exponent)
    return price.quantize(Decimal('1.' + '0' * tick_decimals), rounding=ROUND_DOWN)

def get_usdt_balance(client):
    try:
        account_info = client.get_account()
        usdt_info = next(filter(lambda x: x['asset'] == 'USDT', account_info['balances']), None)
        if usdt_info:
            usdt_free = Decimal(usdt_info['free'])
            usdt_locked = Decimal(usdt_info['locked'])
            total_usdt = usdt_free + usdt_locked
            print(f"Mevcut USDT bakiyesi (Free): {usdt_free}, (Locked): {usdt_locked}, Toplam: {total_usdt}")
            logging.info(f"Mevcut USDT bakiyesi (Free): {usdt_free}, (Locked): {usdt_locked}, Toplam: {total_usdt}")
            return usdt_free
        else:
            print("USDT bakiyesi bulunamadı.")
            logging.error("USDT bakiyesi bulunamadı.")
            return Decimal('0')
    except BinanceAPIException as e:
        logging.error(f"Binance API hatası: {e}")
        print(f"Binance API hatası: {e}")
        exit()
    except Exception as e:
        logging.error(f"Hata: {e}")
        print(f"Hata: {e}")
        exit()

def place_order(client, order_type, symbol, quantity, step_size, tick_size, price=None, min_notional=Decimal('10')):
    try:
        quantity = round_quantity(quantity, step_size)
        if price is not None:
            price = round_price(price, tick_size)

        if order_type == "MARKET":
            logging.info(f"Piyasa emriyle alım yapılıyor: {quantity} {symbol}")
            print("Piyasa emriyle alım yapılıyor...")
            order = client.order_market_buy(symbol=symbol, quantity=str(quantity))
            if 'fills' in order and len(order['fills']) > 0:
                entry_price = Decimal(order['fills'][0]['price'])
                notional = entry_price * quantity
                if notional < min_notional:
                    logging.error(f"Alım notional değeri minimumun altında: {notional} < {min_notional}")
                    print(f"Alım notional değeri minimumun altında: {notional} < {min_notional}")
                    return None
                logging.info(f"Alım işlemi başarılı: {entry_price} fiyatından alındı.")
                print(f"Alım işlemi başarılı: {entry_price} fiyatından alındı.")
                return entry_price
            else:
                logging.error("Alım işlemi gerçekleşmedi.")
                print("Alım işlemi gerçekleşmedi.")
                return None

        elif order_type == "LIMIT":
            if price is None:
                raise Exception("Limit fiyatı belirtilmedi.")
            notional = price * quantity
            if notional < min_notional:
                logging.error(f"Limit alım notional değeri minimumun altında: {notional} < {min_notional}")
                print(f"Limit alım notional değeri minimumun altında: {notional} < {min_notional}")
                return None
            logging.info(f"Limit emriyle alım yapılıyor: {quantity} {symbol} at {price}")
            print(f"Limit emriyle {price} fiyatından alım yapılıyor...")

            tick_decimals = abs(tick_size.as_tuple().exponent)
            price_str = format(price, f'.{tick_decimals}f')
            order = client.order_limit_buy(symbol=symbol, quantity=str(quantity), price=price_str)

            while True:
                order_status = client.get_order(symbol=symbol, orderId=order['orderId'])
                if order_status['status'] == 'FILLED':
                    logging.info("Limit emri gerçekleşti.")
                    print("Limit emri gerçekleşti.")
                    fills = client.get_my_trades(symbol=symbol)
                    if fills:
                        entry_price = Decimal(fills[-1]['price'])
                        notional = entry_price * quantity
                        if notional < min_notional:
                            logging.error(f"Alım notional değeri minimumun altında: {notional} < {min_notional}")
                            print(f"Alım notional değeri minimumun altında: {notional} < {min_notional}")
                            return None
                        logging.info(f"Limit emri başarılı: {entry_price} fiyatından alındı.")
                        print(f"Limit emri başarılı: {entry_price} fiyatından alındı.")
                        return entry_price
                    else:
                        logging.error("Trade bilgisi alınamadı.")
                        print("Trade bilgisi alınamadı.")
                        return None
                else:
                    logging.info("Limit emri henüz dolmadı, bekleniyor...")
                    print("Limit emri henüz dolmadı, bekleniyor...")
                    time.sleep(2)
    except BinanceAPIException as e:
        logging.error(f"Binance API hatası: {e}")
        print(f"Binance API hatası: {e}")
        return None
    except BinanceOrderException as e:
        logging.error(f"Emir işlemi hatası: {e}")
        print(f"Emir işlemi hatası: {e}")
        return None
    except Exception as e:
        logging.error(f"Hata: {e}")
        print(f"Hata: {e}")
        return None

def sell_order(client, symbol, quantity, step_size, tick_size, price=None, min_notional=Decimal('10')):
    try:
        quantity = round_quantity(quantity, step_size)
        if price is not None:
            price = round_price(price, tick_size)

        if price:
            notional = price * quantity
            if notional < min_notional:
                logging.error(f"Limit satış notional değeri minimumun altında: {notional} < {min_notional}")
                print(f"Limit satış notional değeri minimumun altında: {notional} < {min_notional}")
                return None
            logging.info(f"Limit emriyle satış yapılıyor: {quantity} {symbol} at {price}")
            print(f"Limit emriyle {price} fiyatından satış yapılıyor...")

            tick_decimals = abs(tick_size.as_tuple().exponent)
            price_str = format(price, f'.{tick_decimals}f')
            order = client.order_limit_sell(symbol=symbol, quantity=str(quantity), price=price_str)
        else:
            logging.info(f"Piyasa emriyle satış yapılıyor: {quantity} {symbol}")
            print(f"Piyasa emriyle satış yapılıyor: {quantity} {symbol}")
            order = client.order_market_sell(symbol=symbol, quantity=str(quantity))

        return order
    except BinanceAPIException as e:
        logging.error(f"Binance API hatası: {e}")
        print(f"Binance API hatası: {e}")
        return None
    except BinanceOrderException as e:
        logging.error(f"Emir işlemi hatası: {e}")
        print(f"Emir işlemi hatası: {e}")
        return None
    except Exception as e:
        logging.error(f"Hata: {e}")
        print(f"Hata: {e}")
        return None

def place_buy_order(client, symbol, quantity, step_size, tick_size, min_notional=Decimal('10'), buy_price=None):
    try:
        if buy_price is None:
            raise Exception("Alım fiyatı belirtilmedi.")

        buy_price = round_price(buy_price, tick_size)
        notional = buy_price * quantity
        if notional < min_notional:
            logging.error(f"Alım notional değeri minimumun altında: {notional} < {min_notional}")
            print(f"Alım notional değeri minimumun altında: {notional} < {min_notional}")
            return False

        logging.info(f"Limit emriyle alım yapılıyor: {quantity} {symbol} at {buy_price}")
        print(f"Limit emriyle {buy_price} fiyatından alım yapılıyor...")

        tick_decimals = abs(tick_size.as_tuple().exponent)
        buy_price_str = format(buy_price, f'.{tick_decimals}f')

        order = client.order_limit_buy(symbol=symbol, quantity=str(quantity), price=buy_price_str)

        while True:
            order_status = client.get_order(symbol=symbol, orderId=order['orderId'])
            if order_status['status'] == 'FILLED':
                logging.info("Alış emri gerçekleşti.")
                print("Alış emri gerçekleşti.")
                fills = client.get_my_trades(symbol=symbol)
                if fills:
                    entry_price = Decimal(fills[-1]['price'])
                    notional = entry_price * quantity
                    if notional < min_notional:
                        logging.error(f"Alım notional değeri minimumun altında: {notional} < {min_notional}")
                        print(f"Alım notional değeri minimumun altında: {notional} < {min_notional}")
                        return False
                    logging.info(f"Alım işlemi başarılı: {entry_price} fiyatından alındı.")
                    print(f"Alım işlemi başarılı: {entry_price} fiyatından alındı.")
                    return entry_price
                else:
                    logging.error("Trade bilgisi alınamadı.")
                    print("Trade bilgisi alınamadı.")
                    return False
            else:
                logging.info("Alış emri henüz dolmadı, bekleniyor...")
                print("Alış emri henüz dolmadı, bekleniyor...")
                time.sleep(2)
    except BinanceAPIException as e:
        logging.error(f"Binance API hatası: {e}")
        print(f"Binance API hatası: {e}")
        return False
    except BinanceOrderException as e:
        logging.error(f"Emir işlemi hatası: {e}")
        print(f"Emir işlemi hatası: {e}")
        return False
    except Exception as e:
        logging.error(f"Hata: {e}")
        print(f"Hata: {e}")
        return False

def main():
    api_key, api_secret = get_api_credentials()
    client = connect_client(api_key, api_secret)

    symbol = input("İşlem çifti (örn. SUIUSDT): ").upper()

    try:
        profit_percentage = Decimal(input("Kar hedefi yüzdesi (örn. 0.3): "))
        loss_percentage = Decimal(input("Zarar durdurma yüzdesi (örn. 1): "))
    except:
        logging.error("Geçersiz kar veya zarar yüzdesi girişi.")
        print("Geçersiz kar veya zarar yüzdesi girişi.")
        exit()

    order_type = input("Emir türü (MARKET veya LIMIT): ").upper()

    symbol_info = get_symbol_info(client, symbol)

    min_qty, max_qty, step_size, min_price, tick_size, min_notional = extract_filters(symbol_info)

    usdt_balance = get_usdt_balance(client)

    try:
        allocation_percentage = Decimal(input("Toplam bakiyenin ne kadarıyla işlem yapılsın (%): ")) / Decimal('100')
    except:
        logging.error("Geçersiz alım yüzdesi girişi.")
        print("Geçersiz alım yüzdesi girişi.")
        exit()

    allocation_amount = usdt_balance * allocation_percentage

    if allocation_amount < min_notional:
        logging.error(f"Alım için ayrılan miktar notional minimumun altında: {allocation_amount} < {min_notional}")
        print(f"Alım için ayrılan miktar notional minimumun altında: {allocation_amount} < {min_notional}")
        exit()

    limit_price = None
    if order_type == "LIMIT":
        limit_price_input = input(f"Limit fiyatını girin ({symbol}): ")
        try:
            limit_price = Decimal(limit_price_input)
            if limit_price < min_price:
                logging.error(f"Limit fiyatı minimum fiyatın altında: {limit_price} < {min_price}")
                print(f"Limit fiyatı minimum fiyatın altında: {limit_price} < {min_price}")
                exit()
        except:
            logging.error("Geçersiz limit fiyatı girişi.")
            print("Geçersiz limit fiyatı girişi.")
            exit()

    entry_price = None
    if order_type == "MARKET":
        try:
            current_market_price = Decimal(client.get_symbol_ticker(symbol=symbol)['price'])
            quantity = allocation_amount / current_market_price
            quantity = round_quantity(quantity, step_size)

            if quantity < min_qty:
                logging.error(f"Bakiyeniz, minimum işlem miktarının altında. Hesaplanan miktar: {quantity}, Min. miktar: {min_qty}")
                print(f"Bakiyeniz, minimum işlem miktarının altında. Hesaplanan miktar: {quantity}, Min. miktar: {min_qty}")
                exit()

            notional = current_market_price * quantity
            if notional < min_notional:
                logging.error(f"Alım notional değeri minimumun altında: {notional} < {min_notional}")
                print(f"Alım notional değeri minimumun altında: {notional} < {min_notional}")
                exit()

            entry_price = place_order(client, order_type, symbol, quantity, step_size, tick_size, min_notional=min_notional)
        except BinanceAPIException as e:
            logging.error(f"Binance API hatası: {e}")
            print(f"Binance API hatası: {e}")
            exit()
        except Exception as e:
            logging.error(f"Hata: {e}")
            print(f"Hata: {e}")
            exit()
    else:
        quantity = allocation_amount / limit_price
        quantity = round_quantity(quantity, step_size)

        if quantity < min_qty:
            logging.error(f"Bakiyeniz, minimum işlem miktarının altında. Hesaplanan miktar: {quantity}, Min. miktar: {min_qty}")
            print(f"Bakiyeniz, minimum işlem miktarının altında. Hesaplanan miktar: {quantity}, Min. miktar: {min_qty}")
            exit()

        notional = limit_price * quantity
        if notional < min_notional:
            logging.error(f"Limit alım notional değeri minimumun altında: {notional} < {min_notional}")
            print(f"Limit alım notional değeri minimumun altında: {notional} < {min_notional}")
            exit()

        entry_price = place_order(client, order_type, symbol, quantity, step_size, tick_size, limit_price, min_notional=min_notional)

    if entry_price is None:
        print("Başlangıç alım işlemi başarısız oldu, program durduruluyor.")
        logging.info("Başlangıç alım işlemi başarısız oldu, program durduruluyor.")
        exit()

    take_profit_price = entry_price * (Decimal('1') + profit_percentage / Decimal('100'))
    stop_loss_price = entry_price * (Decimal('1') - loss_percentage / Decimal('100'))

    take_profit_price = round_price(take_profit_price, tick_size)
    stop_loss_price = round_price(stop_loss_price, tick_size)

    print(f"Alış fiyatı: {entry_price}, Kar hedefi: {take_profit_price}, Zarar durdurma: {stop_loss_price}")
    logging.info(f"Alış fiyatı: {entry_price}, Kar hedefi: {take_profit_price}, Zarar durdurma: {stop_loss_price}")

    max_loss_count = 5
    current_loss_count = 0
    state = "waiting_for_sell"

    while current_loss_count < max_loss_count:
        try:
            time.sleep(2)
            current_price = Decimal(client.get_symbol_ticker(symbol=symbol)['price'])
            print(f"Güncel fiyat: {current_price}")
            logging.info(f"Güncel fiyat: {current_price}")

            if state == "waiting_for_sell":
                if current_price >= take_profit_price:
                    print(f"Kar hedefi aşıldı, {take_profit_price} fiyatından satış yapılıyor...")
                    logging.info(f"Kar hedefi aşıldı, {take_profit_price} fiyatından satış yapılıyor...")

                    current_symbol_balance = get_usdt_balance(client)
                    if current_symbol_balance < min_qty:
                        logging.error(f"Satış için yeterli {symbol} bakiyesi yok: {current_symbol_balance}")
                        print(f"Satış için yeterli {symbol} bakiyesi yok: {current_symbol_balance}")
                        continue

                    sell_order_response = sell_order(client, symbol, current_symbol_balance, step_size, tick_size, min_notional=min_notional)
                    if sell_order_response is None:
                        print("Satış işlemi başarısız oldu, tekrar deniyor...")
                        logging.info("Satış işlemi başarısız oldu, tekrar deniyor...")
                        continue

                    if 'fills' in sell_order_response and len(sell_order_response['fills']) > 0:
                        sell_price = Decimal(sell_order_response['fills'][0]['price'])
                    else:
                        sell_price = Decimal(client.get_symbol_ticker(symbol=symbol)['price'])
                    print(f"Kar ile satış yapıldı: {sell_price}")
                    logging.info(f"Kar ile satış yapıldı: {sell_price}")

                    buy_price = sell_price * Decimal('0.997')
                    buy_price = round_price(buy_price, tick_size)

                    if buy_price < min_price:
                        logging.error(f"Yeniden alım fiyatı minimum fiyatın altında: {buy_price} < {min_price}")
                        print(f"Yeniden alım fiyatı minimum fiyatın altında: {buy_price} < {min_price}")
                        continue

                    allocation_amount = get_usdt_balance(client) * allocation_percentage
                    if allocation_amount < min_notional:
                        logging.error(f"Alım için ayrılan miktar notional minimumun altında: {allocation_amount} < {min_notional}")
                        print(f"Alım için ayrılan miktar notional minimumun altında: {allocation_amount} < {min_notional}")
                        continue

                    buy_entry_price = place_buy_order(client, symbol, allocation_amount / buy_price, step_size, tick_size, min_notional=min_notional, buy_price=buy_price)
                    if buy_entry_price:
                        take_profit_price = buy_entry_price * (Decimal('1') + profit_percentage / Decimal('100'))
                        stop_loss_price = buy_entry_price * (Decimal('1') - loss_percentage / Decimal('100'))

                        take_profit_price = round_price(take_profit_price, tick_size)
                        stop_loss_price = round_price(stop_loss_price, tick_size)

                        print(f"Yeni alış fiyatı: {buy_entry_price}, Yeni Kar hedefi: {take_profit_price}, Yeni Zarar durdurma: {stop_loss_price}")
                        logging.info(f"Yeni alış fiyatı: {buy_entry_price}, Yeni Kar hedefi: {take_profit_price}, Yeni Zarar durdurma: {stop_loss_price}")

                        state = "waiting_for_sell"
                        current_loss_count = 0
                        continue

                if current_price <= stop_loss_price:
                    print(f"Zarar durdurma fiyatı aşıldı, {stop_loss_price} fiyatından satış yapılıyor...")
                    logging.info(f"Zarar durdurma fiyatı aşıldı, {stop_loss_price} fiyatından satış yapılıyor...")

                    current_symbol_balance = get_usdt_balance(client)
                    if current_symbol_balance < min_qty:
                        logging.error(f"Satış için yeterli {symbol} bakiyesi yok: {current_symbol_balance}")
                        print(f"Satış için yeterli {symbol} bakiyesi yok: {current_symbol_balance}")
                        continue

                    sell_order_response = sell_order(client, symbol, current_symbol_balance, step_size, tick_size, min_notional=min_notional)
                    if sell_order_response is None:
                        print("Satış işlemi başarısız oldu, tekrar deniyor...")
                        logging.info("Satış işlemi başarısız oldu, tekrar deniyor...")
                        continue

                    if 'fills' in sell_order_response and len(sell_order_response['fills']) > 0:
                        sell_price = Decimal(sell_order_response['fills'][0]['price'])
                    else:
                        sell_price = Decimal(client.get_symbol_ticker(symbol=symbol)['price'])
                    print(f"Zarar ile satış yapıldı: {sell_price}")
                    logging.info(f"Zarar ile satış yapıldı: {sell_price}")

                    buy_price = sell_price * Decimal('0.98')
                    buy_price = round_price(buy_price, tick_size)

                    if buy_price < min_price:
                        logging.error(f"Yeniden alım fiyatı minimum fiyatın altında: {buy_price} < {min_price}")
                        print(f"Yeniden alım fiyatı minimum fiyatın altında: {buy_price} < {min_price}")
                        continue

                    allocation_amount = get_usdt_balance(client) * allocation_percentage
                    if allocation_amount < min_notional:
                        logging.error(f"Alım için ayrılan miktar notional minimumun altında: {allocation_amount} < {min_notional}")
                        print(f"Alım için ayrılan miktar notional minimumun altında: {allocation_amount} < {min_notional}")
                        continue

                    buy_entry_price = place_buy_order(client, symbol, allocation_amount / buy_price, step_size, tick_size, min_notional=min_notional, buy_price=buy_price)
                    if buy_entry_price:
                        take_profit_price = buy_entry_price * (Decimal('1') + profit_percentage / Decimal('100'))
                        stop_loss_price = buy_entry_price * (Decimal('1') - loss_percentage / Decimal('100'))

                        take_profit_price = round_price(take_profit_price, tick_size)
                        stop_loss_price = round_price(stop_loss_price, tick_size)

                        print(f"Yeni alış fiyatı: {buy_entry_price}, Yeni Kar hedefi: {take_profit_price}, Yeni Zarar durdurma: {stop_loss_price}")
                        logging.info(f"Yeni alış fiyatı: {buy_entry_price}, Yeni Kar hedefi: {take_profit_price}, Yeni Zarar durdurma: {stop_loss_price}")

                        current_loss_count += 1
                        print(f"Üst üste zarar sayısı: {current_loss_count}")
                        logging.warning(f"Üst üste zarar sayısı: {current_loss_count}")
                        continue

            elif state == "waiting_for_sell":
                pass  # Diğer işlemler zaten yapılıyor

        except BinanceAPIException as e:
            logging.error(f"Binance API hatası: {e}")
            print(f"Binance API hatası: {e}")
            continue
        except BinanceOrderException as e:
            logging.error(f"Emir işlemi hatası: {e}")
            print(f"Emir işlemi hatası: {e}")
            continue
        except Exception as e:
            logging.error(f"Hata: {e}")
            print(f"Hata: {e}")
            continue

    print("5 zarar sonrası işlemler durduruldu.")
    logging.info("5 zarar sonrası işlemler durduruldu.")

if __name__ == "__main__":
    main()
