from pathlib import Path
from typing import List

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="AI Movie Maker", version="0.2.0")
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


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0"}


@app.post("/projects")
def create_project(request: MovieRequest):
    locked = sum(1 for character in request.characters if character.locked)
    return {
        "title": request.title,
        "aspect_ratio": request.aspect_ratio,
        "visual_style": request.visual_style,
        "characters": len(request.characters),
        "locked_characters": locked,
        "status": "cast_saved",
        "next_step": "scene_breakdown",
        "message": f"Cast saved. {locked} character(s) locked. Scene builder is next.",
    }
