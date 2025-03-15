import ccxt
import os
import time
from decimal import Decimal, ROUND_DOWN
import logging

# Eliminamos load_dotenv() para producción
# (Si pruebas localmente, descoméntalo y crea el .env)
# from dotenv import load_dotenv
# load_dotenv()

# Configuración de logs (solo consola)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Eliminamos FileHandler
)
logger = logging.getLogger(__name__)

# Credenciales de KuCoin (¡cargadas desde .env!)
KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY")
KUCOIN_SECRET = os.getenv("KUCOIN_SECRET")
KUCOIN_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")

# Verificación de credenciales
if not all([KUCOIN_API_KEY, KUCOIN_SECRET, KUCOIN_PASSPHRASE]):
    logger.error("❌ Credenciales de KuCoin no configuradas en .env")
    raise ValueError("Verifica el archivo .env")

def get_balance(currency):
    """
    Obtiene el saldo disponible de una moneda en KuCoin.
    """
    exchange = ccxt.kucoin({
        'apiKey': KUCOIN_API_KEY,
        'secret': KUCOIN_SECRET,
        'password': KUCOIN_PASSPHRASE,
    })
    balance = exchange.fetch_balance()
    return balance['total'].get(currency, 0)

def create_order(symbol, type, side, amount):
    """
    Crea una orden en KuCoin.
    """
    exchange = ccxt.kucoin({
        'apiKey': KUCOIN_API_KEY,
        'secret': KUCOIN_SECRET,
        'password': KUCOIN_PASSPHRASE,
    })
    order = exchange.create_order(symbol, type, side, amount)
    return order

def calculate_quantity(balance, price):
    """
    Calcula la cantidad a operar basada en el 90% del saldo.
    """
    return (balance * BALANCE_PERCENTAGE) / price

def get_current_price(symbol):
    """
    Obtiene el precio actual del símbolo.
    """
    exchange = ccxt.kucoin({
        'apiKey': KUCOIN_API_KEY,
        'secret': KUCOIN_SECRET,
        'password': KUCOIN_PASSPHRASE,
    })
    ticker = exchange.fetch_ticker(symbol)
    return Decimal(ticker['last'])

def close_position(symbol):
    """
    Cierra la posición actual (compra o venta).
    """
    global current_position
    if current_position is None:
        logger.info("No hay posición abierta para cerrar.")
        return True

    try:
        if current_position == 'buy':
            # Si la posición actual es de compra, vendemos para cerrar
            currency = symbol.split('/')[0]  # DOGE en "DOGE/USDT"
            balance = get_balance(currency)
            price = get_current_price(symbol)
            amount = calculate_quantity(balance, price)
            order = create_order(symbol, 'market', 'sell', amount)
            logger.info(f"Posición de compra cerrada: {order}")

        elif current_position == 'sell':
            # Si la posición actual es de venta, compramos para cerrar
            currency = symbol.split('/')[1]  # USDT en "DOGE/USDT"
            balance = get_balance(currency)
            price = get_current_price(symbol)
            amount = calculate_quantity(balance, price)
            order = create_order(symbol, 'market', 'buy', amount)
            logger.info(f"Posición de venta cerrada: {order}")

        current_position = None  # Reseteamos la posición actual
        return True

    except Exception as e:
        logger.error(f"Error al cerrar la posición: {str(e)}")
        return False

def execute_order(action):
    """
    Ejecuta una orden en KuCoin con TP y SL, y cierra la posición actual si es necesario.
    """
    global current_position
    max_retries = 3
    retry_delay = 1  # segundos
    symbol = os.getenv("TRADING_SYMBOL", "DOGE/USDT")

    # Si hay una posición abierta y la nueva señal es en contra, cerramos la posición actual
    if current_position is not None and current_position != action:
        logger.info(f"Señal en contra recibida. Cerrando posición actual ({current_position}).")
        if not close_position(symbol):
            logger.error("No se pudo cerrar la posición actual.")
            return False

    for attempt in range(max_retries):
        try:
            # Obtener el saldo disponible
            if action == "buy":
                currency = symbol.split('/')[1]  # USDT en "DOGE/USDT"
                balance = get_balance(currency)
                price = get_current_price(symbol)
                amount = calculate_quantity(balance, price)
                order = create_order(symbol, 'market', 'buy', amount)
                logger.info(f"Orden de compra ejecutada: {order}")
                current_position = 'buy'  # Actualizamos la posición actual

                # Configurar TP y SL
                setup_take_profit_and_stop_loss(symbol, amount, price)
                return True

            elif action == "sell":
                currency = symbol.split('/')[0]  # DOGE en "DOGE/USDT"
                balance = get_balance(currency)
                price = get_current_price(symbol)
                amount = calculate_quantity(balance, price)
                order = create_order(symbol, 'market', 'sell', amount)
                logger.info(f"Orden de venta ejecutada: {order}")
                current_position = 'sell'  # Actualizamos la posición actual

                # Configurar TP y SL
                setup_take_profit_and_stop_loss(symbol, amount, price)
                return True

        except ccxt.NetworkError as e:
            logger.warning(f"Error de red (Intento {attempt+1}/{max_retries}): {str(e)}")
            time.sleep(retry_delay ** attempt)
        except ccxt.ExchangeError as e:
            logger.error(f"Error del exchange: {str(e)}")
            return False
        except Exception as e:
            logger.critical(f"Error inesperado: {str(e)}")
            return False

    logger.error("Falló después de 3 intentos")
    return False

def setup_take_profit_and_stop_loss(symbol, amount, entry_price):
    """
    Configura órdenes de take profit y stop loss.
    """
    exchange = ccxt.kucoin({
        'apiKey': KUCOIN_API_KEY,
        'secret': KUCOIN_SECRET,
        'password': KUCOIN_PASSPHRASE,
    })

    # Calcular precios de TP y SL
    take_profit_price = entry_price * (1 + TAKE_PROFIT_PERCENTAGE)
    stop_loss_price = entry_price * (1 - STOP_LOSS_PERCENTAGE)

    # Crear órdenes limit para TP y SL
    try:
        # Orden de take profit (venta)
        exchange.create_order(symbol, 'limit', 'sell', amount, take_profit_price)
        logger.info(f"Take profit configurado a {take_profit_price}")

        # Orden de stop loss (venta)
        exchange.create_order(symbol, 'limit', 'sell', amount, stop_loss_price)
        logger.info(f"Stop loss configurado a {stop_loss_price}")

    except Exception as e:
        logger.error(f"Error al configurar TP/SL: {str(e)}")
