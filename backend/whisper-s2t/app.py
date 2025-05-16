import whisper

model = whisper.load_model("turbo")
result = model.transcribe("A.mp3")
print(result["text"])