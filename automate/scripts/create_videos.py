import sys
# sys.stdout.reconfigure(encoding='utf-8') # Uncomment if needed

import subprocess
import os
import shutil
import json
import textwrap
import argparse

# --- Constants ---
# Default font path (can be overridden by args)
DEFAULT_SYSTEM_FONT_PATH = "C:/Windows/Fonts/arial.ttf"
# Local filename to copy font to (avoids path issues)
LOCAL_FONT_FILE = "_local_font.ttf"
# Temporary filename for text content
TEMP_TEXT_FILE = "_temp_text.txt"

# --- Helper Functions ---

def load_json(file_path):
    """Loads JSON data from a file."""
    if not os.path.exists(file_path):
        print(f"[Error] File not found: {file_path}", flush=True)
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"[Error] Invalid JSON in file: {file_path}", flush=True)
        return None
    except Exception as e:
        print(f"[Error] Could not read file {file_path}: {e}", flush=True)
        return None

def copy_font_locally(system_font_path):
    """Copies the specified font locally if it doesn't exist."""
    if os.path.exists(LOCAL_FONT_FILE):
        print(f"  > Font '{LOCAL_FONT_FILE}' already exists locally.", flush=True)
        return True
    if not os.path.exists(system_font_path):
        print(f" ERROR: Cannot find font in system: {system_font_path}", flush=True)
        print("Please check the path or copy the font manually.", flush=True)
        return False
    try:
        shutil.copy(system_font_path, LOCAL_FONT_FILE)
        print(f"  > Successfully copied font to local file: {LOCAL_FONT_FILE}", flush=True)
        return True
    except Exception as e:
        print(f" ERROR: Could not copy font: {e}", flush=True)
        return False

def clean_up_temp_files():
    """Removes temporary files created by the script."""
    if os.path.exists(TEMP_TEXT_FILE):
        try:
            os.remove(TEMP_TEXT_FILE)
            # print(f"  > Cleaned up temp file: {TEMP_TEXT_FILE}", flush=True)
        except Exception as e:
            print(f" Warning: Failed to remove temp text file: {e}", flush=True)
    # Don't remove the local font file as it might be needed again soon

# --- Video Creation Logic ---

def create_single_video(base_name, quote_text, author_text, args):
    """
    Creates a single video with quote, optional author, and watermark.
    Uses arguments passed via `args` object.
    """
    print(f"--- Processing '{base_name}' ---", flush=True)

    # 1. Define paths
    image_file = os.path.join(args.image_dir, f"{base_name}.png") # Assuming PNG now
    audio_file = os.path.join(args.audio_dir, f"{base_name}.mp3")
    # Output filename includes _video to distinguish from source files
    output_file = os.path.join(args.output_dir, f"{base_name}_video.mp4")

    # 2. Check inputs
    if not os.path.exists(image_file):
        print(f" SKIPPING: Cannot find image file: {image_file}", flush=True)
        return False
    if not os.path.exists(audio_file):
        print(f" SKIPPING: Cannot find audio file: {audio_file}", flush=True)
        return False

    # 3. Prepare text content
    try:
        wrapped_lines = textwrap.wrap(quote_text, width=args.max_chars)
        wrapped_quote = "\n".join(wrapped_lines)

        final_text = wrapped_quote
        if args.include_author and author_text:
            final_text += f"\n\n— {author_text}" # Add author if requested and available

        with open(TEMP_TEXT_FILE, 'w', encoding='utf-8') as f:
            f.write(final_text)
    except Exception as e:
        print(f" ERROR: Failed to write temp text file: {e}", flush=True)
        return False

    # 4. Build FFmpeg filters
    filters = []

    # Optional scaling filter
    if args.scale:
        filters.append(f"scale={args.scale}")

    # Main text filter
    main_text_filter = (
        f"drawtext=textfile='{TEMP_TEXT_FILE}':"
        f"fontfile='{LOCAL_FONT_FILE}':"
        f"fontsize={args.font_size}:"
        f"fontcolor={args.font_color}:"
        f"reload=1:"
        f"x=(w-text_w)/2:" # Center H
        f"y=(h-text_h)/2:" # Center V
        # Escape comma and single quotes for FFmpeg filtergraph
        f"alpha='min(1\\,t/{args.fade_duration})'"
    )
    filters.append(main_text_filter)

    # Optional watermark filter
    if args.watermark_text:
        watermark_filter = (
            f"drawtext=text='{args.watermark_text}':"
            f"fontfile='{LOCAL_FONT_FILE}':"
            f"fontsize={args.watermark_font_size}:"
            f"fontcolor='{args.watermark_color}':"
            # Position bottom-right with padding
            f"x=w-text_w-{args.watermark_padding}:"
            f"y=h-text_h-{args.watermark_padding}"
        )
        filters.append(watermark_filter)

    # Join all filters with commas
    final_filter_string = ",".join(filters)

    # 5. Build FFmpeg command
    command = [
        args.ffmpeg_path,
        "-loop", "1",           # Loop the input image
        "-i", image_file,
        "-i", audio_file,
        "-vf", final_filter_string, # Apply the combined filters
        "-c:v", "libx264",       # Video codec
        "-preset", "fast",       # Encoding speed vs quality (faster encoding)
        "-crf", "23",            # Constant Rate Factor (quality, lower is better, 18-28 is good range)
        "-c:a", "aac",           # Audio codec
        "-b:a", "192k",          # Audio bitrate
        "-pix_fmt", "yuv420p",   # Pixel format for compatibility
        "-y"                     # Overwrite output without asking
    ]

    # Add duration option
    if args.duration > 0:
        command.extend(["-t", str(args.duration)]) # Use fixed duration
    else:
        command.append("-shortest") # Use duration of shortest input (audio)

    command.append(output_file) # Add the output file path last

    # 6. Run FFmpeg
    try:
        print(f"  > Running FFmpeg for {base_name}...", flush=True)
        # Using Popen to potentially capture output better if needed, but run waits
        process = subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f" Successfully created video: {output_file}", flush=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n ERROR: FFmpeg failed for {base_name}.", flush=True)
        # Print FFmpeg's stderr for detailed error messages
        print("--- FFmpeg Error Output ---", flush=True)
        print(e.stderr, flush=True)
        print("--- End FFmpeg Error ---", flush=True)
        return False
    except FileNotFoundError:
        print(f" ERROR: FFmpeg executable not found at '{args.ffmpeg_path}'. Check path.", flush=True)
        return False
    except Exception as e:
         print(f" An unexpected error occurred during FFmpeg execution: {e}", flush=True)
         return False
    finally:
        # Clean up temp text file after each video
        clean_up_temp_files()

# --- Main Execution ---

def main(args):
    """Main function to orchestrate the video creation batch."""
    print("--- Starting Batch Quote Video Creation ---", flush=True)

    # 1. Validate FFmpeg Path
    if not os.path.exists(args.ffmpeg_path):
        print(f" ERROR: FFmpeg executable not found at: {args.ffmpeg_path}", flush=True)
        return

    # 2. Copy Font
    font_path = args.font_path if args.font_path else DEFAULT_SYSTEM_FONT_PATH
    if not copy_font_locally(font_path):
        print("Aborting: Font file preparation failed.", flush=True)
        return

    # 3. Ensure Output Directory Exists
    try:
        os.makedirs(args.output_dir, exist_ok=True)
        print(f"  > Output directory ready: {args.output_dir}", flush=True)
    except Exception as e:
        print(f" ERROR: Could not create output directory: {e}", flush=True)
        return

    # 4. Load Quotes JSON
    quotes_data = load_json(args.input_json)
    if not quotes_data:
        print("Aborting: Could not load input JSON.", flush=True)
        return
    print(f"  > Loaded {len(quotes_data)} quote entries from {args.input_json}.", flush=True)

    # 5. Process Each Quote
    success_count = 0
    fail_count = 0
    total_videos = len(quotes_data)

    for i, (base_name, data) in enumerate(quotes_data.items()):
        print(f"\n--- Starting Video {i+1} of {total_videos} ---", flush=True)

        quote_text = None
        author_text = None

        if isinstance(data, dict):
            quote_text = data.get('quote')
            author_text = data.get('comment') # Get author if present
        elif isinstance(data, str): # Handle simpler JSON format if needed
             quote_text = data
             # No author in this format

        if not quote_text:
            print(f" SKIPPING {base_name}: 'quote' field missing or empty in JSON data.", flush=True)
            fail_count += 1
            continue

        if args.include_author and not author_text:
             print(f" WARNING for {base_name}: --include-author specified, but 'comment' field missing.", flush=True)

        if create_single_video(base_name, quote_text, author_text, args):
             success_count += 1
        else:
             fail_count += 1

    print("\n--- Batch Process Summary ---", flush=True)
    print(f"Successfully created: {success_count}", flush=True)
    print(f"Failed or skipped: {fail_count}", flush=True)
    print("--- Finished Batch Quote Video Creation ---", flush=True)

# --- Command-Line Argument Parsing ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create videos from images, audio, and quotes.")

    # --- Input Files ---
    parser.add_argument("--input-json", required=True, help="Path to the JSON file containing quotes (e.g., {'001': {'quote': '...', 'comment': '...'}}).")
    parser.add_argument("--image-dir", required=True, help="Directory containing input images (e.g., 001.png, 002.png).")
    parser.add_argument("--audio-dir", required=True, help="Directory containing input audio files (e.g., 001.mp3, 002.mp3).")

    # --- Output ---
    parser.add_argument("--output-dir", required=True, help="Directory where the output videos will be saved.")
    parser.add_argument("--ffmpeg-path", required=True, help="Path to the ffmpeg executable.")

    # --- Text Styling ---
    parser.add_argument("--font-path", default=DEFAULT_SYSTEM_FONT_PATH, help=f"Path to the TTF font file (default: {DEFAULT_SYSTEM_FONT_PATH}).")
    parser.add_argument("--font-size", type=int, default=50, help="Font size for the main quote text (default: 50).")
    parser.add_argument("--font-color", default="white", help="Font color for the main quote text (default: white).")
    parser.add_argument("--max-chars", type=int, default=30, help="Maximum characters per line for text wrapping (default: 30).")
    parser.add_argument("--fade-duration", type=float, default=2.0, help="Duration (seconds) for the text fade-in effect (default: 2.0).")
    parser.add_argument("--include-author", action='store_true', help="Include the author ('comment' field from JSON) below the quote.")

    # --- Watermark Styling ---
    parser.add_argument("--watermark-text", default="", help="Text for the watermark (optional).")
    parser.add_argument("--watermark-font-size", type=int, default=25, help="Font size for the watermark (default: 25).")
    parser.add_argument("--watermark-color", default="white@0.7", help="Font color and opacity for the watermark (default: white@0.7).")
    parser.add_argument("--watermark-padding", type=int, default=15, help="Padding (pixels) for the watermark from the bottom-right corner (default: 15).")

    # --- Video Options ---
    parser.add_argument("--scale", default="", help="Optional: Scale video resolution (e.g., '1080:1920' for portrait).")
    parser.add_argument("--duration", type=float, default=0, help="Optional: Force video duration in seconds (e.g., 15). If 0 or omitted, uses audio duration (default: 0).")

    args = parser.parse_args()

    # Run the main process
    main(args)