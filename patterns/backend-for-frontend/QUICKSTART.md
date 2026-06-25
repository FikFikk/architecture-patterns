# Backend for Frontend Pattern

Implementasi lengkap dari Backend for Frontend (BFF) pattern untuk aplikasi modern dengan multiple client types.

## Struktur

- `README.md` - Dokumentasi lengkap pattern
- `diagram.md` - Visualisasi arsitektur dan flow
- `web_bff.py` - Web BFF implementation (FastAPI)
- `mobile_bff.py` - Mobile BFF implementation (FastAPI)
- `backend_client.py` - HTTP client dengan retry, circuit breaker
- `example_ecommerce.py` - Real-world example untuk e-commerce
- `test_bff.py` - Test suite
- `requirements.txt` - Python dependencies
- `docker-compose.yml` - Deployment setup
- `Dockerfile.web` - Web BFF container
- `Dockerfile.mobile` - Mobile BFF container
- `prometheus.yml` - Monitoring configuration

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run Tests

```bash
pytest test_bff.py -v
```

### 3. Run dengan Docker Compose

```bash
docker-compose up -d
```

Services:
- Web BFF: http://localhost:8000
- Mobile BFF: http://localhost:8001
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

### 4. Test Endpoints

```bash
# Web BFF - Dashboard
curl "http://localhost:8000/api/dashboard?user_id=user-123"

# Mobile BFF - Dashboard (minimal response)
curl "http://localhost:8001/api/dashboard?user_id=user-123"

# E-commerce Example
python example_ecommerce.py
curl "http://localhost:8080/api/homepage?user_id=user-123" \
  -H "X-Platform: mobile"
```

## Key Features

### Web BFF
- Full data responses
- Larger page sizes (24 items)
- Complete product details
- Multiple images per product
- Detailed order information

### Mobile BFF
- Minimal payloads
- Smaller page sizes (12 items)
- Thumbnail images only
- Aggressive caching (10 min TTL)
- Offline sync support

### Backend Client
- Connection pooling
- Exponential backoff retry
- Circuit breaker pattern
- Timeout management
- Request/response logging

## Monitoring

Metrics exposed on `/metrics`:
- Request rate per BFF
- Response latency (P50, P95, P99)
- Cache hit/miss rate
- Backend service call distribution
- Error rate

## Production Considerations

1. **Scaling**: Scale each BFF independently based on traffic
2. **Caching**: Multi-level (in-memory + Redis + CDN)
3. **Security**: Different auth per platform
4. **Observability**: Distributed tracing dengan OpenTelemetry
5. **Deployment**: Blue-green deployment per BFF

## Further Reading

Lihat `README.md` untuk dokumentasi lengkap, trade-offs, dan real-world examples.
