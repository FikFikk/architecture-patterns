"""
Unit tests untuk Sidecar Pattern implementations
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
from pathlib import Path


class TestConfigWatcher(unittest.TestCase):
    """Test Config Watcher Sidecar"""
    
    def setUp(self):
        # Create temporary config file
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "config.yaml")
        with open(self.config_file, 'w') as f:
            f.write("version: 1.0\nmessage: test\n")
    
    def tearDown(self):
        # Cleanup
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @patch('config_watcher.requests.post')
    def test_config_change_detection(self, mock_post):
        """Test deteksi perubahan konfigurasi"""
        from config_watcher import ConfigWatcher
        
        mock_post.return_value.status_code = 200
        
        watcher = ConfigWatcher(
            config_file=self.config_file,
            reload_endpoint="http://localhost:8080/reload"
        )
        
        initial_hash = watcher.current_hash
        
        # Modify config
        with open(self.config_file, 'w') as f:
            f.write("version: 2.0\nmessage: updated\n")
        
        # Trigger change handler
        watcher.handle_config_change()
        
        # Verify hash changed dan reload triggered
        self.assertNotEqual(watcher.current_hash, initial_hash)
        self.assertEqual(watcher.reload_count, 1)
        mock_post.assert_called_once()
    
    def test_config_validation(self):
        """Test validasi konfigurasi"""
        from config_watcher import ConfigWatcher
        
        watcher = ConfigWatcher(
            config_file=self.config_file,
            reload_endpoint="http://localhost:8080/reload"
        )
        
        # Valid config
        self.assertTrue(watcher._validate_config())
        
        # Invalid YAML
        with open(self.config_file, 'w') as f:
            f.write("invalid: yaml: syntax: error:")
        
        self.assertFalse(watcher._validate_config())


class TestLoggingSidecar(unittest.TestCase):
    """Test Logging Sidecar"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "app.log")
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @patch('logging_sidecar.requests.post')
    def test_log_forwarding(self, mock_post):
        """Test forwarding log ke remote endpoint"""
        from logging_sidecar import LogForwarder
        
        mock_post.return_value.status_code = 200
        
        forwarder = LogForwarder(
            endpoint="http://elasticsearch:9200",
            batch_size=2
        )
        
        # Forward 2 logs (triggers batch)
        forwarder.forward_logs(
            ["2024-01-01 INFO Test log 1", "2024-01-01 ERROR Test log 2"],
            self.log_file
        )
        
        # Verify forwarding
        self.assertEqual(forwarder.total_forwarded, 2)
        mock_post.assert_called_once()
    
    def test_log_level_detection(self):
        """Test deteksi log level"""
        from logging_sidecar import LogForwarder
        
        forwarder = LogForwarder("http://localhost:9200")
        
        self.assertEqual(forwarder._detect_log_level("ERROR: something failed"), "ERROR")
        self.assertEqual(forwarder._detect_log_level("WARN: be careful"), "WARN")
        self.assertEqual(forwarder._detect_log_level("INFO: normal log"), "INFO")
        self.assertEqual(forwarder._detect_log_level("DEBUG: detailed info"), "DEBUG")
    
    def test_log_parsing(self):
        """Test parsing log entry"""
        from logging_sidecar import LogForwarder
        
        os.environ['POD_NAME'] = 'test-pod'
        os.environ['POD_NAMESPACE'] = 'test-namespace'
        
        forwarder = LogForwarder("http://localhost:9200")
        
        log_entry = forwarder._parse_log_line(
            "2024-01-01 ERROR Test error",
            "/var/log/app.log"
        )
        
        self.assertIn('timestamp', log_entry)
        self.assertIn('message', log_entry)
        self.assertEqual(log_entry['pod_name'], 'test-pod')
        self.assertEqual(log_entry['namespace'], 'test-namespace')
        self.assertEqual(log_entry['level'], 'ERROR')


class TestMetricsCollector(unittest.TestCase):
    """Test Metrics Collector Sidecar"""
    
    @patch('metrics_collector.requests.get')
    def test_metrics_collection(self, mock_get):
        """Test collection metrics dari aplikasi"""
        from metrics_collector import MetricsCollector
        
        # Mock response dari app
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = """
# HELP app_requests_total Total requests
# TYPE app_requests_total counter
app_requests_total 100

# HELP app_errors_total Total errors
# TYPE app_errors_total counter
app_errors_total 5
"""
        
        collector = MetricsCollector(
            app_metrics_url="http://localhost:8080/metrics"
        )
        
        result = collector.collect_metrics()
        
        self.assertTrue(result)
        self.assertIn('app_requests_total', collector.app_metrics)
        self.assertIn('app_errors_total', collector.app_metrics)
    
    @patch('metrics_collector.requests.get')
    def test_scrape_error_handling(self, mock_get):
        """Test handling error saat scrape"""
        from metrics_collector import MetricsCollector
        
        mock_get.side_effect = Exception("Connection failed")
        
        collector = MetricsCollector(
            app_metrics_url="http://localhost:8080/metrics"
        )
        
        result = collector.collect_metrics()
        
        self.assertFalse(result)
        # Verify error counter incremented
        self.assertTrue(collector.scrape_errors._value._value > 0)


class TestIntegration(unittest.TestCase):
    """Integration tests"""
    
    def test_sidecar_coexistence(self):
        """Test multiple sidecars dapat coexist"""
        # Simulasi scenario dengan multiple sidecars
        # dalam real world, mereka share volumes dan network
        
        temp_dir = tempfile.mkdtemp()
        log_file = os.path.join(temp_dir, "app.log")
        config_file = os.path.join(temp_dir, "config.yaml")
        
        # Create files
        with open(log_file, 'w') as f:
            f.write("Test log entry\n")
        
        with open(config_file, 'w') as f:
            f.write("version: 1.0\n")
        
        try:
            from logging_sidecar import LogForwarder
            from config_watcher import ConfigWatcher
            
            # Both sidecars dapat instantiate
            log_forwarder = LogForwarder("http://elasticsearch:9200")
            config_watcher = ConfigWatcher(
                config_file=config_file,
                reload_endpoint="http://localhost:8080/reload"
            )
            
            # Both dapat operate on same filesystem
            self.assertIsNotNone(log_forwarder)
            self.assertIsNotNone(config_watcher)
            
        finally:
            import shutil
            shutil.rmtree(temp_dir)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestConfigWatcher))
    suite.addTests(loader.loadTestsFromTestCase(TestLoggingSidecar))
    suite.addTests(loader.loadTestsFromTestCase(TestMetricsCollector))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
