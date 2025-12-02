import sys
import os
import json
import datetime
from googleapiclient.discovery import build

# --- Import from your utils ---
import utils

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CONTROLLER_FILE = os.path.join(PROJECT_ROOT, "controller", "controller.json")

def load_json(file_path):
    if not os.path.exists(file_path): return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except: return None

def save_json(data, file_path):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"[Error] Could not save cache: {e}")
        return False

def get_channel_stats(youtube):
    """Fetches public channel stats."""
    print("  > Fetching Channel Stats...", flush=True)
    response = youtube.channels().list(
        mine=True,
        part="statistics,contentDetails,snippet"
    ).execute()

    if not response['items']: return None

    channel = response['items'][0]
    return {
        "channel_title": channel['snippet']['title'],
        "channel_id": channel['id'],
        "subs": channel['statistics'].get('subscriberCount', 0),
        "views": channel['statistics'].get('viewCount', 0),
        "video_count": channel['statistics'].get('videoCount', 0),
        "uploads_playlist": channel['contentDetails']['relatedPlaylists']['uploads'],
        "thumbnail": channel['snippet']['thumbnails']['default']['url']
    }

def get_recent_videos(youtube, playlist_id, limit=20):
    """Fetches details of the last N uploaded videos."""
    print(f"  > Fetching last {limit} videos...", flush=True)
    playlist_response = youtube.playlistItems().list(
        playlistId=playlist_id,
        part="snippet,contentDetails",
        maxResults=limit
    ).execute()

    video_ids = []
    video_map = {} 

    for item in playlist_response['items']:
        vid_id = item['contentDetails']['videoId']
        video_ids.append(vid_id)
        video_map[vid_id] = {
            "title": item['snippet']['title'],
            "published": item['snippet']['publishedAt'],
            "thumbnail": item['snippet']['thumbnails'].get('medium', {}).get('url')
        }

    if not video_ids: return []

    stats_response = youtube.videos().list(
        id=",".join(video_ids),
        part="statistics,status"
    ).execute()

    final_videos = []
    for item in stats_response['items']:
        vid_id = item['id']
        stats = item['statistics']
        status = item['status']
        video_data = video_map.get(vid_id, {})
        video_data.update({
            "id": vid_id,
            "views": stats.get('viewCount', 0),
            "likes": stats.get('likeCount', 0),
            "comments": stats.get('commentCount', 0),
            "privacy": status.get('privacyStatus', 'unknown'),
            "url": f"https://youtu.be/{vid_id}"
        })
        final_videos.append(video_data)
    return final_videos

def get_analytics_report(analytics_service):
    """Fetches Watch Time."""
    print("  > Fetching Analytics Report (Last 28 Days)...", flush=True)
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=28)

    try:
        response = analytics_service.reports().query(
            ids='channel==MINE',
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics='estimatedMinutesWatched,averageViewDuration,views',
            dimensions='day',
            sort='day'
        ).execute()

        rows = response.get('rows', [])
        total_minutes = 0
        chart_data = [] 
        for row in rows:
            total_minutes += row[1]
            chart_data.append({"date": row[0], "watch_time": row[1], "views": row[3]})

        return {"total_watch_time_hours": round(total_minutes / 60, 1), "chart_data": chart_data}
    except Exception as e:
        print(f"  [Warning] Analytics API error: {e}")
        # RETURN EMPTY STRUCTURE SO DASHBOARD DOESN'T CRASH
        return {
            "error": str(e), 
            "total_watch_time_hours": 0, 
            "chart_data": [] 
        }

def main():
    print("--- Starting YouTube Analytics Sync ---", flush=True)
    
    controller_data = load_json(CONTROLLER_FILE)
    if not controller_data: return

    cache_file = controller_data.get("global_settings", {}).get("analytics_cache_file")
    full_cache = {"last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "channels": {}}

    categories = controller_data.get("categories", {})
    
    # --- LOOP THROUGH EACH CATEGORY ---
    for cat_name, config in categories.items():
        print("\n" + "="*40, flush=True)
        print(f"   PROCESSING CATEGORY:  {cat_name}", flush=True)
        print("="*40, flush=True)
        
        client_secrets = config.get("client_secrets_file")
        token_file = config.get("token_file")

        if not client_secrets or not token_file:
            print("  Skipping: Missing Auth files.", flush=True)
            continue

        # Check if we need to login (if token doesn't exist)
        if not os.path.exists(token_file):
            print(f"\n[ACTION REQUIRED] Please look at your browser.")
            print(f"You are about to log in for the **{cat_name.upper()}** account.")
            input(f"Press [ENTER] to open browser for {cat_name}...")
        
        # Authenticate
        creds = utils.authenticate_youtube(client_secrets, token_file)
        if not creds: continue

        yt_data = utils.get_youtube_service(creds)
        yt_analytics = utils.get_analytics_service(creds)

        if not yt_data or not yt_analytics: continue

        # 1. Channel Stats
        channel_data = get_channel_stats(yt_data)
        if not channel_data: continue

        # Confirm we logged into the right account (Self-Check)
        print(f"  > Connected to Channel: {channel_data['channel_title']}")

        # 2. Recent Videos
        recent_videos = get_recent_videos(yt_data, channel_data['uploads_playlist'])

        # 3. Analytics
        analytics_data = get_analytics_report(yt_analytics)

        full_cache["channels"][cat_name] = {
            "info": channel_data,
            "analytics": analytics_data,
            "videos": recent_videos
        }
        print(f"  [Success] Synced data for {cat_name}.")

    if save_json(full_cache, cache_file):
        print(f"\n[Success] All analytics saved to: {cache_file}", flush=True)

if __name__ == "__main__":
    main()