import sys
# sys.stdout.reconfigure(encoding='utf-8') # Uncomment if needed

import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# --- Constants ---
# UPGRADED SCOPES:
# 1. upload: For the Fallback API uploader
# 2. readonly: To fetch video lists and public stats (Cheap API calls)
# 3. yt-analytics.readonly: To fetch Watch Time and Demographics
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly"
]

# --- YouTube Authentication ---

def authenticate_youtube(client_secrets_path, token_path):
    """
    Handles OAuth 2.0 flow. Returns credentials object if successful.
    """
    if not os.path.exists(client_secrets_path):
        print(f"[Error][Auth] Client secrets file not found: {client_secrets_path}", flush=True)
        return None

    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1" # Allow http://localhost redirect
    creds = None

    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            # print(f"[Info][Auth] Loaded credentials from {token_path}", flush=True)
        except Exception as e:
            print(f"[Warning][Auth] Error loading token {token_path}: {e}", flush=True)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[Info][Auth] Credentials expired. Refreshing...", flush=True)
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"[Error][Auth] Refresh failed: {e}. Re-authenticating.", flush=True)
                creds = None
        else:
            print("[Info][Auth] Authenticating for Upload + Analytics...", flush=True)
            try:
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                    client_secrets_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            except Exception as e:
                 print(f"[Error][Auth] Auth flow failed: {e}", flush=True)
                 return None

        # Save the new token with updated scopes
        if creds:
            try:
                os.makedirs(os.path.dirname(token_path), exist_ok=True)
                with open(token_path, 'w') as token_file:
                    token_file.write(creds.to_json())
                print(f"[Info][Auth] New token saved to {token_path}", flush=True)
            except Exception as e:
                print(f"[Error][Auth] Saving token failed: {e}", flush=True)

    return creds

def get_youtube_service(creds):
    """Builds the Data API service (Videos, Uploads, Public Stats)."""
    try:
        return googleapiclient.discovery.build("youtube", "v3", credentials=creds)
    except Exception as e:
        print(f"[Error][Auth] Failed to build YouTube Data service: {e}", flush=True)
        return None

def get_analytics_service(creds):
    """Builds the Analytics API service (Watch Time, Retention)."""
    try:
        return googleapiclient.discovery.build("youtubeAnalytics", "v2", credentials=creds)
    except Exception as e:
        print(f"[Error][Auth] Failed to build YouTube Analytics service: {e}", flush=True)
        return None
    
import datetime
import json

# --- Quota Management ---

def get_pacific_date_str():
    """Returns current date in Pacific Time (PT) as string 'YYYY-MM-DD'."""
    # PT is UTC-8 (roughly, ignoring DST for simplicity which is fine for quota)
    utc_now = datetime.datetime.utcnow()
    pt_now = utc_now - datetime.timedelta(hours=8)
    return pt_now.strftime("%Y-%m-%d")

def track_quota_usage(units_used, controller_path):
    """
    Updates the local quota log. Resets if it's a new day in PT.
    """
    # 1. Determine paths
    # We assume controller_path points to controller.json
    project_root = os.path.dirname(os.path.dirname(controller_path))
    quota_file = os.path.join(project_root, "data", "quota_log.json")

    # 2. Load existing log
    data = {"date": get_pacific_date_str(), "used": 0}
    if os.path.exists(quota_file):
        try:
            with open(quota_file, "r") as f:
                loaded = json.load(f)
                # Check if date matches current PT date
                if loaded.get("date") == data["date"]:
                    data = loaded
                else:
                    print("[Quota] New day detected (PT). Resetting quota counter.", flush=True)
                    # Data stays at 0 used for new date
        except: pass

    # 3. Update usage
    data["used"] += units_used
    
    # 4. Save
    try:
        os.makedirs(os.path.dirname(quota_file), exist_ok=True)
        with open(quota_file, "w") as f:
            json.dump(data, f)
        print(f"[Quota] +{units_used} units. Total used today: {data['used']}/10,000", flush=True)
    except Exception as e:
        print(f"[Warning] Failed to save quota log: {e}", flush=True)