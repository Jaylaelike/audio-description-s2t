#!/usr/bin/env python3
"""
Service startup script for running transcription services
"""
import subprocess
import sys
import signal
import time
import os
from pathlib import Path

class ServiceManager:
    def __init__(self):
        self.processes = []
        self.services = {
            "direct": {
                "name": "Direct Transcription Service",
                "command": ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"],
                "port": 8001,
                "description": "Direct transcription API without queuing"
            },
            "queue": {
                "name": "Queue-based Transcription Service", 
                "command": ["python", "-m", "uvicorn", "main_queue:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
                "port": 8000,
                "description": "Queue-based transcription API with WebSocket support"
            }
        }
    
    def start_service(self, service_name: str):
        """Start a specific service"""
        if service_name not in self.services:
            print(f"Unknown service: {service_name}")
            return False
        
        service = self.services[service_name]
        print(f"Starting {service['name']} on port {service['port']}...")
        print(f"Description: {service['description']}")
        
        try:
            process = subprocess.Popen(
                service["command"],
                cwd=Path(__file__).parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            self.processes.append({
                "name": service_name,
                "process": process,
                "service_info": service
            })
            
            print(f"✓ {service['name']} started with PID {process.pid}")
            print(f"  API docs: http://localhost:{service['port']}/docs")
            print(f"  Health check: http://localhost:{service['port']}/health")
            print()
            
            return True
            
        except Exception as e:
            print(f"✗ Failed to start {service['name']}: {e}")
            return False
    
    def start_all_services(self):
        """Start all services"""
        print("Starting all transcription services...\n")
        
        for service_name in self.services:
            self.start_service(service_name)
            time.sleep(2)  # Give each service time to start
        
        if self.processes:
            print("All services started successfully!")
            print("\nService Overview:")
            for proc_info in self.processes:
                service = proc_info["service_info"]
                print(f"  - {service['name']}: http://localhost:{service['port']}")
            print()
    
    def stop_all_services(self):
        """Stop all running services"""
        print("\nStopping all services...")
        
        for proc_info in self.processes:
            try:
                proc_info["process"].terminate()
                print(f"✓ Stopped {proc_info['service_info']['name']}")
            except:
                try:
                    proc_info["process"].kill()
                    print(f"✓ Force stopped {proc_info['service_info']['name']}")
                except:
                    print(f"✗ Could not stop {proc_info['service_info']['name']}")
        
        print("All services stopped.")
    
    def monitor_services(self):
        """Monitor running services and handle shutdown gracefully"""
        def signal_handler(signum, frame):
            print(f"\nReceived signal {signum}")
            self.stop_all_services()
            sys.exit(0)
        
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print("Monitoring services... Press Ctrl+C to stop all services.")
        print("Logs will be displayed below:\n")
        
        try:
            while True:
                # Check if any process has died
                for proc_info in self.processes[:]:  # Copy list to avoid modification during iteration
                    process = proc_info["process"]
                    if process.poll() is not None:
                        print(f"⚠ {proc_info['service_info']['name']} has stopped (exit code: {process.returncode})")
                        self.processes.remove(proc_info)
                
                # If all processes have died, exit
                if not self.processes:
                    print("All services have stopped.")
                    break
                
                # Display output from processes
                for proc_info in self.processes:
                    process = proc_info["process"]
                    try:
                        # Non-blocking read
                        output = process.stdout.readline()
                        if output:
                            print(f"[{proc_info['name']}] {output.strip()}")
                    except:
                        pass
                
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            self.stop_all_services()

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python start_services.py [direct|queue|all]")
        print()
        print("Services:")
        print("  direct - Direct transcription API (port 8001)")
        print("  queue  - Queue-based transcription API (port 8000)")
        print("  all    - Start both services")
        sys.exit(1)
    
    manager = ServiceManager()
    command = sys.argv[1].lower()
    
    if command == "all":
        manager.start_all_services()
        manager.monitor_services()
    elif command in manager.services:
        manager.start_service(command)
        manager.monitor_services()
    else:
        print(f"Unknown command: {command}")
        print("Available commands: direct, queue, all")
        sys.exit(1)

if __name__ == "__main__":
    main()