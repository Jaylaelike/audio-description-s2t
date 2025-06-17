#!/usr/bin/env python3
"""
Service Orchestrator for Separated Queue System
Starts and manages all components of the separated queue system
"""
import asyncio
import subprocess
import signal
import sys
import time
import os
import argparse
from typing import List, Dict
import psutil
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ServiceManager:
    """Manages multiple services for the separated queue system"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.services: Dict[str, subprocess.Popen] = {}
        self.running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down services...")
        self.running = False
        self.stop_all_services()
        sys.exit(0)
    
    def start_service(self, name: str, command: List[str], cwd: str = None) -> bool:
        """Start a service with the given command"""
        try:
            logger.info(f"Starting service: {name}")
            logger.info(f"Command: {' '.join(command)}")
            
            process = subprocess.Popen(
                command,
                cwd=cwd or os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.services[name] = process
            logger.info(f"Service {name} started with PID {process.pid}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start service {name}: {e}")
            return False
    
    def stop_service(self, name: str) -> bool:
        """Stop a specific service"""
        if name not in self.services:
            logger.warning(f"Service {name} not found")
            return False
        
        try:
            process = self.services[name]
            if process.poll() is None:  # Process is still running
                logger.info(f"Stopping service: {name}")
                process.terminate()
                
                # Wait for graceful shutdown
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Service {name} did not stop gracefully, killing...")
                    process.kill()
                    process.wait()
            
            del self.services[name]
            logger.info(f"Service {name} stopped")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping service {name}: {e}")
            return False
    
    def stop_all_services(self):
        """Stop all running services"""
        logger.info("Stopping all services...")
        
        # Stop in reverse order
        service_names = list(self.services.keys())
        for name in reversed(service_names):
            self.stop_service(name)
    
    def check_service_health(self, name: str) -> bool:
        """Check if a service is running and healthy"""
        if name not in self.services:
            return False
        
        process = self.services[name]
        return process.poll() is None
    
    def get_service_status(self) -> Dict[str, Dict[str, any]]:
        """Get status of all services"""
        status = {}
        
        for name, process in self.services.items():
            is_running = process.poll() is None
            status[name] = {
                "running": is_running,
                "pid": process.pid if is_running else None,
                "returncode": process.returncode if not is_running else None
            }
        
        return status
    
    def monitor_services(self):
        """Monitor services and restart if needed"""
        logger.info("Starting service monitoring...")
        
        while self.running:
            try:
                for name, process in list(self.services.items()):
                    if process.poll() is not None:  # Process has stopped
                        logger.error(f"Service {name} has stopped unexpectedly (return code: {process.returncode})")
                        
                        # Get the last few lines of stderr
                        try:
                            stderr_output = process.stderr.read()
                            if stderr_output:
                                logger.error(f"Service {name} stderr: {stderr_output[-500:]}")  # Last 500 chars
                        except:
                            pass
                        
                        # Remove from services list
                        del self.services[name]
                
                time.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in service monitoring: {e}")
                time.sleep(5)
    
    def start_redis_if_needed(self) -> bool:
        """Start Redis if not already running"""
        try:
            # Check if Redis is already running
            import redis
            client = redis.from_url(self.redis_url)
            client.ping()
            logger.info("Redis is already running")
            return True
        except:
            logger.info("Redis not found, attempting to start...")
            
            # Try to start Redis
            return self.start_service("redis", ["redis-server", "--port", "6379"])
    
    def start_all_services(self, num_workers: int = 2):
        """Start all services in the correct order"""
        logger.info("Starting separated queue system...")
        
        # 1. Start Redis (if needed)
        if not self.start_redis_if_needed():
            logger.error("Failed to start Redis")
            return False
        
        # Wait for Redis to be ready
        time.sleep(2)
        
        # 2. Start Queue HTTP API
        if not self.start_service("queue-api", [
            "python", "queue_http_api.py",
            "--host", "0.0.0.0",
            "--port", "8002",
            "--redis-url", self.redis_url
        ]):
            logger.error("Failed to start Queue API")
            return False
        
        # Wait for Queue API to be ready
        time.sleep(3)
        
        # 3. Start Queue Workers
        for i in range(num_workers):
            worker_id = f"worker-{i+1}"
            if not self.start_service(f"queue-worker-{i+1}", [
                "python", "queue_worker.py",
                "--redis-url", self.redis_url,
                "--worker-id", worker_id,
                "--poll-interval", "1"
            ]):
                logger.error(f"Failed to start Queue Worker {i+1}")
                return False
        
        # Wait for workers to be ready
        time.sleep(2)
        
        # 4. Start Main API
        if not self.start_service("main-api", [
            "python", "main_separated.py",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--queue-url", "http://localhost:8002"
        ]):
            logger.error("Failed to start Main API")
            return False
        
        logger.info("All services started successfully!")
        return True

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Service Orchestrator for Separated Queue System")
    parser.add_argument("--redis-url", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--workers", type=int, default=2, help="Number of queue workers")
    parser.add_argument("--monitor", action="store_true", help="Monitor services after starting")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Start command
    start_parser = subparsers.add_parser("start", help="Start all services")
    start_parser.add_argument("--workers", type=int, default=2, help="Number of workers")
    
    # Stop command
    subparsers.add_parser("stop", help="Stop all services")
    
    # Status command
    subparsers.add_parser("status", help="Show service status")
    
    # Monitor command
    subparsers.add_parser("monitor", help="Monitor services continuously")
    
    args = parser.parse_args()
    
    if not args.command:
        args.command = "start"  # Default command
    
    manager = ServiceManager(redis_url=args.redis_url)
    
    if args.command == "start":
        success = manager.start_all_services(num_workers=args.workers)
        if success:
            logger.info("System started successfully!")
            logger.info("Available endpoints:")
            logger.info("  Main API: http://localhost:8000")
            logger.info("  Queue API: http://localhost:8002")
            logger.info("  Queue Stats: http://localhost:8002/stats")
            logger.info("  Health Check: http://localhost:8000/health")
            
            if args.monitor:
                try:
                    manager.monitor_services()
                except KeyboardInterrupt:
                    logger.info("Monitoring stopped")
            else:
                logger.info("Services running in background. Use Ctrl+C to stop or --monitor to watch.")
                try:
                    while manager.running:
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass
        else:
            logger.error("Failed to start system")
            sys.exit(1)
    
    elif args.command == "stop":
        manager.stop_all_services()
        logger.info("All services stopped")
    
    elif args.command == "status":
        status = manager.get_service_status()
        print("\nService Status:")
        print("-" * 50)
        for name, info in status.items():
            status_str = "RUNNING" if info["running"] else "STOPPED"
            pid_str = f"(PID: {info['pid']})" if info["pid"] else ""
            print(f"{name:<20} {status_str} {pid_str}")
    
    elif args.command == "monitor":
        logger.info("Starting monitoring mode...")
        try:
            manager.monitor_services()
        except KeyboardInterrupt:
            logger.info("Monitoring stopped")

if __name__ == "__main__":
    main()