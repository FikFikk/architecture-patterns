#!/usr/bin/env python3
"""
Simple Flask application untuk demonstrasi Sidecar Pattern

Aplikasi ini:
- Menulis log ke /var/log/app/app.log
- Expose metrics di /metrics
- Mendukung config reload di /reload
"""

from flask import Flask, jsonify, request
import logging
import os
import time
import yaml
from datetime import datetime

app = Flask(__name__)

# Setup logging ke file
log_dir = "/var/log/app"
os.makedirs(log_dir, exist_ok=True)

file_handler = logging.FileHandler(f"{log_dir}/app.log")
file_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)

app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

# Config
config_file = "/etc/app/config.yaml"
app_config = {}

def load_config():
    """Load configuration dari file"""
    global app_config
    try:
        if os.path.exists(config_file):
            with open(config_file) as f:
                app_config = yaml.safe_load(f)
                app.logger.info(f"Config loaded: {app_config}")
        else:
            app_config = {"message": "Hello from Sidecar Demo", "version": "1.0"}
    except Exception as e:
        app.logger.error(f"Failed to load config: {e}")

# Load config on startup
load_config()

# Metrics
request_count = 0
error_count = 0
start_time = time.time()

@app.route('/')
def index():
    """Main endpoint"""
    global request_count
    request_count += 1
    
    app.logger.info(f"Request to / from {request.remote_addr}")
    
    return jsonify({
        "message": app_config.get("message", "Hello"),
        "version": app_config.get("version", "unknown"),
        "timestamp": datetime.utcnow().isoformat(),
        "requests": request_count
    })

@app.route('/api/data')
def get_data():
    """Data endpoint"""
    global request_count
    request_count += 1
    
    app.logger.info("Request to /api/data")
    
    return jsonify({
        "data": [1, 2, 3, 4, 5],
        "count": 5
    })

@app.route('/api/error')
def trigger_error():
    """Endpoint untuk testing error logging"""
    global error_count
    error_count += 1
    
    app.logger.error("Error endpoint triggered!")
    
    return jsonify({"error": "This is a test error"}), 500

@app.route('/metrics')
def metrics():
    """Expose metrics untuk sidecar"""
    uptime = time.time() - start_time
    
    metrics_text = f"""# HELP app_requests_total Total number of requests
# TYPE app_requests_total counter
app_requests_total {request_count}

# HELP app_errors_total Total number of errors
# TYPE app_errors_total counter
app_errors_total {error_count}

# HELP app_uptime_seconds Application uptime in seconds
# TYPE app_uptime_seconds gauge
app_uptime_seconds {uptime:.2f}
"""
    
    return metrics_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route('/reload', methods=['POST'])
def reload_config():
    """Endpoint untuk config reload dari sidecar"""
    app.logger.info("Reload config triggered by sidecar")
    
    try:
        load_config()
        return jsonify({"status": "success", "config": app_config})
    except Exception as e:
        app.logger.error(f"Failed to reload config: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
