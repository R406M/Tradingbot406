import os
import sys
from typing import Optional

class InvalidConfigurationError(Exception):
    """Excepción personalizada para errores de configuración"""
    pass

def get_env_var(name: str, default: Optional[str] = None) -> str:
    """Obtiene y valida variables de entorno críticas"""
    value = os.getenv(name, default)
    
    if not value and default is None:
        raise InvalidConfigurationError(
            f"❌ Variable de entorno faltante: {name} | "
            "Verifica tu configuración en Render"
        )
        
    if name.endswith(('_KEY', '_SECRET', '_TOKEN')) and 'example' in value:
        raise InvalidConfigurationError(
            f"❌ Valor por defecto detectado en {name} | "
            "Usa tus credenciales reales"
        )
        
    return value

# ---------------------------
# Configuración Validada
# ---------------------------
try:
    KUCOIN_API_KEY = get_env_var("KUCOIN_API_KEY")
    KUCOIN_SECRET = get_env_var("KUCOIN_SECRET")
    KUCOIN_PASSPHRASE = get_env_var("KUCOIN_PASSPHRASE")
    WEBHOOK_TOKEN = get_env_var("WEBHOOK_TOKEN")
    
    TRADING_SYMBOL = get_env_var(
        "TRADING_SYMBOL", 
        "DOGE/USDT"
    ).replace('-', '/')  # Normaliza formato

except InvalidConfigurationError as e:
    sys.exit(f"ERROR DE CONFIGURACIÓN: {str(e)}")
