#!/usr/bin/env python3
"""
Logging Sidecar Implementation

Sidecar ini mengumpulkan log dari aplikasi utama dan mengirimkannya
ke sistem logging terpusat (misalnya Elasticsearch, Loki, CloudWatch).

Usage:
    python logging_sidecar.py --log-dir /var/log/app --endpoint http://log-server:9200
"""

import os
import time
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Setup logging untuk sidecar itu sendiri
logging.basicConfig(
    level=logging.INFO,
    format='[SIDECAR] %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LogFileHandler(FileSystemEventHandler):
    """Handler untuk memantau perubahan file log"""
    
    def __init__(self, forwarder):
        self.forwarder = forwarder
        self.file_positions = {}
    
    def on_modified(self, event):
        """Triggered saat file log berubah"""
        if event.is_directory:
            return
        
        if event.src_path.endswith('.log'):
            logger.debug(f"Log file modified: {event.src_path}")
            self.read_new_lines(event.src_path)
    
    def read_new_lines(self, filepath):
        """Baca baris-baris baru dari file log"""
        try:
            # Track posisi terakhir dibaca
            if filepath not in self.file_positions:
                self.file_positions[filepath] = 0
            
            with open(filepath, 'r') as f:
                f.seek(self.file_positions[filepath])
                new_lines = f.readlines()
                self.file_positions[filepath] = f.tell()
            
            if new_lines:
                self.forwarder.forward_logs(new_lines, filepath)
                
        except Exception as e:
            logger.error(f"Error reading log file {filepath}: {e}")


class LogForwarder:
    """Mengirim log ke endpoint remote"""
    
    def __init__(self, endpoint: str, batch_size: int = 100):
        self.endpoint = endpoint
        self.batch_size = batch_size
        self.buffer = []
        self.total_forwarded = 0
        self.total_errors = 0
    
    def forward_logs(self, log_lines: List[str], source_file: str):
        """Forward log lines ke remote endpoint"""
        for line in log_lines:
            log_entry = self._parse_log_line(line, source_file)
            self.buffer.append(log_entry)
            
            if len(self.buffer) >= self.batch_size:
                self._flush_buffer()
    
    def _parse_log_line(self, line: str, source: str) -> Dict:
        """Parse log line dan tambahkan metadata"""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "message": line.strip(),
            "source": source,
            "pod_name": os.getenv("POD_NAME", "unknown"),
            "namespace": os.getenv("POD_NAMESPACE", "default"),
            "container": os.getenv("CONTAINER_NAME", "app"),
            "level": self._detect_log_level(line)
        }
    
    def _detect_log_level(self, line: str) -> str:
        """Deteksi log level dari line"""
        line_upper = line.upper()
        if "ERROR" in line_upper or "FATAL" in line_upper:
            return "ERROR"
        elif "WARN" in line_upper:
            return "WARN"
        elif "INFO" in line_upper:
            return "INFO"
        elif "DEBUG" in line_upper:
            return "DEBUG"
        return "INFO"
    
    def _flush_buffer(self):
        """Kirim buffered logs ke endpoint"""
        if not self.buffer:
            return
        
        try:
            # Elasticsearch bulk format
            payload = "\n".join([
                json.dumps({"index": {"_index": "app-logs"}}) + "\n" + json.dumps(log)
                for log in self.buffer
            ])
            
            response = requests.post(
                f"{self.endpoint}/_bulk",
                data=payload,
                headers={"Content-Type": "application/x-ndjson"},
                timeout=10
            )
            
            if response.status_code == 200:
                self.total_forwarded += len(self.buffer)
                logger.info(f"Forwarded {len(self.buffer)} log entries (total: {self.total_forwarded})")
            else:
                self.total_errors += len(self.buffer)
                logger.error(f"Failed to forward logs: {response.status_code} - {response.text}")
            
        except requests.exceptions.RequestException as e:
            self.total_errors += len(self.buffer)
            logger.error(f"Error forwarding logs: {e}")
        
        finally:
            self.buffer = []
    
    def flush(self):
        """Force flush remaining logs"""
        self._flush_buffer()


class LoggingSidecar:
    """Main sidecar class"""
    
    def __init__(self, log_dir: str, endpoint: str, batch_size: int = 100):
        self.log_dir = Path(log_dir)
        self.forwarder = LogForwarder(endpoint, batch_size)
        self.observer = Observer()
        
        if not self.log_dir.exists():
            raise ValueError(f"Log directory does not exist: {log_dir}")
    
    def start(self):
        """Start watching log directory"""
        logger.info(f"Starting logging sidecar...")
        logger.info(f"Watching directory: {self.log_dir}")
        logger.info(f"Forwarding to: {self.forwarder.endpoint}")
        
        # Setup file watcher
        handler = LogFileHandler(self.forwarder)
        self.observer.schedule(handler, str(self.log_dir), recursive=True)
        self.observer.start()
        
        # Read existing log files first
        self._read_existing_logs(handler)
        
        try:
            while True:
                time.sleep(5)
                # Periodic flush untuk logs yang mungkin belum batch penuh
                self.forwarder.flush()
                
                # Print stats
                if self.forwarder.total_forwarded > 0 or self.forwarder.total_errors > 0:
                    logger.info(
                        f"Stats - Forwarded: {self.forwarder.total_forwarded}, "
                        f"Errors: {self.forwarder.total_errors}"
                    )
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.stop()
    
    def _read_existing_logs(self, handler):
        """Read existing log files on startup"""
        logger.info("Reading existing log files...")
        for log_file in self.log_dir.glob("**/*.log"):
            logger.info(f"Processing: {log_file}")
            handler.read_new_lines(str(log_file))
    
    def stop(self):
        """Stop the sidecar"""
        self.observer.stop()
        self.observer.join()
        self.forwarder.flush()
        logger.info("Sidecar stopped")


def main():
    parser = argparse.ArgumentParser(description="Logging Sidecar")
    parser.add_argument(
        "--log-dir",
        default="/var/log/app",
        help="Directory containing application logs"
    )
    parser.add_argument(
        "--endpoint",
        default="http://elasticsearch:9200",
        help="Log aggregation endpoint (Elasticsearch, Loki, etc.)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of log entries to batch before sending"
    )
    
    args = parser.parse_args()
    
    try:
        sidecar = LoggingSidecar(
            log_dir=args.log_dir,
            endpoint=args.endpoint,
            batch_size=args.batch_size
        )
        sidecar.start()
    except Exception as e:
        logger.error(f"Failed to start sidecar: {e}")
        exit(1)


if __name__ == "__main__":
    main()
