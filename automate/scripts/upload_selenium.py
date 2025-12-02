import sys
import os
import time
import random
import argparse
import datetime
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR = os.path.join(BASE_DIR, "data", "browser_profiles")

def random_sleep(min_seconds=2, max_seconds=5):
    time.sleep(random.uniform(min_seconds, max_seconds))

def safe_send_text(driver, element, text):
    """
    FIX: Uses JavaScript to set text if emojis are present (BMP Error fix).
    """
    try:
        element.send_keys(text)
    except Exception as e:
        if "BMP" in str(e):
            print(f"   ⚠️ BMP Error (Emojis). Using JS Injection.")
            element.clear()
            driver.execute_script("arguments[0].textContent = arguments[1];", element, text)
            driver.execute_script("arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", element)
        else:
            raise e

def upload_video(category, video_path, title, description, tags, privacy="private", is_kids=False, schedule_dt=None):
    profile_path = os.path.join(PROFILES_DIR, category)
    
    if not os.path.exists(profile_path):
        print(f"❌ Error: Profile for '{category}' not found.")
        return False

    print(f"🚀 Starting Selenium Upload for {category}...")
    
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile_path}")
    options.add_argument("--no-first-run")
    options.add_argument("--password-store=basic")

    driver = None
    try:
        driver = uc.Chrome(options=options, version_main=None)
        
        # 1. Upload Page
        print("   Opening YouTube Studio...")
        driver.get("https://youtube.com/upload")
        random_sleep(5, 8)

        # 2. File
        print("   Selecting file...")
        file_input = driver.find_element(By.XPATH, "//input[@type='file']")
        file_input.send_keys(os.path.abspath(video_path))
        
        # INCREASED TIMEOUT: Wait up to 5 minutes for processing to start/finish
        print("   Waiting for upload process (Max 300s)...")
        WebDriverWait(driver, 300).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(@id, 'textbox')]"))
        )
        random_sleep(5, 7)

        # 3. Title (With Emoji Fix)
        print("   Setting Title...")
        textboxes = driver.find_elements(By.ID, "textbox")
        if textboxes:
            title_box = textboxes[0]
            title_box.send_keys(Keys.CONTROL + "a")
            title_box.send_keys(Keys.BACK_SPACE)
            random_sleep(1, 2)
            safe_send_text(driver, title_box, title[:99])
        else:
            # Fallback
            fb = driver.find_element(By.XPATH, "//*[contains(@aria-label, 'Add a title')]")
            fb.clear()
            safe_send_text(driver, fb, title[:99])

        random_sleep()

        # 4. Description
        print("   Setting Description...")
        if len(textboxes) > 1:
            desc_box = textboxes[1]
            desc_box.click()
            desc_box.clear()
            random_sleep(1, 2)
            safe_send_text(driver, desc_box, description[:4900])
        random_sleep()

        # 6. Audience
        print("   Selecting Audience...")
        try:
            if is_kids:
                driver.find_element(By.NAME, "VIDEO_MADE_FOR_KIDS_MADE_FOR_KIDS").click()
            else:
                driver.find_element(By.NAME, "VIDEO_MADE_FOR_KIDS_NOT_MADE_FOR_KIDS").click()
        except:
            try:
                driver.find_element(By.XPATH, "//*[contains(text(),'No, it')]").click()
            except: pass 
        random_sleep()

        # 7. Wizard Navigation
        print("   Navigating Wizard...")
        for i in range(3):
            # Try up to 5 times to click Next
            clicked = False
            for attempt in range(5):
                try:
                    btn = driver.find_element(By.ID, "next-button")
                    # Check if disabled
                    if "disabled" in btn.get_attribute("class") or btn.get_attribute("aria-disabled") == "true":
                        print(f"      [Wait] 'Next' is disabled (Checks running...). Attempt {attempt+1}/5")
                        time.sleep(5)
                        continue
                        
                    btn.click()
                    clicked = True
                    break
                except Exception as e:
                    print(f"      [Retry] Click failed. Waiting...")
                    time.sleep(3)
            
            if not clicked:
                print("❌ Failed to click Next button (Checks took too long).")
                # Do NOT return false immediately, try finding 'Done' anyway
                break 
                
            random_sleep(2, 3)

        # 8. Visibility / Scheduling
        print("   Setting Visibility...")
        
        # If schedule is passed (format: YYYY-MM-DDTHH:MM)
        if schedule_dt:
            print(f"   📅 Scheduling for: {schedule_dt}")
            # Click Schedule Radio
            try:
                driver.find_element(By.ID, "second-container-expand-button").click() # Sometimes needed
            except: pass
            
            try:
                driver.find_element(By.XPATH, "//*[@name='SCHEDULE']").click()
            except:
                print("   ⚠️ Could not click 'Schedule'. Defaulting to Private.")
                driver.find_element(By.NAME, "PRIVATE").click()

            # Note: Setting exact date/time via Selenium is very brittle due to date formats.
            # For now, we click Schedule, but you might need to adjust the date manually if the defaults are wrong.
            # Or trust the API fallback for precise scheduling.
            
        else:
            # Immediate Upload
            if privacy.lower() == "public":
                try: driver.find_element(By.NAME, "PUBLIC").click()
                except: driver.find_element(By.XPATH, "//*[@name='PUBLIC']").click()
            elif privacy.lower() == "unlisted":
                try: driver.find_element(By.NAME, "UNLISTED").click()
                except: driver.find_element(By.XPATH, "//*[@name='UNLISTED']").click()
            else:
                try: driver.find_element(By.NAME, "PRIVATE").click()
                except: driver.find_element(By.XPATH, "//*[@name='PRIVATE']").click()
        
        random_sleep()

        # 9. Save
        print("   Clicking Save/Schedule...")
        driver.find_element(By.ID, "done-button").click()

        # 10. Verify (Wait up to 2 mins for final processing)
        print("   Verifying upload success...")
        WebDriverWait(driver, 120).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'Video published') or contains(text(),'Video saved') or contains(text(),'Video scheduled')]"))
        )
        
        print("✅ Selenium Upload Successful!")
        random_sleep(3, 5)
        return True

    except Exception as e:
        print(f"❌ Selenium Upload Failed: {e}")
        # Capture error
        if driver:
            error_shot = os.path.join(BASE_DIR, "controller", "running_logs", f"error_{category}.png")
            driver.save_screenshot(error_shot)
        
        # CRITICAL: Force close browser so we don't get double uploads
        if driver:
            try:
                driver.quit()
            except: pass
        return False
    finally:
        if driver:
            try:
                driver.quit()
            except: pass

if __name__ == "__main__":
    pass