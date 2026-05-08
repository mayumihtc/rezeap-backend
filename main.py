from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
import os
import json
import requests
import re
import base64

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
        thumbnail_b64 = ""
        plataforma = "desconocida"

        # YouTube
        video_id = get_youtube_id(req.url) if 'tiktok.com' not in req.url else None
        if video_id:
            plataforma = "YouTube"
            yt_api_key = os.environ.get("YOUTUBE_API_KEY")
            if yt_api_key:
                yt_resp = requests.get(
                    f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&part=snippet&key={yt_api_key}",
                    timeout=10
                )
                yt_data = yt_resp.json()
                if yt_data.get("items"):
                    snippet = yt_data["items"][0]["snippet"]
                    titulo_video = snippet.get("title", "")
                    descripcion = snippet.get("description", "")
                    thumbnail_url = snippet.get("thumbnails", {}).get("high", {}).get("url", "")
                    if thumbnail_url:
                        thumb_resp = requests.get(thumbnail_url, timeout=10)
                        if thumb_resp.status_code == 200:
                            thumbnail_b64 = base64.b64encode(thumb_resp.content).decode('utf-8')

        # TikTok
        elif 'tiktok.com' in req.url:
            plataforma = "TikTok"
            oembed_resp = requests.get(
                f"https://www.tiktok.com/oembed?url={req.url}",
                timeout=10
            )
            if oembed_resp.status_code == 200:
                oembed_data = oembed_resp.json()
                titulo_video = oembed_data.get("title", "")
                descripcion = titulo_video
                thumbnail_url = oembed_data.get("thumbnail_url", "")
                if thumbnail_url:
                    thumb_resp = requests.get(thumbnail_url, timeout=10)
                    if thumb_resp.status_code == 200:
                        thumbnail_b64 = base64.b64encode(thumb_resp.content).decode('utf-8')

        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = f"""Eres un experto en extraer recetas de cocina de videos de redes sociales.

Plataforma: {plataforma}
Título del video: {titulo_video if titulo_video else 'No disponible'}
Descripción del video: {descripcion if descripcion else 'No disponible'}
URL: {req.url}

INSTRUCCIONES:
- Si la descripción tiene ingredientes, úsalos EXACTAMENTE como aparecen.
- Si la descripción tiene pasos, úsalos EXACTAMENTE.
- Si NO hay pasos en la descripción, GENERA pasos detallados y realistas basándote en los ingredientes y el título del video.
- Siempre debe haber al menos 4 pasos de preparación.
- El tiempo y porciones SIEMPRE deben tener un valor estimado, nunca null.

Responde SOLO con JSON válido sin backticks:
{{"titulo":"nombre exacto de la receta","tiempo":"tiempo estimado en minutos","porciones":"número de porciones","dificultad":"Fácil/Media/Difícil","descripcion":"descripción corta apetitosa","ingredientes":["ingrediente 1 exacto","ingrediente 2"],"pasos":["paso 1 detallado","paso 2","paso 3","paso 4"],"tags":["tag1","tag2"]}}"""

        parts = [prompt]

        if thumbnail_b64:
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": thumbnail_b64
                }
            })

        response = model.generate_content(parts)
        text = response.text.strip()
        clean = text.replace('```json', '').replace('```', '').strip()
        receta = json.loads(clean)

        return {"receta": receta, "titulo_video": titulo_video, "plataforma": plataforma}

    except Exception as e:
        return {"error": str(e)}, 500