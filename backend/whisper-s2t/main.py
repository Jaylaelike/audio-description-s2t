from fastapi import FastAPI, File, UploadFile, HTTPException
import whisper_timestamped as whisper
import shutil
import os
import json
from fastapi.responses import JSONResponse
import csv # Added for CSV logging
from datetime import datetime # Added for timestamping

LOG_FILE_PATH = "event_log.csv"
LOG_HEADER = ["timestamp", "event_type", "status", "details"]

def log_event(event_type: str, status: str, details: str):
    """Appends an event to the CSV log file."""
    timestamp = datetime.now().isoformat()
    log_entry = {"timestamp": timestamp, "event_type": event_type, "status": status, "details": details}
    
    file_exists = os.path.isfile(LOG_FILE_PATH)
    
    try:
        with open(LOG_FILE_PATH, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=LOG_HEADER)
            if not file_exists or os.path.getsize(LOG_FILE_PATH) == 0:
                writer.writeheader()
            writer.writerow(log_entry)
    except Exception as e:
        print(f"Failed to write to log file {LOG_FILE_PATH}: {e}")

app = FastAPI(
    title="ThaiPbs Transcription API",
    description="API for transcribing audio files using Speech Recognition.",
    version="0.1.0",
)

# Load the Whisper model (consider moving this to a startup event for efficiency)
# For now, loading it here for simplicity.
# Ensure the model name 'turbo' is correct and available.
try:
    model = whisper.load_model("large", device="cpu") # Using "turbo" model for broader compatibility
    log_event("MODEL_LOAD", "SUCCESS", "Whisper model 'turbo' loaded successfully.")
except Exception as e:
    error_message = f"Error loading Whisper model: {e}"
    print(error_message)
    log_event("MODEL_LOAD", "FAILURE", error_message)
    model = None

# Define a Pydantic model for the response if needed, or use dict for simplicity
# For now, we'll return the raw JSON from whisper

@app.post("/transcribe/", 
          summary="Transcribe audio file",
          description="Upload an audio file (e.g., MP3, WAV) to get its transcription with timestamps.",
          response_description="Transcription result in JSON format, including segments and words with timestamps."
)
async def transcribe_audio(file: UploadFile = File(..., description="Audio file to transcribe.")):
    if not model:
        log_event("TRANSCRIBE_REQUEST", "FAILURE", "Model not available.")
        raise HTTPException(status_code=503, detail="Whisper model is not available.")

    if not file.filename:
        log_event("TRANSCRIBE_REQUEST", "FAILURE", "No filename provided.")
        raise HTTPException(status_code=400, detail="No file provided.")

    log_event("TRANSCRIBE_REQUEST", "RECEIVED", f"File: {file.filename}, Content-Type: {file.content_type}")
    # Define a temporary path to save the uploaded file
    temp_file_path = f"temp_{file.filename}"

    try:
        # Save the uploaded file temporarily
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Load audio from the temporary file
        audio = whisper.load_audio(temp_file_path)

        # Transcribe
        # You might want to expose language or other parameters in the API
        result = whisper.transcribe(model, audio, language="th") # Assuming Thai, make this configurable if needed
        log_event("TRANSCRIBE_SUCCESS", "SUCCESS", f"File: {file.filename}")

        # Log the transcription result data
        transcribed_text_snippet = result.get("text", "")[:200] # Get first 200 chars
        log_event("TRANSCRIPTION_DATA", "LOGGED", f"File: {file.filename}, Text Snippet: {transcribed_text_snippet}...")

        # Return the transcription result
        # FastAPI will automatically convert dict to JSONResponse
        return result

    except HTTPException as http_exc: # Catch HTTPExceptions explicitly to log them before re-raising
        log_event("TRANSCRIBE_FAILURE", "HTTP_ERROR", f"File: {file.filename}, Detail: {http_exc.detail}, Status Code: {http_exc.status_code}")
        raise http_exc
    except Exception as e:
        log_event("TRANSCRIBE_FAILURE", "ERROR", f"File: {file.filename}, Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error during transcription: {str(e)}")
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.get("/health", summary="Health Check", description="Check if the API is running.")
async def health_check():
    status_detail = "Model loaded" if model is not None else "Model not loaded"
    log_event("HEALTH_CHECK", "SUCCESS", status_detail)
    return {"status": "ok", "model_loaded": model is not None}

# To run this app:
# 1. Install uvicorn: pip install uvicorn
# 2. Run in terminal: uvicorn main:app --reload
# 3. Access API docs at http://127.0.0.1:8000/docs or http://127.0.0.1:8000/redoc
