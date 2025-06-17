#!/usr/bin/env python3
"""
Queue Monitor and Management Tool
Provides observability and management capabilities for the queue service
"""
import asyncio
import json
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import redis
import time

from queue_service import StandaloneQueueService, TaskStatus, TaskType, QueueStats

class QueueMonitor:
    """Monitor and manage queue operations"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.queue_service = StandaloneQueueService(redis_url=redis_url)
    
    def display_stats(self) -> None:
        """Display current queue statistics"""
        stats = self.queue_service.get_queue_stats()
        
        print("\n" + "="*60)
        print(f"QUEUE SERVICE STATISTICS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        print(f"Redis Connected: {'✓' if stats.redis_connected else '✗'}")
        print(f"Uptime: {timedelta(seconds=int(stats.uptime_seconds))}")
        print(f"Last Backup: {stats.last_backup.strftime('%Y-%m-%d %H:%M:%S') if stats.last_backup else 'Never'}")
        print("\nTask Counts:")
        print(f"  Total Tasks: {stats.total_tasks}")
        print(f"  Queued: {stats.queued_tasks}")
        print(f"  Processing: {stats.processing_tasks}")
        print(f"  Completed: {stats.completed_tasks}")
        print(f"  Failed: {stats.failed_tasks}")
        
        # Calculate success rate
        if stats.completed_tasks + stats.failed_tasks > 0:
            success_rate = (stats.completed_tasks / (stats.completed_tasks + stats.failed_tasks)) * 100
            print(f"  Success Rate: {success_rate:.1f}%")
        
        print("="*60)
    
    def list_tasks(self, status_filter: Optional[str] = None, limit: int = 10) -> None:
        """List tasks with optional status filter"""
        print(f"\nLIST OF TASKS (limit: {limit})")
        print("-" * 80)
        print(f"{'Task ID':<36} {'Type':<15} {'Status':<12} {'Created':<20} {'Progress':<8}")
        print("-" * 80)
        
        # This is a simplified version - in a real implementation,
        # you'd need to scan through Redis keys or maintain an index
        try:
            if self.queue_service.redis_client:
                # Get all task keys
                task_keys = self.queue_service.redis_client.hkeys("queue_tasks")
                completed_keys = self.queue_service.redis_client.hkeys("queue_completed")
                all_keys = list(task_keys) + list(completed_keys)
                
                displayed = 0
                for task_id in all_keys[:limit]:
                    task = self.queue_service.get_task_status(task_id)
                    if task:
                        if status_filter and task.status.value != status_filter:
                            continue
                        
                        created_str = task.created_at.strftime('%m-%d %H:%M:%S')
                        print(f"{task_id:<36} {task.task_type.value:<15} {task.status.value:<12} {created_str:<20} {task.progress:<7.1%}")
                        displayed += 1
                        
                        if displayed >= limit:
                            break
            else:
                # In-memory fallback
                all_tasks = list(self.queue_service.memory_tasks.values()) + list(self.queue_service.memory_completed.values())
                displayed = 0
                
                for task_data in all_tasks[:limit]:
                    if status_filter and task_data.get('status') != status_filter:
                        continue
                    
                    created_at = datetime.fromisoformat(task_data['created_at'])
                    created_str = created_at.strftime('%m-%d %H:%M:%S')
                    task_type = task_data.get('task_type', 'transcription')
                    status = task_data.get('status', 'unknown')
                    progress = task_data.get('progress', 0.0)
                    
                    print(f"{task_data['task_id']:<36} {task_type:<15} {status:<12} {created_str:<20} {progress:<7.1%}")
                    displayed += 1
                    
                    if displayed >= limit:
                        break
        
        except Exception as e:
            print(f"Error listing tasks: {e}")
    
    def show_task_details(self, task_id: str) -> None:
        """Show detailed information about a specific task"""
        task = self.queue_service.get_task_status(task_id)
        
        if not task:
            print(f"Task {task_id} not found")
            return
        
        print(f"\nTASK DETAILS: {task_id}")
        print("-" * 50)
        print(f"Type: {task.task_type.value}")
        print(f"Status: {task.status.value}")
        print(f"Created: {task.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if task.started_at:
            print(f"Started: {task.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        
        if task.completed_at:
            print(f"Completed: {task.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
            duration = task.completed_at - task.created_at
            print(f"Duration: {duration}")
        
        print(f"Progress: {task.progress:.1%}")
        print(f"Retry Count: {task.retry_count}/{task.max_retries}")
        
        if hasattr(task, 'filename'):
            print(f"Filename: {task.filename}")
        
        if hasattr(task, 'language'):
            print(f"Language: {task.language}")
        
        if task.error_message:
            print(f"Error: {task.error_message}")
        
        if task.result:
            print("Result:")
            print(json.dumps(task.result, indent=2))
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a queued task"""
        task = self.queue_service.get_task_status(task_id)
        
        if not task:
            print(f"Task {task_id} not found")
            return False
        
        if task.status != TaskStatus.QUEUED:
            print(f"Cannot cancel task with status: {task.status.value}")
            return False
        
        success = self.queue_service.update_task_status(
            task_id,
            TaskStatus.CANCELLED,
            completed_at=datetime.now(),
            error_message="Cancelled by user"
        )
        
        if success:
            print(f"Task {task_id} cancelled successfully")
        else:
            print(f"Failed to cancel task {task_id}")
        
        return success
    
    def retry_failed_task(self, task_id: str) -> bool:
        """Retry a failed task"""
        task = self.queue_service.get_task_status(task_id)
        
        if not task:
            print(f"Task {task_id} not found")
            return False
        
        if task.status != TaskStatus.FAILED:
            print(f"Task status is {task.status.value}, not failed")
            return False
        
        if task.retry_count >= task.max_retries:
            print(f"Task has exceeded maximum retries ({task.max_retries})")
            return False
        
        # Reset task status and re-queue
        task.status = TaskStatus.QUEUED
        task.retry_count += 1
        task.started_at = None
        task.completed_at = None
        task.error_message = None
        task.progress = 0.0
        
        success = self.queue_service.push_task(task)
        
        if success:
            print(f"Task {task_id} re-queued for retry ({task.retry_count}/{task.max_retries})")
        else:
            print(f"Failed to re-queue task {task_id}")
        
        return success
    
    def clear_completed_tasks(self, older_than_hours: int = 24) -> int:
        """Clear completed tasks older than specified hours"""
        cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
        cleared_count = 0
        
        try:
            if self.queue_service.redis_client:
                # Get all completed task keys
                completed_keys = self.queue_service.redis_client.hkeys("queue_completed")
                
                for task_id in completed_keys:
                    task_data = self.queue_service.redis_client.hget("queue_completed", task_id)
                    if task_data:
                        task_dict = json.loads(task_data)
                        if task_dict.get('completed_at'):
                            completed_at = datetime.fromisoformat(task_dict['completed_at'])
                            if completed_at < cutoff_time:
                                self.queue_service.redis_client.hdel("queue_completed", task_id)
                                cleared_count += 1
            else:
                # In-memory fallback
                to_remove = []
                for task_id, task_data in self.queue_service.memory_completed.items():
                    if task_data.get('completed_at'):
                        completed_at = datetime.fromisoformat(task_data['completed_at'])
                        if completed_at < cutoff_time:
                            to_remove.append(task_id)
                
                for task_id in to_remove:
                    del self.queue_service.memory_completed[task_id]
                    cleared_count += 1
            
            print(f"Cleared {cleared_count} completed tasks older than {older_than_hours} hours")
            
        except Exception as e:
            print(f"Error clearing completed tasks: {e}")
        
        return cleared_count
    
    def force_backup(self) -> bool:
        """Force an immediate backup"""
        print("Forcing backup...")
        success = self.queue_service.save_backup()
        
        if success:
            print("Backup completed successfully")
        else:
            print("Backup failed")
        
        return success
    
    async def watch_queue(self, refresh_interval: int = 5) -> None:
        """Watch queue in real-time"""
        print(f"Watching queue (refresh every {refresh_interval}s, Ctrl+C to stop)...")
        
        try:
            while True:
                # Clear screen (works on most terminals)
                print("\033[2J\033[H")
                
                self.display_stats()
                print(f"\nRefreshing in {refresh_interval}s... (Ctrl+C to stop)")
                
                await asyncio.sleep(refresh_interval)
                
        except KeyboardInterrupt:
            print("\nStopped watching queue")

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="Queue Monitor and Management Tool")
    parser.add_argument("--redis-url", default="redis://localhost:6379", help="Redis URL")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Stats command
    subparsers.add_parser("stats", help="Show queue statistics")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument("--status", help="Filter by status")
    list_parser.add_argument("--limit", type=int, default=10, help="Limit number of results")
    
    # Show command
    show_parser = subparsers.add_parser("show", help="Show task details")
    show_parser.add_argument("task_id", help="Task ID to show")
    
    # Cancel command
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a queued task")
    cancel_parser.add_argument("task_id", help="Task ID to cancel")
    
    # Retry command
    retry_parser = subparsers.add_parser("retry", help="Retry a failed task")
    retry_parser.add_argument("task_id", help="Task ID to retry")
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear completed tasks")
    clear_parser.add_argument("--hours", type=int, default=24, help="Clear tasks older than N hours")
    
    # Backup command
    subparsers.add_parser("backup", help="Force immediate backup")
    
    # Watch command
    watch_parser = subparsers.add_parser("watch", help="Watch queue in real-time")
    watch_parser.add_argument("--interval", type=int, default=5, help="Refresh interval in seconds")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    monitor = QueueMonitor(redis_url=args.redis_url)
    
    if args.command == "stats":
        monitor.display_stats()
    
    elif args.command == "list":
        monitor.list_tasks(status_filter=args.status, limit=args.limit)
    
    elif args.command == "show":
        monitor.show_task_details(args.task_id)
    
    elif args.command == "cancel":
        monitor.cancel_task(args.task_id)
    
    elif args.command == "retry":
        monitor.retry_failed_task(args.task_id)
    
    elif args.command == "clear":
        monitor.clear_completed_tasks(older_than_hours=args.hours)
    
    elif args.command == "backup":
        monitor.force_backup()
    
    elif args.command == "watch":
        asyncio.run(monitor.watch_queue(refresh_interval=args.interval))

if __name__ == "__main__":
    main()