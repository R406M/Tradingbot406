from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from bot import execute_order
import logging
import os
import json
from typing import Dict, Any

# Configuración de aplicación Flask
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Configuración avanzada de logging
logging.basicConfig(
    level=logging.INFO if os.getenv('FLASK_ENV') == 'production' else logging.DEBUG,
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('TradingWebhook')
logger.setLevel(logging.DEBUG if os.getenv('DEBUG') else logging.INFO)

# Configuración de Rate Limiting para producción
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri="memory://" if os.getenv('FLASK_ENV') == 'development' else os.getenv('REDIS_URL', 'memory://'),
    default_limits=["200 per hour", "50 per minute"] if os.getenv('FLASK_ENV') == 'production' else ["unlimited"],
    strategy="fixed-window"
)

def validate_webhook_payload(data: Dict[str, Any]) -> bool:
    """Validación avanzada del payload del webhook"""
    required_fields = {'action', 'token', 'symbol', 'timestamp'}
    return all(field in data for field in required_fields)

@app.route('/webhook', methods=['POST'])
@limiter.limit("20 per minute")
def handle_webhook() -> tuple:
    """Endpoint principal para el webhook de trading"""
    try:
        if not request.is_json:
            logger.warning("Intento de acceso con formato no JSON", extra={
                "client": request.remote_addr,
                "path": request.path
            })
            return jsonify({"status": "error", "code": "INVALID_FORMAT"}), 400

        data: Dict[str, Any] = request.get_json()
        
        if not validate_webhook_payload(data):
            logger.error("Payload incompleto", extra={"payload": data})
            return jsonify({"status": "error", "code": "INVALID_PAYLOAD"}), 400

        if data['token'] != os.getenv("WEBHOOK_TOKEN"):
            logger.warning("Intento de acceso no autorizado", extra={
                "client_ip": request.remote_addr,
                "received_token": data['token'][:3] + "***"
            })
            return jsonify({"status": "error", "code": "INVALID_TOKEN"}), 401

        logger.info("Señal recibida", extra={
            "action": data['action'],
            "symbol": data.get('symbol'),
            "source": data.get('source', 'unknown')
        })

        result = execute_order(
            signal=data['action'],
            symbol=data.get('symbol', os.getenv("DEFAULT_SYMBOL"))
        )

        if result.get('status') == 'success':
            return jsonify({
                "status": "success",
                "order_id": result.get('id'),
                "executed_price": result.get('price'),
                "symbol": result.get('symbol')
            }), 200
        else:
            logger.error("Error en ejecución", extra={"error_code": result.get('code')})
            return jsonify({
                "status": "error",
                "code": result.get('code', 'UNKNOWN_ERROR')
            }), 500

    except Exception as e:
        logger.critical("Error crítico en el webhook", 
                      exc_info=True,
                      extra={"stack_trace": True})
        return jsonify({
            "status": "error",
            "code": "INTERNAL_ERROR",
            "message": "Problema interno del servidor"
        }), 500

@app.route('/health', methods=['GET'])
@limiter.exempt
def health_check() -> tuple:
    """Endpoint de verificación de salud"""
    return jsonify({
        "status": "ok",
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "environment": os.getenv("FLASK_ENV", "development")
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))  # Usa el puerto de Render o 5000 localmente
    app.run(host='0.0.0.0', port=port)
