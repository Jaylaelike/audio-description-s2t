# Separated Transcription Services

This system provides both direct and queue-based transcription services with a clean separation of concerns.

## Architecture Overview

The backend is now divided into separate, focused services:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                          │
└─────────────────────┬───────────────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
┌─────────────────┐    ┌─────────────────┐
│ Direct Service  │    │ Queue Service   │
│   (Port 8001)   │    │   (Port 8000)   │
│                 │    │                 │
│ • Immediate     │    │ • Background    │
│ • Synchronous   │    │ • WebSocket     │
│ • Simple        │    │ • Redis Queue   │
└─────────┬───────┘    └─────────┬───────┘
          │                      │
          └──────────┬───────────┘
                     │
                     ▼
           ┌─────────────────┐
           │ Transcription   │
           │    Service      │
           │                 │
           │ • Core Logic    │
           │ • Whisper Model │
           │ • Chunking      │
           └─────────────────┘
```

## Services

### 1. Direct Transcription Service (`main.py`)
- **Port**: 8001
- **Purpose**: Immediate transcription without queuing
- **Use case**: Small files, real-time requirements
- **Features**: Synchronous processing, simple API

### 2. Queue-based Service (`main_queue.py`)
- **Port**: 8000  
- **Purpose**: Background processing with queue management
- **Use case**: Large files, batch processing, high concurrency
- **Features**: Redis queue, WebSocket updates, task management

### 3. Core Transcription Service (`transcription_service.py`)
- **Shared component** used by both services
- **Features**: 
  - Whisper model management
  - Intelligent audio chunking
  - Large file processing
  - Error handling and logging

### 4. Queue Processing (`queue_processor.py`)
- **Queue management**: Redis-backed task queue
- **Real-time updates**: WebSocket notifications
- **Task lifecycle**: Queued → Processing → Completed/Failed

## Quick Start

### Option 1: Start All Services
```bash
cd backend/whisper-s2t
python start_services.py all
```

### Option 2: Start Individual Services

**Direct Service Only:**
```bash
python start_services.py direct
# Or manually: uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

**Queue Service Only:**
```bash
python start_services.py queue  
# Or manually: uvicorn main_queue:app --host 0.0.0.0 --port 8000 --reload
```

### Option 3: Docker Setup

```bash
cd backend/whisper-s2t
docker-compose up -d
```

### Prerequisites

1. **Python Environment**:
   ```bash
   conda activate audio-describe-whisper
   pip install -r requirements.txt
   ```

2. **Redis (for queue service only)**:
   ```bash
   # macOS
   brew services start redis
   
   # Ubuntu  
   sudo service redis-server start
   
   # Docker
   docker run -d -p 6379:6379 redis:latest
   ```

## API Endpoints

### Direct Service (Port 8001)
- `POST /transcribe/` - Direct transcription (immediate processing)
- `GET /health` - Service health check
- `GET /config` - Service configuration

### Queue Service (Port 8000)
- `POST /transcribe/` - Submit transcription task to queue
- `GET /task/{task_id}` - Get task status and result
- `DELETE /task/{task_id}` - Cancel queued task
- `GET /queue/status` - Get current queue status
- `WebSocket /ws/{task_id}` - Real-time task progress updates
- `GET /health` - Service health and queue status

### Service Selection

**Use Direct Service when:**
- Small audio files (<20MB)
- Need immediate results
- Simple integration requirements
- Low concurrency

**Use Queue Service when:**
- Large audio files (>20MB)
- High concurrency expected
- Need progress tracking
- Background processing acceptable

## Task Lifecycle

1. **Queued** → Task added to Redis stack (LIFO)
2. **Processing** → Worker picks up task and begins transcription
3. **Completed/Failed** → Final result stored and WebSocket notification sent

## Queue Behavior (Stack/LIFO)

The system uses a **stack-based queue** (LIFO - Last In, First Out):
- Recently submitted tasks are processed first
- Good for priority handling (latest requests get priority)
- Reduces wait time for urgent submissions

## Frontend Integration

The frontend automatically:
- Submits tasks to the queue
- Polls for status updates
- Displays real-time progress via WebSocket
- Shows queue position and estimated completion time

## WebSocket Usage

```javascript
// Connect to task updates
const ws = new WebSocket(`ws://localhost:8000/ws/${taskId}`)

ws.onmessage = (event) => {
  const update = JSON.parse(event.data)
  console.log('Progress:', update.data.progress)
  console.log('Status:', update.data.status)
  console.log('Message:', update.data.message)
}
```

## Error Handling

- **Connection Issues**: Automatic WebSocket reconnection
- **Processing Failures**: Detailed error messages in task status
- **Queue Failures**: Fallback to in-memory queue if Redis unavailable
- **Timeout Handling**: Configurable timeouts for different operations

## Configuration

Environment variables:
- `REDIS_URL`: Redis connection URL (default: redis://localhost:6379)
- `MAX_QUEUE_SIZE`: Maximum tasks in queue (default: unlimited)
- `WORKER_TIMEOUT`: Task processing timeout (default: 20 minutes)

## Monitoring

- Queue size and status via `/queue/status` endpoint
- Task progress via WebSocket connections
- Service health via `/health` endpoint
- Redis monitoring via Redis CLI: `redis-cli monitor`

## Scaling

To scale horizontally:
1. Run multiple instances of the transcription service
2. All instances share the same Redis queue
3. Load balance WebSocket connections
4. Consider Redis Cluster for high availability
