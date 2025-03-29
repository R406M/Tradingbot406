from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from bot import execute_order
import logging
import os

app = Flask(__name__)

# Configuración de logs (solo consola)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Eliminamos FileHandler
)
logger = logging.getLogger(__name__)

# Rate Limiting (máx 10 solicitudes/minuto)
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["10 per minute"]
)

@app.route('/webhook', methods=['POST'])
@limiter.limit("5 per minute")  # Límite específico para esta ruta
def handle_webhook():
    try:
        if not request.is_json:
            logger.warning("Intento de acceso con formato no JSON")
            return jsonify({"status": "error", "message": "Se esperaba JSON"}), 400
        
        data = request.json
        action = data.get('action')
        token = data.get('token')
        
        # Validación de seguridad
        if token != os.getenv("WEBHOOK_TOKEN"):
            logger.error("Intento de acceso con token inválido")
            return jsonify({"status": "error", "message": "Token inválido"}), 401
            
        if action not in ['buy', 'sell']:
            logger.warning(f"Acción inválida recibida: {action}")
            return jsonify({"status": "error", "message": "Acción no válida"}), 400
        
        logger.info(f"Señal recibida: {action.upper()}")
        execute_order(action)
        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"Error crítico: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": "Error interno"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))  # Usa el puerto de Render o 8080
    app.run(host='0.0.0.0', port=port)
