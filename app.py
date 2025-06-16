import os
import tempfile
import yt_dlp
import instaloader
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from fake_useragent import UserAgent
import time
import random
from flask import Flask, render_template, request, jsonify, send_file
from urllib.parse import urlparse
import threading
import subprocess
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

# Configure temporary directory
TEMP_DIR = tempfile.mkdtemp()

# --- YouTube Downloader ---
def download_youtube(url, mode="video"):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
    }

    if mode == "audio":
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        ydl_opts['format'] = 'best'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            if mode == "audio":
                downloaded_file = downloaded_file.rsplit('.', 1)[0] + ".mp3"
            return True, downloaded_file
    except Exception as e:
        return False, str(e)

# --- Facebook Downloader ---
def download_facebook(url, content_type="video"):
    if content_type == "image":
        ua = UserAgent()
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"user-agent={ua.random}")

        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            time.sleep(3)

            # Try to find image element
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
                return False, "Could not find image element"

            img_url = img_element.get_attribute('src')
            if not img_url:
                return False, "Image URL not found"

            response = requests.get(img_url, headers={'User-Agent': ua.random})
            if response.status_code == 200:
                filename = f"fb_image_{int(time.time())}.jpg"
                filepath = os.path.join(TEMP_DIR, filename)
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                return True, filepath
            return False, f"Failed to download image: HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)
        finally:
            driver.quit()
    else:  # video
        try:
            filename = f"fb_video_{int(time.time())}.mp4"
            filepath = os.path.join(TEMP_DIR, filename)
            ydl_opts = {
                'outtmpl': filepath,
                'quiet': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return True, filepath
        except Exception as e:
            return False, str(e)

# --- Instagram Downloader ---
def download_instagram(url, content_type="image"):
    try:
        L = instaloader.Instaloader(
            download_pictures=(content_type == "image"),
            download_videos=(content_type == "video"),
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            filename_pattern=os.path.join(TEMP_DIR, "{date_utc:%Y-%m-%d}_{profile}_{mediaid}"),
        )

        shortcode = url.split("/")[-2]
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        if (content_type == "video" and not post.is_video) or (content_type == "image" and post.is_video):
            return False, "Content type mismatch"

        L.download_post(post, target="temp_download")
        
        # Find the downloaded file
        for file in os.listdir(TEMP_DIR):
            if file.startswith(f"{post.date_utc:%Y-%m-%d}_{post.owner_username}_{post.mediaid}"):
                if (content_type == "video" and file.endswith(('.mp4', '.mkv'))) or \
                   (content_type == "image" and file.endswith(('.jpg', '.jpeg', '.png'))):
                    return True, os.path.join(TEMP_DIR, file)
        
        return False, "File not found after download"
    except Exception as e:
        return False, str(e)

# --- Twitter Downloader ---

def download_twitter(url, content_type="video"):
    try:
        # Method 1: Try gallery-dl first (most reliable)
        result = _download_with_gallery_dl(url, content_type)
        if result[0]:
            return result

        # Method 2: Fallback to API method if gallery-dl fails
        result = _download_with_twitter_api(url, content_type)
        if result[0]:
            return result

        # Method 3: Final fallback to browser automation
        return _download_with_selenium(url, content_type)

    except Exception as e:
        return False, f"Error: {str(e)}"

def _download_with_gallery_dl(url, content_type):
    """Method 1: Using gallery-dl"""
    try:
        temp_download_dir = os.path.join(TEMP_DIR, f"twitter_{int(time.time())}")
        os.makedirs(temp_download_dir, exist_ok=True)

        cmd = [
            "gallery-dl",
            "--directory", temp_download_dir,
            "--write-metadata",
            url
        ]

        if content_type == "video":
            cmd.extend(["--filter", "type=video"])
        else:
            cmd.extend(["--filter", "type=image"])

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            return False, f"gallery-dl failed: {result.stderr}"

        # Find downloaded file
        for root, _, files in os.walk(temp_download_dir):
            for file in files:
                if (content_type == "image" and file.lower().endswith(('.jpg', '.jpeg', '.png'))) or \
                   (content_type == "video" and file.lower().endswith(('.mp4', '.mkv'))):
                    return True, os.path.join(root, file)

        return False, "No media found after download"

    except Exception as e:
        return False, str(e)

def _download_with_twitter_api(url, content_type):
    """Method 2: Using Twitter API"""
    try:
        # Extract tweet ID
        tweet_id = re.search(r'(?:twitter\.com|x\.com)\/\w+\/status\/(\d+)', url)
        if not tweet_id:
            return False, "Invalid Twitter URL"
        tweet_id = tweet_id.group(1)

        # Use unofficial API
        api_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}"
        response = requests.get(api_url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://twitter.com/'
        }, timeout=10)

        if response.status_code != 200:
            return False, f"API request failed (HTTP {response.status_code})"

        data = response.json()
        media_url = None

        if content_type == "image" and ('photos' in data or 'media' in data):
            media = data.get('photos', data.get('media', []))
            if media:
                media_url = media[-1]['url'] + "?format=jpg&name=orig"
        elif content_type == "video" and ('video' in data or 'media' in data):
            variants = data.get('video', data.get('media', {})).get('variants', [])
            if variants:
                media_url = max(
                    [v for v in variants if v.get('content_type', '').startswith('video/')],
                    key=lambda x: x.get('bitrate', 0)
                )['url']

        if not media_url:
            return False, "No media URL found"

        # Download the media
        response = requests.get(media_url, stream=True, timeout=30)
        if response.status_code != 200:
            return False, f"Media download failed (HTTP {response.status_code})"

        ext = 'mp4' if content_type == "video" else 'jpg'
        filename = f"twitter_{content_type}_{tweet_id}.{ext}"
        filepath = os.path.join(TEMP_DIR, filename)

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return True, filepath

    except Exception as e:
        return False, str(e)

def _download_with_selenium(url, content_type):
    """Method 3: Using browser automation (fallback)"""
    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        driver = webdriver.Chrome(options=options)
        
        driver.get(url)
        time.sleep(5)  # Wait for page to load

        if content_type == "image":
            # Try to find image element
            img = driver.find_element(By.CSS_SELECTOR, 'img[src*="media"]')
            media_url = img.get_attribute('src')
        else:
            # Try to find video element
            video = driver.find_element(By.CSS_SELECTOR, 'video')
            media_url = video.get_attribute('src')

        if not media_url:
            return False, "Could not find media element"

        # Download the media
        response = requests.get(media_url, stream=True)
        if response.status_code != 200:
            return False, f"Media download failed (HTTP {response.status_code})"

        ext = 'mp4' if content_type == "video" else 'jpg'
        filename = f"twitter_selenium_{content_type}_{int(time.time())}.{ext}"
        filepath = os.path.join(TEMP_DIR, filename)

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return True, filepath

    except Exception as e:
        return False, str(e)
    finally:
        try:
            driver.quit()
        except:
            pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url')
    platform = data.get('platform')
    content_type = data.get('content_type', 'video')
    
    if not url:
        return jsonify({'success': False, 'message': 'URL is required'})

    try:
        if platform == 'youtube':
            mode = 'audio' if content_type == 'audio' else 'video'
            success, result = download_youtube(url, mode)
        elif platform == 'facebook':
            success, result = download_facebook(url, content_type)
        elif platform == 'instagram':
            success, result = download_instagram(url, content_type)
        elif platform == 'twitter':
            success, result = download_twitter(url, content_type)  # Updated call
        else:
            return jsonify({'success': False, 'message': 'Unsupported platform'})

        if success:
            if os.path.exists(result):
                filename = os.path.basename(result)
                return send_file(
                    result,
                    as_attachment=True,
                    download_name=filename
                )
            return jsonify({'success': True, 'message': result})
        return jsonify({'success': False, 'message': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

        if success:
            if os.path.exists(result):
                # Determine filename
                filename = os.path.basename(result)
                if platform == 'youtube' and content_type == 'audio':
                    filename = filename.rsplit('.', 1)[0] + '.mp3'
                
                return send_file(
                    result,
                    as_attachment=True,
                    download_name=filename
                )
            return jsonify({'success': True, 'message': result})
        return jsonify({'success': False, 'message': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == "__main__":
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)