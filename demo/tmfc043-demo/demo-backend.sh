#!/usr/bin/env bash
# Starts the SynaptDI backend on :8000 with the environment the ODA Component CTK run needs
# (ODA_CTK_PYTHON, TMPDIR under $HOME for colima's mount, PATH/DOCKER_HOST/KUBECONFIG for
# docker+helm+kubectl). Frees port 8000 first (stops any backend already bound there), since
# the frontend targets http://localhost:8000. Foreground: Ctrl-C to stop.
set -uo pipefail
export PATH="/opt/homebrew/bin:$PATH"
export KUBECONFIG="$HOME/.kube/config"
export DOCKER_HOST="unix:///Users/aryan/.colima/default/docker.sock"
export ODA_CTK_PYTHON="/Users/aryan/Downloads/CTK/ctk-venv/bin/python"
export TMPDIR="$HOME/synaptdi-ctk-tmp"
mkdir -p "$TMPDIR"

PIDS=$(lsof -ti tcp:8000 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  echo "stopping existing process on :8000 ($PIDS)…"
  echo "$PIDS" | xargs kill 2>/dev/null || true
  sleep 1
  PIDS=$(lsof -ti tcp:8000 2>/dev/null || true)
  [ -n "$PIDS" ] && { echo "force-stopping ($PIDS)…"; echo "$PIDS" | xargs kill -9 2>/dev/null || true; sleep 1; }
fi

cd /Users/aryan/Downloads/SynaptDI/backend
echo "starting SynaptDI backend on :8000 with CTK env…"
echo "  ODA_CTK_PYTHON=$ODA_CTK_PYTHON"
echo "  TMPDIR=$TMPDIR"
exec venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
