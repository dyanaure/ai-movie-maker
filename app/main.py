import os
from pathlib import Path
from typing import List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
LTX_BASE = "https://api.ltx.io"

app = FastAPI(title="AI Movie Maker", version="0.4.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class Character(BaseModel):
    name: str
    role: str = ""
    locked: bool = False


class MovieRequest(BaseModel):
    title: str
    script: str
    aspect_ratio: str = "16:9"
    visual_style: str = "Cinematic fantasy"
    characters: List[Character] = []


class GenerateRequest(BaseModel):
    prompt: str
    aspect_ratio: str = "9:16"
    duration: int = 6
    image_uri: str | None = None


def ltx_headers():
    key = os.environ.get("LTX_API_KEY") or os.environ.get("LTXV_API_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="LTX API key is not configured.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.4.0", "ltx_configured": bool(os.environ.get("LTX_API_KEY") or os.environ.get("LTXV_API_KEY"))}


@app.post("/projects")
def create_project(request: MovieRequest):
    locked = sum(1 for character in request.characters if character.locked)
    return {"title": request.title, "aspect_ratio": request.aspect_ratio, "visual_style": request.visual_style, "characters": len(request.characters), "locked_characters": locked, "status": "cast_saved", "next_step": "scene_breakdown"}


@app.post("/generate/video")
async def generate_video(request: GenerateRequest):
    resolution = "720x1280" if request.aspect_ratio == "9:16" else "1280x720"
    endpoint = "image-to-video" if request.image_uri else "text-to-video"
    payload = {"prompt": request.prompt[:5000], "model": "ltx-2-5-fast", "duration": request.duration, "resolution": resolution, "fps": 24, "generate_audio": True}
    if request.image_uri:
        payload["image_uri"] = request.image_uri
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{LTX_BASE}/v2/{endpoint}", headers=ltx_headers(), json=payload)
    if response.status_code not in (200, 202):
        try:
            raw = response.json()
            if isinstance(raw, dict):
                err = raw.get("error", raw)
                if isinstance(err, dict):
                    detail = err.get("message") or err.get("detail") or str(err)
                else:
                    detail = str(err)
            else:
                detail = str(raw)
        except Exception:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=f"LTX {response.status_code}: {detail}")
    data = response.json()
    return {"id": data["id"], "status": "submitted", "mode": endpoint}


@app.get("/generate/video/{job_id}")
async def generation_status(job_id: str, mode: str = "text-to-video"):
    endpoint = "image-to-video" if mode == "image-to-video" else "text-to-video"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{LTX_BASE}/v2/{endpoint}/{job_id}", headers=ltx_headers())
    if response.status_code != 200:
        try: detail = response.json()
        except Exception: detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)
    data = response.json()
    result = data.get("result") or {}
    return {"id": job_id, "status": data.get("status", "unknown"), "video_url": result.get("video_url"), "error": data.get("error")}
