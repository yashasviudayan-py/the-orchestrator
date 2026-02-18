## Phase 4 Deployment Guide

Complete guide for deploying The Orchestrator Command Center in various environments.

## Table of Contents

1. [Local Development](#local-development)
2. [Production Deployment](#production-deployment)
3. [Docker Deployment](#docker-deployment)
4. [Environment Configuration](#environment-configuration)
5. [Security Considerations](#security-considerations)
6. [Monitoring & Logging](#monitoring--logging)
7. [Troubleshooting](#troubleshooting)

---

## Local Development

### Prerequisites

```bash
# Python 3.10+
python --version

# Redis
brew install redis  # macOS
sudo apt install redis  # Ubuntu

# Ollama
curl https://ollama.ai/install.sh | sh
```

### Installation

```bash
# 1. Clone repository
git clone https://github.com/yashasviudayan-py/the-orchestrator.git
cd the-orchestrator

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Context Core
pip install -e "/path/to/Context Core"

# 5. Configure environment
cp .env.example .env
# Edit .env with your paths
```

### Running Locally

```bash
# Terminal 1: Start Redis
redis-server

# Terminal 2: Start Ollama
ollama serve

# Terminal 3: (Optional) Start Research Agent
cd /path/to/research-agent
python -m uvicorn main:app --port 8000

# Terminal 4: Start Command Center
uvicorn src.web.server:app --host 0.0.0.0 --port 8080 --reload
```

Access at: **http://localhost:8080**

---

## Production Deployment

### Option 1: Systemd Service (Linux)

Create `/etc/systemd/system/orchestrator.service`:

```ini
[Unit]
Description=The Orchestrator Command Center
After=network.target redis.service

[Service]
Type=simple
User=orchestrator
WorkingDirectory=/opt/orchestrator
Environment="PATH=/opt/orchestrator/venv/bin"
ExecStart=/opt/orchestrator/venv/bin/uvicorn src.web.server:app --host 0.0.0.0 --port 8080 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable orchestrator
sudo systemctl start orchestrator
sudo systemctl status orchestrator
```

### Option 2: Supervisor (Linux/macOS)

Install supervisor:
```bash
pip install supervisor
```

Create `/etc/supervisor/conf.d/orchestrator.conf`:

```ini
[program:orchestrator]
command=/opt/orchestrator/venv/bin/uvicorn src.web.server:app --host 0.0.0.0 --port 8080 --workers 4
directory=/opt/orchestrator
user=orchestrator
autostart=true
autorestart=true
stderr_logfile=/var/log/orchestrator/error.log
stdout_logfile=/var/log/orchestrator/access.log
```

Start:
```bash
supervisorctl reread
supervisorctl update
supervisorctl start orchestrator
```

### Option 3: Nginx Reverse Proxy

Install Nginx:
```bash
sudo apt install nginx  # Ubuntu
brew install nginx  # macOS
```

Create `/etc/nginx/sites-available/orchestrator`:

```nginx
upstream orchestrator {
    server 127.0.0.1:8080;
}

server {
    listen 80;
    server_name orchestrator.example.com;

    # SSL configuration (recommended)
    # listen 443 ssl http2;
    # ssl_certificate /path/to/cert.pem;
    # ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://orchestrator;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }

    location /static {
        alias /opt/orchestrator/src/web/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable:
```bash
sudo ln -s /etc/nginx/sites-available/orchestrator /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Docker Deployment

### Dockerfile

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    redis-server \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl https://ollama.ai/install.sh | sh

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Install Context Core
RUN pip install -e "/app/Context Core"

# Expose ports
EXPOSE 8080 6379 11434

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV REDIS_HOST=localhost
ENV REDIS_PORT=6379
ENV OLLAMA_BASE_URL=http://localhost:11434

# Start script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
```

### Docker Entrypoint

Create `docker-entrypoint.sh`:

```bash
#!/bin/bash
set -e

# Start Redis
redis-server --daemonize yes

# Start Ollama
ollama serve &
sleep 5

# Pull required models
ollama pull llama3.1:8b-instruct-q8_0
ollama pull nomic-embed-text

# Start Command Center
exec uvicorn src.web.server:app --host 0.0.0.0 --port 8080
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama-data:/root/.ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 10s
      retries: 3

  orchestrator:
    build: .
    ports:
      - "8080:8080"
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - OLLAMA_BASE_URL=http://ollama:11434
      - RESEARCH_AGENT_PATH=/app/agents/research
      - CONTEXT_CORE_PATH=/app/Context Core
      - PR_AGENT_PATH=/app/agents/pr
    depends_on:
      redis:
        condition: service_healthy
      ollama:
        condition: service_healthy
    volumes:
      - ./logs:/app/logs

volumes:
  redis-data:
  ollama-data:
```

Run:
```bash
docker-compose up -d
```

---

## Environment Configuration

### Required Variables

```env
# Agent Paths (absolute paths)
RESEARCH_AGENT_PATH=/path/to/research-agent
CONTEXT_CORE_PATH=/path/to/context-core
PR_AGENT_PATH=/path/to/pr-agent

# Research Agent API
RESEARCH_AGENT_URL=http://localhost:8000

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b-instruct-q8_0
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Orchestrator
MAX_ITERATIONS=10
LOG_LEVEL=INFO
```

### Optional Variables

```env
# Redis Password (production)
REDIS_PASSWORD=your-secure-password

# GitHub Integration (for PR-Agent)
GITHUB_TOKEN=ghp_your_token_here
GITHUB_USERNAME=your-username

# Ollama Advanced
OLLAMA_TEMPERATURE=0.7
```

---

## Security Considerations

### 1. Network Security

**Local Development**: Fine as-is (localhost only)

**Production**: Add authentication

```python
# Add to server.py
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

@app.get("/")
async def dashboard(credentials: HTTPBasicCredentials = Depends(security)):
    # Verify credentials
    if credentials.username != "admin" or credentials.password != "secure-password":
        raise HTTPException(401, "Invalid credentials")
    return template.render(...)
```

### 2. HTTPS/TLS

Always use HTTPS in production:

```bash
# Generate self-signed cert (dev)
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Run with SSL
uvicorn src.web.server:app --host 0.0.0.0 --port 8443 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Production: Use Let's Encrypt via Certbot

### 3. Redis Security

```bash
# Set password in redis.conf
requirepass your-strong-password

# Bind to localhost only
bind 127.0.0.1
```

### 4. Secret Management

Never commit secrets! Use:
- Environment variables (`.env` not in git)
- Secret managers (HashiCorp Vault, AWS Secrets Manager)
- Encrypted configuration files

### 5. Rate Limiting

Add rate limiting for production:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/api/tasks")
@limiter.limit("10/minute")
async def create_task(request: Request, task: TaskRequest):
    ...
```

---

## Monitoring & Logging

### Application Logs

Configure structured logging:

```python
import logging
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    'logs/orchestrator.log',
    maxBytes=10_000_000,  # 10MB
    backupCount=5
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[handler]
)
```

### Health Check Endpoint

Already available at `/api/health`

Monitor with:
```bash
# Manual check
curl http://localhost:8080/api/health

# Automated monitoring (cron)
*/5 * * * * curl -sf http://localhost:8080/api/health || echo "Service down!"
```

### Metrics (Optional)

Add Prometheus metrics:

```bash
pip install prometheus-fastapi-instrumentator
```

```python
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app)
```

---

## Troubleshooting

### Issue: Port Already in Use

```bash
# Find process
lsof -ti:8080

# Kill process
lsof -ti:8080 | xargs kill -9
```

### Issue: Redis Connection Failed

```bash
# Check if Redis is running
redis-cli ping
# Should return: PONG

# Start Redis
redis-server
```

### Issue: Ollama Not Responding

```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Restart Ollama
pkill ollama
ollama serve
```

### Issue: Static Files Not Loading

Check paths:
```python
# In server.py
_STATIC_DIR = Path(__file__).resolve().parent / "static"
print(f"Static dir: {_STATIC_DIR}")
print(f"Exists: {_STATIC_DIR.exists()}")
```

### Issue: SSE Connection Drops

Nginx configuration:
```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 86400s;  # 24 hours
```

---

## Performance Tuning

### Uvicorn Workers

```bash
# Single worker (development)
uvicorn src.web.server:app --port 8080

# Multiple workers (production)
uvicorn src.web.server:app --port 8080 --workers 4

# Auto-detect CPU cores
uvicorn src.web.server:app --port 8080 --workers $(nproc)
```

### Redis Optimization

```conf
# redis.conf
maxmemory 256mb
maxmemory-policy allkeys-lru
save ""  # Disable persistence if state can be lost
```

### Ollama Performance

```bash
# Use GPU if available
CUDA_VISIBLE_DEVICES=0 ollama serve

# Adjust context window
# Smaller context = faster responses
ollama run llama3.1:8b-instruct-q8_0 --ctx-size 2048
```

---

## Backup & Recovery

### Redis Backup

```bash
# Manual backup
redis-cli save
cp /var/lib/redis/dump.rdb /backup/dump-$(date +%Y%m%d).rdb

# Automated backup (cron)
0 2 * * * redis-cli save && cp /var/lib/redis/dump.rdb /backup/dump-$(date +\%Y\%m\%d).rdb
```

### Application State

Task history and approvals are in Redis. Back up Redis data regularly.

---

## Scaling Considerations

### Horizontal Scaling

Current limitations:
- Single Redis instance (no clustering)
- SSE connections are per-worker
- No distributed task queue

For larger deployments, consider:
1. Redis Cluster for distributed state
2. Message queue (RabbitMQ, Redis Streams)
3. Load balancer with sticky sessions (for SSE)
4. Separate task workers from web workers

---

## License

Part of The Orchestrator project.
