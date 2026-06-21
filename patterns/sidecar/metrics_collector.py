#!/usr/bin/env python3
"""
Metrics Collector Sidecar

Sidecar ini mengumpulkan metrics dari aplikasi utama dan meng-expose-nya
dalam format Prometheus untuk di-scrape oleh monitoring system.

Usage:
    python metrics_collector.py --app-metrics-url http://localhost:8080/metrics --port 9090
"""

import time
import argparse
import logging
import requests
from typing import Dict, List
from http.server import HTTPServer, BaseHTTPRequestHandler
from prometheus_client import (
    CollectorRegistry,
    Gauge,
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST
)

logging.basicConfig(
    level=logging.INFO,
    format='[METRICS-COLLECTOR] %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collect metrics dari aplikasi dan expose untuk Prometheus"""
    
    def __init__(self, app_metrics_url: str, collection_interval: int = 15):
        self.app_metrics_url = app_metrics_url
        self.collection_interval = collection_interval
        self.registry = CollectorRegistry()
        
        # Sidecar metrics
        self.scrape_duration = Histogram(
            'sidecar_scrape_duration_seconds',
            'Time spent scraping app metrics',
            registry=self.registry
        )
        self.scrape_errors = Counter(
            'sidecar_scrape_errors_total',
            'Total number of scrape errors',
            registry=self.registry
        )
        self.last_scrape_success = Gauge(
            'sidecar_last_scrape_success',
            'Whether the last scrape was successful (1=success, 0=failure)',
            registry=self.registry
        )
        
        # App metrics (will be populated from app)
        self.app_metrics: Dict[str, any] = {}
    
    def collect_metrics(self) -> bool:
        """Collect metrics dari aplikasi"""
        try:
            with self.scrape_duration.time():
                response = requests.get(
                    self.app_metrics_url,
                    timeout=10
                )
                
                if response.status_code == 200:
                    self._parse_metrics(response.text)
                    self.last_scrape_success.set(1)
                    logger.debug("Metrics collected successfully")
                    return True
                else:
                    logger.error(f"Failed to collect metrics: {response.status_code}")
                    self.scrape_errors.inc()
                    self.last_scrape_success.set(0)
                    return False
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"Error collecting metrics: {e}")
            self.scrape_errors.inc()
            self.last_scrape_success.set(0)
            return False
    
    def _parse_metrics(self, metrics_text: str):
        """Parse metrics dari response (assume Prometheus format)"""
        # Simple parser - bisa di-extend untuk format lain
        lines = metrics_text.strip().split('\n')
        
        for line in lines:
            if line.startswith('#') or not line.strip():
                continue
            
            try:
                # Parse Prometheus format: metric_name{labels} value timestamp
                parts = line.split()
                if len(parts) >= 2:
                    metric_name = parts[0].split('{')[0]
                    metric_value = float(parts[1])
                    
                    # Create or update metric
                    if metric_name not in self.app_metrics:
                        self.app_metrics[metric_name] = Gauge(
                            f'app_{metric_name}',
                            f'Application metric: {metric_name}',
                            registry=self.registry
                        )
                    
                    self.app_metrics[metric_name].set(metric_value)
                    
            except (ValueError, IndexError) as e:
                logger.debug(f"Could not parse metric line: {line} - {e}")
    
    def get_metrics(self) -> bytes:
        """Get all metrics dalam Prometheus format"""
        return generate_latest(self.registry)


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler untuk metrics endpoint"""
    
    collector = None  # Will be set by server
    
    def do_GET(self):
        """Handle GET request"""
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            
            metrics = self.collector.get_metrics()
            self.wfile.write(metrics)
            
        elif self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
            
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.debug(f"{self.client_address[0]} - {format % args}")


class MetricsServer:
    """HTTP server untuk expose metrics"""
    
    def __init__(self, collector: MetricsCollector, port: int = 9090):
        self.collector = collector
        self.port = port
        self.server = None
    
    def start(self):
        """Start metrics server"""
        logger.info(f"Starting metrics server on port {self.port}")
        
        # Set collector di handler
        MetricsHandler.collector = self.collector
        
        self.server = HTTPServer(('0.0.0.0', self.port), MetricsHandler)
        
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down metrics server...")
            self.server.shutdown()


def run_collector(collector: MetricsCollector):
    """Background thread untuk collect metrics secara periodic"""
    logger.info(f"Starting metrics collection (interval: {collector.collection_interval}s)")
    
    while True:
        try:
            collector.collect_metrics()
            time.sleep(collector.collection_interval)
        except Exception as e:
            logger.error(f"Error in collection loop: {e}")
            time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description="Metrics Collector Sidecar")
    parser.add_argument(
        "--app-metrics-url",
        required=True,
        help="URL of application metrics endpoint"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9090,
        help="Port to expose metrics (default: 9090)"
    )
    parser.add_argument(
        "--collection-interval",
        type=int,
        default=15,
        help="Metrics collection interval in seconds (default: 15)"
    )
    
    args = parser.parse_args()
    
    try:
        # Create collector
        collector = MetricsCollector(
            app_metrics_url=args.app_metrics_url,
            collection_interval=args.collection_interval
        )
        
        # Start collection in background
        import threading
        collection_thread = threading.Thread(
            target=run_collector,
            args=(collector,),
            daemon=True
        )
        collection_thread.start()
        
        # Start metrics server
        server = MetricsServer(collector, args.port)
        server.start()
        
    except Exception as e:
        logger.error(f"Failed to start metrics collector: {e}")
        exit(1)


if __name__ == "__main__":
    main()
