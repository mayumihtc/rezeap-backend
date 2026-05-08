from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
import os
import json
import requests
import re

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

        # YouTube
        video_id = get_youtube_id(req.url)
        if video_id:
            yt_api_key = os.environ.get("YOUTUBE_API_KEY")
            if yt_api_key:
                yt_resp = requests.get(
                    f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&part=snippet&key={yt_api_key}"
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
                            import base64
                            thumbnail_b64 = base64.b64encode(thumb_resp.content).decode('utf-8')

        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = f"""Eres un experto en extraer recetas de cocina de videos de redes sociales.

Título del video: {titulo_video if titulo_video else 'No disponible'}
Descripción del video: {descripcion if descripcion else 'No disponible'}
URL: {req.url}

Extrae la receta exacta del video. Si la descripción tiene ingredientes y pasos úsalos exactamente. Si no, infiere basándote en el título.

Responde SOLO con JSON válido sin backticks:
{{"titulo":"nombre exacto","tiempo":"tiempo","porciones":"porciones","dificultad":"Fácil/Media/Difícil","descripcion":"descripción corta","ingredientes":["ingrediente 1","ingrediente 2"],"pasos":["paso 1","paso 2"],"tags":["tag1","tag2"]}}"""

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

        return {"receta": receta, "titulo_video": titulo_video}

    except Exception as e:
        return {"error": str(e)}, 500