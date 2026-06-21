# Sidecar Pattern Demo

Demonstrasi lengkap dari Sidecar Pattern dengan Docker Compose.

## Cara Menjalankan

### 1. Build dan Start Services

```bash
docker-compose up --build
```

Services yang akan berjalan:
- **app** (port 8080): Aplikasi utama
- **logging-sidecar**: Mengumpulkan log dan forward ke Elasticsearch
- **metrics-sidecar** (port 9090): Mengumpulkan metrics dari app
- **config-sidecar**: Memantau perubahan config dan trigger reload
- **elasticsearch** (port 9200): Log storage
- **prometheus** (port 9091): Metrics storage
- **grafana** (port 3000): Visualization

### 2. Test Aplikasi

```bash
# Health check
curl http://localhost:8080/health

# Main endpoint
curl http://localhost:8080/

# Generate logs
curl http://localhost:8080/api/data
curl http://localhost:8080/api/error

# Check metrics
curl http://localhost:8080/metrics

# Check sidecar metrics
curl http://localhost:9090/metrics
```

### 3. Test Config Reload

```bash
# Update config (akan trigger reload oleh sidecar)
docker exec -it demo-app sh -c 'echo "message: Updated Config
version: 2.0" > /etc/app/config.yaml'

# Verify reload
curl http://localhost:8080/
```

### 4. Monitor Logs di Elasticsearch

```bash
# Check logs
curl http://localhost:9200/app-logs/_search?pretty
```

### 5. View Metrics di Prometheus

Buka browser: http://localhost:9091

Query examples:
- `app_requests_total`
- `app_errors_total`
- `sidecar_scrape_duration_seconds`

### 6. View Dashboard di Grafana

Buka browser: http://localhost:3000
- Username: admin
- Password: admin

Add Prometheus data source: http://prometheus:9090

## Cleanup

```bash
docker-compose down -v
```

## Unit Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest test_sidecar.py -v

# With coverage
python -m pytest test_sidecar.py --cov=. --cov-report=html
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                Docker Network                       │
│                                                     │
│  ┌──────────────┐                                  │
│  │     App      │                                  │
│  │  (Port 8080) │                                  │
│  └──────┬───────┘                                  │
│         │                                          │
│    Shared Volumes                                  │
│         │                                          │
│  ┌──────┴─────────┬─────────────┬────────────┐    │
│  │                │             │            │    │
│  ▼                ▼             ▼            ▼    │
│ Logging       Metrics       Config      Envoy     │
│ Sidecar       Sidecar       Sidecar     Proxy     │
│  │                │             │                 │
│  ▼                ▼             └─────────┐       │
│ Elasticsearch  Prometheus               App       │
│                                          Reload    │
└─────────────────────────────────────────────────────┘
```

## Key Learnings

1. **Separation of Concerns**: App fokus pada business logic, sidecars handle infrastructure
2. **Shared Resources**: Volumes dan network namespace dishare
3. **Independent Lifecycle**: Sidecars dapat diupdate tanpa mengubah app
4. **Observability**: Metrics, logs, dan tracing terpisah dari app code
5. **Configuration**: Config dapat diupdate tanpa restart app
