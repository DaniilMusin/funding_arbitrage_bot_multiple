import os
import time
import logging
import psutil
from flask import Flask, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/livez')
def livez():
    return 'alive', 200

@app.route('/metrics')
def metrics():
    try:
        data = {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'timestamp': time.time(),
        }
        return jsonify(data)
    except Exception as e:
        logging.error(f"Error getting metrics: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('HEALTH_PORT', '5723'))
    logging.info(f"Starting health server on port {port}")
    app.run(host='0.0.0.0', port=port)
