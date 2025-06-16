#!/bin/bash

# Queue-based Transcription Service Setup Script
echo "Setting up Queue-based Transcription Service..."

# Navigate to backend directory
cd backend/whisper-s2t

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Check if Redis is running
echo "Checking Redis connection..."
redis-cli ping > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Redis is running"
else
    echo "❌ Redis is not running. Please start Redis first:"
    echo "   macOS: brew services start redis"
    echo "   Ubuntu: sudo service redis-server start"
    echo "   Docker: docker run -d -p 6379:6379 redis:latest"
    exit 1
fi

# Create temp directory for audio files
mkdir -p temp_audio

echo "✅ Setup complete!"
echo ""
echo "To start the queue-based transcription service:"
echo "  cd backend/whisper-s2t"
echo "  python main_queue.py"
echo ""
echo "The service will run on http://localhost:8000"
echo "WebSocket endpoint: ws://localhost:8000/ws/{task_id}"
