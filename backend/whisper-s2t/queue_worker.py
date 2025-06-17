#!/usr/bin/env python3
"""
Queue Worker Process
Connects to the queue service and processes tasks
"""
import asyncio
import argparse
import logging
import signal
import sys
from datetime import datetime
from typing import Optional

from queue_service import (
    StandaloneQueueService, TranscriptionTask, RiskDetectionTask, 
    TaskStatus, TaskType
)
from transcription_service import TranscriptionService
import os
import gc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('queue_worker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
            logger.error(f"Error calling Ollama API: {e}")
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
    
    async def process_task(self, task: RiskDetectionTask, queue_service: StandaloneQueueService) -> bool:
        """Process a risk detection task"""
        try:
            logger.info(f"Processing risk detection task: {task.task_id}")
            
            # Update status to processing
            queue_service.update_task_status(
                task.task_id, 
                TaskStatus.PROCESSING, 
                started_at=datetime.now(),
                progress=0.1
            )
            
            # Call Ollama API
            queue_service.update_task_status(task.task_id, TaskStatus.PROCESSING, progress=0.5)
            
            ollama_response = await self.call_ollama_api(task.text)
            risk_result = self.extract_risk_result(ollama_response)
            
            # Complete the task
            queue_service.update_task_status(
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
            
            logger.info(f"Risk detection task {task.task_id} completed successfully")
            return True
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error processing risk detection task {task.task_id}: {error_message}")
            
            # Update status to failed
            queue_service.update_task_status(
                task.task_id,
                TaskStatus.FAILED,
                completed_at=datetime.now(),
                error_message=error_message,
                progress=0.0
            )
            
            return False

class QueueWorker:
    """Worker that processes tasks from the queue"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", 
                 worker_id: Optional[str] = None,
                 poll_interval: int = 1):
        self.redis_url = redis_url
        self.worker_id = worker_id or f"worker-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.poll_interval = poll_interval
        self.running = True
        
        # Initialize services
        self.queue_service = StandaloneQueueService(redis_url=redis_url)
        self.transcription_service = TranscriptionService()
        self.risk_detection_processor = RiskDetectionProcessor()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info(f"Worker {self.worker_id} initialized")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Worker {self.worker_id} received signal {signum}, shutting down...")
        self.running = False
    
    async def process_transcription_task(self, task: TranscriptionTask) -> bool:
        """Process a transcription task"""
        try:
            logger.info(f"Processing transcription task: {task.task_id}")
            
            if not self.transcription_service.model:
                raise Exception("Transcription service not available")
            
            # Update status to processing
            self.queue_service.update_task_status(
                task.task_id, 
                TaskStatus.PROCESSING, 
                started_at=datetime.now(),
                progress=0.1
            )
            
            # Update progress
            self.queue_service.update_task_status(task.task_id, TaskStatus.PROCESSING, progress=0.3)
            
            # Use the transcription service
            result = self.transcription_service.transcribe_audio(task.file_path, task.language)
            
            # Update progress
            self.queue_service.update_task_status(task.task_id, TaskStatus.PROCESSING, progress=0.9)
            
            # Clean up temporary file
            if os.path.exists(task.file_path):
                os.remove(task.file_path)
                logger.info(f"Cleaned up temp file: {task.file_path}")
            
            # Force garbage collection
            gc.collect()
            
            # Update status to completed
            self.queue_service.update_task_status(
                task.task_id,
                TaskStatus.COMPLETED,
                completed_at=datetime.now(),
                result=result,
                progress=1.0
            )
            
            logger.info(f"Transcription task {task.task_id} completed successfully")
            return True
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error processing transcription task {task.task_id}: {error_message}")
            
            # Clean up on error
            if os.path.exists(task.file_path):
                os.remove(task.file_path)
            
            # Update status to failed
            self.queue_service.update_task_status(
                task.task_id,
                TaskStatus.FAILED,
                completed_at=datetime.now(),
                error_message=error_message,
                progress=0.0
            )
            
            return False
    
    async def run(self):
        """Main worker loop"""
        logger.info(f"Worker {self.worker_id} starting...")
        
        while self.running:
            try:
                # Check if there are tasks in the queue
                stats = self.queue_service.get_queue_stats()
                
                if stats.queued_tasks > 0:
                    # Get next task
                    task = self.queue_service.pop_task()
                    
                    if task:
                        logger.info(f"Worker {self.worker_id} got task {task.task_id} of type {task.task_type}")
                        
                        # Process task based on type
                        success = False
                        if isinstance(task, TranscriptionTask):
                            success = await self.process_transcription_task(task)
                        elif isinstance(task, RiskDetectionTask):
                            success = await self.risk_detection_processor.process_task(task, self.queue_service)
                        else:
                            logger.error(f"Unknown task type: {type(task)}")
                        
                        if success:
                            logger.info(f"Worker {self.worker_id} completed task {task.task_id}")
                        else:
                            logger.error(f"Worker {self.worker_id} failed to process task {task.task_id}")
                    else:
                        # No task available, wait a bit
                        await asyncio.sleep(self.poll_interval)
                else:
                    # No tasks in queue, wait a bit
                    await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.error(f"Error in worker {self.worker_id} main loop: {e}")
                await asyncio.sleep(self.poll_interval * 5)  # Wait longer on error
        
        logger.info(f"Worker {self.worker_id} stopped")

async def main():
    """Main entry point for queue worker"""
    parser = argparse.ArgumentParser(description="Queue Worker Process")
    parser.add_argument("--redis-url", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--worker-id", help="Worker ID (auto-generated if not provided)")
    parser.add_argument("--poll-interval", type=int, default=1, help="Poll interval in seconds")
    
    args = parser.parse_args()
    
    # Initialize worker
    worker = QueueWorker(
        redis_url=args.redis_url,
        worker_id=args.worker_id,
        poll_interval=args.poll_interval
    )
    
    logger.info(f"Starting queue worker with Redis URL: {args.redis_url}")
    logger.info(f"Worker ID: {worker.worker_id}")
    logger.info(f"Poll interval: {args.poll_interval}s")
    
    # Run worker
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())