"""
Queue-based transcription processor with real-time status updates
"""
import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum
import redis
from pydantic import BaseModel
from fastapi import FastAPI, File, UploadFile, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import shutil
import gc
import pickle
import signal
import sys

# Import the separated transcription service
from transcription_service import TranscriptionService

# Task status enum
class TaskStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"

# Task type enum
class TaskType(str, Enum):
    TRANSCRIPTION = "transcription"
    RISK_DETECTION = "risk_detection"

# Pydantic models
class BaseTask(BaseModel):
    task_id: str
    task_type: TaskType
    status: TaskStatus = TaskStatus.QUEUED
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    progress: float = 0.0

class TranscriptionTask(BaseTask):
    task_type: TaskType = TaskType.TRANSCRIPTION
    file_path: str
    filename: str
    language: str = "th"

class RiskDetectionTask(BaseTask):
    task_type: TaskType = TaskType.RISK_DETECTION
    transcription_id: str
    text: str

class TaskQueue:
    """Stack-based task queue using Redis with backup functionality"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", backup_file: str = "queue_backup.pkl"):
        self.backup_file = backup_file
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            self.redis_client.ping()  # Test connection
            print("Connected to Redis successfully")
        except Exception as e:
            print(f"Redis connection failed: {e}")
            print("Falling back to in-memory queue")
            self.redis_client = None
            self.memory_queue = []
            self.memory_tasks = {}
        
        # Load backup if exists
        self.load_backup()
    
    def push_task(self, task: BaseTask) -> bool:
        """Push task to the stack (LIFO - Last In, First Out)"""
        try:
            task_data = task.dict()
            task_data['created_at'] = task_data['created_at'].isoformat()
            
            if self.redis_client:
                # Use Redis list as stack (LPUSH for stack behavior)
                self.redis_client.lpush("transcription_queue", json.dumps(task_data))
                self.redis_client.hset("transcription_tasks", task.task_id, json.dumps(task_data))
            else:
                # In-memory fallback
                self.memory_queue.insert(0, task_data)  # Insert at beginning for stack behavior
                self.memory_tasks[task.task_id] = task_data
            
            print(f"Task {task.task_id} ({task.task_type}) pushed to queue")
            return True
        except Exception as e:
            print(f"Error pushing task: {e}")
            return False
    
    def pop_task(self) -> Optional[BaseTask]:
        """Pop task from the stack (LIFO)"""
        try:
            if self.redis_client:
                # Use LPOP for stack behavior (Last In, First Out)
                task_data = self.redis_client.lpop("transcription_queue")
                if task_data:
                    task_dict = json.loads(task_data)
                    task_dict['created_at'] = datetime.fromisoformat(task_dict['created_at'])
                    
                    # Create appropriate task type based on task_type field
                    if task_dict.get('task_type') == TaskType.TRANSCRIPTION:
                        return TranscriptionTask(**task_dict)
                    elif task_dict.get('task_type') == TaskType.RISK_DETECTION:
                        return RiskDetectionTask(**task_dict)
                    else:
                        # Default to transcription for backward compatibility
                        task_dict['task_type'] = TaskType.TRANSCRIPTION
                        return TranscriptionTask(**task_dict)
            else:
                # In-memory fallback
                if self.memory_queue:
                    task_data = self.memory_queue.pop(0)  # Pop from beginning for stack behavior
                    task_data['created_at'] = datetime.fromisoformat(task_data['created_at'])
                    
                    # Create appropriate task type based on task_type field
                    if task_data.get('task_type') == TaskType.TRANSCRIPTION:
                        return TranscriptionTask(**task_data)
                    elif task_data.get('task_type') == TaskType.RISK_DETECTION:
                        return RiskDetectionTask(**task_data)
                    else:
                        # Default to transcription for backward compatibility
                        task_data['task_type'] = TaskType.TRANSCRIPTION
                        return TranscriptionTask(**task_data)
            
            return None
        except Exception as e:
            print(f"Error popping task: {e}")
            return None
    
    def update_task_status(self, task_id: str, status: TaskStatus, **kwargs) -> bool:
        """Update task status and additional fields"""
        try:
            if self.redis_client:
                task_data = self.redis_client.hget("transcription_tasks", task_id)
                if task_data:
                    task_dict = json.loads(task_data)
                    task_dict['status'] = status.value
                    
                    # Update additional fields
                    for key, value in kwargs.items():
                        if isinstance(value, datetime):
                            value = value.isoformat()
                        task_dict[key] = value
                    
                    self.redis_client.hset("transcription_tasks", task_id, json.dumps(task_dict))
                    return True
            else:
                # In-memory fallback
                if task_id in self.memory_tasks:
                    self.memory_tasks[task_id]['status'] = status.value
                    for key, value in kwargs.items():
                        if isinstance(value, datetime):
                            value = value.isoformat()
                        self.memory_tasks[task_id][key] = value
                    return True
            
            return False
        except Exception as e:
            print(f"Error updating task status: {e}")
            return False
    
    def get_task_status(self, task_id: str) -> Optional[BaseTask]:
        """Get current task status"""
        try:
            if self.redis_client:
                task_data = self.redis_client.hget("transcription_tasks", task_id)
                if task_data:
                    task_dict = json.loads(task_data)
                    # Handle datetime fields safely
                    task_dict['created_at'] = datetime.fromisoformat(task_dict['created_at'])
                    if task_dict.get('started_at'):
                        task_dict['started_at'] = datetime.fromisoformat(task_dict['started_at'])
                    else:
                        task_dict['started_at'] = None
                    if task_dict.get('completed_at'):
                        task_dict['completed_at'] = datetime.fromisoformat(task_dict['completed_at'])
                    else:
                        task_dict['completed_at'] = None
                    # Ensure optional fields have proper values
                    if not task_dict.get('result'):
                        task_dict['result'] = None
                    if not task_dict.get('error_message'):
                        task_dict['error_message'] = None
                    
                    # Create appropriate task type
                    if task_dict.get('task_type') == TaskType.TRANSCRIPTION:
                        return TranscriptionTask(**task_dict)
                    elif task_dict.get('task_type') == TaskType.RISK_DETECTION:
                        return RiskDetectionTask(**task_dict)
                    else:
                        # Default to transcription for backward compatibility
                        task_dict['task_type'] = TaskType.TRANSCRIPTION
                        return TranscriptionTask(**task_dict)
            else:
                # In-memory fallback
                if task_id in self.memory_tasks:
                    task_dict = self.memory_tasks[task_id].copy()
                    # Handle datetime fields safely
                    task_dict['created_at'] = datetime.fromisoformat(task_dict['created_at'])
                    if task_dict.get('started_at'):
                        task_dict['started_at'] = datetime.fromisoformat(task_dict['started_at'])
                    else:
                        task_dict['started_at'] = None
                    if task_dict.get('completed_at'):
                        task_dict['completed_at'] = datetime.fromisoformat(task_dict['completed_at'])
                    else:
                        task_dict['completed_at'] = None
                    # Ensure optional fields have proper values
                    if not task_dict.get('result'):
                        task_dict['result'] = None
                    if not task_dict.get('error_message'):
                        task_dict['error_message'] = None
                    
                    # Create appropriate task type
                    if task_dict.get('task_type') == TaskType.TRANSCRIPTION:
                        return TranscriptionTask(**task_dict)
                    elif task_dict.get('task_type') == TaskType.RISK_DETECTION:
                        return RiskDetectionTask(**task_dict)
                    else:
                        # Default to transcription for backward compatibility
                        task_dict['task_type'] = TaskType.TRANSCRIPTION
                        return TranscriptionTask(**task_dict)
            
            return None
        except Exception as e:
            print(f"Error getting task status: {e}")
            return None
    
    def get_queue_size(self) -> int:
        """Get current queue size"""
        try:
            if self.redis_client:
                return self.redis_client.llen("transcription_queue")
            else:
                return len(self.memory_queue)
        except Exception as e:
            print(f"Error getting queue size: {e}")
            return 0
    
    def save_backup(self) -> bool:
        """Save current queue state to backup file"""
        try:
            backup_data = {
                'queue': [],
                'tasks': {},
                'timestamp': datetime.now().isoformat()
            }
            
            if self.redis_client:
                # Get all tasks from Redis queue
                queue_data = self.redis_client.lrange("transcription_queue", 0, -1)
                backup_data['queue'] = queue_data
                
                # Get all task details
                task_keys = self.redis_client.hkeys("transcription_tasks")
                for task_id in task_keys:
                    task_data = self.redis_client.hget("transcription_tasks", task_id)
                    backup_data['tasks'][task_id] = task_data
            else:
                # In-memory fallback
                backup_data['queue'] = [json.dumps(task) for task in self.memory_queue]
                backup_data['tasks'] = {k: json.dumps(v) for k, v in self.memory_tasks.items()}
            
            # Write to backup file
            with open(self.backup_file, 'wb') as f:
                pickle.dump(backup_data, f)
            
            print(f"Queue backup saved to {self.backup_file}")
            return True
            
        except Exception as e:
            print(f"Error saving backup: {e}")
            return False
    
    def load_backup(self) -> bool:
        """Load queue state from backup file"""
        try:
            if not os.path.exists(self.backup_file):
                print("No backup file found")
                return False
            
            with open(self.backup_file, 'rb') as f:
                backup_data = pickle.load(f)
            
            restored_count = 0
            
            if self.redis_client:
                # Clear existing data
                self.redis_client.delete("transcription_queue")
                self.redis_client.delete("transcription_tasks")
                
                # Restore queue
                if backup_data.get('queue'):
                    for task_json in reversed(backup_data['queue']):  # Reverse to maintain order
                        self.redis_client.lpush("transcription_queue", task_json)
                        restored_count += 1
                
                # Restore task details
                if backup_data.get('tasks'):
                    for task_id, task_data in backup_data['tasks'].items():
                        self.redis_client.hset("transcription_tasks", task_id, task_data)
            else:
                # In-memory fallback
                self.memory_queue = []
                self.memory_tasks = {}
                
                if backup_data.get('queue'):
                    for task_json in backup_data['queue']:
                        task_data = json.loads(task_json)
                        self.memory_queue.append(task_data)
                        restored_count += 1
                
                if backup_data.get('tasks'):
                    for task_id, task_json in backup_data['tasks'].items():
                        self.memory_tasks[task_id] = json.loads(task_json)
            
            print(f"Backup restored: {restored_count} tasks from {backup_data.get('timestamp', 'unknown time')}")
            
            # Remove backup file after successful restore
            os.remove(self.backup_file)
            print("Backup file removed after successful restore")
            
            return True
            
        except Exception as e:
            print(f"Error loading backup: {e}")
            return False
    
    def clear_backup(self) -> bool:
        """Clear the backup file"""
        try:
            if os.path.exists(self.backup_file):
                os.remove(self.backup_file)
                print("Backup file cleared")
            return True
        except Exception as e:
            print(f"Error clearing backup: {e}")
            return False

class RiskDetectionProcessor:
    """Handles risk detection processing using Ollama API"""
    
    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
        self.model_name = "qwen3:8b"
    
    async def call_ollama_api(self, text: str) -> str:
        """Call Ollama API for risk detection"""
        import aiohttp
        
        prompt = f"""ประโยคเหล่านี้ มีข้อความที่เสี่ยงต่อการทำผิดกฎหมายหรือไม่ 
```
{text}
```
ตอบแค่เข้าข่ายผิด หรือ ไม่ผิดเท่านั้น ไม่ต้องตอบรายละเอียดอย่างยาว"""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.ollama_url,
                    json={
                        "model": self.model_name,
                        "prompt": prompt,
                        "stream": False
                    }
                ) as response:
                    if not response.ok:
                        raise Exception(f"Ollama API error: {response.status}")
                    
                    data = await response.json()
                    return data.get('response', 'ไม่สามารถวิเคราะห์ได้')
        except Exception as e:
            print(f"Error calling Ollama API: {e}")
            raise Exception('Failed to analyze risk')
    
    def extract_risk_result(self, response: str) -> str:
        """Extract risk result from Ollama response"""
        lower_response = response.lower()
        
        # Check for response after <think> section
        import re
        think_match = re.search(r'<think>[\s\S]*?</think>\s*([\s\S]*?)$', response, re.IGNORECASE)
        if think_match:
            after_think = think_match.group(1).strip().lower()
            if 'เข้าข่ายผิด' in after_think or 'ผิดกฎหมาย' in after_think:
                return 'เข้าข่ายผิด'
            elif 'ไม่ผิด' in after_think or 'ไม่เข้าข่าย' in after_think:
                return 'ไม่ผิด'
        
        # Direct Thai answers
        if 'เข้าข่ายผิด' in lower_response or 'ผิดกฎหมาย' in lower_response:
            return 'เข้าข่ายผิด'
        elif 'ไม่ผิด' in lower_response or 'ไม่เข้าข่าย' in lower_response or 'ไม่มีความเสี่ยง' in lower_response:
            return 'ไม่ผิด'
        
        # Check for boxed answers
        boxed_match = re.search(r'\\?boxed\s*\{\s*([^}]+)\s*\}', response, re.IGNORECASE)
        if boxed_match:
            boxed_content = boxed_match.group(1).strip().lower()
            if 'ใช่' in boxed_content or 'yes' in boxed_content or 'เข้าข่าย' in boxed_content:
                return 'เข้าข่ายผิด'
            elif 'ไม่ใช่' in boxed_content or 'no' in boxed_content or 'ไม่เข้าข่าย' in boxed_content:
                return 'ไม่ผิด'
        
        # Fallback keyword matching
        if 'ใช่' in lower_response or 'yes' in lower_response:
            return 'เข้าข่ายผิด'
        elif 'ไม่ใช่' in lower_response or 'no' in lower_response:
            return 'ไม่ผิด'
        
        return 'ไม่สามารถวิเคราะห์ได้'
    
    async def process_task(self, task: RiskDetectionTask, queue: TaskQueue, 
                          websocket_manager: 'WebSocketManager') -> bool:
        """Process a risk detection task"""
        try:
            # Update status to processing
            queue.update_task_status(
                task.task_id, 
                TaskStatus.PROCESSING, 
                started_at=datetime.now(),
                progress=0.1
            )
            
            # Notify WebSocket clients
            await websocket_manager.broadcast_task_update(task.task_id, {
                "status": TaskStatus.PROCESSING.value,
                "progress": 0.1,
                "message": "Starting risk analysis..."
            })
            
            # Call Ollama API
            queue.update_task_status(task.task_id, TaskStatus.PROCESSING, progress=0.5)
            await websocket_manager.broadcast_task_update(task.task_id, {
                "status": TaskStatus.PROCESSING.value,
                "progress": 0.5,
                "message": "Analyzing text for risks..."
            })
            
            ollama_response = await self.call_ollama_api(task.text)
            risk_result = self.extract_risk_result(ollama_response)
            
            # Complete the task
            queue.update_task_status(
                task.task_id,
                TaskStatus.COMPLETED,
                completed_at=datetime.now(),
                result={
                    "risk_result": risk_result,
                    "ollama_response": ollama_response,
                    "transcription_id": task.transcription_id
                },
                progress=1.0
            )
            
            # Notify completion
            await websocket_manager.broadcast_task_update(task.task_id, {
                "status": TaskStatus.COMPLETED.value,
                "progress": 1.0,
                "message": "Risk analysis completed successfully!",
                "result": {
                    "risk_result": risk_result,
                    "ollama_response": ollama_response,
                    "transcription_id": task.transcription_id
                }
            })
            
            print(f"Risk detection task {task.task_id} completed successfully")
            return True
            
        except Exception as e:
            error_message = str(e)
            print(f"Error processing risk detection task {task.task_id}: {error_message}")
            
            # Update status to failed
            queue.update_task_status(
                task.task_id,
                TaskStatus.FAILED,
                completed_at=datetime.now(),
                error_message=error_message,
                progress=0.0
            )
            
            # Notify failure
            await websocket_manager.broadcast_task_update(task.task_id, {
                "status": TaskStatus.FAILED.value,
                "progress": 0.0,
                "message": f"Risk analysis failed: {error_message}"
            })
            
            return False

class TranscriptionProcessor:
    """Handles actual transcription processing using the separated service"""
    
    def __init__(self):
        self.service = TranscriptionService()
    
    async def process_task(self, task: TranscriptionTask, queue: TaskQueue, 
                          websocket_manager: 'WebSocketManager') -> bool:
        """Process a single transcription task using the separated service"""
        try:
            if not self.service.model:
                raise Exception("Transcription service not available")
            
            # Update status to processing
            queue.update_task_status(
                task.task_id, 
                TaskStatus.PROCESSING, 
                started_at=datetime.now(),
                progress=0.1
            )
            
            # Notify WebSocket clients
            await websocket_manager.broadcast_task_update(task.task_id, {
                "status": TaskStatus.PROCESSING.value,
                "progress": 0.1,
                "message": "Starting transcription..."
            })
            
            # Update progress
            queue.update_task_status(task.task_id, TaskStatus.PROCESSING, progress=0.3)
            await websocket_manager.broadcast_task_update(task.task_id, {
                "status": TaskStatus.PROCESSING.value,
                "progress": 0.3,
                "message": "Processing audio file..."
            })
            
            # Use the transcription service
            result = self.service.transcribe_audio(task.file_path, task.language)
            
            # Update progress
            queue.update_task_status(task.task_id, TaskStatus.PROCESSING, progress=0.9)
            await websocket_manager.broadcast_task_update(task.task_id, {
                "status": TaskStatus.PROCESSING.value,
                "progress": 0.9,
                "message": "Transcription complete, finalizing..."
            })
            
            # Clean up temporary file
            if os.path.exists(task.file_path):
                os.remove(task.file_path)
            
            # Force garbage collection
            gc.collect()
            
            # Update status to completed
            queue.update_task_status(
                task.task_id,
                TaskStatus.COMPLETED,
                completed_at=datetime.now(),
                result=result,
                progress=1.0
            )
            
            # Notify completion
            await websocket_manager.broadcast_task_update(task.task_id, {
                "status": TaskStatus.COMPLETED.value,
                "progress": 1.0,
                "message": "Transcription completed successfully!",
                "result": result
            })
            
            print(f"Task {task.task_id} completed successfully")
            return True
            
        except Exception as e:
            error_message = str(e)
            print(f"Error processing task {task.task_id}: {error_message}")
            
            # Clean up on error
            if os.path.exists(task.file_path):
                os.remove(task.file_path)
            
            # Update status to failed
            queue.update_task_status(
                task.task_id,
                TaskStatus.FAILED,
                completed_at=datetime.now(),
                error_message=error_message,
                progress=0.0
            )
            
            # Notify failure
            await websocket_manager.broadcast_task_update(task.task_id, {
                "status": TaskStatus.FAILED.value,
                "progress": 0.0,
                "message": f"Transcription failed: {error_message}"
            })
            
            return False

class WebSocketManager:
    """Manages WebSocket connections for real-time updates"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.task_subscribers: Dict[str, set] = {}  # task_id -> set of connection_ids
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        """Accept WebSocket connection"""
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        print(f"WebSocket connected: {connection_id}")
    
    def disconnect(self, connection_id: str):
        """Remove WebSocket connection"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        
        # Remove from task subscriptions
        for task_id, subscribers in self.task_subscribers.items():
            subscribers.discard(connection_id)
        
        print(f"WebSocket disconnected: {connection_id}")
    
    async def subscribe_to_task(self, connection_id: str, task_id: str):
        """Subscribe connection to task updates"""
        if task_id not in self.task_subscribers:
            self.task_subscribers[task_id] = set()
        self.task_subscribers[task_id].add(connection_id)
        print(f"Connection {connection_id} subscribed to task {task_id}")
    
    async def broadcast_task_update(self, task_id: str, update_data: Dict[str, Any]):
        """Broadcast update to all subscribers of a task"""
        if task_id not in self.task_subscribers:
            return
        
        message = {
            "type": "task_update",
            "task_id": task_id,
            "data": update_data
        }
        
        disconnected_connections = []
        
        for connection_id in self.task_subscribers[task_id]:
            if connection_id in self.active_connections:
                try:
                    await self.active_connections[connection_id].send_text(json.dumps(message))
                except Exception as e:
                    print(f"Error sending to {connection_id}: {e}")
                    disconnected_connections.append(connection_id)
        
        # Clean up disconnected connections
        for connection_id in disconnected_connections:
            self.disconnect(connection_id)

# Global instances
task_queue = TaskQueue()
transcription_processor = TranscriptionProcessor()
risk_detection_processor = RiskDetectionProcessor()
websocket_manager = WebSocketManager()

# Signal handlers for graceful shutdown
def signal_handler(signum, frame):
    """Handle shutdown signals by saving queue backup"""
    print(f"\nReceived signal {signum}, saving queue backup...")
    task_queue.save_backup()
    print("Queue backup saved. Exiting...")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # Termination signal

# Background task processor
async def queue_processor():
    """Background task that continuously processes the queue"""
    print("Queue processor started")
    
    # Track last backup time
    last_backup_time = datetime.now()
    backup_interval = 300  # 5 minutes
    
    while True:
        try:
            # Check if there are tasks in the queue
            if task_queue.get_queue_size() > 0:
                task = task_queue.pop_task()
                if task:
                    print(f"Processing task {task.task_id} of type {task.task_type}")
                    
                    # Process task based on type
                    if isinstance(task, TranscriptionTask):
                        await transcription_processor.process_task(task, task_queue, websocket_manager)
                    elif isinstance(task, RiskDetectionTask):
                        await risk_detection_processor.process_task(task, task_queue, websocket_manager)
                    else:
                        print(f"Unknown task type: {type(task)}")
            else:
                # No tasks, wait a bit
                await asyncio.sleep(1)
            
            # Periodic backup save (every 5 minutes if there are tasks)
            current_time = datetime.now()
            if (current_time - last_backup_time).total_seconds() > backup_interval:
                if task_queue.get_queue_size() > 0:
                    print("Performing periodic backup...")
                    task_queue.save_backup()
                last_backup_time = current_time
        
        except Exception as e:
            print(f"Error in queue processor: {e}")
            # Save backup on error in case of crash
            try:
                task_queue.save_backup()
                print("Emergency backup saved due to error")
            except:
                pass
            await asyncio.sleep(5)  # Wait longer on error
