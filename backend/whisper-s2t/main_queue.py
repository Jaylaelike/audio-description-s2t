"""
Queue-based FastAPI transcription service with WebSocket support
"""
import asyncio
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import shutil

from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from queue_processor import (
    TaskQueue, TranscriptionProcessor, RiskDetectionProcessor, WebSocketManager, 
    TranscriptionTask, RiskDetectionTask, TaskStatus, TaskType, queue_processor,
    task_queue, websocket_manager
)

# FastAPI app
app = FastAPI(
    title="Queue-based Transcription API",
    description="Transcription API with queue system and real-time WebSocket updates",
    version="2.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Response models
class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str
    queue_position: int

class StatusResponse(BaseModel):
    task_id: str
    status: str
    progress: float
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

# Global flag to track if background processor is running
background_processor_started = False

@app.on_event("startup")
async def startup_event():
    """Start the background queue processor"""
    global background_processor_started
    if not background_processor_started:
        asyncio.create_task(queue_processor())
        background_processor_started = True
        print("Background queue processor started")

@app.post("/transcribe/", response_model=TaskResponse)
async def queue_transcription(
    file: UploadFile = File(..., description="Audio file to transcribe"),
    language: str = "th"
):
    """Queue a transcription task"""
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
            created_at=datetime.now()
        )
        
        # Add to queue
        if task_queue.push_task(task):
            queue_position = task_queue.get_queue_size()
            
            return TaskResponse(
                task_id=task_id,
                status=TaskStatus.QUEUED.value,
                message=f"Task queued successfully. Position in queue: {queue_position}",
                queue_position=queue_position
            )
        else:
            # Clean up file if queueing failed
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            raise HTTPException(status_code=500, detail="Failed to queue task")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error queueing transcription: {str(e)}")

@app.get("/task/{task_id}", response_model=StatusResponse)
async def get_task_status(task_id: str):
    """Get status of a transcription task"""
    task = task_queue.get_task_status(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return StatusResponse(
        task_id=task.task_id,
        status=task.status.value,
        progress=task.progress,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result=task.result,
        error_message=task.error_message
    )

@app.get("/queue/status")
async def get_queue_status():
    """Get current queue status"""
    return {
        "queue_size": task_queue.get_queue_size(),
        "timestamp": datetime.now().isoformat()
    }

@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time task updates"""
    connection_id = str(uuid.uuid4())
    
    try:
        await websocket_manager.connect(websocket, connection_id)
        await websocket_manager.subscribe_to_task(connection_id, task_id)
        
        # Send initial task status
        task = task_queue.get_task_status(task_id)
        if task:
            initial_status = {
                "type": "task_update",
                "task_id": task_id,
                "data": {
                    "status": task.status.value,
                    "progress": task.progress,
                    "message": f"Current status: {task.status.value}"
                }
            }
            await websocket.send_text(str(initial_status))
        
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            # Echo back for keepalive
            await websocket.send_text(f"Echo: {data}")
    
    except WebSocketDisconnect:
        websocket_manager.disconnect(connection_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        websocket_manager.disconnect(connection_id)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "queue_size": task_queue.get_queue_size(),
        "timestamp": datetime.now().isoformat()
    }

@app.delete("/task/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a queued task (only works for queued tasks)"""
    task = task_queue.get_task_status(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != TaskStatus.QUEUED:
        raise HTTPException(status_code=400, detail=f"Cannot cancel task with status: {task.status}")
    
    # Mark as failed/cancelled
    task_queue.update_task_status(
        task_id, 
        TaskStatus.FAILED, 
        error_message="Task cancelled by user",
        completed_at=datetime.now()
    )
    
    # Clean up file if it's a transcription task
    if isinstance(task, TranscriptionTask) and hasattr(task, 'file_path') and os.path.exists(task.file_path):
        os.remove(task.file_path)
    
    return {"message": "Task cancelled successfully"}

# Risk detection endpoint
class RiskDetectionRequest(BaseModel):
    transcription_id: str
    text: str

@app.post("/detect-risk/", response_model=TaskResponse)
async def queue_risk_detection(request: RiskDetectionRequest):
    """Queue a risk detection task"""
    try:
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Create risk detection task
        task = RiskDetectionTask(
            task_id=task_id,
            transcription_id=request.transcription_id,
            text=request.text,
            created_at=datetime.now()
        )
        
        # Add to queue
        if task_queue.push_task(task):
            queue_position = task_queue.get_queue_size()
            
            return TaskResponse(
                task_id=task_id,
                status=TaskStatus.QUEUED.value,
                message=f"Risk detection task queued successfully. Position in queue: {queue_position}",
                queue_position=queue_position
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to queue risk detection task")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error queueing risk detection: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
