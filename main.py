from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
import os
import json
import requests
import re
import base64
import yt_dlp
import shutil

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

class VideoRequest(BaseModel):
    url: str

def get_youtube_id(url):
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

@app.get("/")
def root():
    return {"status": "Rezeap backend funcionando"}

@app.post("/extraer-receta")
async def extraer_receta(req: VideoRequest):
    try:
        titulo_video = ""
        descripcion = ""
        frames_b64 = []

        cookies_path = "/etc/secrets/cookies.txt"
        temp_cookies = "/tmp/cookies.txt"

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }

        if os.path.exists(cookies_path):
            shutil.copy2(cookies_path, temp_cookies)
            ydl_opts['cookiefile'] = temp_cookies

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            titulo_video = info.get('title', '')
            descripcion = info.get('description', '')
            thumbnail_url = info.get('thumbnail', '')

        if thumbnail_url:
            thumb_resp = requests.get(thumbnail_url, timeout=10)
            if thumb_resp.status_code == 200:
                frames_b64.append(base64.b64encode(thumb_resp.content).decode('utf-8'))

        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = f"""Eres un experto en extraer recetas de cocina de videos de redes sociales.

Título del video: {titulo_video if titulo_video else 'No disponible'}
Descripción del video: {descripcion if descripcion else 'No disponible'}

IMPORTANTE: Si la descripción tiene ingredientes y pasos, úsalos EXACTAMENTE como aparecen. No inventes ni cambies nada.

Responde SOLO con JSON válido sin backticks:
{{"titulo":"nombre exacto","tiempo":"tiempo","porciones":"porciones","dificultad":"Fácil/Media/Difícil","descripcion":"descripción corta","ingredientes":["ingrediente 1 exacto","ingrediente 2"],"pasos":["paso 1","paso 2"],"tags":["tag1","tag2"]}}"""

        parts = [prompt]

        for frame in frames_b64:
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": frame
                }
            })

        response = model.generate_content(parts)
        text = response.text.strip()
        clean = text.replace('```json', '').replace('```', '').strip()
        receta = json.loads(clean)

        return {"receta": receta, "titulo_video": titulo_video}

    except Exception as e:
        return {"error": str(e)}, 500