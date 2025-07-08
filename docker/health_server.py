import os
import time
import psutil
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/livez')
def livez():
    return 'alive', 200

@app.route('/metrics')
def metrics():
    data = {
        'cpu_percent': psutil.cpu_percent(interval=0.1),
        'memory_percent': psutil.virtual_memory().percent,
        'timestamp': time.time(),
    }
    return jsonify(data)

if __name__ == '__main__':
    port = int(os.getenv('HEALTH_PORT', '5723'))
    app.run(host='0.0.0.0', port=port)
