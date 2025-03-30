import ccxt
import os
import time
import math
import logging
from typing import Tuple, Optional, Dict, Union
from backoff import expo, on_exception

# Configuración de logging profesional
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('KucoinTrader')
logger.setLevel(logging.DEBUG if os.getenv('DEBUG') else logging.INFO)

class TradingEngine:
    """Motor de trading profesional para KuCoin"""
    
    __slots__ = ['exchange', 'symbol', 'market_info', 'current_position']
    
    def __init__(self):
        self.exchange = self._authenticate()
        self.symbol = os.getenv("TRADING_SYMBOL", "DOGE/USDT")
        self.market_info = self._load_market_info()
        self.current_position: Optional[str] = None

    def _authenticate(self) -> ccxt.kucoin:
        """Configuración segura con timeouts y rate limiting"""
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
        """Carga información del mercado con validación"""
        market = self.exchange.load_markets()[self.symbol]
        if not market['active']:
            raise RuntimeError(f"Mercado {self.symbol} inactivo")
        return market

    @on_exception(expo, ccxt.NetworkError, max_tries=3)
    def _get_current_price(self) -> float:
        """Obtiene precio actual con validación de mercado"""
        ticker = self.exchange.fetch_ticker(self.symbol)
        return float(ticker['last'])

    def _calculate_position_size(self, price: float) -> Tuple[float, float]:
        """Calcula tamaño de posición con gestión de riesgo"""
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
        """Balance disponible con ajuste por comisiones"""
        base, quote = self.symbol.split('/')
        balance = self.exchange.fetch_balance()['free'][quote]
        return balance * 0.999  # 0.1% fee adjustment

    def _execute_market_order(self, side: str, amount: float) -> Dict:
        """Ejecuta orden de mercado con protección contra slippage"""
        return self.exchange.create_order(
            symbol=self.symbol,
            type='market',
            side=side,
            amount=amount,
            params={'timeInForce': 'IOC'}
        )

    def process_signal(self, signal: str, symbol: str) -> Dict[str, Union[str, float]]:
        """Manejador principal de señales de trading"""
        try:
            # Actualizar símbolo si es diferente
            if symbol != self.symbol:
                self.symbol = symbol
                self.market_info = self._load_market_info()
                
            # Validar señal
            signal = signal.lower()
            if signal not in ('buy', 'sell'):
                raise ValueError(f"Señal inválida: {signal}")

            # Verificar posición existente
            if self.current_position and self.current_position != signal:
                self._emergency_close()

            # Calcular tamaño de posición
            price = self._get_current_price()
            amount, _ = self._calculate_position_size(price)
            
            # Ejecutar orden
            order = self._execute_market_order(signal, amount)
            self.current_position = signal
            
            logger.info(f"Orden ejecutada: {order['id']}")
            
            return {
                "status": "success",
                "id": order["id"],
                "price": float(order["average"]),
                "symbol": self.symbol
            }

        except ccxt.InsufficientFunds as e:
            logger.error("Fondos insuficientes para ejecutar la operación")
            return {"status": "error", "code": "INSUFFICIENT_FUNDS"}
            
        except ccxt.NetworkError as e:
            logger.error("Error de red: %s", str(e))
            return {"status": "error", "code": "NETWORK_ERROR"}
            
        except Exception as e:
            logger.critical(f"Error crítico: {str(e)}", exc_info=True)
            self._emergency_close()
            return {"status": "error", "code": "INTERNAL_ERROR"}

    def _emergency_close(self):
        """Cierre de emergencia de posición activa"""
        try:
            if self.current_position:
                balance = self._get_available_balance()
                price = self._get_current_price()
                amount = balance / price if self.current_position == 'sell' else balance
                
                self._execute_market_order(
                    'sell' if self.current_position == 'buy' else 'buy',
                    amount
                )
                self.current_position = None
                logger.warning("Posición cerrada por emergencia")
                
        except Exception as e:
            logger.critical(f"Fallo en cierre de emergencia: {str(e)}")

# Instancia singleton del motor
_engine = TradingEngine()

def execute_order(signal: str, symbol: str) -> Dict[str, Union[str, float]]:
    """Interfaz pública para ejecución de órdenes"""
    try:
        return _engine.process_signal(signal, symbol)
    except Exception as e:
        logger.critical(f"Error en execute_order: {str(e)}")
        return {"status": "error", "code": "UNHANDLED_EXCEPTION"}
