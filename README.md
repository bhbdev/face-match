# face-match

Upload a photo of a face and find the closest lookalikes in a collection of old photographs.

- **Face model:** InsightFace `buffalo_l` (SCRFD detector + ArcFace embeddings, 512 numbers per face), running on CPU
- **Search:** Postgres with pgvector, HNSW index, cosine similarity
- **API:** FastAPI (`api/`)
- **Frontend:** SvelteKit (`web/`)
- **Photos:** public-domain portraits from Wikimedia Commons, via the downloader in `api/scripts/`

## Quick start

You need Docker (with Compose) and `make`. No GPU.

```bash
cp .env.example .env     # then set COMMONS_CONTACT to your email or a URL
make up                  # builds and starts db, api and web
make logs                # first start downloads the ~300 MB model; wait for "Application startup complete"

make download            # ~300 public-domain daguerreotype portraits from Commons
make index               # detect + embed every face (a few minutes on CPU)
```

Then open <http://localhost:3000>, drop in a photo, and slide the divider to compare.

### Getting more photos

```bash
make find Q="portrait photographs"                       # search Commons for category names
make download CATEGORY="Category:Cartes de visite" LIMIT=1000
```

`scripts.download_commons` also takes `--depth N` to follow subcategories (use `docker compose run --rm api python -m scripts.download_commons --help`). It keeps only files whose Commons license says public domain or CC0, and writes a `.json` file next to each image with the title, date, creator, license and page URL, which the UI shows. Run `make index` again after each download; it only processes new images.

To use your own photos, put JPG/PNG files in `data/historic/` and run `make index`. Add a `<same-name>.json` file with `title`, `year`, `author`, `license` and `source_url` if you want them displayed.

## Commands

| Command | What it does |
| --- | --- |
| `make up` / `make down` | Start or stop the stack (data is kept) |
| `make logs` | Follow the API logs |
| `make find Q="..."` | Search Commons for category names |
| `make download` | Download photos (`CATEGORY=...`, `LIMIT=...`) |
| `make index` / `make reindex` | Embed new photos / wipe and redo all |
| `make stats` | Count indexed faces |
| `make psql` | SQL shell into the database |
| `make web-dev` | SvelteKit dev server on <http://localhost:5173> against the Docker API (Node 20+) |
| `make reset-db` | Delete the database volume (re-run `make index` after) |

For frontend work: `docker compose up -d db api`, then `make web-dev`.

## How it works

1. `index_images.py` loads each photo, converts it to grayscale, detects faces, and stores each face's 512-number ArcFace embedding in the `faces` table. It also saves a square face crop to `data/crops/`.
2. `POST /search` does the same for the uploaded photo (largest face only, in memory, never saved) and asks pgvector for the nearest embeddings. Only the best face per source photo is returned.
3. The web app proxies `/api/*` to the FastAPI service, so the browser only talks to one origin.

## Tuning

Set these in the `api` service environment in `docker-compose.yml`:

| Variable | Default | Effect |
| --- | --- | --- |
| `GRAYSCALE` | `1` | Convert to grayscale before detection and embedding. If you change it, run `make reindex`. |
| `DET_THRESH` | `0.4` | Detector confidence. Lower finds more faces in blurry scans, and more false ones. |
| `DET_SIZE` | `640` | Detector input size. Larger can find small faces, slower. |

The indexer's `--min-score`, `--min-face-px` and `--max-faces` flags control which faces get stored.

Ideas that should improve matches: restore faces in old photos with GFPGAN or CodeFormer before embedding, add more sources (Library of Congress, NYPL, Smithsonian, Europeana), and run on a GPU for very large collections.

## Before you share or ship this

- **Model license:** InsightFace's pretrained models are for non-commercial research use. A commercial product needs a different model or a license from the authors.
- **Photo licensing:** Commons license labels are crowd-sourced. Spot check anything you plan to publish, and keep the attribution the UI shows.
- **Privacy:** Face data counts as biometric data under laws such as Illinois BIPA, Texas CUBI and the GDPR. This app doesn't store uploads or compare people against each other, which is the safe pattern. Keep it that way if you deploy it publicly, and say so in the UI.

## Layout

```
api/            FastAPI app (app/) and data scripts (scripts/)
web/            SvelteKit frontend
db/init.sql     pgvector schema, applied when the database volume is first created
data/historic/  downloaded photos (git-ignored)
data/crops/     generated face crops (git-ignored)
```
