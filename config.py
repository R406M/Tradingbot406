import os
# Eliminamos load_dotenv() para producción
# from dotenv import load_dotenv
# load_dotenv()

KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY")
KUCOIN_SECRET = os.getenv("KUCOIN_SECRET")
KUCOIN_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN")
TRADING_SYMBOL = os.getenv("TRADING_SYMBOL", "DOGE/USDT")
