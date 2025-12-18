from fastapi import FastAPI, HTTPException, Form, UploadFile, File
import shutil
import os
import random
import cloudinary
import cloudinary.uploader
import edge_tts
# MOVIEPY v2.0 IMPORTS
from moviepy import AudioFileClip, VideoFileClip
from deep_translator import GoogleTranslator
import google.generativeai as genai
import sys

app = FastAPI()

# --- 1. CONFIGURATION ---
cloudinary.config( 
  cloud_name = "domigpf5l", 
  api_key = "749381894976826", 
  api_secret = "XZP26wOlIsVfHatfEi4cMw70-54" 
)

# SETUP GEMINI AI
# FIX 1: Use specific model version to prevent "404 Not Found"
GENAI_API_KEY = "AIzaSyCrZeiVNGdhhFXQJchQ1GuJSyCpaUS6z6I"
genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-001') 

# --- HEALTH CHECK (Essential for Render) ---
@app.get("/")
def home():
    return {"status": "Online", "gemini_version": genai.__version__}

# --- 2. THE AI STORY GENERATOR ---
def get_ai_story():
    print("🤖 Asking Gemini to write a story...")
    try:
        prompts = [
            "Write a scary 2-sentence horror story.",
            "Write a funny short story about a coding bug in 50 words.",
            "Write a mind-blowing fact about space in 3 sentences.",
            "Tell me a short mystery story that ends with a twist."
        ]
        chosen_prompt = random.choice(prompts)
        
        # Call Gemini
        response = model.generate_content(chosen_prompt)
        story = response.text
        
        # Clean up
        story = story.replace("*", "").replace("#", "")
        print(f"✅ AI Wrote: {story[:30]}...")
        return story
        
    except Exception as e:
        print(f"❌ Gemini Error: {e}")
        # Fallback story if AI fails
        return "One day, the AI stopped working. The engineer fixed it. The end."

def translate_to_hindi(text):
    try:
        return GoogleTranslator(source='auto', target='hi').translate(text)
    except:
        return text

# --- 3. STARTUP ---
@app.on_event("startup")
async def startup_event():
    if not os.path.exists("assets"): os.makedirs("assets")
    if not os.path.exists("assets/minecraft.mp4"):
        import urllib.request
        # Using a smaller reliable sample video
        urllib.request.urlretrieve("https://res.cloudinary.com/demo/video/upload/v1689625902/samples/cld-sample-video.mp4", "assets/minecraft.mp4")

# --- 4. GENERATE ENDPOINT ---
@app.post("/generate")
async def generate_media(
    story_mode: str = Form(...),        
    story_text: str = Form(None),
    voice: str = Form("hi-IN-SwaraNeural"), 
    background_choice: str = Form(None),
    background_file: UploadFile = File(None),
    output_format: str = Form("video")
):
    print(f"🚀 Processing Mode: {story_mode}")

    try:
        # A. STORY LOGIC
        if story_mode == "auto":
            text = get_ai_story()
            if "hi-IN" in voice:
                text = translate_to_hindi(text)
        else:
            text = story_text or "No text provided."

        # B. AUDIO
        if "en-US" in voice: voice = "en-US-AriaNeural"

        audio_file = f"temp_{random.randint(1000,9999)}.mp3"
        await edge_tts.Communicate(text, voice).save(audio_file)

        if output_format == "audio":
            url = cloudinary.uploader.upload(audio_file, resource_type="video")['secure_url']
            os.remove(audio_file)
            return {"status": "success", "url": url, "type": "audio"}

        # C. VIDEO (Fixed for MoviePy v2.0)
        bg_path = "assets/minecraft.mp4"
        if background_choice == "upload" and background_file:
            bg_path = f"temp_bg_{random.randint(1000,9999)}.mp4"
            with open(bg_path, "wb") as f: shutil.copyfileobj(background_file.file, f)
        
        # FIX 2: Correct MoviePy v2.0 Loading
        # 'target_resolution' is removed in v2. We must load first, then resize.
        video = VideoFileClip(bg_path)
        
        audio = AudioFileClip(audio_file)
        duration = min(audio.duration, 40) # Cap at 40s
        
        # FIX 3: Correct Resizing and Looping for v2.0
        # Resize to 480x854 (vertical)
        video = video.resized(to_size=(480, 854)) 
        
        # Loop if video is shorter than audio
        if video.duration < duration:
            video = video.looped(duration=duration) # v2 uses .looped(), not .loop()
        
        # Trim and combine
        final = video.subclipped(0, duration).with_audio(audio.subclipped(0, duration))
        
        # Crop to 9:16 aspect ratio (Vertical)
        w, h = final.size
        if w/h > 9/16:
            final = final.cropped(x_center=w/2, width=h*(9/16), height=h)
        
        out_name = f"final_{random.randint(1000,9999)}.mp4"
        # Using ultrafast preset for Render free tier
        final.write_videofile(out_name, codec='libx264', audio_codec='aac', fps=15, preset="ultrafast", threads=2)

        print("☁️ Uploading...")
        url = cloudinary.uploader.upload(out_name, resource_type="video")['secure_url']
        
        # Cleanup
        final.close(); audio.close(); video.close()
        os.remove(audio_file); os.remove(out_name)
        if background_choice == "upload": os.remove(bg_path)

        return {"status": "success", "url": url, "type": "video"}

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return {"status": "error", "message": str(e)}
