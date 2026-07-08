"""
TMFC043 Fault Management — smallest real demo component (official CTK target only).
════════════════════════════════════════════════════════════════════════════════════
This is NOT part of SynaptDI's backend or verdict engine. It exists solely as a real,
DEPLOYABLE HTTP target for the official TM Forum Component CTK, so a genuine TMF642 v4
(Alarm Management) + TMF669 v4 (Party Role Management) conformance run can execute end to
end against something real on this machine.

Nothing here fakes or short-circuits the CTK. The official Newman collections
(TMF642-Alarm-v4.0.0.testkit.json / TMF669-PartyRole-v4.0.0.testkit.json) POST/GET/PATCH/
DELETE against these endpoints and assert on the live responses; this service answers those
requests in the TMF-conformant shape the collections require:
  • POST   → 201, echoes every posted attribute, assigns id + absolute href
  • GET     → 200 array (200/206 accepted); ?fields=X projects to exactly {id, href, X};
               ?attr=value filters
  • GET/{id}→ 200 full resource, or 404 if unknown
  • PATCH   → 200, applies the change
  • DELETE  → 204, and a subsequent GET/{id} is 404

Storage is in-memory (per pod). Every request is logged so the exact CTK traffic that
reached the component is inspectable via `kubectl logs`.
"""
import datetime
import logging
import os
import uuid
from typing import Dict

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("tmfc043-demo")

app = FastAPI(title="TMFC043 Fault Management Demo", version="1.0.0")

STORE: Dict[str, Dict[str, dict]] = {}   # collection -> {id -> resource}
HUBS: Dict[str, dict] = {}
_RESERVED_QUERY = {"fields", "offset", "limit", "sort"}

# Deliberate non-conformance for the "FAIL" demo. When DEMO_BROKEN is set, the alarm API
# omits the mandatory TMF642 attribute named in DEMO_BROKEN_FIELD (default "state") from every
# alarm response — a believable vendor bug. The real TMF642 CTK detects it and SynaptDI's
# normalizer reports an honest FAIL. Unset (the default), the component is fully conformant.
BROKEN = bool(os.environ.get("DEMO_BROKEN"))
BROKEN_FIELD = os.environ.get("DEMO_BROKEN_FIELD", "state")


def _out(collection: str, obj: dict) -> dict:
    if BROKEN and collection == "alarm" and isinstance(obj, dict) and BROKEN_FIELD in obj:
        return {k: v for k, v in obj.items() if k != BROKEN_FIELD}
    return obj


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _coll(name: str) -> Dict[str, dict]:
    return STORE.setdefault(name, {})


@app.middleware("http")
async def log_requests(request: Request, call_next):
    raw = b""
    try:
        raw = await request.body()
    except Exception:
        pass
    log.info("→ %s %s%s", request.method, str(request.url).split("://", 1)[-1].split("/", 1)[-1],
             f"  body={raw[:300].decode('utf-8', 'replace')}" if raw else "")
    resp = await call_next(request)
    log.info("← %s %s  %s", request.method, request.url.path, resp.status_code)
    return resp


@app.get("/health")
@app.get("/")
def health():
    return {"status": "UP", "component": "TMFC043-FaultManagement-Demo",
            "apis": ["TMF642 v4 alarmManagement", "TMF669 v4 partyRoleManagement"]}


def _href(request: Request, collection: str, rid: str) -> str:
    # Absolute href the CTK can re-GET. Base it on the request URL up to the collection.
    root = str(request.url).split("?")[0]
    root = root.rsplit("/" + collection, 1)[0].rstrip("/")   # rsplit: don't match 'alarm' inside 'alarmManagement'
    return f"{root}/{collection}/{rid}"


def _make(request: Request, collection: str, type_name: str, payload: dict) -> dict:
    rid = str(payload.get("id") or uuid.uuid4())
    resource = dict(payload)
    resource["id"] = rid
    resource["href"] = _href(request, collection, rid)
    resource.setdefault("@type", type_name)
    resource.setdefault("@baseType", type_name)
    return resource


def _project(request: Request, items: list) -> list:
    """Apply TMF ?fields= projection and ?attr= filtering.
    ?fields=a,b → each instance reduced to EXACTLY {id, href, a, b} (the CTK asserts the
    filtered instance has *only* id, href and the requested attribute)."""
    qp = dict(request.query_params)
    fields = qp.pop("fields", None)
    filters = {k: v for k, v in qp.items() if k not in _RESERVED_QUERY}
    result = items
    for key, val in filters.items():
        needle = val.strip().strip("'\"")
        result = [it for it in result if str(it.get(key)) == needle]
    if fields is not None:
        wanted = [f.strip() for f in fields.split(",") if f.strip()]
        reduced = []
        for it in result:
            obj = {"id": it.get("id"), "href": it.get("href")}
            for f in wanted:
                if f in it:
                    obj[f] = it[f]
            reduced.append(obj)
        return reduced
    return result


def register_resource(prefix: str, collection: str, type_name: str, defaults: dict):
    path = f"{prefix}/{collection}"

    @app.post(path, name=f"create_{prefix}_{collection}")
    async def _create(request: Request, _c=collection, _t=type_name, _d=defaults):
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        for k, v in _d.items():
            payload.setdefault(k, _now() if v == "__now__" else v)
        resource = _make(request, _c, _t, payload)
        _coll(_c)[resource["id"]] = resource
        return JSONResponse(status_code=201, content=_out(_c, resource))

    @app.get(path, name=f"list_{prefix}_{collection}")
    async def _list(request: Request, _c=collection):
        rows = [_out(_c, r) for r in _project(request, list(_coll(_c).values()))]
        return JSONResponse(status_code=200, content=rows)

    @app.get(path + "/{rid}", name=f"get_{prefix}_{collection}")
    async def _get(rid: str, _c=collection):
        item = _coll(_c).get(rid)
        if not item:
            return JSONResponse(status_code=404, content={"@type": "Error", "reason": "Not Found"})
        return JSONResponse(status_code=200, content=_out(_c, item))

    @app.patch(path + "/{rid}", name=f"patch_{prefix}_{collection}")
    async def _patch(rid: str, request: Request, _c=collection):
        item = _coll(_c).get(rid)
        if not item:
            return JSONResponse(status_code=404, content={"@type": "Error", "reason": "Not Found"})
        try:
            body = await request.json()
        except Exception:
            body = {}
        if isinstance(body, dict):
            item.update({k: v for k, v in body.items() if k not in ("id", "href")})
        return JSONResponse(status_code=200, content=_out(_c, item))

    @app.delete(path + "/{rid}", name=f"delete_{prefix}_{collection}")
    async def _delete(rid: str, _c=collection):
        _coll(_c).pop(rid, None)
        return Response(status_code=204)


def register_hub(prefix: str):
    @app.post(f"{prefix}/hub", name=f"hub_{prefix}")
    async def _hub(request: Request):
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        hid = str(uuid.uuid4())
        HUBS[hid] = {"id": hid, "callback": (payload or {}).get("callback", "")}
        return JSONResponse(status_code=201, content=HUBS[hid])

    @app.delete(f"{prefix}/hub/{{hid}}", name=f"unhub_{prefix}")
    async def _unhub(hid: str):
        HUBS.pop(hid, None)
        return Response(status_code=204)


# TMF642 Alarm Management v4 — mounted at both the CTK-default and swagger base paths so the
# component's published status URL can point at either with no mismatch.
for alarm_prefix in ("/tmf-api/alarmManagement/v4", "/tmf-api/alarm/v4"):
    register_resource(alarm_prefix, "alarm", "Alarm",
                      {"state": "raised", "alarmRaisedTime": "__now__"})
    register_hub(alarm_prefix)

# TMF669 Party Role Management v4.
register_resource("/tmf-api/partyRoleManagement/v4", "partyRole", "PartyRole", {"name": "demo-role"})
register_hub("/tmf-api/partyRoleManagement/v4")


@app.on_event("startup")
def _seed_canvas_role():
    # Publish the component's canvas system role via the party-role API, so the CTK's
    # deployment baseline ("security api must return at least one partyrole with the canvas
    # system role") sees a real role. Kept idempotent + stable so the TMF669 CTK (which
    # creates/deletes its OWN role by id) is unaffected.
    role_name = os.environ.get("CANVAS_SYSTEM_ROLE", "fault-admin")
    coll = _coll("partyRole")
    if not any(r.get("name") == role_name for r in coll.values()):
        rid = "canvas-system-role"
        coll[rid] = {"id": rid, "href": f"/tmf-api/partyRoleManagement/v4/partyRole/{rid}",
                     "name": role_name, "@type": "PartyRole", "@baseType": "PartyRole"}
        log.info("seeded canvas system role partyRole name=%s", role_name)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
