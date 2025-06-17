#!/usr/bin/env python3
"""
Main API Service with Separated Queue
Uses the separated queue service for better observability and reliability
"""
import asyncio
import os
import uuid
import tempfile
import shutil
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from queue_client import QueueClient, TaskStatus

# FastAPI app
app = FastAPI(
    title="Audio Transcription API with Separated Queue",
    description="Main API service using separated queue for transcription and risk detection",
    version="3.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
QUEUE_SERVICE_URL = os.getenv("QUEUE_SERVICE_URL", "http://localhost:8002")
TEMP_AUDIO_DIR = "temp_audio"

# Ensure temp directory exists
os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

# Response models
class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str
    queue_position: Optional[int] = None

class StatusResponse(BaseModel):
    task_id: str
    task_type: str
    status: str
    progress: float
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

class RiskDetectionRequest(BaseModel):
    transcription_id: str
    text: str

# WebSocket manager for real-time updates
class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.task_subscribers: Dict[str, set] = {}
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
    
    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        
        # Remove from task subscriptions
        for task_id, subscribers in self.task_subscribers.items():
            subscribers.discard(connection_id)
    
    async def subscribe_to_task(self, connection_id: str, task_id: str):
        if task_id not in self.task_subscribers:
            self.task_subscribers[task_id] = set()
        self.task_subscribers[task_id].add(connection_id)

websocket_manager = WebSocketManager()

@app.post("/transcribe/", response_model=TaskResponse)
async def queue_transcription(
    file: UploadFile = File(..., description="Audio file to transcribe"),
    language: str = "th",
    priority: int = 0
):
    """Queue a transcription task using the separated queue service"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Generate task ID for file naming
        task_id = str(uuid.uuid4())
        
        # Save uploaded file temporarily
        file_extension = os.path.splitext(file.filename)[1] or ".wav"
        temp_file_path = os.path.join(TEMP_AUDIO_DIR, f"{task_id}{file_extension}")
        
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Submit to queue service
        async with QueueClient(QUEUE_SERVICE_URL) as client:
            queue_task_id = await client.submit_transcription_task(
                file_path=temp_file_path,
                filename=file.filename,
                language=language,
                priority=priority
            )
            
            # Get queue stats for position
            stats = await client.get_queue_stats()
            queue_position = stats.get("queued_tasks", 0)
            
            return TaskResponse(
                task_id=queue_task_id,
                status="queued",
                message=f"Task queued successfully. Position in queue: {queue_position}",
                queue_position=queue_position
            )
    
    except Exception as e:
        # Clean up file on error
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Error queueing transcription: {str(e)}")

@app.post("/detect-risk/", response_model=TaskResponse)
async def queue_risk_detection(request: RiskDetectionRequest, priority: int = 0):
    """Queue a risk detection task using the separated queue service"""
    try:
        async with QueueClient(QUEUE_SERVICE_URL) as client:
            task_id = await client.submit_risk_detection_task(
                transcription_id=request.transcription_id,
                text=request.text,
                priority=priority
            )
            
            # Get queue stats for position
            stats = await client.get_queue_stats()
            queue_position = stats.get("queued_tasks", 0)
            
            return TaskResponse(
                task_id=task_id,
                status="queued",
                message=f"Risk detection task queued successfully. Position in queue: {queue_position}",
                queue_position=queue_position
            )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error queueing risk detection: {str(e)}")

@app.get("/task/{task_id}", response_model=StatusResponse)
async def get_task_status(task_id: str):
    """Get status of a task from the queue service"""
    try:
        async with QueueClient(QUEUE_SERVICE_URL) as client:
            task_status = await client.get_task_status(task_id)
            
            if not task_status:
                raise HTTPException(status_code=404, detail="Task not found")
            
            return StatusResponse(
                task_id=task_status["task_id"],
                task_type=task_status["task_type"],
                status=task_status["status"],
                progress=task_status["progress"],
                created_at=task_status["created_at"],
                started_at=task_status.get("started_at"),
                completed_at=task_status.get("completed_at"),
                result=task_status.get("result"),
                error_message=task_status.get("error_message")
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting task status: {str(e)}")

@app.get("/queue/status")
async def get_queue_status():
    """Get current queue status from the separated queue service"""
    try:
        async with QueueClient(QUEUE_SERVICE_URL) as client:
            stats = await client.get_queue_stats()
            return {
                **stats,
                "timestamp": datetime.now().isoformat()
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting queue status: {str(e)}")

@app.delete("/task/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a queued task"""
    try:
        async with QueueClient(QUEUE_SERVICE_URL) as client:
            success = await client.cancel_task(task_id)
            
            if success:
                return {"message": "Task cancelled successfully"}
            else:
                raise HTTPException(status_code=400, detail="Failed to cancel task")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cancelling task: {str(e)}")

@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time task updates"""
    connection_id = str(uuid.uuid4())
    
    try:
        await websocket_manager.connect(websocket, connection_id)
        await websocket_manager.subscribe_to_task(connection_id, task_id)
        
        # Send initial task status
        try:
            async with QueueClient(QUEUE_SERVICE_URL) as client:
                task_status = await client.get_task_status(task_id)
                if task_status:
                    initial_status = {
                        "type": "task_update",
                        "task_id": task_id,
                        "data": {
                            "status": task_status["status"],
                            "progress": task_status["progress"],
                            "message": f"Current status: {task_status['status']}"
                        }
                    }
                    await websocket.send_json(initial_status)
        except Exception as e:
            await websocket.send_json({
                "type": "error",
                "message": f"Error getting initial status: {str(e)}"
            })
        
        # Poll for updates (in a real implementation, you'd use proper pub/sub)
        while True:
            try:
                # Check for task updates every 2 seconds
                await asyncio.sleep(2)
                
                async with QueueClient(QUEUE_SERVICE_URL) as client:
                    task_status = await client.get_task_status(task_id)
                    if task_status:
                        update = {
                            "type": "task_update",
                            "task_id": task_id,
                            "data": {
                                "status": task_status["status"],
                                "progress": task_status["progress"],
                                "message": f"Status: {task_status['status']}"
                            }
                        }
                        
                        # Include result if completed
                        if task_status["status"] == "completed" and task_status.get("result"):
                            update["data"]["result"] = task_status["result"]
                        elif task_status["status"] == "failed" and task_status.get("error_message"):
                            update["data"]["error"] = task_status["error_message"]
                        
                        await websocket.send_json(update)
                        
                        # Stop polling if task is done
                        if task_status["status"] in ["completed", "failed", "cancelled"]:
                            break
            
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error polling status: {str(e)}"
                })
                break
    
    except WebSocketDisconnect:
        websocket_manager.disconnect(connection_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        websocket_manager.disconnect(connection_id)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check queue service health
        async with QueueClient(QUEUE_SERVICE_URL) as client:
            stats = await client.get_queue_stats()
            queue_healthy = True
    except Exception:
        stats = {}
        queue_healthy = False
    
    return {
        "status": "healthy" if queue_healthy else "degraded",
        "timestamp": datetime.now().isoformat(),
        "queue_service": {
            "url": QUEUE_SERVICE_URL,
            "healthy": queue_healthy,
            "stats": stats
        }
    }

# Administrative endpoints
@app.get("/admin/tasks")
async def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    """List tasks with filtering"""
    try:
        async with QueueClient(QUEUE_SERVICE_URL) as client:
            tasks = await client.list_tasks(status_filter=status, limit=limit)
            return {
                "tasks": tasks,
                "total": len(tasks),
                "limit": limit,
                "offset": offset
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing tasks: {str(e)}")

@app.post("/admin/backup")
async def force_backup():
    """Force backup of queue state"""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{QUEUE_SERVICE_URL}/admin/backup") as response:
                if response.status == 200:
                    return {"message": "Backup completed successfully"}
                else:
                    raise HTTPException(status_code=500, detail="Backup failed")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error forcing backup: {str(e)}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Main API Service with Separated Queue")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--queue-url", default="http://localhost:8002", help="Queue service URL")
    
    args = parser.parse_args()
    
    # Update queue service URL from command line
    QUEUE_SERVICE_URL = args.queue_url
    
    print(f"Starting Main API Service on {args.host}:{args.port}")
    print(f"Queue Service URL: {QUEUE_SERVICE_URL}")
    
    uvicorn.run(app, host=args.host, port=args.port)