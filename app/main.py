from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AI Movie Maker", version="0.1.0")

class MovieRequest(BaseModel):
    title: str
    script: str
    aspect_ratio: str = "16:9"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/projects")
def create_project(request: MovieRequest):
    return {
        "title": request.title,
        "aspect_ratio": request.aspect_ratio,
        "status": "created",
        "next_step": "scene_breakdown",
    }
