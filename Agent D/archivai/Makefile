.PHONY: up up-stub full web-rebuild down logs ps db-init db-psql n8n-import n8n-activate smoke models test clean

# Core stack (no web app; web is behind the "full" profile)
up:
	docker compose up -d postgres minio minio-init ollama ai-service n8n
	@echo "n8n:    http://localhost:5678"
	@echo "MinIO:  http://localhost:9001"
	@echo "AI svc: http://localhost:8000/health"

# Same, but without Ollama — enough for AI_STUB=1 runs (no models needed).
up-stub:
	docker compose up -d postgres minio minio-init ai-service n8n
	@echo "n8n:    http://localhost:5678"
	@echo "MinIO:  http://localhost:9001"
	@echo "AI svc: http://localhost:8000/health"

# Core stack + web app. Skips Ollama (not needed in stub mode; `make up` adds it).
# NOTE: web runs from a built image — after changing anything in web/, run
# `make web-rebuild` (plain `up -d` serves the stale image → 404 on new pages).
full:
	docker compose --profile full up -d postgres minio minio-init ai-service n8n web
	@echo "Web:    http://localhost:3000"

# Rebuild the web image and restart it (run after any change in web/).
web-rebuild:
	docker compose --profile full up -d --build web
	@echo "Web:    http://localhost:3000"

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

# Schema auto-applies on first Postgres boot; use this to (re)apply manually.
# Applies ALL of db/init/*.sql in order (idempotent).
db-init:
	@for f in db/init/*.sql; do \
	  echo "applying $$f"; \
	  docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U $${POSTGRES_USER:-archivai} -d $${POSTGRES_DB:-archivai} < $$f || exit 1; \
	done

db-psql:
	docker compose exec postgres psql -U $${POSTGRES_USER:-archivai} -d $${POSTGRES_DB:-archivai}

# Pull the open-source models into Ollama (run once; ~ several GB).
models:
	docker compose exec ollama ollama pull qwen2.5vl:7b
	docker compose exec ollama ollama pull qwen2.5:7b-instruct
	docker compose exec ollama ollama pull bge-m3

# Import the pipeline workflows into n8n.
# NOTE: CLI import does not hot-register webhooks — run n8n-activate after.
n8n-import:
	docker compose exec n8n n8n import:workflow --separate --input=/workflows

# Publish all ArchivAI workflows and restart n8n so webhooks register.
# n8n 2.x uses publish:workflow; falls back to the 1.x active flag.
n8n-activate:
	docker compose exec -T n8n sh -c 'for w in archivai-w1 archivai-w2 archivai-w3 archivai-w4 archivai-w5 archivai-w6 archivai-w7 archivai-w8; do \
	  n8n publish:workflow --id=$$w || n8n update:workflow --id=$$w --active=true; done'
	docker compose restart n8n

# One-command end-to-end smoke test in stub mode (no GPU/models needed).
smoke:
	bash scripts/smoke.sh

# Demo IoT sensor: feeds storage temperature/humidity into the dashboard widget.
sensor-demo:
	bash scripts/simulate_sensor.sh

# Pre-demo hygiene: remove smoke/stub documents, prune orphan entities, clear chat
# sessions, rebuild edges + stats. Audit/compliance rows are kept.
demo-clean:
	docker compose exec -T postgres psql -qtA -U $${POSTGRES_USER:-archivai} -d $${POSTGRES_DB:-archivai} \
	  -c "SELECT cleanup_test_data();"

# Smoke-test the AI service extraction contract (no models needed).
# AI_STUB=1 is forced: the checks assert the deterministic stub contract, so the
# target must pass on a host already switched to the real models (AI_STUB=0).
test:
	docker compose exec -e AI_STUB=1 ai-service python -m app.selftest

clean:
	docker compose down -v
