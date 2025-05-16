import whisper_timestamped as whisper
import json

audio = whisper.load_audio("A.mp3")

model = whisper.load_model("turbo", device="cpu")

result = whisper.transcribe(model, audio, language="th")

# Save the JSON result to a file
with open("transcript_result.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print("Saved transcript result to transcript_result.json")

# Print the result
print(json.dumps(result, indent=2, ensure_ascii=False))

# Import and run the save_to_csv script
from save_transcript import save_segments_to_csv, save_words_to_csv
save_segments_to_csv(result)
save_words_to_csv(result)