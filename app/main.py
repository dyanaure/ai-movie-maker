import os
import base64
import re
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

app = FastAPI(title="AI Movie Maker", version="0.8.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


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


class KeyframeRequest(BaseModel):
    prompt: str
    aspect_ratio: str = "9:16"
    images: List[str] = []


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
    return {"status": "ok", "version": "0.8.0", "ltx_configured": bool(os.environ.get("LTX_API_KEY") or os.environ.get("LTXV_API_KEY"))}


@app.post("/projects")
def create_project(request: MovieRequest):
    locked = sum(1 for character in request.characters if character.locked)
    return {"title": request.title, "aspect_ratio": request.aspect_ratio, "visual_style": request.visual_style, "characters": len(request.characters), "locked_characters": locked, "status": "cast_saved", "next_step": "scene_breakdown"}


async def upload_data_image(client: httpx.AsyncClient, data_uri: str) -> str:
    match = re.match(r"^data:(image/(?:jpeg|png|webp));base64,(.+)$", data_uri, re.S)
    if not match:
        raise HTTPException(status_code=400, detail="Reference image must be JPEG, PNG, or WEBP.")
    mime, encoded = match.groups()
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Reference image data is invalid.")
    if len(image_bytes) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Reference image is larger than LTX's 15 MB image limit.")
    signed = await client.post(f"{LTX_BASE}/v1/upload", headers={"Authorization": ltx_headers()["Authorization"]})
    if signed.status_code != 200:
        try:
            detail = signed.json()
        except Exception:
            detail = signed.text
        raise HTTPException(status_code=signed.status_code, detail={"stage":"1_upload_setup","message":f"LTX upload setup failed: {detail}"})
    info = signed.json()
    upload_headers = dict(info.get("required_headers") or {})
    upload_headers["Content-Type"] = mime
    uploaded = await client.put(info["upload_url"], content=image_bytes, headers=upload_headers)
    if uploaded.status_code not in (200, 201, 204):
        raise HTTPException(status_code=502, detail={"stage":"2_media_upload","message":f"LTX media upload failed ({uploaded.status_code}): {uploaded.text[:500]}"})
    return info["storage_uri"]


@app.post("/generate/keyframe")
async def generate_keyframe(request: KeyframeRequest):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured on Render.")
    if not request.images:
        raise HTTPException(status_code=400, detail="At least one locked character reference image is required.")

    files = []
    for idx, data_uri in enumerate(request.images[:4]):
        match = re.match(r"^data:(image/(?:jpeg|png|webp));base64,(.+)$", data_uri, re.S)
        if not match:
            raise HTTPException(status_code=400, detail=f"Character reference {idx + 1} must be JPEG, PNG, or WEBP.")
        mime, encoded = match.groups()
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Character reference {idx + 1} is invalid.")
        ext = "jpg" if mime == "image/jpeg" else mime.split("/")[-1]
        files.append(("image[]", (f"reference_{idx + 1}.{ext}", image_bytes, mime)))

    size = "864x1536" if request.aspect_ratio == "9:16" else "1536x864"
    prompt = (
        "CREATE A COMPLETELY NEW CINEMATIC SCENE. The supplied image(s) are IDENTITY REFERENCES ONLY, not a starting frame. "
        "Keep only each character's facial identity, age, hair identity, skin tone, and recognizable facial features. "
        "REPLACE the original pose, body position, clothing, camera angle, crop, background, lighting, props, and environment. "
        "Remove and do not reproduce any text, subtitles, captions, logos, borders, or UI from the reference image. "
        "The final image must look like a newly photographed frame from the requested scene, not an edited copy of the reference.\n\n"
        + request.prompt[:3500]
        + "\nNo text. No subtitles. No watermark. No UI. Photorealistic cinematic still."
    )
    data = {
        "model": "gpt-image-2",
        "prompt": prompt,
        "size": size,
        "quality": "medium",
        "output_format": "jpeg",
        "output_compression": "85",
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post("https://api.openai.com/v1/images/edits", headers=headers, data=data, files=files)
    if response.status_code != 200:
        try:
            raw = response.json()
            detail = raw.get("error", {}).get("message") or str(raw)
        except Exception:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=f"Keyframe generation failed: {detail}")
    raw = response.json()
    image_b64 = raw.get("data", [{}])[0].get("b64_json")
    if not image_b64:
        raise HTTPException(status_code=502, detail="Keyframe service returned no image.")
    return {"image_uri": f"data:image/jpeg;base64,{image_b64}", "provider": "gpt-image-2"}


@app.post("/generate/video")
async def generate_video(request: GenerateRequest):
    resolution = "720x1280" if request.aspect_ratio == "9:16" else "1280x720"
    endpoint = "image-to-video" if request.image_uri else "text-to-video"
    payload = {"prompt": request.prompt[:5000], "model": "ltx-2-5-fast", "duration": request.duration, "resolution": resolution, "fps": 24, "generate_audio": False}
    async with httpx.AsyncClient(timeout=60) as client:
        if request.image_uri:
            image_uri = request.image_uri
            if image_uri.startswith("data:"):
                image_uri = await upload_data_image(client, image_uri)
            payload["image_uri"] = image_uri
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
        raise HTTPException(status_code=response.status_code, detail={"stage":"3_video_submit","message":f"LTX {response.status_code}: {detail}"})
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
