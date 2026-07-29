# AI Document Analysis Platform

A microservice-based platform for uploading PDF documents, indexing them for
retrieval-augmented generation (RAG), and chatting with them over an LLM
(Gemini). Real Postgres, Redis, and RabbitMQ - run locally via Docker,
application services run as plain Python processes.

## Architecture

```
                         +------------------+
                 +------>|  auth-service    |  :8001   Postgres (users)
                 |       +------------------+
+------------+   |       +------------------+
|   client   |-->| HTTP  | document-service |  :8002   Postgres (documents)
| (browser / |   |------>+------------------+            + local disk (PDFs, chunks)
|  API user) |   |  gateway  | Celery task: document.uploaded
+------------+   |  :8000    v
                 |       +------------------+
                 |       | ai-worker-service|  :8004   FAISS (local vector store)
                 |       |  - FastAPI(search)|          Postgres (reads/updates documents)
                 |       |  - Celery worker  |
                 |       |  - Celery beat    |
                 |       +------------------+
                 |               ^ HTTP (/internal/search)
                 |       +------------------+
                 +------>|  chat-service    |  :8003   Redis (cache + session)
                         +------------------+           Gemini API (LLM)

Infra (Docker):  Postgres :5432   Redis :6379   RabbitMQ :5672 (mgmt UI :15672)
```

**Strict rules this codebase follows everywhere (do not deviate):**
- **Redis** is used only for caching, session storage, and rate limiting (`shared/cache/redis_client.py`). Never a message broker.
- **RabbitMQ** is used only as the Celery broker for background jobs (`shared/messaging/celery_app.py`). Task name = event topic (see `shared/schemas/events.py`).
- **Every** inter-service HTTP call goes through the one shared `ServiceClient` (`shared/clients/service_client.py` - httpx + tenacity retry + fixed timeout). No ad hoc `httpx.AsyncClient()` anywhere else.
- No service imports another service's code. Communication is HTTP or a Celery task name only.
- Auth is stateless: `auth-service` issues JWTs; every other service verifies them locally with the shared secret (`shared/security/jwt.py`, `shared/security/oauth.py`) - no network call back to auth-service per request.

## Services

| Service | Port | Responsibility |
|---|---|---|
| `gateway-service` | 8000 | Public entrypoint, rate limiting (Redis), reverse-proxies to the other services |
| `auth-service` | 8001 | Register/login/refresh/me, JWT issuing, Postgres `users` table |
| `document-service` | 8002 | PDF upload, text extraction, chunking, Postgres `documents` table, queues embedding job |
| `ai-worker-service` | 8004 | Celery worker (embeds + indexes chunks in FAISS) + Celery beat (scheduled jobs) + internal search API |
| `chat-service` | 8003 | RAG query endpoint: retrieval + Gemini call + Redis caching/session |

## 1. Start infrastructure (Docker)

```bash
docker compose up -d
docker compose ps                 # all three should be "healthy"
```

Verify each is reachable:
```bash
docker exec ai-doc-redis redis-cli ping                 # -> PONG
docker exec ai-doc-postgres pg_isready -U postgres       # -> accepting connections
# RabbitMQ management UI: http://localhost:15672  (guest / guest)
```

## 2. Install dependencies

One shared virtual environment for the whole monorepo:

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

## 3. Configure environment

```bash
cp .env.example .env
```
Fill in `GEMINI_API_KEY` (required for chat-service to actually call the LLM).
Everything else defaults to the Docker Compose values above.

## 4. Run database migrations

```bash
cd auth-service && PYTHONPATH=.. alembic upgrade head && cd ..
cd document-service && PYTHONPATH=.. alembic upgrade head && cd ..
```

## 5. Run every service

Each command below is run from the **project root**, in its own terminal.
`PYTHONPATH=.` is required so `shared/` is importable.

```bash
# API Gateway
PYTHONPATH=. uvicorn app.main:app --app-dir gateway-service --port 8000 --reload

# Auth Service
PYTHONPATH=. uvicorn app.main:app --app-dir auth-service --port 8001 --reload

# Document Service
PYTHONPATH=. uvicorn app.main:app --app-dir document-service --port 8002 --reload

# Chat Service
PYTHONPATH=. uvicorn app.main:app --app-dir chat-service --port 8003 --reload

# AI Worker Service - internal search API
PYTHONPATH=. uvicorn app.main:app --app-dir ai-worker-service --port 8004 --reload

# AI Worker Service - Celery worker (background embedding jobs)
cd ai-worker-service && PYTHONPATH=.. celery -A app.celery_app worker --loglevel=info

# AI Worker Service - Celery beat (scheduled jobs: cleanup, reindex)
cd ai-worker-service && PYTHONPATH=.. celery -A app.celery_app beat --loglevel=info
```

That's 7 processes total: 5 FastAPI apps + 1 Celery worker + 1 Celery beat.

## 6. Try it

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Ada Lovelace","email":"ada@example.com","password":"password123"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ada@example.com","password":"password123"}'
# -> copy access_token from the response

# Upload a PDF
curl -X POST http://localhost:8000/api/v1/documents/ \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@/path/to/some.pdf"

# Wait a few seconds for the Celery worker to embed it, then ask about it
curl -X POST http://localhost:8000/api/v1/chat/query \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"s1","question":"What is this document about?"}'
```

## Troubleshooting

- **Port already in use** - another process is bound to 5432/6379/5672/8000-8004; stop it or change the port in `docker-compose.yml` / your uvicorn command.
- **`ModuleNotFoundError: shared`** - you forgot `PYTHONPATH=.` (must be run from the project root) or `--app-dir <service>` for uvicorn.
- **Celery worker never picks up a job** - check `docker compose logs rabbitmq` and confirm `RABBITMQ_HOST=localhost` in `.env` matches how you exposed the container port.
- **`GEMINI_API_KEY` errors** - chat-service will raise a clear 502 if the key is missing; retrieval (FAISS search) still works without it.
- **Alembic can't connect** - Postgres must be up and `POSTGRES_*` in `.env` must match `docker-compose.yml`.

## Project layout

```
shared/                  # imported by every service - config, DB base, JWT,
                          # Redis cache/session/rate-limit, Celery/RabbitMQ app,
                          # event schema, shared ServiceClient, exception handling
auth-service/             # users, JWT issuing
document-service/         # upload, extraction, chunking, Postgres `documents`
ai-worker-service/        # Celery worker/beat, embeddings, FAISS, internal search API
chat-service/             # RAG orchestration, Gemini client, Redis cache/session
gateway-service/          # public entrypoint, rate limiting, reverse proxy
docker-compose.yml        # Postgres + Redis + RabbitMQ only
```
