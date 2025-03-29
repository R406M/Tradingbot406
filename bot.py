import ccxt
import os
import time
import logging
from typing import Optional, Dict

# ---------------------------
# Configuración Actualizada
# ---------------------------
current_position: Optional[str] = None
BALANCE_PERCENTAGE = 0.9  # 90% del balance
TAKE_PROFIT = 0.05         # 5% de ganancia por operación
STOP_LOSS = 0.10           # 10% de pérdida máxima por operación

# Configuración mejorada de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('TradingBot')

# ---------------------------
# Núcleo del Sistema de Trading
# ---------------------------

class TradingEngine:
    def __init__(self):
        self.exchange = self._authenticate()
        self.symbol = os.getenv("TRADING_SYMBOL", "DOGE/USDT")
        
    def _authenticate(self) -> ccxt.kucoin:
        """Autenticación segura con KuCoin"""
        return ccxt.kucoin({
            'apiKey': os.getenv("KUCOIN_API_KEY"),
            'secret': os.getenv("KUCOIN_SECRET"),
            'password': os.getenv("KUCOIN_PASSPHRASE"),
            'enableRateLimit': True
        })
    
    def get_balance(self) -> float:
        """Obtiene 90% del balance disponible"""
        free_balance = self.exchange.fetch_balance()['free']
        base, quote = self.symbol.split('/')
        balance = free_balance[quote if current_position != 'buy' else base]
        return balance * BALANCE_PERCENTAGE
    
    def calculate_position_size(self, price: float) -> float:
        """Calcula tamaño de posición con 90% del balance"""
        balance = self.get_balance()
        return balance / price
    
    def execute_signal(self, signal: str) -> bool:
        """Ejecuta lógica principal de trading"""
        global current_position
        
        try:
            # Cerrar posición si hay señal contraria
            if current_position and current_position != signal:
                self.close_position()
            
            # Ejecutar nueva orden
            price = self.exchange.fetch_ticker(self.symbol)['last']
            amount = self.calculate_position_size(price)
            
            order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side=signal,
                amount=amount
            )
            
            logger.info(f"Orden {signal.upper()} ejecutada: {order}")
            current_position = signal
            
            # Configurar TP/SL
            self.place_oco_order(order, price)
            
            return True
            
        except ccxt.NetworkError as e:
            logger.error(f"Error de red: {str(e)}")
            return False
            
        except ccxt.ExchangeError as e:
            logger.error(f"Error del exchange: {str(e)}")
            return False

    def close_position(self) -> None:
        """Cierra posición actual inmediatamente"""
        global current_position
        
        if not current_position:
            return
            
        try:
            balance = self.get_balance()
            price = self.exchange.fetch_ticker(self.symbol)['last']
            amount = balance / price if current_position == 'sell' else balance
            
            order = self.exchange.create_order(
                symbol=self.symbol,
                type='market',
                side='sell' if current_position == 'buy' else 'buy',
                amount=amount
            )
            
            logger.info(f"Posición {current_position.upper()} cerrada: {order}")
            current_position = None
            
        except Exception as e:
            logger.error(f"Error cerrando posición: {str(e)}")
            raise

    def place_oco_order(self, entry_order: Dict, entry_price: float) -> None:
        """Coloca órdenes OCO (TP/SL)"""
        try:
            # Calcular precios
            take_profit_price = entry_price * (1 + TAKE_PROFIT)
            stop_loss_price = entry_price * (1 - STOP_LOSS)
            
            # Crear orden OCO
            self.exchange.create_order(
                symbol=self.symbol,
                type='STOP_LOSS_LIMIT',  # Tipo específico para KuCoin
                side='SELL',
                amount=entry_order['amount'],
                price=take_profit_price,
                stopPrice=stop_loss_price,
                params={'type': 'OCO'}
            )
            
            logger.info(f"Órdenes colocadas | TP: {take_profit_price} | SL: {stop_loss_price}")
            
        except Exception as e:
            logger.error(f"Error colocando OCO: {str(e)}")
            self.close_position()

# ---------------------------
# Handler Principal desde Webhook
# ---------------------------
trading_engine = TradingEngine()

def execute_order(signal: str) -> bool:
    """Manejador principal para ejecutar señales"""
    if signal not in ['buy', 'sell']:
        logger.error("Señal inválida recibida")
        return False
        
    # Verificar si ya hay TP/SL activo
    if trading_engine.check_active_orders():
        logger.warning("Hay órdenes activas - Cerrando antes de nueva señal")
        trading_engine.close_position()
        
    return trading_engine.execute_signal(signal)
