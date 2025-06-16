"""
Direct transcription API service - for immediate processing without queuing
This service handles direct transcription requests synchronously.
"""
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import tempfile
import os
from typing import Optional, Dict, Any
from datetime import datetime

# Import the separated transcription service
from transcription_service import TranscriptionService

app = FastAPI(
    title="Direct Transcription API",
    description="Direct API for transcribing audio files without queue processing",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize transcription service
transcription_service = TranscriptionService()

@app.post("/transcribe/", 
          summary="Direct transcribe audio file",
          description="Upload an audio file to get its transcription immediately. Files >20MB are automatically chunked.",
          response_description="Transcription result in JSON format with segments and word-level timestamps."
)
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio file to transcribe."),
    language: Optional[str] = "th"
):
    """Direct transcription endpoint - processes immediately without queuing"""
    if not transcription_service.model:
        raise HTTPException(status_code=503, detail="Transcription service is not available.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    # Read file content
    content = await file.read()
    file_size = len(content)
    
    print(f"Processing file: {file.filename}, Size: {file_size} bytes")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file_path = os.path.join(temp_dir, file.filename)
        
        try:
            # Save uploaded file
            with open(temp_file_path, "wb") as buffer:
                buffer.write(content)
            
            # Process with transcription service
            result = transcription_service.transcribe_audio(temp_file_path, language)
            
            print(f"Transcription completed for: {file.filename}")
            return result
            
        except Exception as e:
            print(f"Error processing {file.filename}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error during transcription: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    model_info = transcription_service.get_model_info()
    return {
        "status": "healthy" if model_info["model_loaded"] else "unhealthy",
        "service": "direct_transcription",
        "timestamp": datetime.now().isoformat(),
        **model_info
    }

@app.get("/config")
async def get_config():
    """Get service configuration"""
    model_info = transcription_service.get_model_info()
    return {
        "service_type": "direct",
        "description": "Direct transcription without queuing",
        **model_info
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)  # Different port from queue service