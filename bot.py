import ccxt
import os
import time
import math
import logging
from typing import Tuple, Optional, Dict
from backoff import expo, on_exception

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('KucoinTrader')
logger.setLevel(logging.DEBUG if os.getenv('DEBUG') else logging.INFO)

class TradingEngine:
    """Motor de trading para KuCoin"""
    
    __slots__ = ['exchange', 'symbol', 'market_info', 'current_position']
    
    def __init__(self):
        self.exchange = self._authenticate()
        self.symbol = os.getenv("TRADING_SYMBOL", "DOGE/USDT")
        self.market_info = self._load_market_info()
        self.current_position: Optional[str] = None

    def _authenticate(self) -> ccxt.kucoin:
        """Autenticación segura"""
        return ccxt.kucoin({
            'apiKey': os.getenv("KUCOIN_API_KEY"),
            'secret': os.getenv("KUCOIN_SECRET"),
            'password': os.getenv("KUCOIN_PASSPHRASE"),
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {'adjustForTimeDifference': True}
        })

    @on_exception(expo, ccxt.NetworkError, max_tries=5)
    def _load_market_info(self) -> Dict:
        """Carga información del mercado"""
        market = self.exchange.load_markets()[self.symbol]
        if not market['active']:
            raise RuntimeError(f"Mercado {self.symbol} inactivo")
        return market

    @on_exception(expo, ccxt.NetworkError, max_tries=3)
    def _get_current_price(self) -> float:
        """Obtiene precio actual"""
        ticker = self.exchange.fetch_ticker(self.symbol)
        return float(ticker['last'])

    def _calculate_position_size(self, price: float) -> Tuple[float, float]:
        """Calcula tamaño de posición"""
        balance = self._get_available_balance()
        risk_adjusted_balance = balance * 0.9
        raw_amount = risk_adjusted_balance / price
        
        step = self.market_info['precision']['amount']
        amount = math.floor(raw_amount / step) * step
        
        min_amount = self.market_info['limits']['amount']['min']
        if amount < min_amount:
            raise ValueError(f"Monto mínimo no alcanzado: {min_amount}")
            
        return amount, risk_adjusted_balance

    @on_exception(expo, ccxt.NetworkError, max_tries=3)
    def _get_available_balance(self) -> float:
        """Obtiene balance disponible"""
        base, quote = self.symbol.split('/')
        balance = self.exchange.fetch_balance()['free'][quote]
        return balance * 0.999

    def _execute_market_order(self, side: str, amount: float) -> Dict:
        """Ejecuta orden de mercado"""
        return self.exchange.create_order(
            symbol=self.symbol,
            type='market',
            side=side,
            amount=amount,
            params={'timeInForce': 'IOC'}
        )

    def process_signal(self, signal: str) -> bool:
        """Procesa señal de trading"""
        if signal.lower() not in ('buy', 'sell'):
            logger.error(f"Señal inválida: {signal}")
            return False

        try:
            if self.current_position and self.current_position != signal:
                self._emergency_close()

            price = self._get_current_price()
            amount, _ = self._calculate_position_size(price)
            
            order = self._execute_market_order(signal, amount)
            self.current_position = signal
            
            logger.info(f"Orden ejecutada: {order['id']}")
            return True

        except ccxt.InsufficientFunds:
            logger.error("Fondos insuficientes")
            return False
            
        except Exception as e:
            logger.critical(f"Error: {str(e)}")
            self._emergency_close()
            return False

# Instancia única del motor
_engine = TradingEngine()

# Interfaz pública para el webhook
def execute_order(signal: str, symbol: str) -> dict:  # ✅ Asegurar parámetros correctos
    return _engine.process_signal(signal, symbol)  # Ajustar según tu implementación
