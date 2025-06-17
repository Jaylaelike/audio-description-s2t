# Separated Queue System for Audio Transcription

This document describes the new separated queue system architecture that provides better observability, reliability, and backup/recovery capabilities.

## Architecture Overview

The separated queue system consists of the following components:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Main API      │    │   Queue API     │    │     Redis       │
│ (main_separated │    │(queue_http_api) │    │   (Storage)     │
│     .py)        │    │     .py)        │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │  Queue Workers  │
                    │ (queue_worker   │
                    │     .py)        │
                    └─────────────────┘
```

## Components

### 1. Queue Service (`queue_service.py`)
- **Core queue management with Redis backend**
- **Automatic backup and recovery functionality**
- **Priority-based task scheduling (LIFO with priority)**
- **Stuck task cleanup and monitoring**
- **In-memory fallback when Redis is unavailable**

Key features:
- Priority queue using Redis sorted sets
- Automatic periodic backups (every 5 minutes)
- Graceful shutdown with backup on signal
- Task retry mechanism with configurable max retries
- Processing time monitoring and cleanup

### 2. Queue HTTP API (`queue_http_api.py`)
- **REST API for queue operations**
- **Task submission and status checking**
- **Administrative endpoints for monitoring**

Endpoints:
- `POST /tasks/transcription` - Submit transcription task
- `POST /tasks/risk-detection` - Submit risk detection task
- `GET /tasks/{task_id}` - Get task status
- `GET /tasks` - List tasks with filtering
- `DELETE /tasks/{task_id}` - Cancel task
- `GET /stats` - Get queue statistics
- `GET /health` - Health check
- `POST /admin/backup` - Force backup
- `POST /admin/cleanup-stuck-tasks` - Clean stuck tasks

### 3. Queue Workers (`queue_worker.py`)
- **Independent worker processes**
- **Horizontal scaling capability**
- **Automatic task processing**
- **Failure handling and cleanup**

Features:
- Multi-worker support for parallel processing
- Graceful shutdown handling
- Individual worker identification
- Automatic file cleanup after processing
- Memory management with garbage collection

### 4. Queue Client (`queue_client.py`)
- **HTTP client library for queue operations**
- **Async/await support**
- **Convenience functions for common operations**

### 5. Queue Monitor (`queue_monitor.py`)
- **CLI tool for queue monitoring and management**
- **Real-time queue watching**
- **Task management operations**

Commands:
```bash
python queue_monitor.py stats              # Show statistics
python queue_monitor.py list               # List tasks
python queue_monitor.py show <task_id>     # Show task details
python queue_monitor.py cancel <task_id>   # Cancel task
python queue_monitor.py retry <task_id>    # Retry failed task
python queue_monitor.py clear --hours 24   # Clear old completed tasks
python queue_monitor.py backup             # Force backup
python queue_monitor.py watch              # Real-time monitoring
```

### 6. Main API Service (`main_separated.py`)
- **Updated main API using separated queue**
- **WebSocket support for real-time updates**
- **Same external API as before (backward compatible)**

### 7. Service Orchestrator (`start_separated_services.py`)
- **Manages all services in correct startup order**
- **Service monitoring and health checking**
- **Graceful shutdown handling**

## Backup and Recovery

### Automatic Backup
- **Periodic backups every 5 minutes** (configurable)
- **Backup on graceful shutdown** (SIGINT/SIGTERM)
- **Emergency backup on errors**
- **Backup includes:**
  - Queue state (priority order)
  - Task details and metadata
  - Processing task information
  - Queue statistics

### Recovery Process
- **Automatic recovery on startup** if backup file exists
- **Maintains task order and priority**
- **Restores all task metadata**
- **Backup file is removed after successful recovery**

### Backup Storage Format
- **Pickle format for reliable serialization**
- **Includes timestamp for backup tracking**
- **Compressed storage for efficiency**

## Observability Features

### Real-time Monitoring
- **Queue statistics (total, queued, processing, completed, failed)**
- **Individual task progress tracking**
- **Worker status monitoring**
- **Success/failure rates**

### Health Checks
- **Redis connectivity status**
- **Service uptime tracking**
- **Queue service availability**
- **Worker process health**

### Logging
- **Structured logging across all components**
- **Individual log files per service**
- **Configurable log levels**
- **Error tracking and debugging information**

## Deployment Options

### 1. Docker Compose (Recommended)
```bash
# Start all services with Docker
docker-compose -f docker-compose-separated.yml up -d

# Scale workers
docker-compose -f docker-compose-separated.yml up -d --scale queue-worker=4

# Monitor logs
docker-compose -f docker-compose-separated.yml logs -f
```

### 2. Manual Startup
```bash
# Start all services manually
python start_separated_services.py start --workers 2 --monitor

# Or start individual components:
redis-server --port 6379
python queue_http_api.py --host 0.0.0.0 --port 8002
python queue_worker.py --worker-id worker-1
python queue_worker.py --worker-id worker-2
python main_separated.py --host 0.0.0.0 --port 8000
```

### 3. Production Deployment
- **Use Redis Cluster for high availability**
- **Deploy workers on multiple machines**
- **Use load balancer for API endpoints**
- **Set up monitoring and alerting**
- **Configure backup to external storage**

## Configuration

### Environment Variables
```bash
REDIS_URL=redis://localhost:6379          # Redis connection
QUEUE_SERVICE_URL=http://localhost:8002   # Queue API URL
BACKUP_INTERVAL=300                       # Backup interval (seconds)
MAX_PROCESSING_TIME=3600                  # Max task processing time (seconds)
```

### Queue Configuration
- **Priority levels**: Higher number = higher priority
- **Retry mechanism**: Configurable max retries per task
- **Processing timeout**: Automatic cleanup of stuck tasks
- **Backup frequency**: Configurable backup intervals

## Migration from Old System

### Steps to migrate:
1. **Stop old queue system** (`main_queue.py`)
2. **Backup existing queue state** (if any)
3. **Start new separated system**:
   ```bash
   python start_separated_services.py start --workers 2
   ```
4. **Update frontend** to use new API endpoints (if needed)
5. **Monitor system** for proper operation

### Compatibility
- **API endpoints remain the same** for external clients
- **WebSocket interface preserved**
- **Task result format unchanged**
- **Backward compatible with existing integrations**

## Monitoring and Maintenance

### Daily Operations
```bash
# Check system status
python queue_monitor.py stats

# View recent tasks
python queue_monitor.py list --limit 20

# Clean old completed tasks
python queue_monitor.py clear --hours 48

# Force backup
python queue_monitor.py backup
```

### Troubleshooting
```bash
# Watch queue in real-time
python queue_monitor.py watch --interval 5

# Check specific task
python queue_monitor.py show <task_id>

# Retry failed tasks
python queue_monitor.py retry <task_id>

# Check service health
curl http://localhost:8000/health
curl http://localhost:8002/health
```

## Performance Benefits

### Scalability
- **Horizontal worker scaling**
- **Independent service scaling**
- **Redis-based queue for high throughput**

### Reliability
- **Automatic backup and recovery**
- **Graceful failure handling**
- **Service isolation and independence**

### Observability
- **Real-time monitoring dashboard**
- **Detailed task tracking**
- **Performance metrics and statistics**

### Maintainability
- **Modular architecture**
- **Independent deployments**
- **Easy debugging and troubleshooting**

## Future Enhancements

### Planned Features
- **Web-based monitoring dashboard**
- **Metrics export to Prometheus/Grafana**
- **Advanced queue routing and filtering**
- **Distributed worker pools**
- **Automatic scaling based on queue load**

### Integration Options
- **Message queue integration** (RabbitMQ, Apache Kafka)
- **Cloud storage backup** (AWS S3, Google Cloud Storage)
- **Kubernetes deployment** with auto-scaling
- **Advanced monitoring** with alerting systems