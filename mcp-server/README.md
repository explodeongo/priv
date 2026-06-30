# SynaptDI — MCP server

Exposes SynaptDI to AI coding agents over the **Model Context Protocol**, so Cursor, Claude Desktop, or Claude Code can query the TM Forum knowledge base and run deterministic conformance directly.

**Dependencies:** none (Python standard library). It talks to a running SynaptDI backend (default `http://localhost:8000`).

## Tools exposed
| Tool | What it does |
|---|---|
| `tmf_ask` | Ask the TM Forum / MEF knowledge base; returns a cited answer |
| `tmf_check` | TMF630 conformance score for a spec (text or file path) |
| `tmf_profile` | Detect the TMF API + coverage + exact missing operations/fields |
| `tmf_scaffold` | Complete a partial spec from the canonical TMF spec |

## Connect it

**Claude Desktop / Cursor** — add to the MCP config (`claude_desktop_config.json` or Cursor's `mcp.json`):
```json
{
  "mcpServers": {
    "synaptdi": {
      "command": "python3",
      "args": ["/absolute/path/to/SynaptDI/mcp-server/synaptdi_mcp.py"],
      "env": { "SYNAPTDI_URL": "http://localhost:8000" }
    }
  }
}
```

**Claude Code** — `claude mcp add synaptdi -- python3 /absolute/path/to/SynaptDI/mcp-server/synaptdi_mcp.py`

Then ask the agent things like *"check this OpenAPI file against TM Forum"* or *"what's missing for this to be a valid TMF641 Service Order?"* and it will call SynaptDI natively.

> The knowledge-base tool (`tmf_ask`) needs the backend's model running (Ollama); the conformance tools (`tmf_check`/`tmf_profile`/`tmf_scaffold`) are deterministic and need only the backend.
