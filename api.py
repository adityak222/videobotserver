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

# --- 3. API ENDPOINT ---
@app.post("/generate")
async def generate_media(
    story_mode: str = Form(...),       # "custom" or "auto"
    story_text: str = Form(None),
    voice: str = Form("hi-IN-SwaraNeural"),
    background_choice: str = Form(None), # "upload" or "minecraft"
    background_file: UploadFile = File(None),
    output_format: str = Form("video"), # "video" or "audio"
    aspect_ratio: str = Form("9:16")
):
    print(f"🚀 Processing: {output_format} | Mode: {story_mode}")

    # A. PREPARE TEXT
    if story_mode == "auto":
        text = get_automated_story()
        if not text: raise HTTPException(500, "No story found.")
        text = translate_to_hindi(text) if "hi-IN" in voice else text
    else:
        if not story_text: raise HTTPException(400, "No text provided.")
        text = story_text

    # B. GENERATE AUDIO
    audio_file = f"temp_{random.randint(1000,9999)}.mp3"
    await edge_tts.Communicate(text, voice).save(audio_file)

    # C. IF AUDIO ONLY MODE
    if output_format == "audio":
        url = cloudinary.uploader.upload(audio_file, resource_type="video")['secure_url']
        os.remove(audio_file)
        return {"status": "success", "url": url, "type": "audio"}

    # D. IF VIDEO MODE
    bg_path = ""
    is_temp = False

    if background_choice == "upload":
        if not background_file: raise HTTPException(400, "No file uploaded.")
        bg_path = f"temp_bg_{random.randint(1000,9999)}.mp4"
        with open(bg_path, "wb") as f: shutil.copyfileobj(background_file.file, f)
        is_temp = True
    else:
        bg_path = STOCK_VIDEOS.get(background_choice, "assets/minecraft.mp4")

    # E. EDIT VIDEO
    try:
        audio = AudioFileClip(audio_file)
        video = VideoFileClip(bg_path)

        # Loop or Cut
        if video.duration < audio.duration:
             # Simple loop logic for MVP
             video = video.loop(duration=audio.duration)
        
        # Random Start
        max_start = max(0, video.duration - audio.duration)
        start = random.uniform(0, max_start)
        
        final = video.subclipped(start, start + audio.duration).with_audio(audio)

        # Crop (9:16)
        w, h = final.size
        if aspect_ratio == "9:16" and w/h > 9/16:
            final = final.cropped(x_center=w/2, width=h*(9/16), height=h)
        
        # Resize & Save
        final = final.resized(height=1920)
        out_name = f"final_{random.randint(1000,9999)}.mp4"
        final.write_videofile(out_name, codec='libx264', audio_codec='aac', fps=24)

        # Upload
        url = cloudinary.uploader.upload(out_name, resource_type="video")['secure_url']
        
        # Cleanup
        audio.close(); video.close(); final.close()
        os.remove(audio_file); os.remove(out_name)
        if is_temp: os.remove(bg_path)

        return {"status": "success", "url": url, "type": "video"}

    except Exception as e:
        if os.path.exists(audio_file): os.remove(audio_file)
        raise HTTPException(500, str(e))
