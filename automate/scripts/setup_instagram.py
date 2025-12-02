import instaloader
from instaloader import TwoFactorAuthRequiredException, BadCredentialsException, ConnectionException, LoginException
import getpass
import os
import sys

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def setup_instagram_session():
    print("\n--- Instagram Login Setup (Final) ---")
    
    username = "Assistant._.jarvis"
    # Your password (hardcoded as requested)
    password = "nandemonay@goofad.com"  # Change this if you updated it
    
    print(f"Target Account: {username}")
    print(f"Using Password: {password}")

    L = instaloader.Instaloader()

    try:
        print(f"\nAttempting login...")
        L.login(username, password)
        print("✅ Login successful!")
        
        # Save Session
        session_filename = f"session-{username}"
        session_path = os.path.join(SCRIPT_DIR, session_filename)
        L.save_session_to_file(filename=session_path)
        print(f"\n[Success] Session saved to: {session_path}")

    except TwoFactorAuthRequiredException:
        print("\n⚠️ Two-Factor Authentication (2FA) is required.")
        code = input("Enter the 2FA code sent to your SMS/App: ").strip()
        try:
            L.two_factor_login(code)
            print("✅ 2FA Login successful!")
            session_filename = f"session-{username}"
            session_path = os.path.join(SCRIPT_DIR, session_filename)
            L.save_session_to_file(filename=session_path)
            print(f"\n[Success] Session saved to: {session_path}")
        except Exception as e:
            print(f"❌ 2FA Failed: {e}")

    except BadCredentialsException:
        print("\n❌ PASSWORD REJECTED.")
        print("Instagram says the password is wrong.")

    except LoginException as e:
        error_msg = str(e)
        if "Checkpoint" in error_msg:
            print("\n⚠️  INSTAGRAM SECURITY CHECKPOINT REQUIRED ⚠️")
            print("Instagram has flagged this login. You must verify it manually.")
            
            # Extract the relative URL if present
            start_index = error_msg.find("/auth_platform/")
            if start_index != -1:
                # Find end of URL (usually space or end of string)
                end_index = error_msg.find(" ", start_index)
                if end_index == -1: end_index = len(error_msg)
                
                relative_url = error_msg[start_index:end_index]
                full_url = f"https://instagram.com{relative_url}"
                
                print(f"\n👉 OPEN THIS LINK IN YOUR BROWSER NOW:")
                print(f"{full_url}\n")
                print("1. Click the link above.")
                print("2. Log in and say 'Yes, It Was Me'.")
                print("3. Come back here and RUN THIS SCRIPT AGAIN.")
            else:
                print("Could not parse URL. Please check your Instagram App on your phone.")
        else:
            print(f"\n❌ Login Error: {error_msg}")

    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    setup_instagram_session()