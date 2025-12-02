import sys
# FORCE UTF-8 ENCODING FOR WINDOWS CONSOLE
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass 

import os
import json
import shutil
import instaloader
import re
import argparse
from urllib.parse import urlparse

# --- Constants ---
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.mpeg', '.mpg', '.3gp'}

# --- Helper Functions ---

def load_json(file_path):
    if not os.path.exists(file_path):
        print(f"[Error] File not found: {file_path}", flush=True)
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Error] Could not read file {file_path}: {e}", flush=True)
        return None

def setup_folder(folder_path):
    try:
        os.makedirs(folder_path, exist_ok=True)
        print(f"[OK] Download folder ready: {folder_path}", flush=True)
        return True
    except Exception as e:
        print(f"[Error] Could not create download folder {folder_path}: {e}", flush=True)
        return False

def get_shortcode_from_url(url):
    try:
        path = urlparse(url).path
        parts = [p for p in path.split('/') if p]
        return parts[1] if len(parts) >= 2 else None
    except Exception:
        return None

def download_and_rename_media(url, post_key, loader, save_folder, naming_scheme="post_key", prefix=None):
    shortcode = get_shortcode_from_url(url)
    if not shortcode:
        print(f"[WARN] Invalid URL format for {post_key}: {url}", flush=True)
        return False

    # FIX: Store original directory to return to it later
    original_cwd = os.getcwd()
    
    # Change working directory to the save_folder to avoid Instaloader path issues
    try:
        os.chdir(save_folder)
    except Exception as e:
        print(f"[Error] Could not access download folder: {e}", flush=True)
        return False

    temp_dir_name = f"temp_{post_key}"
    
    # Cleanup old temp dir if exists
    if os.path.exists(temp_dir_name):
        try:
            shutil.rmtree(temp_dir_name)
        except: pass

    success = False

    try:
        print(f"[..] Downloading {post_key} ({shortcode})...", flush=True)
        post = instaloader.Post.from_shortcode(loader.context, shortcode)

        if post.is_video:
            # Download to relative folder name (safe)
            loader.download_post(post, target=temp_dir_name)

            video_file_name = None
            if os.path.exists(temp_dir_name):
                for filename in os.listdir(temp_dir_name):
                    if os.path.splitext(filename)[1].lower() in VIDEO_EXTENSIONS:
                        video_file_name = filename
                        break

            if video_file_name:
                old_path = os.path.join(temp_dir_name, video_file_name)
                file_ext = os.path.splitext(video_file_name)[1]
                new_name = ""

                # Determine New Name
                if naming_scheme == "post_key":
                    new_name = f"{post_key}{file_ext}"
                elif naming_scheme == "prefix_number":
                    max_num = 0
                    pattern = re.compile(rf"^{prefix}-(\d{{3}}){re.escape(file_ext)}$")
                    # Scan current directory (save_folder)
                    for existing_file in os.listdir("."):
                        match = pattern.match(existing_file)
                        if match:
                            num = int(match.group(1))
                            if num > max_num: max_num = num
                    new_name = f"{prefix}-{max_num + 1:03d}{file_ext}"
                elif naming_scheme == "base_name":
                      base_name_match = re.match(r"(\d+)_video", post_key)
                      if base_name_match: new_name = f"{base_name_match.group(1)}{file_ext}"
                      else: new_name = f"{post_key}{file_ext}"
                else:
                    new_name = f"{post_key}{file_ext}"

                # Handle duplicates
                final_name = new_name
                counter = 1
                while os.path.exists(final_name):
                      name_part, ext_part = os.path.splitext(new_name)
                      final_name = f"{name_part}_({counter}){ext_part}"
                      counter += 1

                # Move file from temp folder to current folder (save_folder)
                shutil.move(old_path, final_name)
                print(f"[OK] Saved as: {final_name}", flush=True)
                success = True
            else:
                print(f"[WARN] No video file found inside {temp_dir_name}.", flush=True)
        else:
            print(f"[Info] {post_key} is not a video.", flush=True)

    except Exception as e:
        print(f"[Error] Failed to download {post_key}: {e}", flush=True)
    
    finally:
        # Cleanup temp dir
        if os.path.exists(temp_dir_name):
            try: shutil.rmtree(temp_dir_name)
            except: pass
        
        # RESTORE ORIGINAL DIRECTORY
        os.chdir(original_cwd)

    return success

def main(category_name, controller_path):
    print(f"--- Starting Download: {category_name} ---", flush=True)

    controller_data = load_json(controller_path)
    if not controller_data: return

    category_config = controller_data.get("categories", {}).get(category_name)
    if not category_config:
        print(f"[Error] Category '{category_name}' not found.", flush=True)
        return

    save_folder = category_config.get("download_target_dir")
    naming_scheme = category_config.get("download_naming_scheme", "post_key")
    prefix = category_config.get("download_prefix")
    links_data = controller_data.get("json_data", {}).get(category_name)

    if not save_folder or not links_data:
        print("[Info] Missing folder or links.", flush=True)
        return

    if not setup_folder(save_folder): return

    # --- INSTALOADER CONFIG ---
    L = instaloader.Instaloader(
        download_pictures=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        filename_pattern="{profile}_{shortcode}"
    )

    # --- LOAD SESSION ---
    session_file = None
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for f in os.listdir(script_dir):
        if f.startswith("session-"):
            session_file = os.path.join(script_dir, f)
            print(f"[Auth] Found session file: {f}", flush=True)
            break
            
    if session_file:
        try:
            L.load_session_from_file(os.path.basename(session_file).replace("session-", ""), session_file)
            print("[Auth] Logged in successfully.", flush=True)
        except Exception as e:
            print(f"[Warn] Could not load session: {e}", flush=True)
    else:
        print("[Warn] No session file found. Running anonymously.", flush=True)

    download_count = 0
    
    for post_key, entry in links_data.items():
        url = entry if isinstance(entry, str) else entry.get("url")
        if not url: continue

        potential_base = post_key
        if naming_scheme == "base_name":
             m = re.match(r"(\d+)_video", post_key)
             if m: potential_base = m.group(1)
        
        # Basic check for existing files
        exists = False
        for ext in VIDEO_EXTENSIONS:
            if os.path.exists(os.path.join(save_folder, f"{potential_base}{ext}")):
                exists = True
                break
        
        if exists:
            print(f"[Skip] {post_key} already exists.", flush=True)
            continue

        if download_and_rename_media(url.strip(), post_key, L, save_folder, naming_scheme, prefix):
            download_count += 1

    print(f"\n--- Finished. New Downloads: {download_count} ---", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", required=True)
    parser.add_argument("--controller", default="../controller/controller.json")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    controller_abs_path = os.path.abspath(os.path.join(script_dir, args.controller))

    main(args.category, controller_abs_path)