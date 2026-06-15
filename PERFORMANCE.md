# Performance — faster answers, zero quality compromise

**Nothing here reduces answer quality.** Deep mode always uses the full 8B model, all
retrieved chunks, and complete cited answers. These options make that *same* answer
arrive faster by (a) removing wasted work and (b) using hardware you already have.

> Why there's no magic flag: SynaptDI's speed is ~entirely how fast Ollama generates
> tokens, which is a hardware property. A full 8B answer on 4 CPU cores is inherently
> ~1–2 min. To keep full quality *and* go fast you must accelerate the model — not shrink it.

---

## Where the model runs (the number that matters)

| Hardware | Full-quality Deep answer | Notes |
|---|---|---|
| NVIDIA GPU (server/desktop) | **~2–5 s** | The real fix for a team — see [DEPLOY.md](DEPLOY.md) |
| Apple Silicon (M-series) | ~15–40 s | Metal-accelerated automatically |
| Intel laptop **+ IPEX-LLM** | ~30–60 s | Uses the Intel iGPU — see below |
| CPU only (e.g. i7-1165G7) | ~60–140 s | No acceleration; apply the free wins below |

---

## Free wins — already on, or one flag (no quality change)

- **Warm model, no cold reloads** — SynaptDI pre-loads the model at startup and keeps it
  resident (`OLLAMA_KEEP_ALIVE=30m`). Only the first question of a session can be slow.
- **Answer cache** — a repeated question returns instantly.
- **Flash attention** — a free Ollama speedup + lower memory. Set it once on the machine
  running Ollama, then restart Ollama:
  - **Windows** (PowerShell): `setx OLLAMA_FLASH_ATTENTION 1`
  - **macOS / Linux**: `export OLLAMA_FLASH_ATTENTION=1`
- **CPU threads** — if Ollama isn't using all your cores, set `OLLAMA_NUM_THREAD` to your
  **physical** core count (e.g. `4` on an i7-1165G7) in SynaptDI's backend environment.
- **Latest models** — `ollama pull llama3.1:8b` occasionally ships faster builds.

---

## Intel laptops (Iris Xe / Arc) — accelerate the *same* model on the iGPU

Plain Ollama runs **CPU-only** on Intel graphics — your Iris Xe sits idle. Intel's
**IPEX-LLM** runs Ollama on the Intel GPU and is typically **2–4× faster with identical
answers** (same model, same weights — no quality loss).

1. Follow Intel's official **"Run Ollama with IPEX-LLM"** quickstart: <https://github.com/intel/ipex-llm> (docs → Quickstart → Ollama).
2. It installs `ipex-llm[cpp]`, then `init-ollama` creates an Ollama that targets the iGPU.
3. Start that Ollama and `ollama pull llama3.1:8b nomic-embed-text` as usual.
4. SynaptDI needs **no changes** — it talks to it through `OLLAMA_URL` (default
   `http://localhost:11434`). Point there if it runs on a different port.

This is the recommended path for getting full-quality answers fast on an Intel laptop
without a discrete GPU.

---

## The team answer: one GPU host

For everyone to get **~2–5 s** answers with zero local setup, run the Docker deploy on a
box with an NVIDIA GPU (uncomment the GPU block in `docker-compose.yml`) — see
**[DEPLOY.md](DEPLOY.md)**. Then the whole team just opens one URL. This is the right
long-term home for SynaptDI; laptops are for trying it, a GPU host is for using it daily.

---

## Tuning reference (backend env vars)

| Variable | Default | Effect |
|---|---|---|
| `OLLAMA_KEEP_ALIVE` | `30m` | Keep model in RAM between queries |
| `OLLAMA_NUM_THREAD` | `0` (auto) | Pin CPU threads (set to physical cores) |
| `NUM_CTX` | `4096` | Context window (don't lower — risks truncation) |
| `WARM_MODELS` | `1` | Pre-load model at startup |
| `LLM_CONCURRENCY` | `1` | Parallel generations (raise only with a GPU) |

None of these change what the model *says* — only how fast it says it.
