#!/usr/bin/env python3
"""
Test script to verify the separated transcription architecture
"""
import sys
import importlib.util

def test_import(module_name, file_path):
    """Test if a module can be imported successfully"""
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        print(f"✓ {module_name}: Import successful")
        return True, module
    except Exception as e:
        print(f"✗ {module_name}: Import failed - {e}")
        return False, None

def test_transcription_service():
    """Test the core transcription service"""
    print("\n=== Testing Core Transcription Service ===")
    
    success, module = test_import("transcription_service", "transcription_service.py")
    if not success:
        return False
    
    try:
        # Test that we can create the service instance
        service = module.TranscriptionService()
        print(f"✓ TranscriptionService: Instance created")
        
        # Test model info method
        info = service.get_model_info()
        print(f"✓ Model info: {info}")
        
        return True
    except Exception as e:
        print(f"✗ TranscriptionService: {e}")
        return False

def test_queue_processor():
    """Test the queue processor module"""
    print("\n=== Testing Queue Processor ===")
    
    success, module = test_import("queue_processor", "queue_processor.py")
    if not success:
        return False
    
    try:
        # Test queue classes
        task_queue = module.TaskQueue()
        print(f"✓ TaskQueue: Instance created")
        
        transcription_processor = module.TranscriptionProcessor()
        print(f"✓ TranscriptionProcessor: Instance created")
        
        return True
    except Exception as e:
        print(f"✗ Queue processor components: {e}")
        return False

def test_direct_service():
    """Test the direct service"""
    print("\n=== Testing Direct Service ===")
    
    success, module = test_import("main", "main.py")
    if not success:
        return False
    
    try:
        # Test that FastAPI app is created
        app = module.app
        print(f"✓ Direct service FastAPI app: Created")
        
        # Test that transcription service is initialized
        service = module.transcription_service
        print(f"✓ Transcription service: Initialized")
        
        return True
    except Exception as e:
        print(f"✗ Direct service: {e}")
        return False

def test_queue_service():
    """Test the queue service"""
    print("\n=== Testing Queue Service ===")
    
    success, module = test_import("main_queue", "main_queue.py")
    if not success:
        return False
    
    try:
        # Test that FastAPI app is created
        app = module.app
        print(f"✓ Queue service FastAPI app: Created")
        
        return True
    except Exception as e:
        print(f"✗ Queue service: {e}")
        return False

def main():
    """Run all tests"""
    print("Testing Separated Transcription Architecture")
    print("=" * 50)
    
    tests = [
        test_transcription_service,
        test_queue_processor,
        test_direct_service,
        test_queue_service
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
    
    print(f"\n=== Test Results ===")
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! The separation is working correctly.")
        print("\nNext steps:")
        print("1. Start services: python start_services.py all")
        print("2. Test direct API: http://localhost:8001/docs")
        print("3. Test queue API: http://localhost:8000/docs")
        return True
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)