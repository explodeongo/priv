#!/usr/bin/env python3
"""
SynaptDI MCP server
═══════════════════
Exposes the SynaptDI backend to AI coding agents (Cursor, Claude Desktop, Claude Code,
…) over the Model Context Protocol — so an agent can ask the TM Forum knowledge base and
run deterministic conformance/profile/scaffold without leaving the editor.

Transport: stdio, newline-delimited JSON-RPC 2.0 (the MCP stdio transport).
Dependencies: none — Python standard library only. It calls a running SynaptDI backend
(default http://localhost:8000; override with SYNAPTDI_URL).
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("SYNAPTDI_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = int(os.environ.get("SYNAPTDI_TIMEOUT", "60"))
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "synaptdi", "version": "0.1.0"}


def _http(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return {"error": "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:300])}
    except urllib.error.URLError as e:
        return {"error": "Cannot reach SynaptDI at %s (%s). Is the backend running?" % (BASE, e.reason)}


def _spec(s):
    return open(s, encoding="utf-8").read() if isinstance(s, str) and os.path.isfile(s) else s


TOOLS = [
    {
        "name": "tmf_ask",
        "description": "Ask the TM Forum / MEF knowledge base a question and get a cited answer.",
        "inputSchema": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]},
        "handler": lambda a: _http("POST", "/query", {"question": a["question"], "top_k": a.get("top_k", 8), "scope": a.get("scope", "all")}),
    },
    {
        "name": "tmf_check",
        "description": "Score an OpenAPI/Swagger spec against the TM Forum design guidelines (TMF630). Pass spec text or a file path.",
        "inputSchema": {"type": "object", "properties": {"spec": {"type": "string", "description": "Spec text or a file path"}}, "required": ["spec"]},
        "handler": lambda a: _http("POST", "/conformance/text", {"content": _spec(a["spec"])}),
    },
    {
        "name": "tmf_profile",
        "description": "Detect which TMF API a spec is and report coverage + the exact missing operations/fields vs the canonical spec.",
        "inputSchema": {"type": "object", "properties": {"spec": {"type": "string"}}, "required": ["spec"]},
        "handler": lambda a: _http("POST", "/conformance/profile", {"content": _spec(a["spec"])}),
    },
    {
        "name": "tmf_scaffold",
        "description": "Complete a partial spec by merging the missing operations + fields from the canonical TMF spec.",
        "inputSchema": {"type": "object", "properties": {"spec": {"type": "string"}}, "required": ["spec"]},
        "handler": lambda a: _http("POST", "/conformance/scaffold", {"content": _spec(a["spec"])}),
    },
]


def _result(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        return _result(mid, {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {}}, "serverInfo": SERVER_INFO})
    if method in ("notifications/initialized", "initialized"):
        return None                                              # notification — no response
    if method == "tools/list":
        return _result(mid, {"tools": [{"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]} for t in TOOLS]})
    if method == "tools/call":
        params = msg.get("params") or {}
        tool = next((t for t in TOOLS if t["name"] == params.get("name")), None)
        if not tool:
            return _err(mid, -32602, "Unknown tool: %s" % params.get("name"))
        try:
            out = tool["handler"](params.get("arguments") or {})
            text = json.dumps(out, indent=2)[:12000]
            return _result(mid, {"content": [{"type": "text", "text": text}], "isError": bool(isinstance(out, dict) and out.get("error"))})
        except Exception as e:
            return _result(mid, {"content": [{"type": "text", "text": "Error: %s" % e}], "isError": True})
    if mid is not None:
        return _err(mid, -32601, "Method not found: %s" % method)
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
