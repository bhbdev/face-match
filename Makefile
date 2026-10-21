.PHONY: help up down logs download find index reindex stats psql reset-db web-dev

# Defaults for `make download`; override on the command line, e.g.
#   make download CATEGORY="Category:Cartes de visite" LIMIT=500
CATEGORY ?= Category:Daguerreotype portraits
LIMIT    ?= 300

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

up: ## Build and start db, api and web (http://localhost:3000)
	docker compose up -d --build

down: ## Stop everything (keeps the database)
	docker compose down

logs: ## Follow api logs (first start downloads the model)
	docker compose logs -f api

find: ## Find Commons categories: make find Q="daguerreotype portraits"
	docker compose run --rm api python -m scripts.download_commons --find "$(Q)"

download: ## Download public-domain portraits from a Commons category
	docker compose run --rm api python -m scripts.download_commons --category "$(CATEGORY)" --limit $(LIMIT)

index: ## Embed any new photos in data/historic into the database
	docker compose run --rm api python -m scripts.index_images

reindex: ## Wipe the index and embed everything again
	docker compose run --rm api python -m scripts.index_images --reindex

stats: ## Show how many faces are indexed
	@curl -s http://localhost:8000/stats; echo

psql: ## Open a psql shell in the database
	docker compose exec db sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

reset-db: ## DANGER: delete the database volume (re-run `make index` afterwards)
	docker compose down
	docker volume rm face-match_pgdata

web-dev: ## Run the SvelteKit dev server against the dockerized api
	cd web && npm install && API_URL=http://localhost:8000 npm run dev
