import json
import csv
import os
import pandas as pd
import sys

def save_segments_to_csv(result, output_file="transcript_segments.csv"):
    """Save transcript segments to CSV file."""
    segments = result.get("segments", [])
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Segment ID', 'Start Time', 'End Time', 'Text', 'Confidence'])
        
        for segment in segments:
            writer.writerow([
                segment.get('id', ''),
                segment.get('start', ''),
                segment.get('end', ''),
                segment.get('text', ''),
                segment.get('confidence', '')
            ])
    
    print(f"Segments saved to {output_file}")
    return output_file

def save_words_to_csv(result, output_file="transcript_words.csv"):
    """Save individual words with timestamps to CSV file."""
    all_words = []
    
    for segment in result.get("segments", []):
        segment_id = segment.get('id', '')
        for word in segment.get('words', []):
            all_words.append({
                'Segment ID': segment_id,
                'Word': word.get('text', ''),
                'Start Time': word.get('start', ''),
                'End Time': word.get('end', ''),
                'Confidence': word.get('confidence', '')
            })
    
    # Convert to DataFrame for easier CSV handling with Thai characters
    df = pd.DataFrame(all_words)
    df.to_csv(output_file, index=False, encoding='utf-8')
    
    print(f"Words saved to {output_file}")
    return output_file

def main():
    # Use the result from whisper_timestamped
    input_file = "transcript_result.json"
    
    # If result was saved to a file, load it
    if os.path.exists(input_file):
        with open(input_file, 'r', encoding='utf-8') as f:
            result = json.load(f)
    else:
        # If not saved yet, you can modify the script to use the result directly
        print(f"File {input_file} not found. Please run the transcription first and save the result.")
        return
    
    # Save both formats
    save_segments_to_csv(result)
    save_words_to_csv(result)
    
    print("Transcription saved successfully!")

if __name__ == "__main__":
    main()