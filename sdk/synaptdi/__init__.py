"""
SynaptDI — Python SDK
═════════════════════
A thin, dependency-free client for the SynaptDI REST API. Ask the TM Forum knowledge
base, and run deterministic Open API conformance / profile / scaffold / X-ray against a
running SynaptDI backend.

    from synaptdi import SynaptDI
    sd = SynaptDI("http://localhost:8000")

    print(sd.check("openapi.yaml")["score"])          # TMF630 structural score
    print(sd.profile("openapi.yaml")["coverage"])     # % of the real canonical TMF API
    sd.scaffold("openapi.yaml")                        # auto-complete from the canonical spec
    sd.xray(["a.yaml", "b.yaml"])                      # portfolio report across many specs
    sd.ask("What fields does a Product Order have in TMF622?")

Uses only the Python standard library (urllib) — installing it pulls in nothing else.
"""
import json
import os
import urllib.error
import urllib.request

__version__ = "0.1.0"
__all__ = ["SynaptDI", "SynaptDIError"]


class SynaptDIError(RuntimeError):
    """Raised when a request fails or the backend can't be reached."""


class SynaptDI:
    """Client for a running SynaptDI backend (default http://localhost:8000)."""

    def __init__(self, base_url: str = "http://localhost:8000", token: str = None, timeout: int = 60):
        self.base = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    # ── transport ────────────────────────────────────────────────────────────
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = "Bearer " + self.token
        return h

    def _request(self, method: str, path: str, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            raise SynaptDIError("%s %s -> HTTP %s: %s" % (method, path, e.code, detail))
        except urllib.error.URLError as e:
            raise SynaptDIError("Could not reach SynaptDI at %s (%s). Is the backend running?" % (self.base, e.reason))

    @staticmethod
    def _read(spec: str):
        """Accept a spec as a file path (read it) or as raw spec text."""
        if isinstance(spec, str) and os.path.isfile(spec):
            with open(spec, encoding="utf-8") as f:
                return f.read(), os.path.basename(spec)
        return spec, ""

    # ── knowledge base ───────────────────────────────────────────────────────
    def ask(self, question: str, top_k: int = 8, scope: str = "all") -> dict:
        """Ask the TM Forum knowledge base. Returns {answer, sources, ...}."""
        return self._request("POST", "/query", {"question": question, "top_k": top_k, "scope": scope})

    # ── conformance (deterministic, no AI) ───────────────────────────────────
    def check(self, spec, filename: str = "") -> dict:
        """TMF630 structural conformance (+ profile). Returns {score, summary, findings, profile}."""
        content, fn = self._read(spec)
        return self._request("POST", "/conformance/text", {"content": content, "filename": filename or fn})

    def profile(self, spec) -> dict:
        """Detect the TMF API and diff it against the canonical spec. Returns {detected, coverage, ...}."""
        content, _ = self._read(spec)
        return self._request("POST", "/conformance/profile", {"content": content})

    def fix(self, spec) -> dict:
        """Auto-fix fixable TMF630 issues. Returns {content, fixed, score}."""
        content, _ = self._read(spec)
        return self._request("POST", "/conformance/fix", {"content": content})

    def scaffold(self, spec) -> dict:
        """Complete a partial spec from the canonical TMF spec. Returns {content, added, coverage_after}."""
        content, _ = self._read(spec)
        return self._request("POST", "/conformance/scaffold", {"content": content})

    def component(self, manifest) -> dict:
        """ODA Component conformance — score the TMF Open APIs an ODA component manifest
        (.component.yaml) exposes and depends on. Accepts manifest text or a file path."""
        content, _ = self._read(manifest)
        return self._request("POST", "/conformance/component", {"content": content})

    def xray(self, specs) -> dict:
        """Portfolio X-ray across many specs. `specs` = file paths or {filename, content} dicts."""
        items = []
        for s in specs:
            if isinstance(s, dict):
                items.append(s)
            else:
                content, fn = self._read(s)
                items.append({"filename": fn or "spec", "content": content})
        return self._request("POST", "/conformance/portfolio", {"specs": items})

    def health(self) -> dict:
        return self._request("GET", "/health")
