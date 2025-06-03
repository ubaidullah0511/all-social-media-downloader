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




# --- YouTube Downloader Function ---
def download_youtube(url, mode="video", base_folder="yt_downloads"):
    os.makedirs(base_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = hashlib.md5(timestamp.encode()).hexdigest()[:8]
    folder_name = f"yt_{session_id}"
    folder_path = os.path.join(base_folder, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    output_template = os.path.join(folder_path, "%(title).50s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "quiet": False,
        "no_warnings": True,
        "noplaylist": True,
    }

    if mode == "audio":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        ydl_opts["format"] = "best"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            if mode == "audio":
                downloaded_file = downloaded_file.rsplit('.', 1)[0] + ".mp3"
            print(f"\n✅ Download complete: {downloaded_file}")

            metadata_path = os.path.join(folder_path, "metadata.json")
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2, ensure_ascii=False)
            print(f"💾 Metadata saved: {metadata_path}")
    except Exception as e:
        print(f"❌ Download failed: {e}")


def download_facebook_image(post_url, download_folder='facebook_images'):
    # Define path to local ChromeDriver
    CHROMEDRIVER_PATH = r"D:\projects and stuffs\google project\chromedriver-win64\chromedriver.exe"

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
        # Use your local chromedriver
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



# --- Facebook Downloader ---
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

# --- Instagram Downloader ---
def download_instagram():
    SETTINGS = instaloader.Instaloader(
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        post_metadata_txt_pattern="", 
    )

    while True:
        link = input("Enter Instagram post URL (or 'e' to exit): ")
        if link.lower() == "e":
            print("Exiting Instagram downloader.")
            break
        try:
            shortcode = link.split("/")[-2]
            post = instaloader.Post.from_shortcode(SETTINGS.context, shortcode)
            user_choice = input("Image or Video? (I/V, 'e' to exit): ").lower()
            if user_choice == "e":
                print("Exiting Instagram downloader.")
                break
            if user_choice in ["v", "video"] and post.is_video:
                os.makedirs("videos", exist_ok=True)
                os.chdir("videos")
                print("Downloading video...")
                SETTINGS.download_post(post, target="your_videos")
                os.chdir("..")
                print("Download complete :)")
            elif user_choice in ["i", "image"] and not post.is_video:
                os.makedirs("images", exist_ok=True)
                os.chdir("images")
                print("Downloading image...")
                SETTINGS.download_post(post, target="your_pictures")
                os.chdir("..")
                print("Download complete :)")
            else:
                print("Invalid content type or input. Try again.")
        except Exception as e:
            print(f"Error: {e}. Check the link and try again.")

# --- Twitter Media Downloader (gallery-dl) ---
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

# --- Twitter Video Downloader (yt-dlp) ---
def download_twitter_video(tweet_url):
    output_name = input("Enter output filename (with extension, e.g., video.mp4): ").strip()

    ydl_opts = {
        'outtmpl': output_name,
        'quiet': False,
        'no_warnings': True,
        'format': 'best',
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Downloading Twitter video from: {tweet_url}")
            ydl.download([tweet_url])
        print("Download completed.")
    except Exception as e:
        print(f"Error: {e}")
        print("No video found or download failed.")

# --- Main App ---
def main():

    while True:
        print("\n--- Media Downloader ---")
        print("1. Download Facebook Video")
        print("2. Download Instagram Post")
        print("3. Download Twitter Image ")
        print("4. Download Twitter Video ")
        print("5. Download YouTube Video/Audio")
        print("6. Download Facebook Image")   
        print("0. Exit")

        choice = input("Select an option: ").strip()
        if choice == "0":
            print("Exiting app. Goodbye!")
            break
        elif choice == "1":
            url = input("Enter Facebook video URL (public): ").strip()
            output = input("Enter output filename (default: video.mp4): ").strip()
            if not output:
                output = "video.mp4"
            download_facebook_video(url, output)
        elif choice == "2":
            download_instagram()
        elif choice == "3":
            url = input("Enter Tweet URL for media download: ").strip()
            download_tweet_media(url)
        elif choice == "4":
            url = input("Enter Tweet URL for video download: ").strip()
            download_twitter_video(url)
        elif choice == "5":
            url = input("Enter YouTube URL: ").strip()
            mode = input("Download mode ('video' or 'audio', default video): ").strip().lower()
            if mode not in ["video", "audio"]:
                mode = "video"
            download_youtube(url, mode)

        elif choice == "6":
            url = input("Enter Facebook post URL (image): ").strip()
            download_facebook_image(url)

if __name__ == "__main__":
    main()
