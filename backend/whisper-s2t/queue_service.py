#!/usr/bin/env python3
"""
Standalone Queue Service with Backup and Recovery
Separates queue management from main transcription service for better observability
"""
import asyncio
import json
import os
import pickle
import signal
import sys
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum
import argparse
import logging

import redis
import aiohttp
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('queue_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Task models
class TaskStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskType(str, Enum):
    TRANSCRIPTION = "transcription"
    RISK_DETECTION = "risk_detection"

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
    priority: int = 0  # Higher number = higher priority
    retry_count: int = 0
    max_retries: int = 3

class TranscriptionTask(BaseTask):
    task_type: TaskType = TaskType.TRANSCRIPTION
    file_path: str
    filename: str
    language: str = "th"

class RiskDetectionTask(BaseTask):
    task_type: TaskType = TaskType.RISK_DETECTION
    transcription_id: str
    text: str

class QueueStats(BaseModel):
    total_tasks: int
    queued_tasks: int
    processing_tasks: int
    completed_tasks: int
    failed_tasks: int
    uptime_seconds: float
    last_backup: Optional[datetime] = None
    redis_connected: bool = False

class StandaloneQueueService:
    """
    Standalone queue service with backup/recovery and monitoring
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379", 
                 backup_file: str = "queue_backup.pkl",
                 backup_interval: int = 300,
                 max_processing_time: int = 3600):
        self.redis_url = redis_url
        self.backup_file = backup_file
        self.backup_interval = backup_interval  # seconds
        self.max_processing_time = max_processing_time  # seconds
        self.start_time = datetime.now()
        self.last_backup_time = None
        self.processing_tasks: Dict[str, datetime] = {}
        self.stats = QueueStats(
            total_tasks=0,
            queued_tasks=0,
            processing_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            uptime_seconds=0
        )
        
        # Initialize Redis connection
        self._init_redis()
        
        # Load backup on startup
        self.load_backup()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("Queue service initialized")
    
    def _init_redis(self):
        """Initialize Redis connection with fallback to in-memory"""
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            self.redis_client.ping()
            self.stats.redis_connected = True
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, using in-memory fallback")
            self.redis_client = None
            self.stats.redis_connected = False
            self.memory_queue = []
            self.memory_tasks = {}
            self.memory_completed = {}
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, performing graceful shutdown...")
        self.save_backup()
        logger.info("Graceful shutdown complete")
        sys.exit(0)
    
    def push_task(self, task: BaseTask) -> bool:
        """Add task to queue with priority support"""
        try:
            task_data = task.dict()
            task_data['created_at'] = task_data['created_at'].isoformat()
            
            if self.redis_client:
                # Store task details
                self.redis_client.hset("queue_tasks", task.task_id, json.dumps(task_data))
                
                # Add to priority queue (using sorted sets for priority)
                score = task.priority * 1000000 + int(time.time())  # Priority + timestamp
                self.redis_client.zadd("queue_priority", {task.task_id: score})
                
                # Update counters
                self.redis_client.hincrby("queue_stats", "total_tasks", 1)
                self.redis_client.hincrby("queue_stats", "queued_tasks", 1)
            else:
                # In-memory fallback with priority sorting
                self.memory_tasks[task.task_id] = task_data
                self.memory_queue.append((task.priority, time.time(), task.task_id))
                self.memory_queue.sort(key=lambda x: (-x[0], x[1]))  # Sort by priority (desc), then time (asc)
                
                self.stats.total_tasks += 1
                self.stats.queued_tasks += 1
            
            logger.info(f"Task {task.task_id} ({task.task_type}) queued with priority {task.priority}")
            return True
            
        except Exception as e:
            logger.error(f"Error pushing task: {e}")
            return False
    
    def pop_task(self) -> Optional[BaseTask]:
        """Get next task from priority queue"""
        try:
            if self.redis_client:
                # Get highest priority task
                task_ids = self.redis_client.zrevrange("queue_priority", 0, 0)
                if not task_ids:
                    return None
                
                task_id = task_ids[0]
                
                # Remove from priority queue
                self.redis_client.zrem("queue_priority", task_id)
                
                # Get task data
                task_data = self.redis_client.hget("queue_tasks", task_id)
                if not task_data:
                    return None
                
                task_dict = json.loads(task_data)
                task_dict['created_at'] = datetime.fromisoformat(task_dict['created_at'])
                
                # Update counters
                self.redis_client.hincrby("queue_stats", "queued_tasks", -1)
                self.redis_client.hincrby("queue_stats", "processing_tasks", 1)
                
            else:
                # In-memory fallback
                if not self.memory_queue:
                    return None
                
                _, _, task_id = self.memory_queue.pop(0)  # Get highest priority
                task_dict = self.memory_tasks[task_id].copy()
                task_dict['created_at'] = datetime.fromisoformat(task_dict['created_at'])
                
                self.stats.queued_tasks -= 1
                self.stats.processing_tasks += 1
            
            # Track processing start time
            self.processing_tasks[task_id] = datetime.now()
            
            # Create appropriate task type
            if task_dict.get('task_type') == TaskType.TRANSCRIPTION:
                return TranscriptionTask(**task_dict)
            elif task_dict.get('task_type') == TaskType.RISK_DETECTION:
                return RiskDetectionTask(**task_dict)
            else:
                task_dict['task_type'] = TaskType.TRANSCRIPTION
                return TranscriptionTask(**task_dict)
                
        except Exception as e:
            logger.error(f"Error popping task: {e}")
            return None
    
    def update_task_status(self, task_id: str, status: TaskStatus, **kwargs) -> bool:
        """Update task status and metadata"""
        try:
            if self.redis_client:
                task_data = self.redis_client.hget("queue_tasks", task_id)
                if not task_data:
                    return False
                
                task_dict = json.loads(task_data)
                task_dict['status'] = status.value
                
                # Update additional fields
                for key, value in kwargs.items():
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    task_dict[key] = value
                
                self.redis_client.hset("queue_tasks", task_id, json.dumps(task_dict))
                
                # Update counters based on status change
                if status == TaskStatus.PROCESSING:
                    pass  # Already updated in pop_task
                elif status == TaskStatus.COMPLETED:
                    self.redis_client.hincrby("queue_stats", "processing_tasks", -1)
                    self.redis_client.hincrby("queue_stats", "completed_tasks", 1)
                    # Move to completed tasks for history
                    self.redis_client.hset("queue_completed", task_id, json.dumps(task_dict))
                elif status == TaskStatus.FAILED:
                    self.redis_client.hincrby("queue_stats", "processing_tasks", -1)
                    self.redis_client.hincrby("queue_stats", "failed_tasks", 1)
                
            else:
                # In-memory fallback
                if task_id not in self.memory_tasks:
                    return False
                
                old_status = self.memory_tasks[task_id].get('status', 'queued')
                self.memory_tasks[task_id]['status'] = status.value
                
                for key, value in kwargs.items():
                    if isinstance(value, datetime):
                        value = value.isoformat()
                    self.memory_tasks[task_id][key] = value
                
                # Update counters
                if status == TaskStatus.COMPLETED:
                    self.stats.processing_tasks -= 1
                    self.stats.completed_tasks += 1
                    self.memory_completed[task_id] = self.memory_tasks[task_id].copy()
                elif status == TaskStatus.FAILED:
                    self.stats.processing_tasks -= 1
                    self.stats.failed_tasks += 1
            
            # Remove from processing tracker
            if task_id in self.processing_tasks:
                del self.processing_tasks[task_id]
            
            logger.info(f"Task {task_id} status updated to {status.value}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating task status: {e}")
            return False
    
    def get_task_status(self, task_id: str) -> Optional[BaseTask]:
        """Get task details by ID"""
        try:
            task_data = None
            
            if self.redis_client:
                # Check active tasks first
                task_data = self.redis_client.hget("queue_tasks", task_id)
                if not task_data:
                    # Check completed tasks
                    task_data = self.redis_client.hget("queue_completed", task_id)
            else:
                # In-memory fallback
                if task_id in self.memory_tasks:
                    task_data = json.dumps(self.memory_tasks[task_id])
                elif task_id in self.memory_completed:
                    task_data = json.dumps(self.memory_completed[task_id])
            
            if not task_data:
                return None
            
            task_dict = json.loads(task_data)
            
            # Handle datetime fields
            task_dict['created_at'] = datetime.fromisoformat(task_dict['created_at'])
            if task_dict.get('started_at'):
                task_dict['started_at'] = datetime.fromisoformat(task_dict['started_at'])
            if task_dict.get('completed_at'):
                task_dict['completed_at'] = datetime.fromisoformat(task_dict['completed_at'])
            
            # Create appropriate task type
            if task_dict.get('task_type') == TaskType.TRANSCRIPTION:
                return TranscriptionTask(**task_dict)
            elif task_dict.get('task_type') == TaskType.RISK_DETECTION:
                return RiskDetectionTask(**task_dict)
            else:
                task_dict['task_type'] = TaskType.TRANSCRIPTION
                return TranscriptionTask(**task_dict)
                
        except Exception as e:
            logger.error(f"Error getting task status: {e}")
            return None
    
    def get_queue_stats(self) -> QueueStats:
        """Get current queue statistics"""
        try:
            if self.redis_client:
                stats_data = self.redis_client.hmget("queue_stats", 
                    ["total_tasks", "queued_tasks", "processing_tasks", "completed_tasks", "failed_tasks"])
                
                self.stats.total_tasks = int(stats_data[0] or 0)
                self.stats.queued_tasks = int(stats_data[1] or 0)
                self.stats.processing_tasks = int(stats_data[2] or 0)
                self.stats.completed_tasks = int(stats_data[3] or 0)
                self.stats.failed_tasks = int(stats_data[4] or 0)
                self.stats.redis_connected = True
            else:
                # Stats already maintained in memory
                self.stats.redis_connected = False
            
            self.stats.uptime_seconds = (datetime.now() - self.start_time).total_seconds()
            self.stats.last_backup = self.last_backup_time
            
            return self.stats
            
        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")
            return self.stats
    
    def cleanup_stuck_tasks(self):
        """Clean up tasks that have been processing too long"""
        current_time = datetime.now()
        stuck_tasks = []
        
        for task_id, start_time in self.processing_tasks.items():
            if (current_time - start_time).total_seconds() > self.max_processing_time:
                stuck_tasks.append(task_id)
        
        for task_id in stuck_tasks:
            logger.warning(f"Cleaning up stuck task: {task_id}")
            self.update_task_status(
                task_id, 
                TaskStatus.FAILED, 
                error_message="Task exceeded maximum processing time",
                completed_at=current_time
            )
    
    def save_backup(self) -> bool:
        """Save current state to backup file"""
        try:
            backup_data = {
                'queue': [],
                'tasks': {},
                'completed': {},
                'stats': self.stats.dict(),
                'timestamp': datetime.now().isoformat(),
                'processing_tasks': {k: v.isoformat() for k, v in self.processing_tasks.items()}
            }
            
            if self.redis_client:
                # Export from Redis
                # Get priority queue
                queue_items = self.redis_client.zrevrange("queue_priority", 0, -1, withscores=True)
                backup_data['queue'] = [(task_id, score) for task_id, score in queue_items]
                
                # Get all tasks
                task_keys = self.redis_client.hkeys("queue_tasks")
                for task_id in task_keys:
                    task_data = self.redis_client.hget("queue_tasks", task_id)
                    backup_data['tasks'][task_id] = task_data
                
                # Get completed tasks
                completed_keys = self.redis_client.hkeys("queue_completed")
                for task_id in completed_keys:
                    task_data = self.redis_client.hget("queue_completed", task_id)
                    backup_data['completed'][task_id] = task_data
            else:
                # Export from memory
                backup_data['queue'] = self.memory_queue
                backup_data['tasks'] = {k: json.dumps(v) for k, v in self.memory_tasks.items()}
                backup_data['completed'] = {k: json.dumps(v) for k, v in self.memory_completed.items()}
            
            # Write backup file
            with open(self.backup_file, 'wb') as f:
                pickle.dump(backup_data, f)
            
            self.last_backup_time = datetime.now()
            logger.info(f"Backup saved to {self.backup_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving backup: {e}")
            return False
    
    def load_backup(self) -> bool:
        """Load state from backup file"""
        try:
            if not os.path.exists(self.backup_file):
                logger.info("No backup file found")
                return False
            
            with open(self.backup_file, 'rb') as f:
                backup_data = pickle.load(f)
            
            restored_tasks = 0
            
            if self.redis_client:
                # Clear existing data
                self.redis_client.delete("queue_priority", "queue_tasks", "queue_completed", "queue_stats")
                
                # Restore priority queue
                if backup_data.get('queue'):
                    priority_mapping = {}
                    for item in backup_data['queue']:
                        if isinstance(item, tuple) and len(item) == 2:
                            task_id, score = item
                            priority_mapping[task_id] = float(score)
                        elif isinstance(item, (list, tuple)) and len(item) >= 3:
                            # Old format: (priority, timestamp, task_id)
                            priority, timestamp, task_id = item[:3]
                            score = priority * 1000000 + timestamp
                            priority_mapping[task_id] = score
                    
                    if priority_mapping:
                        self.redis_client.zadd("queue_priority", priority_mapping)
                        restored_tasks = len(priority_mapping)
                
                # Restore tasks
                if backup_data.get('tasks'):
                    for task_id, task_data in backup_data['tasks'].items():
                        self.redis_client.hset("queue_tasks", task_id, task_data)
                
                # Restore completed tasks
                if backup_data.get('completed'):
                    for task_id, task_data in backup_data['completed'].items():
                        self.redis_client.hset("queue_completed", task_id, task_data)
                
                # Restore stats
                if backup_data.get('stats'):
                    for key, value in backup_data['stats'].items():
                        if key not in ['uptime_seconds', 'last_backup']:  # Skip computed fields
                            self.redis_client.hset("queue_stats", key, str(value))
            else:
                # In-memory restore
                self.memory_queue = backup_data.get('queue', [])
                
                if backup_data.get('tasks'):
                    self.memory_tasks = {k: json.loads(v) for k, v in backup_data['tasks'].items()}
                else:
                    self.memory_tasks = {}
                
                if backup_data.get('completed'):
                    self.memory_completed = {k: json.loads(v) for k, v in backup_data['completed'].items()}
                else:
                    self.memory_completed = {}
                
                restored_tasks = len(self.memory_queue)
                
                # Restore stats
                if backup_data.get('stats'):
                    stats_dict = backup_data['stats']
                    self.stats = QueueStats(**stats_dict)
            
            # Restore processing tasks
            if backup_data.get('processing_tasks'):
                self.processing_tasks = {
                    k: datetime.fromisoformat(v) 
                    for k, v in backup_data['processing_tasks'].items()
                }
            
            logger.info(f"Backup restored: {restored_tasks} tasks from {backup_data.get('timestamp', 'unknown time')}")
            
            # Remove backup file after successful restore
            os.remove(self.backup_file)
            logger.info("Backup file removed after successful restore")
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading backup: {e}")
            return False
    
    async def run_periodic_tasks(self):
        """Run periodic maintenance tasks"""
        while True:
            try:
                # Save backup periodically
                if (datetime.now() - (self.last_backup_time or datetime.min)).total_seconds() > self.backup_interval:
                    if self.get_queue_stats().total_tasks > 0:
                        logger.info("Performing periodic backup...")
                        self.save_backup()
                
                # Clean up stuck tasks
                self.cleanup_stuck_tasks()
                
                await asyncio.sleep(60)  # Run every minute
                
            except Exception as e:
                logger.error(f"Error in periodic tasks: {e}")
                await asyncio.sleep(60)

async def main():
    """Main entry point for standalone queue service"""
    parser = argparse.ArgumentParser(description="Standalone Queue Service")
    parser.add_argument("--redis-url", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--backup-file", default="queue_backup.pkl", help="Backup file path")
    parser.add_argument("--backup-interval", type=int, default=300, help="Backup interval in seconds")
    parser.add_argument("--max-processing-time", type=int, default=3600, help="Max processing time in seconds")
    
    args = parser.parse_args()
    
    # Initialize queue service
    queue_service = StandaloneQueueService(
        redis_url=args.redis_url,
        backup_file=args.backup_file,
        backup_interval=args.backup_interval,
        max_processing_time=args.max_processing_time
    )
    
    logger.info("Starting standalone queue service...")
    logger.info(f"Redis URL: {args.redis_url}")
    logger.info(f"Backup file: {args.backup_file}")
    logger.info(f"Backup interval: {args.backup_interval}s")
    
    # Start periodic tasks
    await queue_service.run_periodic_tasks()

if __name__ == "__main__":
    asyncio.run(main())