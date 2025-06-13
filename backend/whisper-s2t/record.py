import pyaudio
import wave
from pydub import AudioSegment
from datetime import datetime
import os

# Parameters for recording
FORMAT = pyaudio.paInt16  # Audio format
CHANNELS = 1              # Number of channels (mono)
RATE = 44100              # Sampling rate
CHUNK = 1024              # Buffer size
RECORD_SECONDS = 30        # Duration of recording
WAV_FILENAME = "output.wav"
MP3_FILENAME = "output.mp3"

# Initialize PyAudio
audio = pyaudio.PyAudio()

# Start recording
stream = audio.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)

print("Recording started...")

frames = []

for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
    data = stream.read(CHUNK)
    frames.append(data)

print("Recording stopped.")

# Stop and close the stream
stream.stop_stream()
stream.close()
audio.terminate()

# Save as WAV file
with wave.open(WAV_FILENAME, 'wb') as wf:
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))

# Convert WAV to MP3
sound = AudioSegment.from_wav(WAV_FILENAME)
sound.export(MP3_FILENAME, format="mp3")

# Optional: Remove the WAV file
os.remove(WAV_FILENAME)

print(f"Audio saved as {MP3_FILENAME}")