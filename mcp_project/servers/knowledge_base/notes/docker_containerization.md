# Docker Containerization Guide

## What is Docker?

Docker is a platform that uses containerization technology to package applications and their dependencies into lightweight, portable containers. These containers can run consistently across different environments, from development to production.

## Key Concepts

### Images
Docker images are read-only templates used to create containers. They contain the application code, runtime, system tools, libraries, and settings.

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "app.py"]
```

### Containers
Containers are running instances of Docker images. They are isolated processes that share the host OS kernel.

```bash
# Run a container
docker run -d -p 8080:80 --name myapp nginx

# List running containers
docker ps

# Stop a container
docker stop myapp
```

### Dockerfile
A Dockerfile is a text file containing instructions to build a Docker image.

```dockerfile
# Use official Python runtime as base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV FLASK_APP=app.py

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]
```

## Docker Commands

### Image Management
```bash
# Build an image
docker build -t myapp:latest .

# List images
docker images

# Remove an image
docker rmi myapp:latest

# Pull an image from registry
docker pull nginx:alpine

# Push an image to registry
docker push myregistry/myapp:latest
```

### Container Management
```bash
# Run container in background
docker run -d --name myapp -p 8080:80 nginx

# Run container interactively
docker run -it --rm ubuntu:20.04 /bin/bash

# Execute command in running container
docker exec -it myapp /bin/bash

# View container logs
docker logs myapp

# Copy files to/from container
docker cp file.txt myapp:/app/
docker cp myapp:/app/output.txt ./
```

### System Management
```bash
# View system information
docker system info

# Clean up unused resources
docker system prune

# View resource usage
docker stats

# View container processes
docker top myapp
```

## Docker Compose

Docker Compose is a tool for defining and running multi-container Docker applications using a YAML file.

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mydb
    depends_on:
      - db
      - redis
    volumes:
      - ./app:/app
    networks:
      - app-network

  db:
    image: postgres:13
    environment:
      POSTGRES_DB: mydb
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - app-network

  redis:
    image: redis:alpine
    networks:
      - app-network

volumes:
  postgres_data:

networks:
  app-network:
    driver: bridge
```

### Compose Commands
```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f web

# Scale services
docker-compose up -d --scale web=3

# Execute command in service
docker-compose exec web python manage.py migrate
```

## Best Practices

### Image Optimization
1. **Use multi-stage builds** to reduce image size
2. **Use specific base image tags** instead of 'latest'
3. **Minimize layers** by combining RUN commands
4. **Use .dockerignore** to exclude unnecessary files
5. **Run as non-root user** for security

```dockerfile
# Multi-stage build example
FROM node:16-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

FROM node:16-alpine AS runtime
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY . .
USER node
CMD ["node", "server.js"]
```

### Security
1. **Scan images for vulnerabilities**
2. **Use official base images**
3. **Keep images updated**
4. **Limit container privileges**
5. **Use secrets management**

```bash
# Scan image for vulnerabilities
docker scan myapp:latest

# Run container with limited privileges
docker run --read-only --tmpfs /tmp myapp:latest
```

### Performance
1. **Use appropriate base images** (alpine for smaller size)
2. **Optimize layer caching** by ordering Dockerfile instructions
3. **Use health checks** for container monitoring
4. **Set resource limits**

```bash
# Run with resource limits
docker run -m 512m --cpus="1.0" myapp:latest
```

## Networking

### Bridge Network (Default)
```bash
# Create custom bridge network
docker network create mynetwork

# Run containers on custom network
docker run -d --network mynetwork --name app1 nginx
docker run -d --network mynetwork --name app2 nginx
```

### Host Network
```bash
# Use host networking
docker run --network host nginx
```

### Overlay Network (Swarm)
```bash
# Create overlay network for swarm
docker network create -d overlay myoverlay
```

## Volumes and Data Management

### Named Volumes
```bash
# Create named volume
docker volume create mydata

# Use named volume
docker run -v mydata:/data nginx

# List volumes
docker volume ls

# Remove volume
docker volume rm mydata
```

### Bind Mounts
```bash
# Mount host directory
docker run -v /host/path:/container/path nginx

# Mount current directory
docker run -v $(pwd):/app nginx
```

### tmpfs Mounts
```bash
# Mount tmpfs (in-memory)
docker run --tmpfs /tmp nginx
```

## Monitoring and Logging

### Container Logs
```bash
# View logs
docker logs myapp

# Follow logs
docker logs -f myapp

# View last 100 lines
docker logs --tail 100 myapp
```

### Resource Monitoring
```bash
# View resource usage
docker stats

# View specific container stats
docker stats myapp
```

## Troubleshooting

### Common Issues
1. **Port conflicts** - Use different host ports
2. **Permission issues** - Check file ownership and permissions
3. **Network connectivity** - Verify network configuration
4. **Resource constraints** - Monitor CPU and memory usage

### Debugging Commands
```bash
# Inspect container configuration
docker inspect myapp

# View container processes
docker top myapp

# Access container shell
docker exec -it myapp /bin/bash

# View container filesystem changes
docker diff myapp
```

## Production Deployment

### Container Orchestration
- **Docker Swarm** - Built-in orchestration
- **Kubernetes** - Advanced orchestration platform
- **Amazon ECS** - AWS container service
- **Google Cloud Run** - Serverless containers

### CI/CD Integration
```yaml
# GitHub Actions example
name: Build and Deploy
on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build Docker image
        run: docker build -t myapp:${{ github.sha }} .
      - name: Push to registry
        run: docker push myapp:${{ github.sha }}
```

Tags: docker, containers, devops, deployment, microservices, infrastructure