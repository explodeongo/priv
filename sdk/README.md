# SynaptDI — Python SDK

A thin, **dependency-free** client for the [SynaptDI](https://github.com/dibuAI/SynaptDI) REST API. Lets any external system query the TM Forum knowledge base and run deterministic Open API conformance against a running SynaptDI backend.

## Install
```bash
pip install ./sdk          # from the repo
# or, once published:  pip install synaptdi
```
No third-party dependencies — it uses only the Python standard library.

## Use
```python
from synaptdi import SynaptDI

sd = SynaptDI("http://localhost:8000")          # a running SynaptDI backend

# Deterministic conformance (no AI):
report = sd.check("orders.yaml")                 # → {score, summary, findings, profile}
print(report["score"], "/100")

gap = sd.profile("orders.yaml")                  # → vs the canonical TMF API
print(gap["detected"]["tmf"], gap["coverage"], "%")

sd.fix("orders.yaml")                            # → corrected spec
sd.scaffold("orders.yaml")                       # → completed from the canonical spec
estate = sd.xray(["a.yaml", "b.yaml"])           # → portfolio report (+ markdown)

# Knowledge base (needs the backend's model running):
ans = sd.ask("What fields does a Product Order have in TMF622?")
print(ans["answer"])
```

Each spec argument accepts a **file path** or **raw spec text**. Pass a `token=` to the
constructor for an authenticated backend.

## Methods
| Method | Backend endpoint | Returns |
|---|---|---|
| `check(spec)` | `POST /conformance/text` | TMF630 score + findings + profile |
| `profile(spec)` | `POST /conformance/profile` | detected API + coverage + gaps |
| `fix(spec)` | `POST /conformance/fix` | corrected spec |
| `scaffold(spec)` | `POST /conformance/scaffold` | spec completed from the canonical |
| `xray(specs)` | `POST /conformance/portfolio` | portfolio report + markdown |
| `ask(question)` | `POST /query` | cited answer + sources |
| `health()` | `GET /health` | backend status |
