# Strangler Fig Pattern

## Gambaran Umum

Strangler Fig Pattern adalah strategi migrasi bertahap untuk mengganti sistem monolitik lama dengan arsitektur baru (biasanya microservices) tanpa harus melakukan "big bang rewrite". Pattern ini dinamai dari pohon Strangler Fig yang tumbuh mengelilingi pohon inang, perlahan-lahan mengambil alih fungsinya, hingga akhirnya pohon inang bisa dilepas.

## Problem yang Diselesaikan

### Tantangan Migrasi Sistem Legacy

1. **Big Bang Rewrite Risk**: Mengganti seluruh sistem sekaligus sangat berisiko dan sering gagal
2. **Business Continuity**: Sistem harus tetap berjalan selama migrasi
3. **Feature Development**: Tim masih perlu deliver fitur baru saat migrasi berlangsung
4. **Technical Debt**: Sistem lama penuh technical debt tapi masih business-critical
5. **Risk Management**: Perlu cara untuk rollback jika ada masalah

### Kapan Menggunakan Pattern Ini

✅ **Gunakan ketika:**
- Sistem monolitik legacy perlu dimodernisasi
- Risiko big bang rewrite terlalu tinggi
- Business tidak bisa stop untuk migrasi total
- Ingin migrasi incremental dengan validasi tiap tahap
- Tim perlu belajar teknologi baru sambil deliver value

❌ **Hindari ketika:**
- Sistem kecil yang bisa direwrite cepat (< 2 bulan)
- Tidak ada infrastruktur untuk routing/proxy
- Tim tidak punya kapasitas maintain dua sistem sekaligus
- Regulasi mengharuskan cut-over sekaligus

## Cara Kerja Pattern

### Fase 1: Persiapan (Foundation)
```
┌─────────────────────────┐
│   Legacy Monolith       │
│  ┌─────────────────┐   │
│  │  All Features   │   │
│  └─────────────────┘   │
└─────────────────────────┘
         ▲
         │
    All Traffic
```

### Fase 2: Intercept Layer
```
    ┌──────────────┐
    │  Facade/Proxy│
    └──────┬───────┘
           │
    ┌──────▼───────────────┐
    │                      │
┌───▼──────┐      ┌───────▼────┐
│ Legacy   │      │ New Service│
│ Monolith │      │ (Feature A)│
└──────────┘      └────────────┘
```

### Fase 3: Migrasi Bertahap
```
    ┌──────────────┐
    │  Facade/Proxy│
    └──┬───┬───┬───┘
       │   │   │
   ┌───▼┐ ┌▼──┐▼───┐
   │Svc │ │Svc│Svc │
   │ A  │ │ B │ C  │
   └────┘ └───┴────┘
            Legacy
          (shrinking)
```

### Fase 4: Complete Migration
```
    ┌──────────────┐
    │  API Gateway │
    └──┬───┬───┬───┘
       │   │   │
   ┌───▼┐ ┌▼──┐▼───┐
   │Svc │ │Svc│Svc │
   │ A  │ │ B │ C  │
   └────┘ └───┴────┘
   
   Legacy retired ✓
```

## Implementation Guide

### 1. Setup Facade/Proxy Layer

Gunakan reverse proxy atau API Gateway sebagai intercept layer.

**Contoh menggunakan NGINX:**

```nginx
# nginx.conf
upstream legacy {
    server legacy-app:8080;
}

upstream new_service_users {
    server users-service:8081;
}

upstream new_service_orders {
    server orders-service:8082;
}

server {
    listen 80;
    
    # Route ke service baru
    location /api/v2/users {
        proxy_pass http://new_service_users;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /api/v2/orders {
        proxy_pass http://new_service_orders;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # Sisanya ke legacy
    location / {
        proxy_pass http://legacy;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 2. Extract First Service

Pilih bounded context yang jelas untuk service pertama. Lihat `example_service.py` untuk implementasi lengkap.

### 3. Implement Feature Toggles

Control migrasi dengan feature flags. Lihat `feature_flags.py` untuk implementasi.

### 4. Data Migration Strategy

Gunakan dual-write pattern untuk transisi data. Lihat `data_migration.py`.

### 5. Monitoring & Observability

Setup metrics untuk track progress migrasi. Lihat `monitoring.py`.

## Trade-offs

### Kelebihan ✅

1. **Risk Mitigation**: Migrasi incremental mengurangi risiko
2. **Business Continuity**: Sistem tetap jalan selama migrasi
3. **Learning Curve**: Tim bisa belajar sambil jalan
4. **Rollback Easy**: Bisa rollback per feature
5. **Prove Value**: Tunjukkan value improvement tiap tahap
6. **Parallel Development**: Feature baru di service baru, maintain legacy minimal

### Kekurangan ❌

1. **Complexity**: Maintain dua sistem sekaligus
2. **Dual Write Overhead**: Perlu sync data temporary
3. **Extended Timeline**: Migrasi bisa memakan waktu lama (months-years)
4. **Proxy Layer Overhead**: Extra hop, potential bottleneck
5. **Inconsistency Risk**: Data bisa inconsistent during dual-write period
6. **Technical Debt**: Facade layer sendiri bisa jadi debt

### Perbandingan dengan Alternatif

| Aspek | Strangler Fig | Big Bang Rewrite | Parallel Run |
|-------|--------------|------------------|--------------|
| Risk | Low-Medium | Very High | Medium |
| Timeline | Long (6-24mo) | Medium (3-12mo) | Long (12-36mo) |
| Cost | Medium | High | Very High |
| Business Disruption | Minimal | High | Low |
| Rollback | Easy | Hard | Easy |
| Learning | Gradual | Steep | Gradual |

## Scalability Considerations

### 1. Proxy Layer Scaling

**Nginx sebagai proxy** dapat handle 10k-50k req/s per instance:
```yaml
# docker-compose.yml
services:
  nginx-proxy:
    image: nginx:alpine
    deploy:
      replicas: 3  # Scale horizontal
      resources:
        limits:
          cpus: '1'
          memory: 512M
    ports:
      - "80:80"
```

**API Gateway alternatif** untuk complex routing:
- Kong: 10k+ req/s, plugin ecosystem
- Envoy: High performance, service mesh ready
- Traefik: Docker/K8s native, dynamic config

### 2. Database Migration at Scale

Batch migration untuk data besar - lihat `batch_migration.py` untuk implementasi.

### 3. Cache Strategy

Gunakan cache untuk reduce load pada dual-read - lihat `cache_strategy.py`.

## Real-World Examples

### 1. Spotify - Monolith ke Microservices

**Context**: Spotify punya monolith besar di 2013 yang sulit di-scale untuk 40M users.

**Approach**:
- Setup API Gateway (Nginx + HAProxy) di depan
- Extract domain per domain: Playlist → User → Search → Recommendations
- Gunakan Kafka untuk event-driven communication
- Dual-write selama 3-6 bulan per service

**Result**:
- Migrasi 3 tahun (2013-2016)
- Dari 1 monolith → 800+ microservices
- Deployment frequency: 1x/week → 10,000x/day
- Zero downtime during migration

**Lessons**:
- Start dengan service yang paling independent
- Invest heavy di observability dari awal
- Accept bahwa akan ada inconsistency temporary

### 2. Soundcloud - Rails Monolith Migration

**Context**: Rails monolith jadi bottleneck untuk scale dan development velocity.

**Approach**:
- Gunakan HAProxy untuk routing
- Extract services: User Identity, Audio Storage, Feed Generation
- Implement event bus (RabbitMQ) untuk async communication
- Careful pada shared database migration (paling tricky)

**Result**:
- Migrasi bertahap 2 tahun
- Dapat scale independent per service
- Development teams jadi autonomous

**Challenges**:
- Database coupling paling sulit dibreak
- Butuh strong contract testing between services
- Transaction boundaries jadi kompleks

### 3. Amazon - Two-Pizza Teams

**Context**: Amazon e-commerce monolith circa early 2000s.

**Approach** (pre-AWS era):
- Service-Oriented Architecture sebagai precursor microservices
- Conway's Law: reorganize team structure dulu
- Each team owns service end-to-end
- API-first culture

**Insight**:
- Organizational change sama pentingnya dengan technical
- Clear ownership mengurangi coupling
- "You build it, you run it" accountability

### 4. Shopify - Modular Monolith dulu, Microservices gradual

**Context**: Rails monolith untuk ecommerce platform.

**Approach**:
- Phase 1: Modularize monolith dengan strong boundaries (Rails Engines)
- Phase 2: Extract critical services (payment, inventory)
- Phase 3: Gradual extraction based on scale needs
- Keep modular monolith untuk features yang ga perlu extracted

**Result**:
- Hybrid approach: monolith + microservices
- Extract hanya kalau ada clear benefit (scale, team autonomy)
- Avoid premature microservices

**Lesson**: 
- **Tidak semua harus microservices**
- Modular monolith bisa jadi end state yang baik untuk banyak kasus
- Strangler Fig tidak harus berakhir dengan full microservices

## Anti-Patterns yang Harus Dihindari

### 1. ❌ Extract terlalu cepat tanpa clear boundary
```python
# WRONG: Extract terlalu granular
class UserEmailService:  # Terlalu kecil untuk jadi service
    def send_email(user_id, message): pass

# RIGHT: Extract bounded context yang jelas
class NotificationService:  # Clear boundary, multiple capabilities
    def send_email(user, template, data): pass
    def send_sms(user, message): pass
    def get_preferences(user): pass
```

### 2. ❌ Shared Database tanpa plan migrasi
```
Service A ──┐
            ├──→ Shared DB ←─── Service B
Service C ──┘
# Ini bukan microservices, cuma distributed monolith!
```

**Correct approach**: Database per service + event-driven sync
```
Service A → DB A ──→ Event Bus ──→ Service B → DB B
```

### 3. ❌ No monitoring/observability dari awal
Extract service tanpa tau response time, error rate, usage pattern = flying blind.

### 4. ❌ Melupakan data migration plan
Code migrasi gampang, data migrasi yang susah terutama untuk production dengan millions records.

## Migration Checklist

### Phase 0: Preparation (1-2 bulan)
- [ ] Inventory sistem existing dan dependencies
- [ ] Identify bounded contexts / domain boundaries
- [ ] Setup observability stack
- [ ] Setup proxy/gateway layer
- [ ] Document current system throughput & performance baseline
- [ ] Get buy-in dari stakeholders (engineering + business)

### Phase 1: First Service (2-3 bulan)
- [ ] Pilih service pertama (independent, clear boundary)
- [ ] Setup database baru untuk service
- [ ] Implement service dengan comprehensive tests
- [ ] Setup monitoring & alerting
- [ ] Deploy di staging dengan synthetic traffic
- [ ] Shadow mode: panggil service baru + legacy, compare results
- [ ] Canary deploy: 5% → 25% → 50% → 100%
- [ ] Document lessons learned

### Phase 2: Iteration (3-18 bulan)
- [ ] Repeat untuk services lain berdasarkan priority
- [ ] Maintain dual-write where needed
- [ ] Incremental data migration
- [ ] Monitor data consistency
- [ ] Regular retrospectives

### Phase 3: Decommission Legacy (final 2-3 bulan)
- [ ] Verify all traffic sudah di service baru
- [ ] Stop dual-write
- [ ] Migrate remaining data
- [ ] Archive legacy code (jangan langsung delete)
- [ ] Remove proxy routing for legacy
- [ ] Celebrate! 🎉

## Tools & Technologies

### Proxy/Gateway Layer
- **Nginx**: Lightweight, proven, 10k+ req/s
- **Kong**: Feature-rich, plugin system, API management
- **Envoy**: High-performance, service mesh ready (Istio)
- **Traefik**: Kubernetes-native, dynamic config
- **AWS ALB/API Gateway**: Managed option

### Feature Flags
- **LaunchDarkly**: SaaS, sophisticated targeting
- **Unleash**: Open-source, self-hosted
- **Split.io**: Experimentation + feature flags
- **Flagsmith**: Open-source alternative

### Monitoring
- **Prometheus + Grafana**: Metrics & visualization
- **Jaeger/Zipkin**: Distributed tracing
- **ELK/Loki**: Centralized logging
- **Datadog/New Relic**: All-in-one observability (paid)

### Data Migration
- **Debezium**: Change Data Capture (CDC) dari database
- **Apache Kafka**: Event streaming untuk data sync
- **AWS DMS**: Managed database migration service

## Referensi

### Papers & Articles
1. Martin Fowler - "StranglerFigApplication" (martinfowler.com)
2. Sam Newman - "Building Microservices" (O'Reilly, 2021)
3. Chris Richardson - "Microservices Patterns" (Manning, 2018)

### Case Studies
1. Spotify Engineering Blog - "System Migration at Scale"
2. Soundcloud Developers - "Building Products at SoundCloud"
3. AWS Architecture Blog - "Strangler Fig Pattern for Legacy Modernization"

### Tools Documentation
1. Nginx Reverse Proxy Guide: nginx.org/en/docs/
2. Kong API Gateway: docs.konghq.com
3. Prometheus Monitoring: prometheus.io/docs/

---

**Dibuat oleh:** Hermes Agent  
**Tanggal:** 2026-06-19  
**Lisensi:** MIT
