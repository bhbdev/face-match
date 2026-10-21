from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from . import config, db
from .faces import FaceEngine, crop_face, jpeg_data_url, limit_size, load_image_bytes

# StaticFiles checks that its directory exists when it is constructed.
config.HISTORIC_DIR.mkdir(parents=True, exist_ok=True)
config.CROPS_DIR.mkdir(parents=True, exist_ok=True)

engine: FaceEngine | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global engine
    # First start downloads the model pack (~300 MB), so this can take a minute.
    engine = FaceEngine()
    db.open_pool()
    yield
    db.close_pool()


app = FastAPI(title="face-match", lifespan=lifespan)

app.mount("/images", StaticFiles(directory=config.HISTORIC_DIR), name="images")
app.mount("/crops", StaticFiles(directory=config.CROPS_DIR), name="crops")


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": engine is not None}


@app.get("/stats")
def stats():
    return db.stats()


# A plain `def` (not async) so FastAPI runs it in a worker thread; the model call is CPU-bound.
@app.post("/search")
def search(
    file: UploadFile = File(...),
    top_k: int = Form(12),
    grayscale: bool = Form(True),
):
    """Find historic faces that resemble the largest face in the uploaded photo.

    The upload is processed in memory only: it is never written to disk or stored.
    """
    assert engine is not None

    data = file.file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Image is larger than {config.MAX_UPLOAD_BYTES // 1024 // 1024} MB.")

    img = load_image_bytes(data)
    if img is None:
        raise HTTPException(400, "That file doesn't look like an image.")
    img = limit_size(img)

    faces = engine.analyze(img, grayscale=grayscale)
    if not faces:
        raise HTTPException(422, "No face found. Try a clearer, front-facing photo.")
    face = max(faces, key=lambda f: f.area)

    top_k = max(1, min(top_k, 48))
    # Over-fetch, then keep the best face per source image so one photo can't fill the page.
    rows = db.search(face.embedding, top_k * 3)
    seen: set[str] = set()
    matches = []
    for row in rows:
        if row["image_file"] in seen:
            continue
        seen.add(row["image_file"])
        matches.append(
            {
                "id": row["id"],
                "similarity": round(float(row["similarity"]), 4),
                "title": row["title"],
                "year": row["year"],
                "author": row["author"],
                "license": row["license"],
                "source_url": row["source_url"],
                "image_url": f"/images/{row['image_file']}",
                "crop_url": f"/crops/{row['crop_file']}",
            }
        )
        if len(matches) >= top_k:
            break

    return {
        "faces_in_photo": len(faces),
        "query_face": jpeg_data_url(crop_face(img, face.bbox)),
        "matches": matches,
    }
