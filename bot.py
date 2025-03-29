import ccxt
import os
import time
import math
import logging
from typing import Tuple, Optional, Dict
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
    """Motor de trading profesional para KuCoin con gestión avanzada de riesgo"""
    
    __slots__ = ['exchange', 'symbol', 'market_info', 'current_position']
    
    def __init__(self):
        self.exchange = self._authenticate()
        self.symbol = os.getenv("TRADING_SYMBOL", "DOGE/USDT")
        self.market_info = self._load_market_info()
        self.current_position: Optional[str] = None  # 'buy'|'sell'|None

    def _authenticate(self) -> ccxt.kucoin:
        """Configuración segura con timeouts y rate limiting"""
        return ccxt.kucoin({
            'apiKey': os.getenv("KUCOIN_API_KEY"),
            'secret': os.getenv("KUCOIN_SECRET"),
            'password': os.getenv("KUCOIN_PASSPHRASE"),
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {
                'adjustForTimeDifference': True,
                'recvWindow': 10000
            }
        })

    @on_exception(expo, ccxt.NetworkError, max_tries=5, jitter=None)
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
        """Calcula tamaño de posición con gestión de riesgo avanzada"""
        balance = self._get_available_balance()
        risk_adjusted_balance = balance * 0.9  # 90% del balance
        raw_amount = risk_adjusted_balance / price
        
        # Ajuste de precisión según reglas del exchange
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
            params={'timeInForce': 'IOC'}  # Immediate or Cancel
        )

    def _place_oco_order(self, amount: float, entry_price: float):
        """Orden OCO (One Cancels Other) con TP/SL dinámicos"""
        try:
            tp_price = entry_price * 1.05
            sl_price = entry_price * 0.90
            
            return self.exchange.create_order(
                symbol=self.symbol,
                type='STOP_LIMIT',
                side='sell',
                amount=amount,
                price=tp_price,
                stopPrice=sl_price,
                params={
                    'type': 'OCO',
                    'stopLimitPrice': sl_price,
                    'stopLimitTimeInForce': 'GTC'
                }
            )
        except Exception as e:
            logger.error(f"Fallo OCO: {str(e)}")
            self._emergency_close()
            raise

    @on_exception(expo, ccxt.NetworkError, max_tries=5)
    def _emergency_close(self):
        """Cierre de emergencia de posición activa"""
        if not self.current_position:
            return

        try:
            balance = self._get_available_balance()
            price = self._get_current_price()
            amount = balance / price if self.current_position == 'sell' else balance
            
            self._execute_market_order(
                side='sell' if self.current_position == 'buy' else 'buy',
                amount=amount
            )
            self.current_position = None
            logger.warning("Posición cerrada por emergencia")
            
        except ccxt.BaseError as e:
            logger.critical(f"Fallo cierre emergencia: {str(e)}")
            raise

    def process_signal(self, signal: str) -> bool:
        """Manejador principal de señales de trading"""
        if signal not in ('buy', 'sell'):
            logger.error(f"Señal inválida: {signal}")
            return False

        try:
            # Verificar posición existente
            if self.current_position and self.current_position != signal:
                logger.info(f"Cerrando posición {self.current_position} para nueva señal")
                self._emergency_close()

            # Calcular tamaño de posición
            price = self._get_current_price()
            amount, risk_capital = self._calculate_position_size(price)
            
            logger.info(f"""
            🚀 Nueva Operación
            ------------------
            Señal: {signal.upper()}
            Capital en riesgo: {risk_capital:.4f} {self.symbol.split('/')[1]}
            Monto: {amount:.2f} {self.symbol.split('/')[0]}
            Precio entrada: {price:.8f}
            TP: {price * 1.05:.8f} (+5%)
            SL: {price * 0.90:.8f} (-10%)
            """)

            # Ejecutar orden principal
            order = self._execute_market_order(signal, amount)
            self.current_position = signal
            
            # Colocar órdenes de protección
            self._place_oco_order(amount, price)
            
            logger.info(f"Orden ejecutada exitosamente: {order['id']}")
            return True

        except ccxt.InsufficientFunds as e:
            logger.error("Fondos insuficientes para ejecutar la operación")
            return False
            
        except ccxt.NetworkError as e:
            logger.error("Fallo de red, reintentando...")
            raise
            
        except Exception as e:
            logger.critical(f"Error crítico: {str(e)}", exc_info=True)
            self._emergency_close()
            return False
