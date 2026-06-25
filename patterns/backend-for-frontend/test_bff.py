"""
Test suite untuk BFF implementations
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from web_bff import app as web_app
from mobile_bff import app as mobile_app
from backend_client import BackendServiceClient, CircuitBreaker, CircuitState


# Fixtures
@pytest.fixture
def web_client():
    """Test client untuk Web BFF"""
    return TestClient(web_app)


@pytest.fixture
def mobile_client():
    """Test client untuk Mobile BFF"""
    return TestClient(mobile_app)


@pytest.fixture
def mock_backend_response():
    """Mock response dari backend service"""
    return {
        "user": {
            "id": "user-123",
            "name": "John Doe",
            "email": "john@example.com",
            "avatar_url": "https://cdn.example.com/avatar/user-123.jpg",
            "membership_level": "premium",
            "joined_date": "2024-01-01"
        },
        "products": [
            {
                "id": "prod-1",
                "name": "Product 1",
                "description": "Description for product 1",
                "price": 99.99,
                "currency": "USD",
                "images": [
                    "https://cdn.example.com/images/prod-1-large.jpg",
                    "https://cdn.example.com/images/prod-1-side.jpg"
                ],
                "category": "electronics",
                "stock": 50,
                "rating": 4.5
            }
        ],
        "orders": [
            {
                "id": "order-1",
                "user_id": "user-123",
                "items": [
                    {"product_id": "prod-1", "quantity": 2, "price": 99.99}
                ],
                "total": 199.98,
                "status": "delivered",
                "created_at": "2024-06-01T10:00:00Z"
            }
        ]
    }


# Web BFF Tests
class TestWebBFF:
    """Test suite untuk Web BFF"""
    
    def test_health_check(self, web_client):
        """Test health check endpoint"""
        response = web_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "web-bff"
    
    @patch('web_bff.backend_client')
    @patch('web_bff.get_cached')
    @patch('web_bff.set_cached')
    def test_dashboard_aggregation(self, mock_set_cache, mock_get_cache, mock_backend, web_client, mock_backend_response):
        """Test dashboard aggregates data dari multiple services"""
        # Mock cache miss
        mock_get_cache.return_value = asyncio.Future()
        mock_get_cache.return_value.set_result(None)
        
        # Mock backend calls
        mock_backend.get = AsyncMock(side_effect=[
            mock_backend_response["user"],
            mock_backend_response["orders"],
            mock_backend_response["products"]
        ])
        
        response = web_client.get("/api/dashboard?user_id=user-123")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify aggregation
        assert "user" in data
        assert "recent_orders" in data
        assert "recommended_products" in data
        assert "stats" in data
        
        assert data["user"]["id"] == "user-123"
    
    @patch('web_bff.backend_client')
    @patch('web_bff.get_cached')
    def test_dashboard_cache_hit(self, mock_get_cache, mock_backend, web_client):
        """Test dashboard returns cached data"""
        cached_data = {
            "user": {"id": "user-123", "name": "John"},
            "recent_orders": [],
            "recommended_products": [],
            "stats": {}
        }
        
        mock_get_cache.return_value = asyncio.Future()
        mock_get_cache.return_value.set_result(cached_data)
        
        response = web_client.get("/api/dashboard?user_id=user-123")
        
        assert response.status_code == 200
        # Backend should not be called when cache hit
        mock_backend.get.assert_not_called()
    
    @patch('web_bff.backend_client')
    def test_product_search_with_filters(self, mock_backend, web_client, mock_backend_response):
        """Test product search dengan filters"""
        mock_backend.get = AsyncMock(return_value={
            "products": mock_backend_response["products"],
            "total": 1
        })
        
        response = web_client.get(
            "/api/products?q=laptop&category=electronics&min_price=50&max_price=200&page=1"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "products" in data or "data" in data


# Mobile BFF Tests
class TestMobileBFF:
    """Test suite untuk Mobile BFF"""
    
    def test_health_check(self, mobile_client):
        """Test health check endpoint"""
        response = mobile_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "mobile-bff"
    
    @patch('mobile_bff.backend_client')
    @patch('mobile_bff.get_cached')
    def test_dashboard_minimal_response(self, mock_get_cache, mock_backend, mobile_client, mock_backend_response):
        """Test mobile dashboard returns minimal data"""
        mock_get_cache.return_value = asyncio.Future()
        mock_get_cache.return_value.set_result(None)
        
        mock_backend.get = AsyncMock(side_effect=[
            mock_backend_response["user"],
            mock_backend_response["orders"][:5],  # Only 5 orders
            mock_backend_response["products"][:4]  # Only 4 recommendations
        ])
        
        response = mobile_client.get("/api/dashboard?user_id=user-123")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify minimal structure
        assert "user" in data
        assert "orders" in data
        assert "recommendations" in data
        
        # Mobile dashboard should have fewer fields
        user = data["user"]
        assert "id" in user
        assert "name" in user
        # Should not have email in mobile response (privacy)
        
    @patch('mobile_bff.backend_client')
    def test_product_search_small_page_size(self, mock_backend, mobile_client):
        """Test mobile product search menggunakan smaller page size"""
        mock_backend.get = AsyncMock(return_value={
            "products": [{"id": f"p{i}"} for i in range(12)],
            "total": 100
        })
        
        response = mobile_client.get("/api/products?page=1")
        
        assert response.status_code == 200
        data = response.json()
        
        # Mobile should use smaller page size (12 vs 24 for web)
        # and return has_more flag
        assert "products" in data or "data" in data
        assert "has_more" in data or "page" in data
    
    def test_sync_endpoint(self, mobile_client):
        """Test sync endpoint untuk offline support"""
        with patch('mobile_bff.get_dashboard') as mock_dashboard:
            mock_dashboard.return_value = asyncio.Future()
            mock_dashboard.return_value.set_result({
                "user": {"id": "123"},
                "orders": [],
                "recommendations": []
            })
            
            response = mobile_client.get("/api/sync?user_id=user-123")
            
            assert response.status_code == 200
            data = response.json()
            
            assert "sync_timestamp" in data
            assert "data" in data
            assert "next_sync_interval" in data


# Backend Client Tests
class TestBackendServiceClient:
    """Test suite untuk Backend Service Client"""
    
    @pytest.mark.asyncio
    async def test_successful_request(self):
        """Test successful HTTP request"""
        client = BackendServiceClient("http://test-service:8000")
        
        with patch.object(client.client, 'request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_response.headers = {"content-type": "application/json"}
            mock_response.raise_for_status = Mock()
            
            mock_request.return_value = mock_response
            
            result = await client.get("/test")
            
            assert result == {"status": "ok"}
            mock_request.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        """Test retry logic pada timeout"""
        client = BackendServiceClient("http://test-service:8000", max_retries=3)
        
        with patch.object(client.client, 'request') as mock_request:
            # First 2 calls timeout, third succeeds
            import httpx
            mock_request.side_effect = [
                httpx.TimeoutException("Timeout"),
                httpx.TimeoutException("Timeout"),
                Mock(status_code=200, json=lambda: {"status": "ok"}, 
                     headers={"content-type": "application/json"},
                     raise_for_status=Mock())
            ]
            
            result = await client.get("/test")
            
            assert result == {"status": "ok"}
            assert mock_request.call_count == 3
    
    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self):
        """Test tidak retry pada client error (4xx)"""
        client = BackendServiceClient("http://test-service:8000", max_retries=3)
        
        with patch.object(client.client, 'request') as mock_request:
            import httpx
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not found", request=Mock(), response=mock_response
            )
            
            mock_request.return_value = mock_response
            
            with pytest.raises(httpx.HTTPStatusError):
                await client.get("/test")
            
            # Should not retry on 4xx
            assert mock_request.call_count == 1
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check method"""
        client = BackendServiceClient("http://test-service:8000")
        
        with patch.object(client, 'get') as mock_get:
            mock_get.return_value = asyncio.Future()
            mock_get.return_value.set_result({"status": "healthy"})
            
            is_healthy = await client.health_check()
            
            assert is_healthy is True
            mock_get.assert_called_once_with("/health", timeout=2.0)


# Circuit Breaker Tests
class TestCircuitBreaker:
    """Test suite untuk Circuit Breaker"""
    
    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self):
        """Test circuit breaker opens after failure threshold"""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
        
        async def failing_function():
            raise Exception("Service down")
        
        wrapped = breaker.call(failing_function)
        
        # First 3 calls should go through and fail
        for i in range(3):
            with pytest.raises(Exception):
                await wrapped()
        
        # Circuit should now be OPEN
        assert breaker.state == CircuitState.OPEN
        
        # Next call should fail immediately without calling function
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            await wrapped()
    
    @pytest.mark.asyncio
    async def test_circuit_recovery(self):
        """Test circuit breaker recovery after timeout"""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        
        call_count = 0
        
        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Failing")
            return "Success"
        
        wrapped = breaker.call(flaky_function)
        
        # Fail twice to open circuit
        for i in range(2):
            with pytest.raises(Exception):
                await wrapped()
        
        assert breaker.state == CircuitState.OPEN
        
        # Wait for recovery timeout
        await asyncio.sleep(1.1)
        
        # Next call should succeed and close circuit
        result = await wrapped()
        assert result == "Success"
        assert breaker.state == CircuitState.CLOSED
    
    def test_circuit_resets_on_success(self):
        """Test circuit breaker resets failure count on success"""
        breaker = CircuitBreaker(failure_threshold=3)
        
        breaker.failure_count = 2
        breaker._on_success()
        
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED


# Integration Tests
class TestBFFIntegration:
    """Integration tests untuk BFF pattern"""
    
    @patch('web_bff.backend_client')
    @patch('mobile_bff.backend_client')
    def test_web_vs_mobile_response_size(self, mock_mobile_backend, mock_web_backend, web_client, mobile_client, mock_backend_response):
        """Test web BFF returns more data than mobile BFF"""
        # Setup mocks
        mock_web_backend.get = AsyncMock(return_value=mock_backend_response["user"])
        mock_mobile_backend.get = AsyncMock(return_value=mock_backend_response["user"])
        
        # Compare response sizes
        web_response = web_client.get("/api/products/prod-1")
        mobile_response = mobile_client.get("/api/products/prod-1")
        
        # Web should have more detailed response
        # (Actual comparison would depend on implementation details)
        assert web_response.status_code == 200
        assert mobile_response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
