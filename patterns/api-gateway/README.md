# API Gateway Pattern

## Ringkasan

API Gateway adalah single entry point yang bertindak sebagai reverse proxy untuk menerima semua request dari client, meneruskannya ke service yang sesuai, dan mengembalikan response. Pattern ini fundamental dalam arsitektur microservices dan distributed systems.

## Problem yang Diselesaikan

### Masalah dalam Microservices

1. **Kompleksitas Client-Side**
   - Client harus mengetahui endpoint dari puluhan/ratusan microservices
   - Setiap service punya format API, autentikasi, dan protokol berbeda
   - Client harus melakukan multiple requests untuk satu use case

2. **Cross-Cutting Concerns**
   - Authentication & authorization tersebar di setiap service
   - Rate limiting, logging, monitoring perlu diimplementasi ulang
   - SSL/TLS termination dilakukan di masing-masing service

3. **Protocol Translation**
   - Client modern butuh REST/GraphQL, backend bisa pakai gRPC, SOAP, atau binary protocol
   - Mobile client butuh response lebih kecil dibanding web client

4. **Network Chattiness**
   - Mobile/web app harus melakukan banyak round-trips ke backend
   - Latency tinggi pada jaringan lambat

## Solusi: API Gateway

API Gateway menyediakan **unified interface** di depan semua backend services:

```
[Mobile App]  ──┐
[Web App]     ──┼─→ [API Gateway] ──┬─→ [User Service]
[Third-party] ──┘                   ├─→ [Order Service]
                                    ├─→ [Payment Service]
                                    ├─→ [Inventory Service]
                                    └─→ [Analytics Service]
```

## Kapan Menggunakan

✅ **Gunakan API Gateway ketika:**

- Arsitektur microservices dengan > 5 services
- Perlu aggregasi data dari multiple services
- Client heterogen (mobile, web, IoT, third-party)
- Butuh centralized authentication/authorization
- Perlu rate limiting & throttling
- Multi-tenant application dengan routing rules berbeda
- Legacy modernization (strangler fig pattern)

❌ **Hindari API Gateway ketika:**

- Monolithic application sederhana
- Internal service-to-service communication
- Real-time/streaming dengan latency ultra-low (<5ms)
- Overhead tambahan tidak acceptable
- Team kecil tanpa resource untuk maintain gateway

## Implementasi

### 1. Basic API Gateway (Node.js + Express)

```javascript
// gateway.js
const express = require('express');
const axios = require('axios');
const jwt = require('jsonwebtoken');
const rateLimit = require('express-rate-limit');

const app = express();
app.use(express.json());

// Rate Limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 menit
  max: 100 // max 100 requests per IP
});
app.use('/api/', limiter);

// Authentication Middleware
const authenticateToken = (req, res, next) => {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];
  
  if (!token) {
    return res.status(401).json({ error: 'Token diperlukan' });
  }
  
  jwt.verify(token, process.env.JWT_SECRET, (err, user) => {
    if (err) return res.status(403).json({ error: 'Token invalid' });
    req.user = user;
    next();
  });
};

// Service Registry
const services = {
  users: 'http://user-service:3001',
  orders: 'http://order-service:3002',
  products: 'http://product-service:3003',
  payments: 'http://payment-service:3004'
};

// Request Logging
app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
  next();
});

// Route Proxying dengan Circuit Breaker
const proxyRequest = async (serviceUrl, req) => {
  try {
    const response = await axios({
      method: req.method,
      url: serviceUrl + req.path,
      data: req.body,
      headers: {
        'X-User-Id': req.user?.id,
        'X-Request-Id': req.headers['x-request-id'] || generateRequestId()
      },
      timeout: 5000
    });
    return response.data;
  } catch (error) {
    if (error.code === 'ECONNABORTED') {
      throw new Error('Service timeout');
    }
    throw error;
  }
};

// API Routes
app.use('/api/users/*', authenticateToken, async (req, res) => {
  try {
    const data = await proxyRequest(services.users, req);
    res.json(data);
  } catch (error) {
    res.status(error.response?.status || 500)
       .json({ error: error.message });
  }
});

app.use('/api/orders/*', authenticateToken, async (req, res) => {
  try {
    const data = await proxyRequest(services.orders, req);
    res.json(data);
  } catch (error) {
    res.status(error.response?.status || 500)
       .json({ error: error.message });
  }
});

// Request Aggregation Endpoint
app.get('/api/dashboard', authenticateToken, async (req, res) => {
  try {
    const [userProfile, recentOrders, recommendations] = await Promise.all([
      axios.get(`${services.users}/profile/${req.user.id}`),
      axios.get(`${services.orders}/user/${req.user.id}/recent`),
      axios.get(`${services.products}/recommendations/${req.user.id}`)
    ]);
    
    res.json({
      user: userProfile.data,
      orders: recentOrders.data,
      recommendations: recommendations.data
    });
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch dashboard data' });
  }
});

// Health Check
app.get('/health', (req, res) => {
  res.json({ status: 'healthy', timestamp: new Date() });
});

const generateRequestId = () => {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
};

const PORT = process.env.PORT || 8080;
app.listen(PORT, () => {
  console.log(`API Gateway running on port ${PORT}`);
});
```

### 2. API Gateway dengan Protocol Translation (gRPC → REST)

```javascript
// grpc-gateway.js
const express = require('express');
const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');

const app = express();
app.use(express.json());

// Load gRPC proto
const packageDefinition = protoLoader.loadSync('user.proto', {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true
});

const userProto = grpc.loadPackageDefinition(packageDefinition).user;
const userClient = new userProto.UserService(
  'user-service:50051',
  grpc.credentials.createInsecure()
);

// REST endpoint yang memanggil gRPC service
app.get('/api/users/:id', (req, res) => {
  userClient.GetUser({ id: req.params.id }, (error, response) => {
    if (error) {
      return res.status(500).json({ 
        error: 'gRPC call failed',
        details: error.message 
      });
    }
    res.json(response);
  });
});

app.post('/api/users', (req, res) => {
  userClient.CreateUser(req.body, (error, response) => {
    if (error) {
      return res.status(500).json({ error: error.message });
    }
    res.status(201).json(response);
  });
});

app.listen(8080);
```

### 3. API Gateway dengan Response Caching

```javascript
// caching-gateway.js
const express = require('express');
const redis = require('redis');
const axios = require('axios');

const app = express();
const redisClient = redis.createClient({
  host: process.env.REDIS_HOST || 'localhost',
  port: 6379
});

redisClient.connect();

// Cache Middleware
const cacheMiddleware = (duration) => {
  return async (req, res, next) => {
    const key = `cache:${req.originalUrl}`;
    
    try {
      const cached = await redisClient.get(key);
      if (cached) {
        console.log('Cache HIT:', key);
        return res.json(JSON.parse(cached));
      }
      
      console.log('Cache MISS:', key);
      res.originalJson = res.json;
      res.json = async (data) => {
        await redisClient.setEx(key, duration, JSON.stringify(data));
        res.originalJson(data);
      };
      next();
    } catch (error) {
      next();
    }
  };
};

// Cached endpoint (5 menit)
app.get('/api/products', cacheMiddleware(300), async (req, res) => {
  const response = await axios.get('http://product-service:3003/products');
  res.json(response.data);
});

// Non-cached endpoint
app.post('/api/orders', async (req, res) => {
  const response = await axios.post(
    'http://order-service:3002/orders',
    req.body
  );
  
  // Invalidate related caches
  await redisClient.del('cache:/api/orders');
  
  res.json(response.data);
});

app.listen(8080);
```

### 4. Production-Ready dengan Kong Gateway

```yaml
# docker-compose.yml
version: '3.8'

services:
  kong-database:
    image: postgres:14
    environment:
      POSTGRES_USER: kong
      POSTGRES_DB: kong
      POSTGRES_PASSWORD: kong
    volumes:
      - kong-data:/var/lib/postgresql/data

  kong-migrations:
    image: kong:3.4
    command: kong migrations bootstrap
    environment:
      KONG_DATABASE: postgres
      KONG_PG_HOST: kong-database
      KONG_PG_PASSWORD: kong
    depends_on:
      - kong-database

  kong:
    image: kong:3.4
    environment:
      KONG_DATABASE: postgres
      KONG_PG_HOST: kong-database
      KONG_PG_PASSWORD: kong
      KONG_PROXY_ACCESS_LOG: /dev/stdout
      KONG_ADMIN_ACCESS_LOG: /dev/stdout
      KONG_PROXY_ERROR_LOG: /dev/stderr
      KONG_ADMIN_ERROR_LOG: /dev/stderr
      KONG_ADMIN_LISTEN: 0.0.0.0:8001
    ports:
      - "8000:8000"  # Proxy
      - "8443:8443"  # Proxy SSL
      - "8001:8001"  # Admin API
    depends_on:
      - kong-database
      - kong-migrations

  # Backend Services
  user-service:
    image: user-service:latest
    environment:
      PORT: 3001

  order-service:
    image: order-service:latest
    environment:
      PORT: 3002

volumes:
  kong-data:
```

**Konfigurasi Kong via Admin API:**

```bash
# Tambah Service
curl -i -X POST http://localhost:8001/services \
  --data name=user-service \
  --data url=http://user-service:3001

# Tambah Route
curl -i -X POST http://localhost:8001/services/user-service/routes \
  --data 'paths[]=/api/users' \
  --data name=user-route

# Tambah Rate Limiting Plugin
curl -i -X POST http://localhost:8001/services/user-service/plugins \
  --data name=rate-limiting \
  --data config.minute=100 \
  --data config.policy=local

# Tambah JWT Authentication
curl -i -X POST http://localhost:8001/services/user-service/plugins \
  --data name=jwt

# Tambah CORS
curl -i -X POST http://localhost:8001/services/user-service/plugins \
  --data name=cors \
  --data config.origins=* \
  --data config.methods=GET,POST,PUT,DELETE

# Tambah Response Caching
curl -i -X POST http://localhost:8001/services/user-service/plugins \
  --data name=proxy-cache \
  --data config.strategy=memory \
  --data config.content_type="application/json" \
  --data config.cache_ttl=300
```

### 5. API Gateway dengan Service Discovery (Consul)

```javascript
// service-discovery-gateway.js
const express = require('express');
const Consul = require('consul');
const axios = require('axios');

const app = express();
const consul = new Consul({
  host: process.env.CONSUL_HOST || 'localhost',
  port: 8500
});

// Service Discovery
const getServiceUrl = async (serviceName) => {
  try {
    const result = await consul.health.service({
      service: serviceName,
      passing: true
    });
    
    if (result.length === 0) {
      throw new Error(`Service ${serviceName} tidak ditemukan`);
    }
    
    // Load balancing: pilih random instance
    const instance = result[Math.floor(Math.random() * result.length)];
    const { Address, ServicePort } = instance.Service;
    return `http://${Address}:${ServicePort}`;
  } catch (error) {
    throw new Error(`Service discovery failed: ${error.message}`);
  }
};

// Dynamic routing
app.all('/api/:service/*', async (req, res) => {
  const serviceName = req.params.service;
  const path = req.params[0];
  
  try {
    const serviceUrl = await getServiceUrl(serviceName);
    const response = await axios({
      method: req.method,
      url: `${serviceUrl}/${path}`,
      data: req.body,
      headers: req.headers
    });
    
    res.status(response.status).json(response.data);
  } catch (error) {
    res.status(503).json({ 
      error: 'Service unavailable',
      service: serviceName
    });
  }
});

app.listen(8080);
```

## Trade-offs dan Considerations

### Kelebihan ✅

1. **Simplified Client**
   - Single endpoint untuk semua services
   - Konsisten API interface
   - Reduced network calls

2. **Centralized Cross-Cutting Concerns**
   - Authentication & Authorization di satu tempat
   - Rate limiting, logging, monitoring terpusat
   - SSL/TLS termination

3. **Protocol Translation**
   - Backend bisa pakai gRPC, client tetap REST
   - Support legacy protocols

4. **Request Aggregation**
   - Reduce network latency
   - Optimized untuk mobile/slow network

5. **Evolutionary Architecture**
   - Mudah migrate backend services
   - Backend bisa di-refactor tanpa impact client

### Kekurangan ❌

1. **Single Point of Failure**
   - Gateway down = seluruh sistem down
   - Mitigasi: redundancy, auto-scaling, health checks

2. **Performance Bottleneck**
   - Semua traffic lewat gateway
   - Added latency (1-5ms typical)
   - Mitigasi: caching, horizontal scaling

3. **Increased Complexity**
   - Additional infrastructure component
   - Perlu monitoring & maintenance
   - DevOps overhead

4. **Development Bottleneck**
   - Gateway perlu update setiap ada service baru
   - Mitigasi: dynamic routing, service discovery

5. **Testing Complexity**
   - Integration testing lebih kompleks
   - Mock gateway di development environment

## Scalability Considerations

### 1. Horizontal Scaling

```yaml
# kubernetes-deployment.yml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-gateway
spec:
  replicas: 3  # Multiple instances
  selector:
    matchLabels:
      app: api-gateway
  template:
    metadata:
      labels:
        app: api-gateway
    spec:
      containers:
      - name: gateway
        image: api-gateway:latest
        ports:
        - containerPort: 8080
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 3
---
apiVersion: v1
kind: Service
metadata:
  name: api-gateway-service
spec:
  type: LoadBalancer
  selector:
    app: api-gateway
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-gateway-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api-gateway
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### 2. Caching Strategy

- **Browser Caching**: Cache-Control headers
- **CDN Caching**: Static content & API responses
- **Gateway Caching**: Redis/Memcached untuk responses
- **Service-Level Caching**: Masing-masing service cache internal

### 3. Rate Limiting Strategy

```javascript
// Multi-tier rate limiting
const rateLimitTiers = {
  free: { requests: 100, window: '15m' },
  basic: { requests: 1000, window: '15m' },
  premium: { requests: 10000, window: '15m' },
  enterprise: { requests: 100000, window: '15m' }
};

const getRateLimitForUser = (user) => {
  return rateLimitTiers[user.tier] || rateLimitTiers.free;
};
```

## Real-World Examples

### 1. **Netflix**

- Menggunakan **Zuul** (custom-built API Gateway)
- Handle 2+ billion requests per day
- Dynamic routing, filters, resilience
- Migrasi ke **Zuul 2** (non-blocking I/O) untuk scalability

### 2. **Amazon**

- **Amazon API Gateway** (AWS service)
- Managed service dengan auto-scaling
- Integrated dengan Lambda, EC2, ECS
- Built-in authentication (Cognito, IAM)

### 3. **Uber**

- Custom API Gateway di atas Envoy Proxy
- Melayani 1000+ microservices
- Protocol translation (HTTP/2, gRPC)
- Advanced traffic management & canary deployment

### 4. **Spotify**

- **Kong Gateway** + custom plugins
- 800+ backend services
- Rate limiting per user tier
- Analytics & monitoring terintegrasi

### 5. **Twitter**

- Custom gateway bernama **Maccaw**
- Handle millions requests/second
- Request aggregation untuk mobile apps
- Geo-distributed deployment

## Monitoring & Observability

```javascript
// metrics-middleware.js
const prometheus = require('prom-client');

const httpRequestDuration = new prometheus.Histogram({
  name: 'http_request_duration_seconds',
  help: 'Duration of HTTP requests in seconds',
  labelNames: ['method', 'route', 'status_code']
});

const httpRequestTotal = new prometheus.Counter({
  name: 'http_requests_total',
  help: 'Total number of HTTP requests',
  labelNames: ['method', 'route', 'status_code']
});

const metricsMiddleware = (req, res, next) => {
  const start = Date.now();
  
  res.on('finish', () => {
    const duration = (Date.now() - start) / 1000;
    const labels = {
      method: req.method,
      route: req.route?.path || req.path,
      status_code: res.statusCode
    };
    
    httpRequestDuration.observe(labels, duration);
    httpRequestTotal.inc(labels);
  });
  
  next();
};

// Expose metrics endpoint
app.get('/metrics', async (req, res) => {
  res.set('Content-Type', prometheus.register.contentType);
  res.end(await prometheus.register.metrics());
});
```

## Security Best Practices

1. **Authentication & Authorization**
   - JWT tokens dengan short expiration
   - OAuth 2.0 / OpenID Connect
   - API keys untuk third-party

2. **Rate Limiting & Throttling**
   - Per-user, per-IP, per-endpoint
   - Sliding window algorithm

3. **Input Validation**
   - Schema validation (JSON Schema, Joi)
   - Sanitize input untuk prevent injection

4. **HTTPS/TLS**
   - Mandatory SSL/TLS
   - Certificate pinning untuk mobile apps

5. **CORS Configuration**
   - Whitelist allowed origins
   - Credential handling

6. **Request/Response Logging**
   - Audit trail untuk compliance
   - Jangan log sensitive data (passwords, tokens)

## Kesimpulan

API Gateway adalah **essential pattern** untuk arsitektur microservices modern. Meskipun menambah complexity dan potential single point of failure, benefits yang didapat (simplified clients, centralized security, protocol translation) biasanya jauh lebih besar.

**Key Takeaways:**
- Gunakan managed solutions (Kong, AWS API Gateway) untuk production
- Implement proper monitoring & alerting
- Design for failure (circuit breakers, timeouts, retries)
- Scale horizontally dengan load balancing
- Cache aggressively untuk reduce backend load

## Referensi & Further Reading

### Books
- *Building Microservices* — Sam Newman (O'Reilly, 2021)
- *Microservices Patterns* — Chris Richardson (Manning, 2018)
- *Site Reliability Engineering* — Google (O'Reilly, 2016)

### Articles & Papers
- [Pattern: API Gateway / Backend for Front-End](https://microservices.io/patterns/apigateway.html) — Chris Richardson
- [API Gateway Pattern](https://learn.microsoft.com/en-us/azure/architecture/microservices/design/gateway) — Microsoft Azure Architecture
- [Netflix Zuul](https://github.com/Netflix/zuul/wiki) — Netflix OSS

### Tools & Frameworks
- [Kong Gateway](https://konghq.com/) — Open-source API Gateway
- [AWS API Gateway](https://aws.amazon.com/api-gateway/) — Managed service
- [Traefik](https://traefik.io/) — Cloud-native proxy & load balancer
- [Envoy Proxy](https://www.envoyproxy.io/) — CNCF graduated project
- [Tyk](https://tyk.io/) — Open-source API Gateway
- [Apache APISIX](https://apisix.apache.org/) — Cloud-native API Gateway

### Community & Forums
- [CNCF Slack](https://slack.cncf.io/) — #api-gateway channel
- [Kong Community Forum](https://discuss.konghq.com/)
- [r/microservices](https://reddit.com/r/microservices)
