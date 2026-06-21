#!/usr/bin/env python3
"""
Configuration Watcher Sidecar

Sidecar ini memantau perubahan konfigurasi dari ConfigMap/Secret Kubernetes
atau file konfigurasi eksternal, lalu memberitahu aplikasi utama untuk reload.

Usage:
    python config_watcher.py --config-file /etc/app/config.yaml --reload-endpoint http://localhost:8080/reload
"""

import os
import time
import hashlib
import argparse
import requests
import logging
from pathlib import Path
from typing import Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logging.basicConfig(
    level=logging.INFO,
    format='[CONFIG-WATCHER] %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConfigChangeHandler(FileSystemEventHandler):
    """Handler untuk memantau perubahan file konfigurasi"""
    
    def __init__(self, watcher):
        self.watcher = watcher
    
    def on_modified(self, event):
        """Triggered saat file konfigurasi berubah"""
        if event.is_directory:
            return
        
        if event.src_path == str(self.watcher.config_file):
            logger.info(f"Configuration file changed: {event.src_path}")
            self.watcher.handle_config_change()


class ConfigWatcher:
    """Main configuration watcher class"""
    
    def __init__(
        self,
        config_file: str,
        reload_endpoint: Optional[str] = None,
        reload_signal: Optional[str] = None,
        check_interval: int = 30
    ):
        self.config_file = Path(config_file)
        self.reload_endpoint = reload_endpoint
        self.reload_signal = reload_signal
        self.check_interval = check_interval
        self.current_hash = None
        self.reload_count = 0
        
        if not self.config_file.exists():
            raise ValueError(f"Config file does not exist: {config_file}")
        
        # Get initial hash
        self.current_hash = self._get_file_hash()
        logger.info(f"Initial config hash: {self.current_hash}")
    
    def _get_file_hash(self) -> str:
        """Calculate SHA256 hash of config file"""
        sha256 = hashlib.sha256()
        with open(self.config_file, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def handle_config_change(self):
        """Handle configuration file change"""
        new_hash = self._get_file_hash()
        
        if new_hash == self.current_hash:
            logger.debug("Config hash unchanged, skipping reload")
            return
        
        logger.info(f"Config changed: {self.current_hash[:8]} -> {new_hash[:8]}")
        
        # Validate config sebelum reload
        if not self._validate_config():
            logger.error("Config validation failed, skipping reload")
            return
        
        # Trigger reload
        success = self._trigger_reload()
        
        if success:
            self.current_hash = new_hash
            self.reload_count += 1
            logger.info(f"Config reloaded successfully (total reloads: {self.reload_count})")
        else:
            logger.error("Failed to reload config")
    
    def _validate_config(self) -> bool:
        """Validate configuration file"""
        try:
            # Basic validation - check if file is readable
            with open(self.config_file, 'r') as f:
                content = f.read()
            
            # Add custom validation logic here
            # For example, check YAML/JSON syntax
            if self.config_file.suffix == '.yaml':
                import yaml
                yaml.safe_load(content)
            elif self.config_file.suffix == '.json':
                import json
                json.loads(content)
            
            logger.info("Config validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Config validation error: {e}")
            return False
    
    def _trigger_reload(self) -> bool:
        """Trigger application reload"""
        if self.reload_endpoint:
            return self._reload_via_http()
        elif self.reload_signal:
            return self._reload_via_signal()
        else:
            logger.warning("No reload method configured")
            return False
    
    def _reload_via_http(self) -> bool:
        """Reload via HTTP endpoint"""
        try:
            logger.info(f"Sending reload request to {self.reload_endpoint}")
            response = requests.post(
                self.reload_endpoint,
                timeout=10,
                json={"config_file": str(self.config_file)}
            )
            
            if response.status_code == 200:
                logger.info("Reload request successful")
                return True
            else:
                logger.error(f"Reload request failed: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending reload request: {e}")
            return False
    
    def _reload_via_signal(self) -> bool:
        """Reload via Unix signal (e.g., SIGHUP)"""
        try:
            import signal
            
            # Find app process
            app_pid = self._find_app_process()
            if not app_pid:
                logger.error("Could not find app process")
                return False
            
            sig = getattr(signal, self.reload_signal, signal.SIGHUP)
            logger.info(f"Sending signal {self.reload_signal} to PID {app_pid}")
            os.kill(app_pid, sig)
            return True
            
        except Exception as e:
            logger.error(f"Error sending signal: {e}")
            return False
    
    def _find_app_process(self) -> Optional[int]:
        """Find application process ID"""
        # In Kubernetes pod, app container biasanya PID 1 atau di /proc
        app_name = os.getenv("APP_PROCESS_NAME", "app")
        
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name']):
                if app_name in proc.info['name']:
                    return proc.info['pid']
        except ImportError:
            # Fallback: read from environment or file
            pid_file = os.getenv("APP_PID_FILE", "/var/run/app.pid")
            if os.path.exists(pid_file):
                with open(pid_file) as f:
                    return int(f.read().strip())
        
        return None
    
    def start_watching(self):
        """Start watching config file dengan file system events"""
        logger.info(f"Starting config watcher...")
        logger.info(f"Watching file: {self.config_file}")
        logger.info(f"Reload method: {'HTTP' if self.reload_endpoint else 'Signal'}")
        
        handler = ConfigChangeHandler(self)
        observer = Observer()
        observer.schedule(
            handler,
            str(self.config_file.parent),
            recursive=False
        )
        observer.start()
        
        try:
            while True:
                time.sleep(self.check_interval)
                # Periodic check as backup (untuk kasus di mana file events miss)
                self.handle_config_change()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            observer.stop()
        
        observer.join()
    
    def start_polling(self):
        """Start watching config file dengan polling"""
        logger.info(f"Starting config watcher (polling mode)...")
        logger.info(f"Watching file: {self.config_file}")
        logger.info(f"Check interval: {self.check_interval}s")
        
        try:
            while True:
                time.sleep(self.check_interval)
                self.handle_config_change()
        except KeyboardInterrupt:
            logger.info("Shutting down...")


def main():
    parser = argparse.ArgumentParser(description="Configuration Watcher Sidecar")
    parser.add_argument(
        "--config-file",
        required=True,
        help="Configuration file to watch"
    )
    parser.add_argument(
        "--reload-endpoint",
        help="HTTP endpoint to trigger reload (e.g., http://localhost:8080/reload)"
    )
    parser.add_argument(
        "--reload-signal",
        help="Unix signal to send (e.g., SIGHUP)"
    )
    parser.add_argument(
        "--check-interval",
        type=int,
        default=30,
        help="Check interval in seconds (default: 30)"
    )
    parser.add_argument(
        "--mode",
        choices=["watch", "poll"],
        default="watch",
        help="Watching mode: watch (file events) or poll (periodic check)"
    )
    
    args = parser.parse_args()
    
    if not args.reload_endpoint and not args.reload_signal:
        parser.error("Either --reload-endpoint or --reload-signal must be provided")
    
    try:
        watcher = ConfigWatcher(
            config_file=args.config_file,
            reload_endpoint=args.reload_endpoint,
            reload_signal=args.reload_signal,
            check_interval=args.check_interval
        )
        
        if args.mode == "watch":
            watcher.start_watching()
        else:
            watcher.start_polling()
            
    except Exception as e:
        logger.error(f"Failed to start watcher: {e}")
        exit(1)


if __name__ == "__main__":
    main()
