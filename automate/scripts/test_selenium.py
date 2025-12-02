import sys
import os
import time
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR = os.path.join(BASE_DIR, "data", "browser_profiles")

# --- TEST SETTINGS (EDIT THESE TO TEST DIFFERENT ACCOUNTS) ---
TEST_CATEGORY = "Anime"  # Change to Cars, Entertopia, etc.
TEST_VIDEO_NAME = "test_video.mp4" # Make sure this file exists in your Anime download folder
TEST_TITLE = "Selenium Test with Emojis 🚀🔥 Works?" 
TEST_DESC = "This is a test description.\n\nLine 2.\nLine 3."

def random_sleep(min_seconds=2, max_seconds=5):
    time.sleep(random.uniform(min_seconds, max_seconds))

def safe_send_text(driver, element, text):
    """
    FIX FOR BMP ERROR:
    Uses JavaScript to set text if emojis are present, avoiding the crash.
    """
    try:
        # Try standard typing first (looks more human)
        element.send_keys(text)
    except Exception as e:
        if "BMP" in str(e):
            print(f"   ⚠️ BMP Error detected (Emojis). Switching to JS Injection for: '{text[:15]}...'")
            # Clear element first
            element.clear()
            # Inject text via JavaScript
            driver.execute_script("arguments[0].textContent = arguments[1];", element, text)
            # Trigger an 'input' event so YouTube knows text changed
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", element)
        else:
            raise e # Re-raise if it's a different error

def run_test():
    print("--- STARTING SELENIUM DIAGNOSTIC TEST ---")
    
    # 1. Check Paths
    profile_path = os.path.join(PROFILES_DIR, TEST_CATEGORY)
    if not os.path.exists(profile_path):
        print(f"❌ CRITICAL: Profile folder not found at {profile_path}")
        print("   Please run 'setup_profiles.py' first.")
        return

    # Find the video
    # Assuming video is in data/downloaded_videos/Category
    video_path = os.path.join(BASE_DIR, "data", "downloaded_videos", TEST_CATEGORY, TEST_VIDEO_NAME)
    
    # If not found there, check if user provided full path or put it elsewhere? 
    # For this test, let's create a dummy file if it doesn't exist
    if not os.path.exists(video_path):
        print(f"⚠️ Video not found at {video_path}")
        print("   Creating a dummy text file renamed to .mp4 just for testing UI...")
        os.makedirs(os.path.dirname(video_path), exist_ok=True)
        with open(video_path, "w") as f: f.write("DUMMY VIDEO CONTENT")
    
    print(f"✅ Profile: {TEST_CATEGORY}")
    print(f"✅ Video: {video_path}")
    print(f"✅ Title: {TEST_TITLE}")

    # 2. Launch Browser
    print("\n[1/10] Launching Chrome...")
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_path}")
    options.add_argument("--no-first-run")
    options.add_argument("--password-store=basic")
    
    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=None)
        
        # 3. Open Upload Page
        print("[2/10] Navigating to upload page...")
        driver.get("https://youtube.com/upload")
        random_sleep(5, 7)

        # 4. Upload File
        print("[3/10] Uploading file...")
        try:
            file_input = driver.find_element(By.XPATH, "//input[@type='file']")
            file_input.send_keys(os.path.abspath(video_path))
        except Exception as e:
            print(f"❌ Failed to find file input: {e}")
            return

        # 5. Wait for Processing
        print("[4/10] Waiting for UI to load (Wait 60s max)...")
        try:
            # Wait for title box
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(@id, 'textbox')]"))
            )
            print("   > UI Loaded.")
        except Exception as e:
            print("❌ Timed out waiting for YouTube UI. taking screenshot...")
            driver.save_screenshot("debug_timeout.png")
            return

        random_sleep(2, 4)

        # 6. Set Title (With Emoji Fix)
        print("[5/10] Setting Title...")
        textboxes = driver.find_elements(By.ID, "textbox")
        if textboxes:
            title_box = textboxes[0]
            # Clear existing title (Ctrl+A -> Del is safer than .clear() for divs)
            title_box.send_keys(Keys.CONTROL + "a")
            title_box.send_keys(Keys.BACK_SPACE)
            time.sleep(1)
            
            # USE THE SAFE SEND FUNCTION
            safe_send_text(driver, title_box, TEST_TITLE)
        else:
            print("❌ Could not find Title Box.")
            return

        # 7. Set Description
        print("[6/10] Setting Description...")
        if len(textboxes) > 1:
            desc_box = textboxes[1]
            desc_box.click()
            time.sleep(0.5)
            desc_box.clear()
            safe_send_text(driver, desc_box, TEST_DESC)
        
        random_sleep()

        # 8. Set Audience
        print("[7/10] Setting Audience (Not for Kids)...")
        try:
            driver.find_element(By.NAME, "VIDEO_MADE_FOR_KIDS_NOT_MADE_FOR_KIDS").click()
        except:
            # Try finding by text if Name fails
            try:
                driver.find_element(By.XPATH, "//*[contains(text(),'No, it')]").click()
            except:
                print("⚠️ Could not click Audience button. Continuing anyway...")

        # 9. Next Steps
        print("[8/10] Clicking Next -> Next -> Next...")
        for i in range(3):
            try:
                btn = driver.find_element(By.ID, "next-button")
                btn.click()
                print(f"   > Clicked Next ({i+1}/3)")
                random_sleep(2, 3)
            except:
                print("   > 'Next' button not clickable yet, waiting...")
                time.sleep(3)
                driver.find_element(By.ID, "next-button").click()

        # 10. Visibility
        print("[9/10] Setting Visibility (Private)...")
        try:
            driver.find_element(By.NAME, "PRIVATE").click()
        except:
            driver.find_element(By.XPATH, "//*[@name='PRIVATE']").click()
        
        random_sleep()

        # 11. Done
        print("[10/10] Clicking SAVE...")
        driver.find_element(By.ID, "done-button").click()

        print("\n✅ TEST PASSED: Button clicked. Waiting 10s to ensure upload registers...")
        time.sleep(10)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        # Capture the screen state at failure
        driver.save_screenshot("debug_crash.png")
        print("📸 Saved screenshot to 'debug_crash.png'")
        
        import traceback
        traceback.print_exc()

    finally:
        print("\nClosing browser in 5 seconds...")
        time.sleep(5)
        if driver:
            driver.quit()

if __name__ == "__main__":
    run_test()