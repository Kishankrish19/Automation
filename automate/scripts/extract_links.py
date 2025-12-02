import json
import re
import os
import argparse # To read command-line arguments

# --- REGEX PATTERNS ---
# Simple URL extraction
URL_PATTERN = r'https?://[^\s]+'
# URL + Name extraction (URL on one line, Name on the next non-empty line)
ENTRY_PATTERN = r'(https?://[^\s]+)\s+([^\n]+)'

# --- Helper Functions ---

def extract_simple_links(text):
    """Extracts only URLs."""
    return re.findall(URL_PATTERN, text)

def extract_name_url_entries(text):
    """Extracts (URL, Name) tuples."""
    return re.findall(ENTRY_PATTERN, text)

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

# --- Main Logic ---

def main(category_name, controller_path):
    """
    Extracts links for a specific category based on controller configuration.
    """
    print(f"--- Starting Link Extraction for Category: {category_name} ---", flush=True)

    # 1. Load Controller Config
    controller_data = load_json(controller_path)
    if not controller_data:
        return # Error printed in load_json

    category_config = controller_data.get("categories", {}).get(category_name)
    if not category_config:
        print(f"[Error] Category '{category_name}' not found in controller.", flush=True)
        return

    # 2. Get settings from config
    input_txt_file = category_config.get("input_txt_file")
    extractor_type = category_config.get("link_extractor_type")

    if not input_txt_file:
        print(f"[Info] No input_txt_file configured for '{category_name}'. Skipping extraction.", flush=True)
        return # Not an error if the category doesn't use link extraction (like Quotes)

    if not extractor_type:
        print(f"[Error] 'link_extractor_type' not configured for '{category_name}'.", flush=True)
        return

    # 3. Read the input text file
    if not os.path.exists(input_txt_file):
        print(f"[Error] Input text file not found: {input_txt_file}", flush=True)
        return
    try:
        with open(input_txt_file, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"[Error] Could not read input file {input_txt_file}: {e}", flush=True)
        return

    # 4. Extract data based on type
    extracted_data = {}
    items_found = 0

    if extractor_type == "simple":
        urls = extract_simple_links(content)
        if not urls:
            print(f"[Warning] No valid links found in {input_txt_file}", flush=True)
        else:
            extracted_data = {f"post{i+1}": url for i, url in enumerate(urls)}
            items_found = len(urls)
    elif extractor_type == "name_url":
        entries = extract_name_url_entries(content)
        if not entries:
            print(f"[Warning] No valid entries (link + name) found in {input_txt_file}", flush=True)
        else:
            extracted_data = {f"post{i+1}": {"url": url, "name": name.strip()} for i, (url, name) in enumerate(entries)}
            items_found = len(entries)
    else:
        print(f"[Error] Unknown 'link_extractor_type': {extractor_type}", flush=True)
        return

    # 5. Update controller.json
    if "json_data" not in controller_data:
        controller_data["json_data"] = {} # Ensure the section exists

    # Overwrite the specific category's data
    controller_data["json_data"][category_name] = extracted_data

    # 6. Save the updated controller file
    if save_json(controller_data, controller_path):
        print(f"[Success] {items_found} items extracted and saved to controller for '{category_name}'.", flush=True)
    else:
        print(f"[Error] Failed to save updated controller data.", flush=True)

    print(f"--- Finished Link Extraction for {category_name} ---", flush=True)

# --- Command-Line Argument Parsing ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract links from a text file and update the controller JSON.")
    parser.add_argument("--category", required=True, help="The category name (e.g., 'Anime', 'Cars') as defined in controller.json.")
    parser.add_argument("--controller", default="../controller/controller.json", help="Path to the main controller JSON file.") # Default relative path

    args = parser.parse_args()

    # Make controller path absolute relative to this script's location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    controller_abs_path = os.path.abspath(os.path.join(script_dir, args.controller))

    main(args.category, controller_abs_path)