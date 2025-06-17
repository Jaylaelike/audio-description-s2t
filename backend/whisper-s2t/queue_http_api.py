#!/usr/bin/env python3
"""
HTTP API for Queue Service
Provides REST API endpoints for queue management
"""
import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging

from fastapi import FastAPI, HTTPException, File, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import tempfile
import os
import shutil

from queue_service import (
    StandaloneQueueService, TranscriptionTask, RiskDetectionTask,
    TaskStatus, TaskType, QueueStats
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Queue Service HTTP API",
    description="REST API for managing transcription and risk detection queue",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global queue service instance
queue_service = None

# Request/Response models
class TranscriptionTaskRequest(BaseModel):
    filename: str
    language: str = "th"
    priority: int = 0

class RiskDetectionTaskRequest(BaseModel):
    transcription_id: str
    text: str
    priority: int = 0

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str
    queue_position: Optional[int] = None

class TaskStatusResponse(BaseModel):
    task_id: str
    task_type: str
    status: str
    progress: float
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

@app.on_event("startup")
async def startup_event():
    """Initialize queue service on startup"""
    global queue_service
    queue_service = StandaloneQueueService()
    logger.info("Queue HTTP API started")

@app.post("/tasks/transcription", response_model=TaskResponse)
async def submit_transcription_task(
    file: UploadFile = File(...),
    language: str = "th",
    priority: int = 0
):
    """Submit a transcription task to the queue"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Create temp directory if it doesn't exist
        temp_dir = "temp_audio"
        os.makedirs(temp_dir, exist_ok=True)
        
        # Save uploaded file
        file_extension = os.path.splitext(file.filename)[1] or ".wav"
        temp_file_path = os.path.join(temp_dir, f"{task_id}{file_extension}")
        
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Create transcription task
        task = TranscriptionTask(
            task_id=task_id,
            file_path=temp_file_path,
            filename=file.filename,
            language=language,
            priority=priority,
            created_at=datetime.now()
        )
        
        # Add to queue
        if queue_service.push_task(task):
            stats = queue_service.get_queue_stats()
            
            return TaskResponse(
                task_id=task_id,
                status=TaskStatus.QUEUED.value,
                message=f"Transcription task queued successfully",
                queue_position=stats.queued_tasks
            )
        else:
            # Clean up file if queueing failed
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise HTTPException(status_code=500, detail="Failed to queue task")
    
    except Exception as e:
        logger.error(f"Error submitting transcription task: {e}")
        raise HTTPException(status_code=500, detail=f"Error queueing transcription: {str(e)}")

@app.post("/tasks/risk-detection", response_model=TaskResponse)
async def submit_risk_detection_task(request: RiskDetectionTaskRequest):
    """Submit a risk detection task to the queue"""
    try:
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Create risk detection task
        task = RiskDetectionTask(
            task_id=task_id,
            transcription_id=request.transcription_id,
            text=request.text,
            priority=request.priority,
            created_at=datetime.now()
        )
        
        # Add to queue
        if queue_service.push_task(task):
            stats = queue_service.get_queue_stats()
            
            return TaskResponse(
                task_id=task_id,
                status=TaskStatus.QUEUED.value,
                message=f"Risk detection task queued successfully",
                queue_position=stats.queued_tasks
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to queue risk detection task")
    
    except Exception as e:
        logger.error(f"Error submitting risk detection task: {e}")
        raise HTTPException(status_code=500, detail=f"Error queueing risk detection: {str(e)}")

@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Get status of a specific task"""
    task = queue_service.get_task_status(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskStatusResponse(
        task_id=task.task_id,
        task_type=task.task_type.value,
        status=task.status.value,
        progress=task.progress,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result=task.result,
        error_message=task.error_message,
        retry_count=task.retry_count,
        max_retries=task.max_retries
    )

@app.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 10,
    offset: int = 0
):
    """List tasks with optional filtering"""
    # This is a simplified implementation
    # In a real system, you'd implement proper pagination and filtering
    tasks = []
    
    try:
        if queue_service.redis_client:
            # Get task keys from Redis
            task_keys = queue_service.redis_client.hkeys("queue_tasks")
            completed_keys = queue_service.redis_client.hkeys("queue_completed")
            all_keys = list(task_keys) + list(completed_keys)
            
            for task_id in all_keys[offset:offset+limit]:
                task = queue_service.get_task_status(task_id)
                if task:
                    # Apply filters
                    if status and task.status.value != status:
                        continue
                    if task_type and task.task_type.value != task_type:
                        continue
                    
                    tasks.append({
                        "task_id": task.task_id,
                        "task_type": task.task_type.value,
                        "status": task.status.value,
                        "progress": task.progress,
                        "created_at": task.created_at,
                        "started_at": task.started_at,
                        "completed_at": task.completed_at
                    })
        else:
            # In-memory fallback
            all_tasks = list(queue_service.memory_tasks.values()) + list(queue_service.memory_completed.values())
            
            for task_data in all_tasks[offset:offset+limit]:
                # Apply filters
                if status and task_data.get('status') != status:
                    continue
                if task_type and task_data.get('task_type') != task_type:
                    continue
                
                tasks.append({
                    "task_id": task_data['task_id'],
                    "task_type": task_data.get('task_type', 'transcription'),
                    "status": task_data.get('status', 'unknown'),
                    "progress": task_data.get('progress', 0.0),
                    "created_at": datetime.fromisoformat(task_data['created_at']),
                    "started_at": datetime.fromisoformat(task_data['started_at']) if task_data.get('started_at') else None,
                    "completed_at": datetime.fromisoformat(task_data['completed_at']) if task_data.get('completed_at') else None
                })
    
    except Exception as e:
        logger.error(f"Error listing tasks: {e}")
        raise HTTPException(status_code=500, detail="Error listing tasks")
    
    return {
        "tasks": tasks,
        "total": len(tasks),
        "offset": offset,
        "limit": limit
    }

@app.delete("/tasks/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a queued task"""
    task = queue_service.get_task_status(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.QUEUED:
        raise HTTPException(status_code=400, detail=f"Cannot cancel task with status: {task.status.value}")
    
    # Update task status to cancelled
    success = queue_service.update_task_status(
        task_id,
        TaskStatus.CANCELLED,
        completed_at=datetime.now(),
        error_message="Task cancelled by user"
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel task")
    
    # Clean up file if it's a transcription task
    if isinstance(task, TranscriptionTask) and hasattr(task, 'file_path') and os.path.exists(task.file_path):
        os.remove(task.file_path)
    
    return {"message": "Task cancelled successfully"}

@app.get("/stats")
async def get_queue_stats():
    """Get current queue statistics"""
    stats = queue_service.get_queue_stats()
    return stats.dict()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    stats = queue_service.get_queue_stats()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "queue_stats": stats.dict()
    }

@app.post("/admin/backup")
async def force_backup():
    """Force an immediate backup"""
    try:
        success = queue_service.save_backup()
        if success:
            return {"message": "Backup completed successfully"}
        else:
            raise HTTPException(status_code=500, detail="Backup failed")
    except Exception as e:
        logger.error(f"Error forcing backup: {e}")
        raise HTTPException(status_code=500, detail=f"Backup error: {str(e)}")

@app.post("/admin/cleanup-stuck-tasks")
async def cleanup_stuck_tasks():
    """Clean up tasks that have been processing too long"""
    try:
        queue_service.cleanup_stuck_tasks()
        return {"message": "Stuck tasks cleanup completed"}
    except Exception as e:
        logger.error(f"Error cleaning up stuck tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup error: {str(e)}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Queue Service HTTP API")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8002, help="Port to bind to")
    parser.add_argument("--redis-url", default="redis://localhost:6379", help="Redis URL")
    
    args = parser.parse_args()
    
    logger.info(f"Starting Queue HTTP API on {args.host}:{args.port}")
    logger.info(f"Redis URL: {args.redis_url}")
    
    uvicorn.run(app, host=args.host, port=args.port)