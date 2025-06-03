# --- Imports ---
import os
import sys
import subprocess
import yt_dlp
import instaloader
import hashlib
import json
import requests
from pathlib import Path
from datetime import datetime
import hashlib
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from fake_useragent import UserAgent
import time
import random
# ========================== Facebook Media Downloader ==========================
def download_facebook_video(url, output_filename="video.mp4"):
    ydl_opts = {
        'outtmpl': output_filename if output_filename.endswith('.mp4') else output_filename + '.mp4',
        'quiet': False,
        'noplaylist': True,
        'format': 'best'
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"[+] Downloading Facebook video from: {url}")
            ydl.download([url])
            print(f"[✔] Video saved as: {ydl_opts['outtmpl']}")
    except Exception as e:
        print(f"[!] Failed to download: {e}")

def download_facebook_image(post_url, download_folder='facebook_images'):
    CHROMEDRIVER_PATH = r"D:\\projects and stuffs\\google project\\chromedriver-win64\\chromedriver.exe"
    os.makedirs(download_folder, exist_ok=True)
    ua = UserAgent()

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument(f"user-agent={ua.random}")
    chrome_options.add_argument(f"window-size={random.randint(1000,1400)},{random.randint(700,900)}")

    try:
        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        print(f"[!] Error initializing ChromeDriver: {e}")
        return

    try:
        print("Opening Facebook post...")
        driver.get(post_url)
        time.sleep(random.uniform(1.0, 3.0))

        img_element = None
        selectors = [
            'img[src*="scontent"]',
            'div[data-visualcompletion="media-vc-image"] img',
            'img.x1ey2m1c.xds687c.x5yr21d.x10l6tqk.x17qophe.x13vifvy.xh8yej3'
        ]

        for selector in selectors:
            try:
                img_element = driver.find_element(By.CSS_SELECTOR, selector)
                if img_element:
                    break
            except:
                continue

        if not img_element:
            print("[!] Could not find image element.")
            return

        img_url = img_element.get_attribute('src')
        if not img_url:
            print("[!] Image URL not found.")
            return

        print(f"[+] Found image URL: {img_url}")
        response = requests.get(img_url, headers={'User-Agent': ua.random})

        if response.status_code == 200:
            filename = f"fb_image_{int(time.time())}.jpg"
            save_path = os.path.join(download_folder, filename)

            if os.path.exists(save_path):
                print(f"[!] Image already exists: {save_path}")
                return save_path

            with open(save_path, 'wb') as f:
                f.write(response.content)

            print(f"[✓] Image saved to: {save_path}")
            return save_path
        else:
            print(f"[!] Failed to download image: HTTP {response.status_code}")
    except Exception as e:
        print(f"[!] Error: {e}")
    finally:
        driver.quit()

# ========================== Facebook Auto Handler ==========================
def handle_facebook_url(url):
    url_lower = url.lower()
    if 'reel' in url_lower:
        print("[*] Detected Facebook Reel (Video)")
        download_facebook_video(url)
    elif 'photo' in url_lower or 'fbid=' in url_lower:
        print("[*] Detected Facebook Photo (Image)")
        download_facebook_image(url)
    elif 'videos' in url_lower or 'watch' in url_lower:
        download_facebook_video(url)
    else:
        print("[!] Facebook URL format not recognized for video/image download.")

# ========================== instagram ==========================

def download_instagram(url):
    SETTINGS = instaloader.Instaloader(
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        post_metadata_txt_pattern="", 
    )

    try:
        # Extract shortcode from URL (always second last segment)
        shortcode = url.split("/")[-2]

        # Detect post type from URL path
        if "/reel/" in url:
            content_type = "video"
        elif "/p/" in url:
            content_type = "image"
        else:
            print("[!] URL does not contain /p/ or /reel/. Cannot detect content type.")
            return

        post = instaloader.Post.from_shortcode(SETTINGS.context, shortcode)

        # Check if post type matches expected content type
        if content_type == "video" and post.is_video:
            os.makedirs("videos", exist_ok=True)
            print("Downloading video...")
            SETTINGS.download_post(post, target="videos")
            print("Download complete :)")
        elif content_type == "image" and not post.is_video:
            os.makedirs("images", exist_ok=True)
            print("Downloading image...")
            SETTINGS.download_post(post, target="images")
            print("Download complete :)")
        else:
            print("[!] Content type in URL does not match actual media type of the post.")
            print(f"URL content type: {content_type}, Post.is_video: {post.is_video}")

    except Exception as e:
        print(f"Error: {e}. Check the link and try again.")

            
# ========================== YouTube Downloader ==========================
def download_youtube_video(url, output_folder='youtube_downloads'):
    os.makedirs(output_folder, exist_ok=True)
    ydl_opts = {
        'outtmpl': os.path.join(output_folder, '%(title)s.%(ext)s'),
        'format': 'best'
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"[+] Downloading YouTube video from: {url}")
            ydl.download([url])
            print("[✓] YouTube video downloaded.")
    except Exception as e:
        print(f"[!] Failed to download YouTube video: {e}")

# ========================== Twitter Downloader ==========================
def download_tweet_media(tweet_url, output_dir="downloads"):
    print(f"📥 Downloading images from: {tweet_url}")
    os.makedirs(output_dir, exist_ok=True)

    # gallery-dl command with filter to download images only
    # --filter "type=image" filters only image media, skipping videos
    cmd = [
        "gallery-dl",
        "--directory", output_dir,
        "--filter", "type=image",
        tweet_url
    ]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        print("✅ Download successful.\n")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("❌ Download failed.")
        print(e.stderr)


# ========================== Main App ==========================
def main():
    while True:
        url = input("\nEnter media URL (or type 'exit' to quit): ").strip()

        if url.lower() == 'exit':
            print("Exiting app. Goodbye!")
            break

        if not url.startswith("http"):
            print("[!] Invalid URL.")
            continue

        url_lower = url.lower()

        if "facebook.com" in url_lower:
            handle_facebook_url(url)
        elif "instagram.com" in url_lower:
            download_instagram(url)
        elif "youtube.com" in url_lower or "youtu.be" in url_lower:
            download_youtube_video(url)
        elif "twitter.com" in url_lower or "x.com" in url_lower:
            download_tweet_media(url)
        else:
            print("[!] Unsupported URL or platform.")

if __name__ == "__main__":
    main()
