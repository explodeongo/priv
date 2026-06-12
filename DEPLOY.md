# Deploying SynaptDI on a shared server

One server, one command, one URL the whole team opens. Everything runs locally on that
machine — no cloud, no data leaves the network.

## Requirements
- Docker + Docker Compose v2 (`docker compose version`)
- ~12 GB disk (models + index) · 16 GB RAM recommended (8B model)
- Optional NVIDIA GPU — uncomment the GPU block in `docker-compose.yml` for much faster answers

## First-time setup

```bash
git clone https://github.com/dibuAI/SynaptDI.git
cd SynaptDI

# 1. Start everything. SERVER_HOST = the hostname/IP users' browsers will use.
SERVER_HOST=$(hostname -f) docker compose up -d --build

# 2. Pull the models into the ollama container (one time; ~5 GB)
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull llama3.2
docker compose exec ollama ollama pull nomic-embed-text

# 3. Build the knowledge index (one time; downloads TM Forum repos and embeds them)
docker compose exec backend python ingest.py
```

Now share the link: **`http://<SERVER_HOST>:3000`** — demo logins are on the sign-in screen.

> Already have a built index on a laptop? Skip step 3 by copying its `backend/chroma_db/`
> and `backend/storage/` folders onto the server before `docker compose up` — the compose
> file mounts them straight in.

## Day-2 operations

| Task | Command |
|---|---|
| Update to latest code | `git pull && SERVER_HOST=$(hostname -f) docker compose up -d --build` |
| Refresh the knowledge base | Admin → Analytics → "Refresh now" (or `curl -X POST .../admin/refresh-kb` with an admin token; cron-able) |
| Logs | `docker compose logs -f backend` |
| Quality check | `docker compose exec backend python eval.py` |
| Back up | copy `backend/chroma_db/` + `backend/storage/` (index, users, conversations, analytics) |
| Stop | `docker compose down` (data persists in the mounted folders) |

## Tuning

| Env var | Default | Meaning |
|---|---|---|
| `SERVER_HOST` | `localhost` | Address baked into the frontend for reaching the backend — **must be browser-reachable** |
| `LLM_MODEL` | `llama3.1:8b` | Deep-mode model |
| `FAST_MODEL` | `llama3.2:latest` | Fast-mode model (the ⚡ toggle in chat) |
| `LLM_CONCURRENCY` | `1` | Parallel generations; raise only with a GPU |

Changed `SERVER_HOST` later? Rebuild the frontend: `docker compose up -d --build frontend`.

## Notes
- Intended for a trusted internal network. Before exposing wider, put a reverse proxy
  with TLS in front (Caddy/nginx) and restrict ports 8000/3000 to the proxy.
- Concurrent users are queued per `LLM_CONCURRENCY` — the answer cache (instant repeats)
  takes most of the sting out on CPU-only servers.
