import sys
import os
import time
import undetected_chromedriver as uc

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR = os.path.join(BASE_DIR, "data", "browser_profiles")

def setup_profile(profile_name):
    profile_path = os.path.join(PROFILES_DIR, profile_name)
    os.makedirs(profile_path, exist_ok=True)

    print(f"\n--- Launching Stealth Profile: {profile_name} ---")
    print("1. A Chrome window will open.")
    print("2. Google should now allow you to log in.")
    print("3. Log in -> Switch to correct Channel.")
    print("4. Close the browser manually when done.")
    
    # Configure Undetected Chrome
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_path}")
    
    # These flags help bypass detection
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")

    try:
        # Initialize the stealth driver
        # version_main=None allows it to auto-detect your Chrome version
        driver = uc.Chrome(options=options, version_main=None)
        
        driver.get("https://www.youtube.com")
        
        print(f"Browser open for '{profile_name}'. Close it to save state...")
        
        # Keep script alive until browser is closed
        while True:
            try:
                _ = driver.window_handles
                time.sleep(1)
            except:
                break
            
        print(f"✅ Profile '{profile_name}' saved successfully.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Tip: Make sure ALL other Chrome windows are closed before running this.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python setup_profiles.py <CategoryName>")
    else:
        setup_profile(sys.argv[1])