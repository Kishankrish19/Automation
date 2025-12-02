import sys
import os

# --- PATH FIX ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
# ----------------

import base64
import re
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash, Response
import subprocess
import json
import time
import datetime  # <--- THIS WAS MISSING. ADD THIS LINE.
from werkzeug.utils import secure_filename
import pytz 
from pathlib import Path 
from flask import send_from_directory

# Import from the sibling folder 'scripts'
from scripts import upload_to_youtube 

app = Flask(__name__)
app.secret_key = "supersecretkey"
# --- Configuration ---
CONTROLLER_DIR = os.path.dirname(os.path.abspath(__file__))
CONTROLLER_FILE = os.path.join(CONTROLLER_DIR, "controller.json")
LOG_DIR = os.path.join(CONTROLLER_DIR, "running_logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# --- Process Management ---
RUNNING_PROCESSES = {}
FINISHED_LOG = []

# -------------------------
# Utility Functions
# -------------------------
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

def save_json(data, file_path):
    """Saves data to a JSON file."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"[Error] Could not write file {file_path}: {e}", flush=True)
        return False
# --- Replace the existing start_python_task function with this one ---
# --- Replace the existing start_python_task function with this one ---
# --- Replace the existing start_python_task function ---
def start_python_task(task_name, controller_data):
    """
    Looks up the task, builds the command, and runs the script non-blocking.
    Only adds --controller arg if --category is present in task args.
    Returns the Popen object and log file path.
    """
    print(f"\n[DEBUG] Entering start_python_task for: '{task_name}'", flush=True)
    tasks = controller_data.get("tasks", {})
    task_config = tasks.get(task_name)

    if not task_config:
        print(f"[Error][start_task] Task '{task_name}' not found in controller tasks.", flush=True)
        return None, None, None

    script_relative_path = task_config.get("script")
    script_args = task_config.get("args", [])

    if not script_relative_path:
        print(f"[Error][start_task] 'script' path missing for task '{task_name}'.", flush=True)
        return None, None, None

    project_root = os.path.dirname(CONTROLLER_DIR)
    script_abs_path = os.path.abspath(os.path.join(project_root, script_relative_path))
    script_dir = os.path.dirname(script_abs_path)
    script_filename = os.path.basename(script_abs_path)

    if not os.path.exists(script_abs_path):
        print(f"[Error][start_task] Script file not found: {script_abs_path}", flush=True)
        return None, None, None

    command = [ sys.executable, "-u", script_filename ]
    command.extend(script_args)
    needs_controller_arg = "--category" in script_args
    if needs_controller_arg: command.extend(["--controller", CONTROLLER_FILE])

    print(f"[DEBUG][start_task] Final Command List: {command}", flush=True)

    safe_task_name = "".join(c if c.isalnum() else "_" for c in task_name)
    log_file_path = os.path.join(LOG_DIR, f"{safe_task_name}.log")
    print(f"[DEBUG][start_task] Log File Path: {log_file_path}", flush=True)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    log_file_handle = None
    process = None
    try:
        print(f"[DEBUG][start_task] Attempting to open log file...", flush=True)
        log_file_handle = open(log_file_path, 'w', encoding='utf-8', buffering=1)
        print(f"[DEBUG][start_task] Log file opened.", flush=True)

        print(f"[DEBUG][start_task] Attempting subprocess.Popen...", flush=True)
        process = subprocess.Popen(
            command,
            cwd=script_dir,
            stdout=log_file_handle,
            stderr=log_file_handle,
            text=True,
            encoding='utf-8',     # Specify UTF-8 encoding
            errors='replace',     # Replace undecodable chars
            env=env
        )
        print(f"[DEBUG][start_task] Popen executed. Process: {process}", flush=True)

        time.sleep(0.2)
        poll_result = process.poll()
        if poll_result is not None:
            print(f"[Warning][start_task] Process exited immediately: {poll_result}. Check log '{os.path.basename(log_file_path)}'.", flush=True)

        return process, log_file_path, log_file_handle

    except FileNotFoundError as fnf_error:
        print(f"[CRITICAL ERROR][start_task] FileNotFoundError during Popen: {fnf_error}. Is Python/script path correct?", flush=True)
        if log_file_handle:
             try:
                 log_file_handle.close()
             # --- CORRECTED SYNTAX: pass on new line ---
             except Exception:
                 pass # Correctly indented pass
        return None, None, None
    except OSError as os_error:
         print(f"[CRITICAL ERROR][start_task] OSError during Popen: {os_error}. Check permissions/paths.", flush=True)
         if log_file_handle:
             try:
                 log_file_handle.close()
             # --- CORRECTED SYNTAX: pass on new line ---
             except Exception:
                 pass # Correctly indented pass
         return None, None, None
    except Exception as e:
        print(f"[CRITICAL ERROR][start_task] Failed to start process for task '{task_name}': {e}", flush=True)
        if log_file_handle:
             try:
                 log_file_handle.close()
             # --- CORRECTED SYNTAX: pass on new line ---
             except Exception:
                 pass # Correctly indented pass
        return None, None, None
def add_to_finished_log(name, success, output):
    """Adds a job result to the front of the log and trims."""
    log_entry = {"name": name, "success": success, "output": output}
    FINISHED_LOG.insert(0, log_entry)
    while len(FINISHED_LOG) > 20:
        FINISHED_LOG.pop()

def reap_finished_processes():
    """Checks for finished processes, closes logs, reads output, cleans up."""
    # Create a copy of keys to iterate safely while modifying dictionary
    for task_name in list(RUNNING_PROCESSES.keys()):
        proc_data = RUNNING_PROCESSES[task_name]
        process = proc_data['process']
        
        # Check if process has finished
        return_code = process.poll()
        
        if return_code is not None:
            print(f"Process {task_name} finished with code {return_code}.", flush=True)
            
            # 1. CLOSE THE WRITE HANDLE FIRST
            if proc_data.get('log_handle') and not proc_data['log_handle'].closed:
                try:
                    proc_data['log_handle'].close()
                except Exception as e:
                    print(f"Error closing log handle: {e}", flush=True)

            # 2. READ THE LOG CONTENT
            output = ""
            log_path = proc_data.get('log_file')
            if log_path and os.path.exists(log_path):
                try:
                    # Small delay to let Windows release the file lock
                    time.sleep(0.5) 
                    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                        output = f.read()
                except Exception as e:
                    output = f"Error reading log file: {e}"
            else:
                output = "Log file not found."

            # 3. SAVE TO HISTORY
            add_to_finished_log(task_name, return_code == 0, output)

            # 4. ATTEMPT DELETE (With Retry)
            if log_path and os.path.exists(log_path):
                try:
                    os.remove(log_path)
                except PermissionError:
                    # If Windows locks it, just leave it. It's temporary anyway.
                    print(f"[Info] Could not remove log file (locked by Windows): {os.path.basename(log_path)}", flush=True)
                except Exception as e:
                    print(f"[Warning] Error removing log file: {e}", flush=True)

            # 5. REMOVE FROM RUNNING LIST
            del RUNNING_PROCESSES[task_name]
# -------------------------
# Routes
# -------------------------
# --- Add this near the other imports ---


def _find_arg_value(arg_name, args_list):
    """Internal helper to find a value for an arg in a list."""
    try:
        index = args_list.index(arg_name)
        if index + 1 < len(args_list):
            return args_list[index + 1]
    except ValueError:
        pass # Arg not found
    except Exception as e:
        print(f"[Error][_find_arg_value] Error finding '{arg_name}': {e}", flush=True)
    return None

@app.route('/gallery')
def gallery():
    """Display all media files from configured directories."""
    if not session.get("logged_in"): return redirect(url_for("login"))

    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data:
        flash("Controller file not found", "danger")
        return redirect(url_for("dashboard"))

    media_folders = []
    
    # 1. Get media paths from controller.json
    all_paths = {} # Use a dict to avoid duplicate scanning

    # 1a. Get Quotes media paths
    try:
        quotes_task_config = controller_data.get("tasks", {}).get("Create Quotes Videos", {})
        args = quotes_task_config.get("args", [])
        
        img_path = _find_arg_value("--image-dir", args)
        aud_path = _find_arg_value("--audio-dir", args)
        
        if img_path: all_paths[os.path.abspath(img_path)] = "Quotes Input Images"
        if aud_path: all_paths[os.path.abspath(aud_path)] = "Quotes Input Audio"
    except Exception as e:
        print(f"[Error][Gallery] Could not parse Quotes task paths: {e}", flush=True)

    # 1b. Get Category media paths
    categories = controller_data.get("categories", {})
    for cat_name, config in categories.items():
        # Folders where videos are waiting to be uploaded
        src_path = config.get("upload_source_dir")
        if src_path: all_paths[os.path.abspath(src_path)] = f"{cat_name} - Ready for Upload"
        
        # Folders where videos are moved after upload
        up_path = config.get("uploaded_dir")
        if up_path: all_paths[os.path.abspath(up_path)] = f"{cat_name} - Uploaded"

    # 2. Scan each path for media files
    media_extensions = {
        'image': ('.png', '.jpg', '.jpeg', '.gif', '.webp'),
        'video': ('.mp4', '.mov', '.mkv', '.avi', '.webm'),
        'audio': ('.mp3', '.wav', '.ogg', '.m4a')
    }

    for path, display_name in all_paths.items():
        folder_data = {"name": display_name, "path": path, "files": []}
        if not os.path.exists(path):
            print(f"[Warning][Gallery] Path not found, skipping: {path}", flush=True)
            continue
        
        try:
            for filename in sorted(os.listdir(path)):
                file_ext = os.path.splitext(filename)[1].lower()
                file_type = "other"

                if file_ext in media_extensions['image']: file_type = 'image'
                elif file_ext in media_extensions['video']: file_type = 'video'
                elif file_ext in media_extensions['audio']: file_type = 'audio'
                else: continue # Skip non-media files

                full_path = os.path.abspath(os.path.join(path, filename))
                
                # We base64 encode the path to safely pass it in a URL
                url_safe_path = base64.urlsafe_b64encode(full_path.encode('utf-8')).decode('utf-8')

                folder_data["files"].append({
                    "name": filename,
                    "type": file_type,
                    "full_path": full_path,
                    "url_path": url_safe_path,
                    "smart_delete": "Quotes Input" in display_name # Flag for the UI
                })
        except Exception as e:
            print(f"[Error][Gallery] Failed to scan directory {path}: {e}", flush=True)
            
        media_folders.append(folder_data)

    return render_template("gallery.html", media_folders=media_folders)


@app.route('/media/<path:path>')
def serve_media_file(path):
    """Safely serves media files for the gallery."""
    if not session.get("logged_in"): return "Unauthorized", 401

    try:
        # Decode the path from base64
        decoded_path = base64.urlsafe_b64decode(path.encode('utf-8')).decode('utf-8')
        
        # Use send_from_directory for security
        directory = os.path.dirname(decoded_path)
        filename = os.path.basename(decoded_path)
        
        if not os.path.exists(directory):
            return "Directory not found", 404
            
        return send_from_directory(directory, filename)
        
    except Exception as e:
        print(f"[Error][serve_media_file] Failed to serve file for path {path}: {e}", flush=True)
        return "Error serving file", 500


@app.route("/delete_media", methods=["POST"])
def delete_media():
    """Handles the 'Smart Delete' logic."""
    if not session.get("logged_in"): return redirect(url_for("login"))

    file_path = request.form.get("file_path")
    if not file_path or not os.path.exists(file_path):
        flash("File not found or path was missing.", "danger")
        return redirect(url_for("gallery"))

    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data:
        flash("Controller file not found, cannot perform smart delete.", "danger")
        return redirect(url_for("gallery"))

    try:
        # --- Check if this is a "Quotes" file ---
        quotes_task_config = controller_data.get("tasks", {}).get("Create Quotes Videos", {})
        args = quotes_task_config.get("args", [])
        
        image_dir = _find_arg_value("--image-dir", args)
        audio_dir = _find_arg_value("--audio-dir", args)
        input_json_path = _find_arg_value("--input-json", args)

        file_dir = os.path.dirname(file_path)
        base_name = Path(file_path).stem # e.g., "005"
        
        # Check if the deleted file is in the quotes image or audio dir
        is_quote_media = (image_dir and os.path.abspath(file_dir) == os.path.abspath(image_dir)) or \
                         (audio_dir and os.path.abspath(file_dir) == os.path.abspath(audio_dir))

        if is_quote_media and input_json_path:
            # --- SMART DELETE LOGIC ---
            print(f"[Info][Delete] Smart deleting Quote record: {base_name}", flush=True)
            
            # 1. Find all associated files
            image_to_delete = os.path.join(image_dir, f"{base_name}.png")
            audio_to_delete = os.path.join(audio_dir, f"{base_name}.mp3")
            
            # 2. Delete from JSON
            quotes_json = load_json(input_json_path)
            if quotes_json and base_name in quotes_json:
                del quotes_json[base_name]
                save_json(quotes_json, input_json_path)
                print(f"  > Removed '{base_name}' from {os.path.basename(input_json_path)}", flush=True)
            
            # 3. Delete media files
            if os.path.exists(image_to_delete):
                os.remove(image_to_delete)
                print(f"  > Deleted: {os.path.basename(image_to_delete)}", flush=True)
            if os.path.exists(audio_to_delete):
                os.remove(audio_to_delete)
                print(f"  > Deleted: {os.path.basename(audio_to_delete)}", flush=True)
                
            flash(f"Successfully deleted Quote record '{base_name}' (JSON entry, image, and audio).", "success")

        else:
            # --- SIMPLE DELETE LOGIC ---
            print(f"[Info][Delete] Simple deleting file: {os.path.basename(file_path)}", flush=True)
            os.remove(file_path)
            flash(f"Successfully deleted file: {os.path.basename(file_path)}", "success")

    except Exception as e:
        print(f"[Error][Delete] Failed to delete file {file_path}: {e}", flush=True)
        flash(f"An error occurred while deleting the file: {e}", "danger")

    return redirect(url_for("gallery"))

@app.route('/quote_media/images/<path:filename>')
def serve_quote_image(filename):
    if not session.get("logged_in"): return "Unauthorized", 401 # Basic security

    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data: return "Controller Error", 500

    # Find the image directory path from the task config
    quotes_task_config = controller_data.get("tasks", {}).get("Create Quotes Videos", {})
    args = quotes_task_config.get("args", [])
    def find_arg_value(arg_name, args_list): # Local helper
        try: index = args_list.index(arg_name); return args_list[index + 1]
        except: return None
    image_dir_path = find_arg_value("--image-dir", args)

    if not image_dir_path or not os.path.isdir(image_dir_path):
        print(f"[Error] Image directory not found or invalid: {image_dir_path}", flush=True)
        return "Image directory not configured", 404

    # Use send_from_directory for security (prevents path traversal)
    # It requires an absolute path
    abs_image_dir_path = os.path.abspath(image_dir_path)
    print(f"[Debug] Serving image: {filename} from {abs_image_dir_path}", flush=True) # DEBUG
    try:
        return send_from_directory(abs_image_dir_path, filename)
    except FileNotFoundError:
        print(f"[Error] Image file not found in directory: {filename}", flush=True)
        return "Image not found", 404
    except Exception as e:
        print(f"[Error] Error serving image {filename}: {e}", flush=True)
        return "Server error", 500


# --- Route to serve quote audio ---
@app.route('/quote_media/audio/<path:filename>')
def serve_quote_audio(filename):
    if not session.get("logged_in"): return "Unauthorized", 401

    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data: return "Controller Error", 500

    # Find the audio directory path from the task config
    quotes_task_config = controller_data.get("tasks", {}).get("Create Quotes Videos", {})
    args = quotes_task_config.get("args", [])
    def find_arg_value(arg_name, args_list): # Local helper
        try: index = args_list.index(arg_name); return args_list[index + 1]
        except: return None
    audio_dir_path = find_arg_value("--audio-dir", args)

    if not audio_dir_path or not os.path.isdir(audio_dir_path):
        print(f"[Error] Audio directory not found or invalid: {audio_dir_path}", flush=True)
        return "Audio directory not configured", 404

    # Use send_from_directory
    abs_audio_dir_path = os.path.abspath(audio_dir_path)
    print(f"[Debug] Serving audio: {filename} from {abs_audio_dir_path}", flush=True) # DEBUG
    try:
        return send_from_directory(abs_audio_dir_path, filename)
    except FileNotFoundError:
        print(f"[Error] Audio file not found in directory: {filename}", flush=True)
        return "Audio not found", 404
    except Exception as e:
        print(f"[Error] Error serving audio {filename}: {e}", flush=True)
        return "Server error", 500
    

# --- Route Code ---
@app.route("/quotes_manager")
def quotes_manager():
    """Display quotes, check for media files, and manage quote content."""
    if not session.get("logged_in"): return redirect(url_for("login"))

    print("\n[DEBUG][QuotesMgr] Loading controller data...", flush=True) # DEBUG
    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data:
        flash("Controller file not found", "danger")
        return redirect(url_for("dashboard"))

    # --- Get Paths from Controller Task Args ---
    print("[DEBUG][QuotesMgr] Looking for 'Create Quotes Videos' task config...", flush=True) # DEBUG
    # Use the correct task name key as defined in your controller.json
    quotes_task_config = controller_data.get("tasks", {}).get("Create Quotes Videos", {})
    args = quotes_task_config.get("args", [])
    print(f"[DEBUG][QuotesMgr] Task Args found: {args}", flush=True) # DEBUG

    # Helper to find argument values robustly
    def find_arg_value(arg_name, args_list):
        try:
            index = args_list.index(arg_name)
            # Check if there is a value after the argument name
            if index + 1 < len(args_list):
                value = args_list[index + 1]
                print(f"  [DEBUG][FindArg] Found '{arg_name}' -> '{value}'", flush=True) # DEBUG
                return value
            else:
                print(f"  [DEBUG][FindArg] Found '{arg_name}' but no value after it.", flush=True) # DEBUG
                return None
        except ValueError:
            # Argument name not found in the list
            print(f"  [DEBUG][FindArg] Argument '{arg_name}' not found in list.", flush=True) # DEBUG
            return None
        except Exception as e:
             print(f"  [DEBUG][FindArg] Error finding '{arg_name}': {e}", flush=True) # DEBUG
             return None

    # Call helper for each required path
    input_json_path = find_arg_value("--input-json", args)
    image_dir_path = find_arg_value("--image-dir", args)
    audio_dir_path = find_arg_value("--audio-dir", args)

    # --- Validation ---
    if not all([input_json_path, image_dir_path, audio_dir_path]):
        print("[ERROR][QuotesMgr] Failed to find one or more required paths in task args.", flush=True) # DEBUG
        flash("Could not find input paths (--input-json, --image-dir, --audio-dir) in the 'Create Quotes Videos' task arguments within controller.json. Please check configuration.", "danger")
        # Render template but indicate the error clearly
        return render_template("quotes_manager.html",
                               quotes_data={},
                               base_names=[],
                               error_message="Configuration Error: Input paths not found in task arguments.")

    print(f"[DEBUG][QuotesMgr] Paths found: JSON='{input_json_path}', Img='{image_dir_path}', Audio='{audio_dir_path}'", flush=True) # DEBUG

    # --- Load Quotes JSON ---
    print(f"[DEBUG][QuotesMgr] Loading quotes JSON from: {input_json_path}", flush=True) # DEBUG
    quotes_content = load_json(input_json_path)
    if quotes_content is None:
        quotes_content = {}
        # Don't flash here if the file genuinely might not exist yet
        print(f"[Warning][QuotesMgr] Could not load or find {os.path.basename(input_json_path)}. Proceeding with empty data.", flush=True) # DEBUG

    # --- Prepare Data for Template ---
    quotes_display_data = {}
    base_names = sorted(quotes_content.keys())

    for base_name in base_names:
        data = quotes_content[base_name]
        image_exists = False
        audio_exists = False

        # Use Pathlib for robust path joining and checking
        try:
            image_path = Path(image_dir_path) / f"{base_name}.png"
            if image_path.is_file():
                image_exists = True

            audio_path = Path(audio_dir_path) / f"{base_name}.mp3"
            if audio_path.is_file():
                audio_exists = True
        except Exception as e:
             print(f"[Error][QuotesMgr] Error checking files for base_name '{base_name}': {e}", flush=True)


        quotes_display_data[base_name] = {
            "quote": data.get("quote", ""),
            "author": data.get("comment", ""),
            "image_exists": image_exists,
            "audio_exists": audio_exists
        }

    print(f"[DEBUG][QuotesMgr] Prepared data for {len(quotes_display_data)} quotes.", flush=True) # DEBUG

    return render_template("quotes_manager.html",
                           quotes_data=quotes_display_data,
                           base_names=base_names,
                           image_dir=image_dir_path,
                           audio_dir=audio_dir_path,
                           error_message=None, # Pass None if no config error
                           # --- PASS PATHS FOR JS UPLOAD ---
                           image_upload_path=image_dir_path,
                           audio_upload_path=audio_dir_path
                           )

# --- NEW UPLOAD ROUTE ---
ALLOWED_EXTENSIONS = {'png', 'mp3'}
FILENAME_PATTERN = re.compile(r'^(\d{3,})\.(png|mp3)$', re.IGNORECASE) # Match 001.png, 002.mp3 etc.

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload_quote_files', methods=['POST'])
def upload_quote_files():
    """Handle image/audio file uploads for the quotes manager."""
    if not session.get("logged_in"):
        return jsonify(error="Unauthorized"), 401

    if 'file' not in request.files:
        return jsonify(error="No file part in the request"), 400

    file = request.files['file']
    upload_type = request.form.get('type') # 'image' or 'audio'
    image_dir_path = request.form.get('image_dir') # Get paths from form data
    audio_dir_path = request.form.get('audio_dir')

    if not file or file.filename == '':
        return jsonify(error="No selected file"), 400
    if not upload_type or not image_dir_path or not audio_dir_path:
        return jsonify(error="Missing upload type or directory paths"), 400

    if allowed_file(file.filename):
        # Use secure_filename but then validate our specific pattern
        # secure_filename removes path components and normalizes
        filename = secure_filename(file.filename)
        match = FILENAME_PATTERN.match(filename)

        if not match:
             return jsonify(error=f"Invalid filename format. Must be like '001.png' or '001.mp3'."), 400

        base_name = match.group(1) # e.g., "001"
        extension = match.group(2).lower() # e.g., "png"

        target_dir = ""
        expected_extension = ""
        if upload_type == 'image' and extension == 'png':
            target_dir = image_dir_path
            expected_extension = '.png'
        elif upload_type == 'audio' and extension == 'mp3':
            target_dir = audio_dir_path
            expected_extension = '.mp3'
        else:
             return jsonify(error=f"File type mismatch. Expected '{upload_type}' (.{'png' if upload_type == 'image' else 'mp3'}) but got '.{extension}'."), 400

        # Construct final path and check for duplicates
        final_path = os.path.join(target_dir, f"{base_name}{expected_extension}")
        print(f"Checking for existing file at: {final_path}", flush=True) # DEBUG

        if os.path.exists(final_path):
             print(f"File already exists: {final_path}", flush=True) # DEBUG
             # Return a success but indicate it already exists
             return jsonify(success=True, message=f"File '{filename}' already exists.", filename=filename), 200

        # Save the file
        try:
            print(f"Saving file to: {final_path}", flush=True) # DEBUG
            # Ensure target directory exists (should exist based on controller)
            os.makedirs(target_dir, exist_ok=True)
            file.save(final_path)
            return jsonify(success=True, message=f"File '{filename}' uploaded successfully.", filename=filename), 200
        except Exception as e:
            print(f"Error saving file {filename}: {e}", flush=True) # DEBUG
            return jsonify(error=f"Server error saving file: {e}"), 500

    else:
        return jsonify(error="File type not allowed. Only .png and .mp3 are accepted."), 400
@app.route("/", methods=["GET", "POST"])
def login():
    if session.get("logged_in"): return redirect(url_for("dashboard"))
    if request.method == "POST":
        password = request.form.get("password")
        if password == "1234": # TODO: Change this!
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        else:
            flash("Incorrect password!", "danger")
    return render_template("login.html")
@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"): return redirect(url_for("login"))

    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data:
        flash("CRITICAL: controller.json not found or is corrupted!", "danger")
        return render_template("dashboard.html", modules=[])

    modules = []
    categories = controller_data.get("categories", {})
    all_tasks = controller_data.get("tasks", {})
    txt_file_map_paths = controller_data.get("global_settings", {}).get("txt_file_map", {})
    txt_file_map_names = {v: k for k, v in txt_file_map_paths.items()}

    # --- Debug: Print loaded task names ---
    print(f"\nLoaded Task Names: {list(all_tasks.keys())}", flush=True)
    # --- End Debug ---

    for cat_name in sorted(categories.keys()):
        cat_config = categories[cat_name]
        module = {
            "name": cat_name,
            "tasks": [],
            "txt_file_name": None,
            "txt_file_path": cat_config.get("input_txt_file"),
            "can_edit_json": cat_config.get("link_extractor_type") == "simple"
        }

        # Match Tasks
        print(f"\n--- Checking category: '{cat_name}' ---", flush=True) # DEBUG
        cat_name_lower_stripped = cat_name.lower().strip() # Trim whitespace
        print(f"  Cleaned category name for comparison: '{cat_name_lower_stripped}'", flush=True) # DEBUG

        for task_name in all_tasks.keys():
            task_name_lower_stripped = task_name.lower().strip() # Trim whitespace
            # --- DETAILED DEBUG PRINTS ---
            print(f"  Comparing category '{cat_name_lower_stripped}' with task '{task_name_lower_stripped}'", flush=True)
            comparison_result = cat_name_lower_stripped in task_name_lower_stripped
            print(f"  -> Check: '{cat_name_lower_stripped}' in '{task_name_lower_stripped}'? Result: {comparison_result}", flush=True)
            # --- END DETAILED DEBUG ---

            if comparison_result: # Use the variable here
                module["tasks"].append(task_name)
                print(f"    --> MATCH FOUND! Added task.", flush=True) # DEBUG
            # --- Optional: Print if no match found ---
            # else:
            #     print(f"    --> No match.", flush=True)
            # --- End Optional ---


        # Find TXT button name using the path stored in the category
        if module["txt_file_path"] and module["txt_file_path"] in txt_file_map_names:
             module["txt_file_name"] = txt_file_map_names[module["txt_file_path"]]

        modules.append(module)

    return render_template("dashboard.html", modules=modules)

# --- Run & Monitor ---
@app.route("/run_task/<task_name>")
def run_task(task_name):
    if not session.get("logged_in"): return redirect(url_for("login"))
    reap_finished_processes()
    if task_name in RUNNING_PROCESSES:
        flash(f"Task '{task_name}' is already running!", "warning")
        return redirect(url_for("monitor"))
    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data:
        flash("Could not load controller.json", "danger")
        return redirect(url_for("dashboard"))

    process, log_file, log_handle = start_python_task(task_name, controller_data)
    if process:
        RUNNING_PROCESSES[task_name] = {'process': process, 'log_file': log_file, 'log_handle': log_handle}
        flash(f"Started task: {task_name}", "success")
    else:
        flash(f"Failed to start task: {task_name}", "danger")
        if 'log_handle' in locals() and log_handle:
            try: log_handle.close()
            except: pass
        if 'log_file' in locals() and log_file and os.path.exists(log_file):
            try: os.remove(log_file)
            except: pass
    return redirect(url_for("monitor"))

@app.route("/stream_log/<task_name>")
def stream_log(task_name):
    if not session.get("logged_in"): return Response("Unauthorized", status=401)
    proc_data = RUNNING_PROCESSES.get(task_name)
    if not proc_data:
        return Response("data: --- TASK NOT FOUND OR ALREADY FINISHED ---\n\n", mimetype="text/event-stream")

    def generate_log_stream():
        log_file_path = proc_data['log_file']
        yield "data: --- Connected to log stream. Waiting for output... ---\n\n"
        try:
            with open(log_file_path, 'r', encoding='utf-8') as f:
                for existing_line in f: yield f"data: {existing_line.rstrip()}\n\n"
                while task_name in RUNNING_PROCESSES:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        if RUNNING_PROCESSES.get(task_name) is None: break
                        continue
                    yield f"data: {line.rstrip()}\n\n"
            yield "data: --- TASK FINISHED OR STOPPED ---\n\n"
        except FileNotFoundError: yield f"data: --- LOG FILE NOT FOUND: {os.path.basename(log_file_path)} ---\n\n"
        except Exception as e: yield f"data: --- LOG STREAMING ERROR: {e} ---\n\n"

    return Response(generate_log_stream(), mimetype="text/event-stream")

@app.route("/monitor")
def monitor():
    if not session.get("logged_in"): return redirect(url_for("login"))
    reap_finished_processes()
    return render_template("monitor.html", running_processes=RUNNING_PROCESSES, finished_log=FINISHED_LOG)

@app.route("/stop_task/<task_name>")
def stop_task(task_name):
    if not session.get("logged_in"): return redirect(url_for("login"))
    proc_data = RUNNING_PROCESSES.get(task_name)
    if proc_data:
        process, log_handle, log_file = proc_data['process'], proc_data.get('log_handle'), proc_data.get('log_file')
        output = ""
        print(f"Attempting to stop task: {task_name}", flush=True)
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"Process {task_name} unresponsive, killing...", flush=True)
            process.kill()
            output += "--- Process unresponsive, had to kill. ---\n"
        except Exception as e:
            print(f"Error during terminate/kill: {e}", flush=True)
            output += f"--- Error during stop: {e} ---\n"

        if log_handle and not log_handle.closed: log_handle.close()
        try:
            if log_file and os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f: output = f.read()
                output = f"--- STOPPED BY USER ---\n{output}"
                os.remove(log_file)
            else: output += f"--- STOPPED BY USER (Log file '{log_file}' not found) ---"
        except Exception as e:
            output += f"--- STOPPED BY USER (Error reading/removing log): {e} ---"

        add_to_finished_log(task_name, False, output)
        if task_name in RUNNING_PROCESSES: del RUNNING_PROCESSES[task_name]
        flash(f"Stopped task: {task_name}", "warning")
    else:
        flash(f"Task '{task_name}' not found or already finished.", "info")
    return redirect(url_for("monitor"))

@app.route("/clear_log")
def clear_log():
    if not session.get("logged_in"): return redirect(url_for("login"))
    FINISHED_LOG.clear()
    cleared_files = 0
    errors = []
    try:
        for f in os.listdir(LOG_DIR):
            if f.endswith(".log"):
                try:
                    os.remove(os.path.join(LOG_DIR, f))
                    cleared_files += 1
                except Exception as e_remove:
                    errors.append(f"Could not remove {f}: {e_remove}")
        if not errors:
            flash(f"Finished job log cleared. Removed {cleared_files} log files.", "info")
        else:
            flash(f"Log cleared, but failed to clean up some files: {'; '.join(errors)}", "warning")
    except Exception as e:
        flash(f"Log cleared, but failed to scan/clean log directory: {e}", "danger")
    return redirect(url_for("monitor"))

# --- Edit Routes ---
@app.route("/edit_json/<category_name>", methods=["GET", "POST"])
def edit_json(category_name):
    if not session.get("logged_in"): return redirect(url_for("login"))
    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data:
        flash("Controller file not found", "danger")
        return redirect(url_for("dashboard"))

    category_config = controller_data.get("categories", {}).get(category_name)
    if not category_config or category_config.get("link_extractor_type") != "simple":
         flash(f"Direct JSON editing not supported for '{category_name}'.", "warning")
         return redirect(url_for("dashboard"))

    links_data = controller_data.get("json_data", {}).get(category_name, {})
    try:
        sorted_items = sorted(links_data.items(), key=lambda item: int(item[0].replace('post','')))
        links_text = "\n".join([v for k, v in sorted_items])
    except: links_text = "\n".join(links_data.values())

    if request.method == "POST":
        links_input = request.form.get("links", "")
        links_list = [link.strip() for link in links_input.splitlines() if link.strip()]
        new_data = {f"post{i+1}": link for i, link in enumerate(links_list)}
        if "json_data" not in controller_data: controller_data["json_data"] = {}
        controller_data["json_data"][category_name] = new_data
        if save_json(controller_data, CONTROLLER_FILE):
             flash(f"Successfully updated {category_name} links in controller.", "success")
        else:
             flash(f"Failed to save updated controller file.", "danger")
        return redirect(url_for("dashboard"))

    return render_template("edit_json.html", section_name=category_name, links_text=links_text)


@app.route("/settings")
def settings_overview():
    """Show links to global and category-specific settings."""
    if not session.get("logged_in"): return redirect(url_for("login"))
    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data:
        flash("Controller file not found", "danger")
        return redirect(url_for("dashboard"))

    categories = controller_data.get("categories", {}).keys()
    return render_template("settings_overview.html", categories=sorted(categories))

@app.route("/settings/global", methods=["GET", "POST"])
def settings_global():
    """Edit global settings."""
    if not session.get("logged_in"): return redirect(url_for("login"))
    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data:
        flash("Controller file not found", "danger")
        return redirect(url_for("settings_overview"))

    if request.method == "POST":
        # --- Save updated global settings ---
        try:
            current_settings = controller_data.get("global_settings", {})
            current_settings["ollama_api_url"] = request.form.get("ollama_api_url", current_settings.get("ollama_api_url"))
            current_settings["ollama_model"] = request.form.get("ollama_model", current_settings.get("ollama_model"))
            current_settings["ollama_timeout"] = int(request.form.get("ollama_timeout", current_settings.get("ollama_timeout", 60)))

            # Update txt_file_map (more complex, handle carefully)
            # For simplicity now, let's assume txt_file_map isn't editable here
            # Or requires specific add/remove buttons

            controller_data["global_settings"] = current_settings
            if save_json(controller_data, CONTROLLER_FILE):
                flash("Global settings updated successfully.", "success")
            else:
                flash("Failed to save controller file.", "danger")
            return redirect(url_for("settings_global")) # Redirect back to refresh
        except ValueError:
             flash("Invalid input: Ollama timeout must be a number.", "danger")
        except Exception as e:
            flash(f"Error saving global settings: {e}", "danger")

    # Pass current settings and timezone list to the template
    timezones = pytz.common_timezones # Get list of valid timezones
    return render_template("settings_global.html",
                           settings=controller_data.get("global_settings", {}),
                           timezones=timezones)


@app.route("/settings/category/<category_name>", methods=["GET", "POST"])
def settings_category(category_name):
    """Edit settings for a specific category."""
    if not session.get("logged_in"): return redirect(url_for("login"))
    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data:
        flash("Controller file not found", "danger")
        return redirect(url_for("settings_overview"))

    category_config = controller_data.get("categories", {}).get(category_name)
    if not category_config:
        flash(f"Category '{category_name}' not found.", "warning")
        return redirect(url_for("settings_overview"))

    if request.method == "POST":
        # --- Save updated category settings ---
        try:
            # Update paths (ensure forward slashes for consistency internally?)
            category_config["input_txt_file"] = request.form.get("input_txt_file") or None # Allow empty
            category_config["download_target_dir"] = request.form.get("download_target_dir")
            category_config["upload_source_dir"] = request.form.get("upload_source_dir")
            category_config["uploaded_dir"] = request.form.get("uploaded_dir")
            category_config["schedule_log_file"] = request.form.get("schedule_log_file")
            category_config["token_file"] = request.form.get("token_file")
            category_config["client_secrets_file"] = request.form.get("client_secrets_file")

            # Update types/schemes
            category_config["link_extractor_type"] = request.form.get("link_extractor_type") or None
            category_config["download_naming_scheme"] = request.form.get("download_naming_scheme")
            category_config["download_prefix"] = request.form.get("download_prefix") or None

            # Update YouTube settings
            category_config["yt_category_id"] = request.form.get("yt_category_id")
            category_config["yt_default_title"] = request.form.get("yt_default_title")
            category_config["yt_default_description"] = request.form.get("yt_default_description")
            # Tags need special handling (textarea -> list)
            tags_text = request.form.get("yt_default_tags", "")
            category_config["yt_default_tags"] = [tag.strip() for tag in tags_text.splitlines() if tag.strip()]

            # Update toggles
            category_config["use_ai_generator"] = "use_ai_generator" in request.form

            # Update schedule settings within the separate schedule file
            schedule_file_path = category_config.get("schedule_log_file")
            schedule_data = load_json(schedule_file_path) if schedule_file_path else {}
            if schedule_data is None: schedule_data = {} # Handle file not found or invalid JSON

            schedule_data["schedule_enabled"] = "schedule_enabled" in request.form
            schedule_data["schedule_start_datetime"] = request.form.get("schedule_start_datetime")
            schedule_data["schedule_frequency_days"] = int(request.form.get("schedule_frequency_days", 1))
            schedule_data["schedule_timezone"] = request.form.get("schedule_timezone")
            schedule_data["scheduled_task_name"] = request.form.get("scheduled_task_name")
            # Keep existing last_scheduled_utc
            schedule_data["last_scheduled_utc"] = schedule_data.get("last_scheduled_utc")

            # Save main controller
            controller_data["categories"][category_name] = category_config
            main_save_ok = save_json(controller_data, CONTROLLER_FILE)

            # Save schedule file
            schedule_save_ok = False
            if schedule_file_path:
                schedule_save_ok = save_json(schedule_data, schedule_file_path)
            else:
                 flash("Schedule settings not saved: 'schedule_log_file' path missing in category config.", "warning")


            if main_save_ok and (not schedule_file_path or schedule_save_ok):
                flash(f"Settings for '{category_name}' updated successfully.", "success")
            else:
                flash(f"Failed to save settings for '{category_name}'. Check file permissions.", "danger")

            return redirect(url_for("settings_category", category_name=category_name)) # Redirect back

        except ValueError:
             flash("Invalid input: Frequency must be a number.", "danger")
        except Exception as e:
            flash(f"Error saving settings for '{category_name}': {e}", "danger")

    # Load schedule data for display
    schedule_file_path = category_config.get("schedule_log_file")
    schedule_data = load_json(schedule_file_path) if schedule_file_path else {}
    if schedule_data is None: schedule_data = {} # Default if file missing/corrupt

    timezones = pytz.common_timezones
    # Convert tags list back to string for textarea
    tags_display = "\n".join(category_config.get("yt_default_tags", []))

    return render_template("settings_category.html",
                           category_name=category_name,
                           config=category_config,
                           schedule_config=schedule_data,
                           timezones=timezones,
                           tags_display=tags_display,
                           tasks=controller_data.get("tasks", {}).keys() # Pass task names for dropdown
                           )

# --- Add this near the bottom, BEFORE if __name__ == "__main__": ---
# Make pytz available to all templates if needed (optional)
@app.context_processor
def inject_pytz():
    return dict(pytz=pytz)


@app.route("/edit_txt/<txt_task_name>", methods=["GET", "POST"])
def edit_txt(txt_task_name):
    if not session.get("logged_in"): return redirect(url_for("login"))
    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data:
        flash("Controller file not found", "danger")
        return redirect(url_for("dashboard"))

    txt_file_map = controller_data.get("global_settings", {}).get("txt_file_map", {})
    txt_path = txt_file_map.get(txt_task_name)
    if not txt_path:
        flash(f"TXT file path not found for task '{txt_task_name}'!", "danger")
        return redirect(url_for("dashboard"))

    if not os.path.exists(txt_path):
        try:
            os.makedirs(os.path.dirname(txt_path), exist_ok=True)
            with open(txt_path, "w", encoding="utf-8") as f: f.write("")
            flash(f"Created new file: {os.path.basename(txt_path)}", "info")
        except Exception as e:
            flash(f"Could not create file at {txt_path}: {e}", "danger")
            return redirect(url_for("dashboard"))

    content = ""
    try:
        with open(txt_path, "r", encoding="utf-8") as f: content = f.read()
    except Exception as e: flash(f"Error reading {os.path.basename(txt_path)}: {e}", "danger")

    if request.method == "POST":
        new_content = request.form.get("content", "")
        try:
            with open(txt_path, "w", encoding="utf-8") as f: f.write(new_content)
            flash(f"Successfully updated {txt_task_name}.", "success")
        except Exception as e:
            flash(f"Error writing to {os.path.basename(txt_path)}: {e}", "danger")
        return redirect(url_for("dashboard"))

    return render_template("edit_txt.html", txt_name=txt_task_name, content=content)

@app.route("/analytics")
def analytics():
    if not session.get("logged_in"): return redirect(url_for("login"))

    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data:
        flash("Controller file not found", "danger")
        return redirect(url_for("dashboard"))

    # 1. Load Analytics Cache
    cache_path = controller_data.get("global_settings", {}).get("analytics_cache_file")
    analytics_data = {}
    last_updated = "Never"
    if cache_path and os.path.exists(cache_path):
        cache_content = load_json(cache_path)
        if cache_content:
            analytics_data = cache_content.get("channels", {})
            last_updated = cache_content.get("last_updated", "Unknown")

    # 2. Load Quota Log (NEW)
    quota_path = os.path.join(os.path.dirname(CONTROLLER_DIR), "data", "quota_log.json")
    quota_data = {"used": 0, "date": "Today"}
    if os.path.exists(quota_path):
        q_load = load_json(quota_path)
        if q_load: quota_data = q_load
    
    # Calculate percentages
    used = quota_data.get("used", 0)
    limit = 10000
    percent = min(100, int((used / limit) * 100))
    
    # Estimate remaining actions
    uploads_left = int((limit - used) / 1600)
    syncs_left = int((limit - used) / 50)

    return render_template(
        "analytics.html", 
        channels=analytics_data, 
        last_updated=last_updated,
        quota={
            "used": used,
            "percent": percent,
            "uploads_left": uploads_left,
            "syncs_left": syncs_left
        }
    )

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

# --- MANUAL UPLOAD FLOW ---

@app.route("/upload_select/<category>")
def upload_select(category):
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    controller_data = load_json(CONTROLLER_FILE)
    cat_config = controller_data.get("categories", {}).get(category)
    
    source_dir = cat_config.get("upload_source_dir")
    files = []
    
    if source_dir and os.path.exists(source_dir):
        files = sorted([f for f in os.listdir(source_dir) if f.lower().endswith(('.mp4', '.mov', '.mkv'))])
        
    return render_template("upload_select.html", category=category, files=files, source_dir=source_dir)

@app.route("/upload_review/<category>/<filename>")
def upload_review(category, filename):
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    controller_data = load_json(CONTROLLER_FILE)
    cat_config = controller_data.get("categories", {}).get(category)
    
    # 1. Generate Defaults (Simulate what the script would have done)
    base_name = os.path.splitext(filename)[0]
    
    # Try getting metadata from JSON (Entertopia style)
    meta_entry = controller_data.get("json_data", {}).get(category, {}).get(base_name)
    video_name = meta_entry.get("name") if isinstance(meta_entry, dict) else None
    video_url = meta_entry.get("url") if isinstance(meta_entry, dict) else (meta_entry if isinstance(meta_entry, str) else None)
    
    # Default Fallbacks
    default_title = cat_config.get("yt_default_title", "")
    default_desc = cat_config.get("yt_default_description", "")
    default_tags = cat_config.get("yt_default_tags", [])
    
    # Construct initial values
    final_title = default_title
    final_desc = default_desc
    
    if video_name: 
        final_title = f"{video_name.title()} #shorts"
    if video_url:
        final_desc += f"\n\nSource: {video_url}"
        
    # Schedule Estimate (Tomorrow 10 AM)
    now = datetime.datetime.now()
    tmrw = now + datetime.timedelta(days=1)
    schedule_str = tmrw.strftime("%Y-%m-%dT10:00")

    defaults = {
        "title": final_title,
        "description": final_desc,
        "tags": ", ".join(default_tags),
        "schedule": schedule_str
    }
    
    return render_template("upload_review.html", category=category, filename=filename, defaults=defaults)

@app.route("/upload_execute", methods=["POST"])
def upload_execute():
    if not session.get("logged_in"): return redirect(url_for("login"))
    
    category = request.form.get("category")
    filename = request.form.get("filename")
    
    # Call the helper function in the script
    success, message = upload_to_youtube.upload_single_video_from_flask(
        category, filename, request.form, CONTROLLER_FILE
    )
    
    if success:
        flash(f"Success: {message}", "success")
    else:
        flash(f"Failed: {message}", "danger")
        
    return redirect(url_for('upload_select', category=category))

# --- Run ---
if __name__ == "__main__":
    # Change CWD to the script's directory for reliable relative paths
    os.chdir(CONTROLLER_DIR)
    print(f"Changed working directory to: {CONTROLLER_DIR}")
    print(f"Controller file path: {CONTROLLER_FILE}")
    print(f"Log directory path: {LOG_DIR}")
    app.run(host="0.0.0.0", port=5000, debug=True)