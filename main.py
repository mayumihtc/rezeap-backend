from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import google.generativeai as genai
import os
import base64
import tempfile
import json
from PIL import Image

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

@app.get("/")
def root():
    return {"status": "Rezeap backend funcionando"}

@app.post("/extraer-receta")
async def extraer_receta(req: VideoRequest):
    try:
        # 1. Descargar info y descripción del video
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
        }
        
        info = {}
        descripcion = ""
        titulo_video = ""
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            descripcion = info.get('description', '')
            titulo_video = info.get('title', '')

        # 2. Descargar thumbnail del video
        thumbnail_url = info.get('thumbnail', '')
        thumbnail_b64 = ""
        
        if thumbnail_url:
            import requests
            resp = requests.get(thumbnail_url, timeout=10)
            if resp.status_code == 200:
                thumbnail_b64 = base64.b64encode(resp.content).decode('utf-8')

        # 3. Mandar a Gemini con título, descripción e imagen
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"""Eres un experto en extraer recetas de cocina de videos de redes sociales.

Título del video: {titulo_video}
Descripción del video: {descripcion}

Analiza esta información y extrae la receta exacta del video. Si la descripción tiene ingredientes y pasos, úsalos exactamente. Si no, infiere la receta basándote en el título.

Responde SOLO con un JSON válido sin backticks:
{{"titulo":"nombre exacto de la receta","tiempo":"tiempo de preparación","porciones":"número de porciones","dificultad":"Fácil/Media/Difícil","descripcion":"descripción corta","ingredientes":["ingrediente 1 con cantidad exacta","ingrediente 2"],"pasos":["paso 1 detallado","paso 2"],"tags":["tag1","tag2"]}}"""

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