import sys
import os
import datetime
import json
import shutil
import re
import argparse
import requests

# --- Custom Imports ---
try:
    if __name__ == "__main__":
        import upload_selenium
        import utils
    else:
        from scripts import upload_selenium
        from scripts import utils
    SELENIUM_AVAILABLE = True
except ImportError:
    print("[Warning] Dependencies not found. Hybrid mode issues.", flush=True)
    SELENIUM_AVAILABLE = False

import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload

# --- Constants ---
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.mkv', '.avi', '.flv')

# --- Helper Functions ---
def load_json(file_path):
    if not os.path.exists(file_path): 
        return None
    try: 
        with open(file_path, "r", encoding="utf-8") as f: 
            return json.load(f)
    except: 
        return None

def save_json(data, file_path):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f: 
            json.dump(data, f, indent=4)
        return True
    except: 
        return False

def generate_video_details_OLLAMA(name, url, ollama_config):
    # Basic fallback if needed
    return {"title": name, "description": url, "tags": []}

def generate_fallback_details(name, url, default_title, default_desc, default_tags):
    final_title = default_title[:100]
    final_desc = default_desc
    if name:
        t = f"{name.title()} #shorts"
        if len(t) < 100: final_title = t
    if url: final_desc += f"\n\nSource: {url}"
    return {"title": final_title, "description": final_desc, "tags": default_tags[:50]}

# --- Upload Wrappers ---

def run_selenium_upload(category, video_path, title, desc, tags, privacy="private", is_kids=False, schedule_dt=None):
    """Wrapper to call the selenium script with schedule support."""
    if not SELENIUM_AVAILABLE: return False
    try:
        return upload_selenium.upload_video(category, video_path, title, desc, tags, privacy, is_kids, schedule_dt)
    except Exception as e:
        print(f"   [Selenium Crash] {e}", flush=True)
        return False

def run_api_upload(client_secrets, token_file, video_path, title, desc, tags, category_id, schedule_dt, privacy, is_kids):
    """Standard API Upload with specific details."""
    
    # 1. GET CREDENTIALS
    creds = utils.authenticate_youtube(client_secrets, token_file)
    if not creds: 
        print("   [API Error] Could not authenticate.", flush=True)
        return False
    
    # 2. BUILD SERVICE
    yt_service = utils.get_youtube_service(creds)
    if not yt_service:
        print("   [API Error] Could not build YouTube Service object.", flush=True)
        return False
    
    # Format schedule time
    publish_at = None
    status_body = {
        "selfDeclaredMadeForKids": is_kids
    }

    if schedule_dt:
        # API requires ISO format with 'Z' for UTC/Offset
        publish_at = schedule_dt.isoformat(timespec='seconds') + "Z"
        status_body["privacyStatus"] = "private" # API requires private for scheduling
        status_body["publishAt"] = publish_at
    else:
        status_body["privacyStatus"] = privacy

    body = {
        "snippet": {
            "categoryId": str(category_id),
            "title": title,
            "description": desc,
            "tags": tags
        },
        "status": status_body
    }
    
    try:
        print(f"   [API] Uploading '{os.path.basename(video_path)}'...", flush=True)
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        req = yt_service.videos().insert(part="snippet,status", body=body, media_body=media)
        
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status: print(f"    [API] Progress: {int(status.progress() * 100)}%", flush=True)
            
        print(f"   [API] Success! ID: {resp['id']}", flush=True)
        return True
    except Exception as e:
        print(f"   [API Error] {e}", flush=True)
        return False

# --- FLASK EXECUTION FUNCTION ---
def upload_single_video_from_flask(category_name, video_filename, form_data, controller_path):
    """
    Called by the Flask app to execute the upload based on User Review.
    """
    print(f"--- Manual Upload Execution: {video_filename} ---", flush=True)
    
    controller_data = load_json(controller_path)
    cat_config = controller_data.get("categories", {}).get(category_name)
    
    video_path = os.path.join(cat_config.get("upload_source_dir"), video_filename)
    uploaded_dir = cat_config.get("uploaded_dir")
    
    # Check file existence
    if not os.path.exists(video_path):
        return False, "File not found. It might have been already uploaded."

    # Extract form data
    title = form_data.get("title")
    desc = form_data.get("description")
    tags = [t.strip() for t in form_data.get("tags", "").split(",")]
    privacy = form_data.get("privacy", "private")
    is_kids = form_data.get("is_kids") == "on"
    mode = form_data.get("upload_mode", "hybrid") 
    
    enable_schedule = form_data.get("enable_schedule") == "on"
    schedule_dt = None
    
    if enable_schedule:
        schedule_input = form_data.get("schedule_time")
        if schedule_input:
            try:
                # Input format from HTML datetime-local is 'YYYY-MM-DDTHH:MM'
                schedule_dt = datetime.datetime.strptime(schedule_input, "%Y-%m-%dT%H:%M")
            except: pass

    success = False
    
    # --- LOGIC BRANCHING ---
    if enable_schedule:
        print("   📅 Scheduled Upload -> Forcing API for reliability.", flush=True)
        # Note: We must pass arguments by keyword or correct position. 
        # Using Dictionary lookup for safety
        if run_api_upload(
            cat_config["client_secrets_file"], 
            cat_config["token_file"], 
            video_path, 
            title, 
            desc, 
            tags, 
            cat_config["yt_category_id"], 
            schedule_dt, 
            privacy, 
            is_kids
        ):
            utils.track_quota_usage(1600, controller_path)
            success = True
    else:
        # IMMEDIATE UPLOAD LOGIC
        print(f"   🔹 Upload Mode: {mode.upper()}", flush=True)
        
        if mode == "api_only":
            # 1. API ONLY
            if run_api_upload(cat_config["client_secrets_file"], cat_config["token_file"], video_path, title, desc, tags, cat_config["yt_category_id"], None, privacy, is_kids):
                utils.track_quota_usage(1600, controller_path)
                success = True
                
        elif mode == "selenium_only":
            # 2. SELENIUM ONLY
            if run_selenium_upload(category_name, video_path, title, desc, tags, privacy, is_kids):
                utils.track_quota_usage(0, controller_path)
                success = True
            else:
                print("   ❌ Selenium Failed. No fallback requested.", flush=True)
                
        else:
            # 3. HYBRID (Selenium -> API)
            if run_selenium_upload(category_name, video_path, title, desc, tags, privacy, is_kids):
                utils.track_quota_usage(0, controller_path)
                success = True
            else:
                print("   ⚠️ Selenium Failed. Engaging API Fallback...", flush=True)
                if run_api_upload(cat_config["client_secrets_file"], cat_config["token_file"], video_path, title, desc, tags, cat_config["yt_category_id"], None, privacy, is_kids):
                    utils.track_quota_usage(1600, controller_path)
                    success = True

    # Cleanup
    if success:
        try:
            os.makedirs(uploaded_dir, exist_ok=True)
            dest_path = os.path.join(uploaded_dir, video_filename)
            counter = 1
            while os.path.exists(dest_path):
                base, ext = os.path.splitext(video_filename)
                dest_path = os.path.join(uploaded_dir, f"{base}_{counter}{ext}")
                counter += 1
            shutil.move(video_path, dest_path)
            return True, "Upload Successful"
        except Exception as e:
            return True, f"Upload OK, but move failed: {e}"
            
    return False, "Upload Failed."

def main(category_name, controller_path):
    print("This script is now optimized for the Web Dashboard.")

if __name__ == "__main__":
    pass