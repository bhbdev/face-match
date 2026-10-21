"""Detect faces in data/historic/, embed them, and store the vectors in Postgres.

    python -m scripts.index_images              # index anything new
    python -m scripts.index_images --reindex    # wipe the index and start over

Safe to re-run: images already scanned are skipped. Face crops used by the UI are
written to data/crops/.
"""

import argparse
import json
from pathlib import Path

from tqdm import tqdm

from app import config, db
from app.faces import FaceEngine, crop_face, encode_jpeg, load_image_path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def read_sidecar(img_path: Path) -> dict:
    sidecar = img_path.with_suffix(".json")
    if sidecar.exists():
        try:
            return json.loads(sidecar.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--min-score", type=float, default=0.6,
                    help="Minimum detector confidence for a face to be indexed (default 0.6)")
    ap.add_argument("--min-face-px", type=int, default=60,
                    help="Skip faces whose short side is smaller than this (default 60)")
    ap.add_argument("--max-faces", type=int, default=3,
                    help="Index at most this many faces per image, largest first (default 3)")
    ap.add_argument("--limit", type=int, help="Only process this many new images (for testing)")
    ap.add_argument("--reindex", action="store_true", help="Clear the index first")
    args = ap.parse_args()

    config.CROPS_DIR.mkdir(parents=True, exist_ok=True)
    db.open_pool()
    try:
        if args.reindex:
            db.clear_index()
            print("Index cleared.")

        done = db.indexed_image_files()
        todo = sorted(
            p for p in config.HISTORIC_DIR.iterdir()
            if p.suffix.lower() in IMAGE_EXTS and p.name not in done
        )
        if args.limit:
            todo = todo[: args.limit]
        if not todo:
            print(f"Nothing new to index in {config.HISTORIC_DIR}.")
            return

        print(f"Loading model, then indexing {len(todo)} images "
              f"(grayscale={config.GRAYSCALE})...")
        engine = FaceEngine()

        total_faces = no_face = unreadable = 0
        for path in tqdm(todo, unit="img"):
            img = load_image_path(path)
            if img is None:
                unreadable += 1
                continue  # not recorded, so a fixed file gets retried next run

            faces = [
                f for f in engine.analyze(img)
                if f.det_score >= args.min_score and min(f.width, f.height) >= args.min_face_px
            ]
            faces.sort(key=lambda f: f.area, reverse=True)
            faces = faces[: args.max_faces]

            meta = read_sidecar(path)
            rows = []
            for idx, face in enumerate(faces):
                crop_name = f"{path.stem}_{idx}.jpg"
                # Crop from the original (color) image; only detection/embedding use grayscale.
                (config.CROPS_DIR / crop_name).write_bytes(
                    encode_jpeg(crop_face(img, face.bbox))
                )
                rows.append(
                    {
                        "image_file": path.name,
                        "face_idx": idx,
                        "crop_file": crop_name,
                        "title": meta.get("title") or path.stem,
                        "year": meta.get("year") or None,
                        "author": meta.get("author") or None,
                        "license": meta.get("license") or None,
                        "source_url": meta.get("source_url") or None,
                        "det_score": face.det_score,
                        "bbox": list(face.bbox),
                        "embedding": face.embedding,
                    }
                )
            db.insert_image_result(path.name, rows)
            total_faces += len(rows)
            no_face += not rows

        print(
            f"\nDone. {len(todo) - unreadable} images scanned, {total_faces} faces indexed, "
            f"{no_face} images had no usable face, {unreadable} unreadable."
        )
        print(db.stats())
    finally:
        db.close_pool()


if __name__ == "__main__":
    main()
