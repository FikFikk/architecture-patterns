"""
Backend Service Client
HTTP client dengan retry logic, circuit breaker, dan timeout management
Digunakan oleh BFF untuk communicate dengan backend microservices
"""

import httpx
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker untuk prevent cascading failures"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED
    
    def call(self, func):
        """Decorator untuk wrap function dengan circuit breaker"""
        async def wrapper(*args, **kwargs):
            if self.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if self.last_failure_time and \
                   datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout):
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit breaker entering HALF_OPEN state")
                else:
                    raise Exception("Circuit breaker is OPEN")
            
            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exception as e:
                self._on_failure()
                raise e
        
        return wrapper
    
    def _on_success(self):
        """Reset circuit breaker on successful call"""
        if self.state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker recovered, state: CLOSED")
        
        self.failure_count = 0
        self.state = CircuitState.CLOSED
    
    def _on_failure(self):
        """Record failure dan potentially open circuit"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.error(f"Circuit breaker OPEN after {self.failure_count} failures")


class BackendServiceClient:
    """
    HTTP client untuk backend services dengan:
    - Connection pooling
    - Retry logic dengan exponential backoff
    - Circuit breaker
    - Timeout management
    - Request/response logging
    """
    
    def __init__(
        self,
        base_url: str,
        timeout: float = 5.0,
        max_retries: int = 3,
        pool_connections: int = 10,
        pool_maxsize: int = 50
    ):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        
        # HTTP client dengan connection pooling
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_keepalive_connections=pool_connections,
                max_connections=pool_maxsize
            )
        )
        
        # Circuit breaker per service
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            expected_exception=httpx.HTTPError
        )
    
    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """GET request dengan retry dan circuit breaker"""
        return await self._request("GET", path, params=params, headers=headers, timeout=timeout)
    
    async def post(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """POST request dengan retry dan circuit breaker"""
        return await self._request("POST", path, json=json, headers=headers, timeout=timeout)
    
    async def put(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """PUT request dengan retry dan circuit breaker"""
        return await self._request("PUT", path, json=json, headers=headers, timeout=timeout)
    
    async def delete(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """DELETE request dengan retry dan circuit breaker"""
        return await self._request("DELETE", path, headers=headers, timeout=timeout)
    
    async def _request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Internal request method dengan retry logic"""
        url = f"{self.base_url}/{path.lstrip('/')}"
        
        for attempt in range(self.max_retries):
            try:
                # Call melalui circuit breaker
                result = await self.circuit_breaker.call(self._do_request)(
                    method, url, **kwargs
                )
                return result
                
            except httpx.TimeoutException as e:
                logger.warning(f"Timeout on {method} {url} (attempt {attempt + 1}/{self.max_retries})")
                if attempt == self.max_retries - 1:
                    raise
                
                # Exponential backoff
                await asyncio.sleep(2 ** attempt)
                
            except httpx.HTTPStatusError as e:
                # Don't retry client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    logger.error(f"Client error {e.response.status_code} on {method} {url}")
                    raise
                
                # Retry server errors (5xx)
                logger.warning(f"Server error {e.response.status_code} on {method} {url} (attempt {attempt + 1}/{self.max_retries})")
                if attempt == self.max_retries - 1:
                    raise
                
                await asyncio.sleep(2 ** attempt)
                
            except Exception as e:
                logger.error(f"Unexpected error on {method} {url}: {str(e)}")
                if attempt == self.max_retries - 1:
                    raise
                
                await asyncio.sleep(2 ** attempt)
    
    async def _do_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute HTTP request"""
        start_time = datetime.now()
        
        try:
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            
            # Log successful request
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"{method} {url} - {response.status_code} ({duration:.3f}s)")
            
            # Parse JSON response
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            else:
                return {"data": response.text}
                
        except httpx.HTTPStatusError as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"{method} {url} - {e.response.status_code} ({duration:.3f}s)")
            raise
        
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"{method} {url} - Error: {str(e)} ({duration:.3f}s)")
            raise
    
    async def health_check(self) -> bool:
        """Check if backend service is healthy"""
        try:
            await self.get("/health", timeout=2.0)
            return True
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return False
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Example usage
if __name__ == "__main__":
    async def main():
        # Create client untuk user service
        async with BackendServiceClient("http://user-service:8001") as client:
            # Health check
            is_healthy = await client.health_check()
            print(f"Service healthy: {is_healthy}")
            
            # GET request
            user = await client.get("/users/123")
            print(f"User: {user}")
            
            # POST request
            new_user = await client.post("/users", json={
                "name": "John Doe",
                "email": "john@example.com"
            })
            print(f"Created user: {new_user}")
    
    asyncio.run(main())
