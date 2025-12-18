import os
import random
import shutil
import requests
import edge_tts
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from moviepy import VideoFileClip, AudioFileClip
from deep_translator import GoogleTranslator
import cloudinary
import cloudinary.uploader

# --- 1. SETUP ---
cloudinary.config( 
  cloud_name = "domigpf5l", 
  api_key = "749381894976826", 
  api_secret = "XZP26wOlIsVfHatfEi4cMw70-54" 
)

app = FastAPI()

# Stock Library (Must exist in 'assets' folder)
STOCK_VIDEOS = {
    "minecraft": "assets/minecraft.mp4",
}

SUBREDDIT = "Glitch_in_the_Matrix" 

# --- 2. HELPERS ---
# --- UPDATED HELPER FUNCTION ---
def get_automated_story():
    print(f"🕵️ Fetching story from r/{SUBREDDIT}...")
    
    # 1. Try fetching from Reddit
    try:
        url = f"https://www.reddit.com/r/{SUBREDDIT}/top.json?limit=10&t=week"
        # We use a very specific User-Agent to try to trick Reddit
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        response = requests.get(url, headers=headers, timeout=5) # 5 second timeout
        
        if response.status_code == 200:
            posts = response.json().get('data', {}).get('children', [])
            valid = [p['data'] for p in posts if not p['data'].get('over_18') and 200 < len(p['data'].get('selftext', '')) < 1500]
            
            if valid:
                post = random.choice(valid)
                print(f"✅ Reddit Success: {post['title'][:30]}...")
                return f"{post['title']}. {post['selftext']}"
        else:
            print(f"⚠️ Reddit Blocked Us (Status: {response.status_code}). Switching to Backup.")

    except Exception as e:
        print(f"⚠️ Reddit Connection Failed: {e}. Switching to Backup.")

    # 2. FALLBACK: The "Backup Story" (Use this if Reddit fails)
    # This guarantees the app NEVER crashes with Error 500
    print("✅ Using Backup Story.")
    return (
        "Let me tell you something that happened to me last night. "
        "I live alone in a small apartment. Around 3 AM, I heard a knock on my window. "
        "I live on the 7th floor. I froze, too scared to move. "
        "The knocking stopped, but then I saw a flashlight beam sweep across my living room floor... from inside the hallway. "
        "I realized the knocking wasn't coming from outside. It was a reflection. someone was standing right behind me."
    )

def translate_to_hindi(text):
    try:
        if len(text) > 1000: text = text[:1000]
        return GoogleTranslator(source='auto', target='hi').translate(text)
    except: return text

# --- HYPER-FAST MODE (Designed for Render Free Tier) ---
@app.post("/generate")
async def generate_media(
    story_mode: str = Form(...),       
    story_text: str = Form(None),
    voice: str = Form("hi-IN-SwaraNeural"),
    background_choice: str = Form(None),
    background_file: UploadFile = File(None),
    output_format: str = Form("video"),
    aspect_ratio: str = Form("9:16")
):
    print(f"🚀 Processing: {output_format} | Mode: {story_mode}")

    try:
        # 1. PREPARE TEXT
        if story_mode == "auto":
            text = get_automated_story()
            if not text: text = "This is a backup story."
            text = translate_to_hindi(text) if "hi-IN" in voice else text
        else:
            text = story_text or "No text provided."

        # 2. GENERATE AUDIO
        audio_file = f"temp_{random.randint(1000,9999)}.mp3"
        await edge_tts.Communicate(text, voice).save(audio_file)

        if output_format == "audio":
            url = cloudinary.uploader.upload(audio_file, resource_type="video")['secure_url']
            os.remove(audio_file)
            return {"status": "success", "url": url, "type": "audio"}

        # 3. VIDEO PROCESSING
        bg_path = "assets/minecraft.mp4"
        if background_choice == "upload" and background_file:
            bg_path = f"temp_bg_{random.randint(1000,9999)}.mp4"
            with open(bg_path, "wb") as f: shutil.copyfileobj(background_file.file, f)
        
        print("🎬 Editing Video (Hyper-Fast Mode)...")
        audio = AudioFileClip(audio_file)
        
        # OPTIMIZATION 1: Load video with reduced target resolution immediately
        # 480p (Height 854) is much faster than 720p or 1080p
        video = VideoFileClip(bg_path, target_resolution=(854, 480))

        # OPTIMIZATION 2: Cap Duration at 45 seconds (Safe Zone)
        final_duration = min(audio.duration, 45) 
        
        if video.duration < final_duration:
            video = video.loop(duration=final_duration)
        
        final = video.subclipped(0, final_duration).with_audio(audio.subclipped(0, final_duration))

        # Crop to 9:16
        w, h = final.size
        if w/h > 9/16:
            final = final.cropped(x_center=w/2, width=h*(9/16), height=h)
        
        out_name = f"final_{random.randint(1000,9999)}.mp4"
        
        # OPTIMIZATION 3: Low FPS and Ultrafast Preset
        final.write_videofile(
            out_name, 
            codec='libx264', 
            audio_codec='aac', 
            fps=15,               # <--- 15 FPS IS VERY FAST TO RENDER
            preset="ultrafast",   # <--- SACRIFICE COMPRESSION FOR SPEED
            threads=2             # <--- USE MULTIPLE CORES
        )

        print("☁️ Uploading...")
        url = cloudinary.uploader.upload(out_name, resource_type="video")['secure_url']
        
        # Cleanup
        final.close(); audio.close(); video.close()
        os.remove(audio_file); os.remove(out_name)
        if background_choice == "upload": os.remove(bg_path)

        return {"status": "success", "url": url, "type": "video"}

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return {"status": "error", "message": str(e)}
