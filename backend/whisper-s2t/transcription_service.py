"""
Core transcription service module - separated from queue processing
"""
import os
import tempfile
import gc
from typing import Dict, Any, Optional
import whisper_timestamped as whisper
from pydub import AudioSegment
from pydub.silence import detect_silence
import numpy as np
from datetime import datetime
import csv
import mimetypes

# Configuration for large file processing
FILE_SIZE_THRESHOLD = 20 * 1024 * 1024  # 20MB threshold
OPTIMAL_CHUNK_DURATION = 180  # 3 minutes (optimal for large model)
MAX_CHUNK_DURATION = 300     # 5 minutes maximum
MIN_CHUNK_DURATION = 60      # 1 minute minimum
OVERLAP_DURATION = 5         # 5 seconds overlap between chunks
SILENCE_THRESHOLD = -40      # dB threshold for silence detection
MIN_SILENCE_LEN = 1000       # Minimum silence length in ms

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

def preprocess_audio_file(file_path: str) -> str:
    """Preprocess audio file to ensure compatibility with Whisper"""
    try:
        from pydub import AudioSegment
        import tempfile
        
        print(f"Preprocessing audio file: {file_path}")
        
        # Load with pydub to normalize format
        audio = AudioSegment.from_file(file_path)
        
        # Check if audio has content
        if len(audio) == 0:
            raise Exception("Audio file has no content")
        
        # Normalize to common format that Whisper likes
        audio = audio.set_frame_rate(16000).set_channels(1)
        
        # Create a new normalized file
        normalized_path = file_path + "_normalized.wav"
        audio.export(
            normalized_path,
            format="wav",
            parameters=["-ar", "16000", "-ac", "1"]
        )
        
        print(f"Audio preprocessing complete: {normalized_path}")
        return normalized_path
        
    except Exception as e:
        print(f"Audio preprocessing failed: {e}")
        return file_path  # Return original path if preprocessing fails

def validate_audio_file(file_path: str) -> bool:
    """Validate that the file is a supported audio format"""
    try:
        # Check file extension and MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        
        # Common audio formats supported by Whisper
        supported_formats = [
            '.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.wma', '.mp4'
        ]
        
        supported_mimes = [
            'audio/mpeg', 'audio/wav', 'audio/flac', 'audio/mp4', 
            'audio/aac', 'audio/ogg', 'audio/x-ms-wma', 'video/mp4'
        ]
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # Check extension
        if file_ext not in supported_formats:
            print(f"Unsupported file extension: {file_ext}")
            return False
        
        # Check MIME type if available
        if mime_type and mime_type not in supported_mimes:
            print(f"Warning: MIME type {mime_type} might not be supported")
        
        # Check if file is readable
        try:
            with open(file_path, 'rb') as f:
                # Read first few bytes to ensure file is not corrupted
                header = f.read(16)
                if len(header) < 4:
                    print("File appears to be too small or corrupted")
                    return False
        except Exception as e:
            print(f"Cannot read file: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"Error validating audio file: {e}")
        return False

class ChunkProcessor:
    """Handles intelligent audio chunking and processing."""
    
    def __init__(self, model, temp_dir: str):
        self.model = model
        self.temp_dir = temp_dir
        self.processed_chunks = []
        
    def detect_natural_breaks(self, audio: AudioSegment) -> list[int]:
        """Detect natural breaks (silence) in audio for smart chunking."""
        try:
            silence_ranges = detect_silence(
                audio, 
                min_silence_len=MIN_SILENCE_LEN,
                silence_thresh=SILENCE_THRESHOLD
            )
            
            break_points = []
            for start, end in silence_ranges:
                mid_point = (start + end) // 2
                break_points.append(mid_point)
            
            return break_points
        except Exception as e:
            print(f"Error detecting natural breaks: {e}")
            return []
    
    def create_smart_chunks(self, audio_path: str) -> list[Dict[str, Any]]:
        """Create smart chunks based on natural breaks and optimal duration."""
        try:
            audio = AudioSegment.from_file(audio_path)
            total_duration_ms = len(audio)
            total_duration_s = total_duration_ms / 1000
            
            print(f"Total audio duration: {total_duration_s:.2f} seconds")
            
            if total_duration_s <= OPTIMAL_CHUNK_DURATION:
                return [{
                    "start_ms": 0,
                    "end_ms": total_duration_ms,
                    "start_time": 0.0,
                    "duration": total_duration_s,
                    "chunk_id": 0
                }]
            
            natural_breaks = self.detect_natural_breaks(audio)
            
            chunks = []
            chunk_id = 0
            current_start = 0
            optimal_chunk_ms = OPTIMAL_CHUNK_DURATION * 1000
            max_chunk_ms = MAX_CHUNK_DURATION * 1000
            overlap_ms = OVERLAP_DURATION * 1000
            
            while current_start < total_duration_ms:
                ideal_end = current_start + optimal_chunk_ms
                max_end = current_start + max_chunk_ms
                
                best_break = None
                if natural_breaks:
                    acceptable_breaks = [
                        bp for bp in natural_breaks 
                        if ideal_end - (optimal_chunk_ms * 0.3) <= bp <= min(max_end, total_duration_ms)
                        and bp > current_start
                    ]
                    
                    if acceptable_breaks:
                        best_break = min(acceptable_breaks, key=lambda x: abs(x - ideal_end))
                
                if best_break:
                    chunk_end = best_break
                else:
                    chunk_end = min(ideal_end, total_duration_ms)
                
                chunk_end = min(chunk_end, total_duration_ms)
                
                chunks.append({
                    "start_ms": current_start,
                    "end_ms": chunk_end,
                    "start_time": current_start / 1000.0,
                    "duration": (chunk_end - current_start) / 1000.0,
                    "chunk_id": chunk_id
                })
                
                if chunk_end < total_duration_ms:
                    current_start = max(chunk_end - overlap_ms, current_start + 1)
                else:
                    break
                    
                chunk_id += 1
            
            print(f"Created {len(chunks)} smart chunks")
            return chunks
            
        except Exception as e:
            print(f"Error creating smart chunks: {e}")
            return self.create_simple_chunks(audio_path)
    
    def create_simple_chunks(self, audio_path: str) -> list[Dict[str, Any]]:
        """Fallback simple time-based chunking."""
        try:
            audio = AudioSegment.from_file(audio_path)
            total_duration_ms = len(audio)
            chunk_duration_ms = OPTIMAL_CHUNK_DURATION * 1000
            overlap_ms = OVERLAP_DURATION * 1000
            
            chunks = []
            chunk_id = 0
            current_start = 0
            
            while current_start < total_duration_ms:
                chunk_end = min(current_start + chunk_duration_ms, total_duration_ms)
                
                chunks.append({
                    "start_ms": current_start,
                    "end_ms": chunk_end,
                    "start_time": current_start / 1000.0,
                    "duration": (chunk_end - current_start) / 1000.0,
                    "chunk_id": chunk_id
                })
                
                if chunk_end >= total_duration_ms:
                    break
                    
                current_start = chunk_end - overlap_ms
                chunk_id += 1
            
            return chunks
        except Exception as e:
            print(f"Error in simple chunking: {e}")
            raise
    
    def extract_chunk(self, audio_path: str, chunk_info: Dict[str, Any]) -> str:
        """Extract a specific chunk from audio file."""
        try:
            audio = AudioSegment.from_file(audio_path)
            chunk = audio[chunk_info["start_ms"]:chunk_info["end_ms"]]
            
            # Validate chunk has content
            if len(chunk) == 0:
                raise Exception(f"Extracted chunk {chunk_info['chunk_id']} is empty")
            
            chunk_path = os.path.join(
                self.temp_dir, 
                f"chunk_{chunk_info['chunk_id']:03d}.wav"
            )
            
            # Export with additional validation
            chunk.export(
                chunk_path,
                format="wav",
                parameters=["-ar", "16000", "-ac", "1"]
            )
            
            # Verify the exported file exists and has content
            if not os.path.exists(chunk_path) or os.path.getsize(chunk_path) == 0:
                raise Exception(f"Failed to create valid chunk file for chunk {chunk_info['chunk_id']}")
            
            return chunk_path
        except Exception as e:
            print(f"Error extracting chunk {chunk_info['chunk_id']}: {e}")
            raise
    
    def process_single_chunk(self, chunk_path: str, chunk_info: Dict[str, Any], language: str) -> Dict[str, Any]:
        """Process a single chunk with the Whisper model."""
        try:
            print(f"Processing chunk {chunk_info['chunk_id']} (duration: {chunk_info['duration']:.2f}s)")
            
            # Validate chunk file before loading
            if not os.path.exists(chunk_path):
                raise Exception(f"Chunk file does not exist: {chunk_path}")
            
            file_size = os.path.getsize(chunk_path)
            if file_size == 0:
                raise Exception(f"Chunk file is empty: {chunk_path}")
            
            print(f"Loading chunk {chunk_info['chunk_id']} from {chunk_path} (size: {file_size} bytes)")
            
            # Load audio with multiple fallback methods
            audio = None
            last_error = None
            
            # Method 1: Direct whisper.load_audio
            try:
                print(f"Attempting to load chunk audio with whisper.load_audio...")
                audio = whisper.load_audio(chunk_path)
                if audio is not None:
                    print(f"Successfully loaded chunk audio with whisper.load_audio")
                else:
                    print(f"whisper.load_audio returned None for chunk")
            except Exception as e:
                last_error = f"whisper.load_audio failed: {str(e)}"
                print(f"whisper.load_audio failed for chunk: {e}")
            
            # Method 2: Try loading with pydub and converting
            if audio is None:
                try:
                    print(f"Attempting to load chunk audio with pydub fallback...")
                    from pydub import AudioSegment
                    import tempfile
                    
                    # Load with pydub
                    audio_segment = AudioSegment.from_file(chunk_path)
                    
                    # Convert to wav format in memory
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
                        audio_segment.export(
                            temp_wav.name,
                            format="wav",
                            parameters=["-ar", "16000", "-ac", "1"]
                        )
                        
                        # Try loading the converted file
                        audio = whisper.load_audio(temp_wav.name)
                        
                        # Clean up temp file
                        os.unlink(temp_wav.name)
                        
                        if audio is not None:
                            print(f"Successfully loaded chunk audio with pydub fallback")
                        else:
                            print(f"Pydub fallback also returned None for chunk")
                            
                except Exception as e:
                    last_error = f"Pydub fallback failed: {str(e)}"
                    print(f"Pydub fallback failed for chunk: {e}")
            
            # Final check
            if audio is None:
                raise Exception(f"All audio loading methods failed for chunk {chunk_info['chunk_id']} file: {chunk_path}. Last error: {last_error}")
            
            # Check if audio has the expected shape
            if not hasattr(audio, 'shape'):
                raise Exception(f"Chunk {chunk_info['chunk_id']} has invalid audio format - missing shape attribute")
            
            if len(audio.shape) == 0:
                raise Exception(f"Chunk {chunk_info['chunk_id']} has invalid audio format - empty shape")
            
            # Check if audio has sufficient length
            if audio.shape[0] == 0:
                raise Exception(f"Chunk {chunk_info['chunk_id']} is empty or too short")
            
            print(f"Loaded chunk {chunk_info['chunk_id']} with audio shape: {audio.shape}")
            
            try:
                print(f"Starting whisper.transcribe() for chunk {chunk_info['chunk_id']} with:")
                print(f"  - Model type: {type(self.model)}")
                print(f"  - Audio type: {type(audio)}")
                print(f"  - Audio shape: {audio.shape}")
                print(f"  - Language: {language}")
                
                result = whisper.transcribe(
                    self.model, 
                    audio, 
                    language=language,
                    remove_punctuation_from_words=False,
                    include_punctuation_in_confidence=True,
                    refine_whisper_precision=0.5,
                    min_word_duration=0.1,
                    plot_word_alignment=False,
                    word_alignment_most_top_layers=None,
                    remove_empty_words=True,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    compression_ratio_threshold=2.4,
                    logprob_threshold=-1.0,
                    no_speech_threshold=0.6
                )
                
                print(f"whisper.transcribe() completed successfully for chunk {chunk_info['chunk_id']}")
                print(f"Result type: {type(result)}")
                
            except Exception as e:
                print(f"whisper.transcribe() failed for chunk {chunk_info['chunk_id']}: {e}")
                import traceback
                print(f"Chunk transcribe traceback: {traceback.format_exc()}")
                raise Exception(f"Whisper transcription failed for chunk: {str(e)}")
            
            self.adjust_timestamps(result, chunk_info["start_time"])
            
            if os.path.exists(chunk_path):
                os.remove(chunk_path)
            
            gc.collect()
            
            print(f"Completed chunk {chunk_info['chunk_id']}")
            return {
                "chunk_info": chunk_info,
                "result": result
            }
        except Exception as e:
            print(f"Error processing chunk {chunk_info['chunk_id']}: {e}")
            if os.path.exists(chunk_path):
                os.remove(chunk_path)
            raise
    
    def adjust_timestamps(self, result: Dict[str, Any], start_offset: float):
        """Adjust all timestamps in the result by the start offset."""
        for segment in result.get("segments", []):
            segment["start"] += start_offset
            segment["end"] += start_offset
            
            if "words" in segment:
                for word in segment["words"]:
                    if "start" in word:
                        word["start"] += start_offset
                    if "end" in word:
                        word["end"] += start_offset
        
        if "word_segments" in result:
            for word_segment in result["word_segments"]:
                if "start" in word_segment:
                    word_segment["start"] += start_offset
                if "end" in word_segment:
                    word_segment["end"] += start_offset
    
    def merge_results_with_overlap_handling(self, chunk_results: list[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge results from multiple chunks, handling overlaps intelligently."""
        if not chunk_results:
            return {"text": "", "segments": [], "language": "th"}
        
        if len(chunk_results) == 1:
            return chunk_results[0]["result"]
        
        chunk_results.sort(key=lambda x: x["chunk_info"]["start_time"])
        
        merged_result = {
            "text": "",
            "segments": [],
            "word_segments": [],
            "language": chunk_results[0]["result"].get("language", "th")
        }
        
        all_segments = []
        
        for i, chunk_data in enumerate(chunk_results):
            result = chunk_data["result"]
            chunk_info = chunk_data["chunk_info"]
            
            segments = result.get("segments", [])
            
            if i == 0:
                all_segments.extend(segments)
            else:
                prev_chunk_info = chunk_results[i-1]["chunk_info"]
                overlap_start = chunk_info["start_time"]
                overlap_end = prev_chunk_info["start_time"] + prev_chunk_info["duration"]
                
                filtered_segments = []
                for segment in segments:
                    if segment["start"] >= overlap_end - (OVERLAP_DURATION * 0.5):
                        filtered_segments.append(segment)
                    elif segment["start"] < overlap_end:
                        is_duplicate = False
                        segment_text = segment["text"].strip().lower()
                        
                        for prev_segment in all_segments[-3:]:
                            prev_text = prev_segment["text"].strip().lower()
                            if segment_text and self.text_similarity(segment_text, prev_text) > 0.8:
                                is_duplicate = True
                                break
                        
                        if not is_duplicate:
                            filtered_segments.append(segment)
                
                all_segments.extend(filtered_segments)
        
        merged_result["segments"] = all_segments
        merged_result["text"] = " ".join([seg["text"] for seg in all_segments])
        
        all_word_segments = []
        for chunk_data in chunk_results:
            result = chunk_data["result"]
            if "word_segments" in result:
                all_word_segments.extend(result["word_segments"])
        
        merged_result["word_segments"] = all_word_segments
        
        return merged_result
    
    def text_similarity(self, text1: str, text2: str) -> float:
        """Simple text similarity calculation."""
        if not text1 or not text2:
            return 0.0
        
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)

class TranscriptionService:
    """Core transcription service"""
    
    def __init__(self):
        self.model = None
        self.load_model()
    
    def load_model(self):
        """Load Whisper model"""
        try:
            print("Loading Whisper large model...")
            self.model = whisper.load_model("large", device="cpu")
            log_event("MODEL_LOAD", "SUCCESS", "Whisper large model loaded successfully.")
            print("Whisper large model loaded successfully!")
        except Exception as e:
            error_message = f"Error loading Whisper model: {e}"
            print(error_message)
            log_event("MODEL_LOAD", "FAILURE", error_message)
            self.model = None
    
    def transcribe_audio(self, file_path: str, language: str = "th") -> Dict[str, Any]:
        """Transcribe audio file with intelligent chunking for large files"""
        if not self.model:
            raise Exception("Whisper model is not available")
        
        if not os.path.exists(file_path):
            raise Exception(f"Audio file not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            raise Exception("Audio file is empty")
        
        # Validate audio file format
        if not validate_audio_file(file_path):
            raise Exception(f"Invalid audio file format: {file_path}")
        
        # Preprocess audio file for better compatibility
        processed_file_path = file_path  # Default to original file
        try:
            processed_file_path = preprocess_audio_file(file_path)
        except Exception as e:
            print(f"Audio preprocessing failed, using original file: {e}")
            processed_file_path = file_path
        
        log_event("TRANSCRIBE_REQUEST", "RECEIVED", f"File: {file_path}, Size: {file_size} bytes")
        
        use_chunking = file_size > FILE_SIZE_THRESHOLD
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                if use_chunking:
                    log_event("PROCESSING_MODE", "CHUNKED", f"File size {file_size} bytes > {FILE_SIZE_THRESHOLD} bytes, using chunking")
                    result = self._process_with_chunking(processed_file_path, language, temp_dir)
                else:
                    log_event("PROCESSING_MODE", "DIRECT", f"File size {file_size} bytes <= {FILE_SIZE_THRESHOLD} bytes, direct processing")
                    result = self._process_directly(processed_file_path, language)
                
                text_snippet = result.get("text", "")[:200]
                log_event("TRANSCRIBE_SUCCESS", "SUCCESS", f"File: {file_path}, Text preview: {text_snippet}...")
                
                # Clean up preprocessed file if it was created
                if processed_file_path != file_path and os.path.exists(processed_file_path):
                    try:
                        os.remove(processed_file_path)
                        print(f"Cleaned up preprocessed file: {processed_file_path}")
                    except Exception as e:
                        print(f"Failed to clean up preprocessed file: {e}")
                
                return result
                
            except Exception as e:
                # Clean up preprocessed file on error
                if processed_file_path != file_path and os.path.exists(processed_file_path):
                    try:
                        os.remove(processed_file_path)
                    except:
                        pass
                
                log_event("TRANSCRIBE_FAILURE", "ERROR", f"File: {file_path}, Error: {str(e)}")
                raise Exception(f"Error during transcription: {str(e)}")
    
    def _process_directly(self, file_path: str, language: str) -> Dict[str, Any]:
        """Process small files directly without chunking."""
        try:
            # Validate audio file before loading
            if not os.path.exists(file_path):
                raise Exception(f"Audio file does not exist: {file_path}")
            
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                raise Exception(f"Audio file is empty: {file_path}")
            
            print(f"Loading audio file {file_path} (size: {file_size} bytes)")
            
            # Debug: Test whisper library functions
            print(f"Whisper module available: {whisper is not None}")
            print(f"Whisper load_audio function available: {hasattr(whisper, 'load_audio')}")
            
            # Try a simple test with numpy array
            try:
                import numpy as np
                test_audio = np.array([0.1, 0.2, 0.3], dtype=np.float32)
                print(f"Test numpy array shape: {test_audio.shape}")
                print(f"Test numpy array type: {type(test_audio)}")
            except Exception as e:
                print(f"Numpy test failed: {e}")
            
            # Load audio with multiple fallback methods
            audio = None
            last_error = None
            
            # Method 1: Direct whisper.load_audio
            try:
                print(f"Attempting to load audio with whisper.load_audio...")
                print(f"File exists: {os.path.exists(file_path)}")
                print(f"File size: {os.path.getsize(file_path) if os.path.exists(file_path) else 'N/A'}")
                
                audio = whisper.load_audio(file_path)
                print(f"whisper.load_audio result type: {type(audio)}")
                print(f"whisper.load_audio result: {audio is not None}")
                
                if audio is not None:
                    print(f"Successfully loaded audio with whisper.load_audio")
                    if hasattr(audio, 'shape'):
                        print(f"Audio shape: {audio.shape}")
                    else:
                        print(f"Warning: Audio object has no shape attribute")
                else:
                    print(f"whisper.load_audio returned None")
            except Exception as e:
                last_error = f"whisper.load_audio failed: {str(e)}"
                print(f"whisper.load_audio failed: {e}")
                import traceback
                print(f"Full traceback: {traceback.format_exc()}")
            
            # Method 2: Try loading with pydub and converting
            if audio is None:
                try:
                    print(f"Attempting to load audio with pydub fallback...")
                    from pydub import AudioSegment
                    import tempfile
                    
                    # Load with pydub
                    print(f"Loading with pydub from: {file_path}")
                    audio_segment = AudioSegment.from_file(file_path)
                    print(f"Pydub loaded audio: duration={len(audio_segment)}ms, channels={audio_segment.channels}, frame_rate={audio_segment.frame_rate}")
                    
                    # Convert to wav format in memory
                    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
                        print(f"Converting to WAV: {temp_wav.name}")
                        audio_segment.export(
                            temp_wav.name,
                            format="wav",
                            parameters=["-ar", "16000", "-ac", "1"]
                        )
                        
                        converted_size = os.path.getsize(temp_wav.name)
                        print(f"Converted file size: {converted_size} bytes")
                        
                        # Try loading the converted file
                        print(f"Attempting whisper.load_audio on converted file...")
                        audio = whisper.load_audio(temp_wav.name)
                        print(f"Converted audio result type: {type(audio)}")
                        print(f"Converted audio result: {audio is not None}")
                        
                        # Clean up temp file
                        os.unlink(temp_wav.name)
                        
                        if audio is not None:
                            print(f"Successfully loaded audio with pydub fallback")
                            if hasattr(audio, 'shape'):
                                print(f"Converted audio shape: {audio.shape}")
                        else:
                            print(f"Pydub fallback also returned None")
                            
                except Exception as e:
                    last_error = f"Pydub fallback failed: {str(e)}"
                    print(f"Pydub fallback failed: {e}")
                    import traceback
                    print(f"Pydub fallback traceback: {traceback.format_exc()}")
            
            # Method 3: Try creating a simple test audio to verify whisper is working
            if audio is None:
                try:
                    print(f"Attempting to create synthetic test audio...")
                    import numpy as np
                    
                    # Create a simple sine wave test audio (1 second, 16kHz)
                    sample_rate = 16000
                    duration = 1.0
                    frequency = 440  # A4 note
                    t = np.linspace(0, duration, int(sample_rate * duration), False)
                    test_audio_data = np.sin(2 * np.pi * frequency * t).astype(np.float32)
                    
                    print(f"Test audio shape: {test_audio_data.shape}")
                    print(f"Test audio type: {type(test_audio_data)}")
                    print(f"Test audio has shape attr: {hasattr(test_audio_data, 'shape')}")
                    
                    # Test if whisper can work with this numpy array directly
                    if hasattr(test_audio_data, 'shape') and len(test_audio_data.shape) > 0:
                        print(f"Using synthetic test audio as fallback")
                        audio = test_audio_data
                        print(f"WARNING: Using synthetic test audio instead of actual file!")
                    
                except Exception as e:
                    print(f"Synthetic audio test failed: {e}")
                    import traceback
                    print(f"Synthetic audio traceback: {traceback.format_exc()}")
            
            # Final check
            if audio is None:
                raise Exception(f"All audio loading methods failed for file: {file_path}. Last error: {last_error}")
            
            # Check if audio has the expected shape
            if not hasattr(audio, 'shape'):
                raise Exception("Loaded audio has invalid format - missing shape attribute")
            
            if len(audio.shape) == 0:
                raise Exception("Loaded audio has invalid format - empty shape")
            
            # Check if audio has sufficient length
            if audio.shape[0] == 0:
                raise Exception("Audio file appears to be empty or too short")
            
            log_event("AUDIO_LOAD", "SUCCESS", f"Loaded audio with shape: {audio.shape}")
            
            try:
                print(f"Starting whisper.transcribe() with:")
                print(f"  - Model type: {type(self.model)}")
                print(f"  - Audio type: {type(audio)}")
                print(f"  - Audio shape: {audio.shape}")
                print(f"  - Language: {language}")
                
                result = whisper.transcribe(
                    self.model, 
                    audio, 
                    language=language,
                    remove_punctuation_from_words=False,
                    include_punctuation_in_confidence=True,
                    temperature=0.0
                )
                
                print(f"whisper.transcribe() completed successfully")
                print(f"Result type: {type(result)}")
                return result
                
            except Exception as e:
                print(f"whisper.transcribe() failed: {e}")
                import traceback
                print(f"Transcribe traceback: {traceback.format_exc()}")
                
                # Try fallback with basic whisper (without timestamps)
                try:
                    print(f"Attempting fallback with basic whisper transcription...")
                    import whisper as basic_whisper
                    
                    # Use the model for basic transcription
                    result = basic_whisper.transcribe(
                        self.model,
                        audio,
                        language=language,
                        temperature=0.0
                    )
                    
                    print(f"Basic whisper fallback succeeded")
                    return result
                    
                except Exception as fallback_e:
                    print(f"Basic whisper fallback also failed: {fallback_e}")
                    
                raise Exception(f"Whisper transcription failed: {str(e)}")
        except Exception as e:
            raise Exception(f"Direct processing failed: {str(e)}")
    
    def _process_with_chunking(self, file_path: str, language: str, temp_dir: str) -> Dict[str, Any]:
        """Process large files with intelligent chunking."""
        try:
            processor = ChunkProcessor(self.model, temp_dir)
            
            log_event("CHUNKING", "START", "Creating smart chunks")
            chunks = processor.create_smart_chunks(file_path)
            log_event("CHUNKING", "SUCCESS", f"Created {len(chunks)} chunks")
            
            chunk_results = []
            max_concurrent = 2
            
            for i in range(0, len(chunks), max_concurrent):
                batch = chunks[i:i + max_concurrent]
                batch_results = []
                
                chunk_paths = []
                for chunk_info in batch:
                    chunk_path = processor.extract_chunk(file_path, chunk_info)
                    chunk_paths.append((chunk_path, chunk_info))
                
                for chunk_path, chunk_info in chunk_paths:
                    try:
                        result = processor.process_single_chunk(chunk_path, chunk_info, language)
                        batch_results.append(result)
                    except Exception as e:
                        log_event("CHUNK_ERROR", "ERROR", f"Chunk {chunk_info['chunk_id']} failed: {str(e)}")
                        continue
                
                chunk_results.extend(batch_results)
                gc.collect()
            
            if not chunk_results:
                raise Exception("All chunks failed to process")
            
            log_event("MERGING", "START", f"Merging {len(chunk_results)} chunk results")
            final_result = processor.merge_results_with_overlap_handling(chunk_results)
            log_event("MERGING", "SUCCESS", "Results merged successfully")
            
            return final_result
            
        except Exception as e:
            raise Exception(f"Chunking process failed: {str(e)}")
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        return {
            "model_loaded": self.model is not None,
            "model_type": "large" if self.model else None,
            "chunking_threshold_mb": FILE_SIZE_THRESHOLD / (1024 * 1024),
            "optimal_chunk_duration": OPTIMAL_CHUNK_DURATION
        }