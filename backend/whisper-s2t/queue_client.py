#!/usr/bin/env python3
"""
Queue Client
HTTP client interface for interacting with the separated queue service
"""
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
import aiohttp
import logging

from queue_service import TaskStatus, TaskType, TranscriptionTask, RiskDetectionTask

logger = logging.getLogger(__name__)

class QueueClient:
    """HTTP client for queue service operations"""
    
    def __init__(self, queue_service_url: str = "http://localhost:8002"):
        self.queue_service_url = queue_service_url.rstrip('/')
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to queue service"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        url = f"{self.queue_service_url}{endpoint}"
        
        try:
            async with self.session.request(method, url, **kwargs) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    raise Exception(f"Queue service error {response.status}: {error_text}")
                
                return await response.json()
        
        except aiohttp.ClientError as e:
            logger.error(f"Queue service connection error: {e}")
            raise Exception(f"Failed to connect to queue service: {e}")
    
    async def submit_transcription_task(self, file_path: str, filename: str, 
                                      language: str = "th", priority: int = 0) -> str:
        """Submit a transcription task to the queue"""
        task_data = {
            "task_type": TaskType.TRANSCRIPTION.value,
            "file_path": file_path,
            "filename": filename,
            "language": language,
            "priority": priority
        }
        
        response = await self._make_request("POST", "/tasks/transcription", json=task_data)
        return response["task_id"]
    
    async def submit_risk_detection_task(self, transcription_id: str, text: str, 
                                       priority: int = 0) -> str:
        """Submit a risk detection task to the queue"""
        task_data = {
            "task_type": TaskType.RISK_DETECTION.value,
            "transcription_id": transcription_id,
            "text": text,
            "priority": priority
        }
        
        response = await self._make_request("POST", "/tasks/risk-detection", json=task_data)
        return response["task_id"]
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status by ID"""
        try:
            response = await self._make_request("GET", f"/tasks/{task_id}")
            return response
        except Exception as e:
            if "404" in str(e):
                return None
            raise
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get current queue statistics"""
        return await self._make_request("GET", "/stats")
    
    async def list_tasks(self, status_filter: Optional[str] = None, 
                        limit: int = 10) -> List[Dict[str, Any]]:
        """List tasks with optional filtering"""
        params = {"limit": limit}
        if status_filter:
            params["status"] = status_filter
        
        response = await self._make_request("GET", "/tasks", params=params)
        return response["tasks"]
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a queued task"""
        try:
            await self._make_request("DELETE", f"/tasks/{task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            return False
    
    async def wait_for_completion(self, task_id: str, timeout: int = 300, 
                                poll_interval: int = 2) -> Dict[str, Any]:
        """Wait for task completion with timeout"""
        start_time = datetime.now()
        
        while True:
            task_status = await self.get_task_status(task_id)
            
            if not task_status:
                raise Exception(f"Task {task_id} not found")
            
            status = task_status["status"]
            
            if status in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
                return task_status
            
            # Check timeout
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout:
                raise Exception(f"Task {task_id} timed out after {timeout} seconds")
            
            await asyncio.sleep(poll_interval)

# Convenience functions for direct use
async def submit_transcription(file_path: str, filename: str, language: str = "th", 
                             priority: int = 0, queue_url: str = "http://localhost:8002") -> str:
    """Submit transcription task and return task ID"""
    async with QueueClient(queue_url) as client:
        return await client.submit_transcription_task(file_path, filename, language, priority)

async def submit_risk_detection(transcription_id: str, text: str, priority: int = 0,
                               queue_url: str = "http://localhost:8002") -> str:
    """Submit risk detection task and return task ID"""
    async with QueueClient(queue_url) as client:
        return await client.submit_risk_detection_task(transcription_id, text, priority)

async def get_task_result(task_id: str, timeout: int = 300, 
                         queue_url: str = "http://localhost:8002") -> Dict[str, Any]:
    """Submit task and wait for completion"""
    async with QueueClient(queue_url) as client:
        return await client.wait_for_completion(task_id, timeout)

# Example usage
async def example_usage():
    """Example of how to use the queue client"""
    async with QueueClient() as client:
        # Submit transcription task
        task_id = await client.submit_transcription_task(
            file_path="/path/to/audio.mp3",
            filename="audio.mp3",
            language="th",
            priority=1
        )
        print(f"Submitted transcription task: {task_id}")
        
        # Wait for completion
        result = await client.wait_for_completion(task_id, timeout=300)
        print(f"Task completed with status: {result['status']}")
        
        if result['status'] == TaskStatus.COMPLETED.value:
            print("Transcription result:", result['result'])
        elif result['status'] == TaskStatus.FAILED.value:
            print("Task failed:", result['error_message'])

if __name__ == "__main__":
    asyncio.run(example_usage())