# PLM adapter SDK

TwinOps talks to PLM through a small protocol — not a vendor SDK.

```text
PlmAdapter
  ├── FilePlmAdapter   (JSON catalog on disk)     — demo-real
  ├── RestPlmAdapter   (generic HTTP + ETag)      — demo-real / production-credible
  ├── MockPlmAdapter   (in-memory demo helper)
  ├── MockPlmHTTPServer (test/E2E mock with ETag/409/5xx)
  └── TeamcenterStub / WindchillStub              — stub-only (shape only)
```

## Demo-real vs stub-only

| Path | Status | Notes |
|------|--------|-------|
| File / Mock catalog | **demo-real** | Used by `make plm-demo`, examples |
| RestPlmAdapter + mock HTTP | **demo-real** | Contract + reliability tests; kind E2E |
| `spec.plm` on DigitalTwin | **demo-real** | Operator polls ETag, syncs mappings, folds fingerprint into input digest |
| TeamcenterStub / WindchillStub | **stub-only** | Raises `NotImplementedError` for compare/sync |

## Protocol

```python
class PlmAdapter(Protocol):
    @property
    def items(self) -> list[PlmItem]: ...
    def get(self, item_id: str) -> PlmItem | None: ...
    def bump_revision(self, item_id: str, *, to: str | None = None) -> PlmItem: ...
    def compare_manifest(self, manifest) -> list[dict]: ...
    def sync_manifest(self, manifest_path, *, write: bool = True) -> dict: ...
```

See [ADR-0017](adr/0017-generic-plm-adapters.md).

## REST reliability contract

`RestPlmAdapter` + `PlmSyncSession` implement:

- **ETag / If-None-Match** — `GET /items` returns 304 when unchanged
- **Exponential backoff + jitter** — retries on 5xx / timeout
- **409 conflicts** — `PUT` with stale `If-Match` → `PlmConflictError`; DigitalTwin `PlmConflict` condition
- **Auth failure** — 401/403 → `PlmAuthError`
- **Idempotent resync** — after outage, the next successful poll increments `resyncCount` exactly once

Operator field:

```yaml
spec:
  plm:
    url: http://plm.example:9090
    tokenSecretRef: { name: plm-token, key: token }
    pollSeconds: 5
    syncManifest: true
status:
  plm:
    etag: W/"…"
    fingerprint: "…"
    resyncCount: 1
    conflict: false
```

Kind E2E: `make operator-plm-e2e` (PLM revision bump → new immutable `status.output.history` entry; outage→recovery resync once).

## File adapter

Catalog shape (`examples/assembly-line/plm-catalog.json`):

```json
{
  "provider": "file",
  "items": [
    {
      "itemId": "1004711",
      "revision": "A",
      "lifecycle": "Released",
      "prim": "/World/Factory/LineA/Robot01",
      "name": "Robot01"
    }
  ]
}
```

```bash
twinopsctl plm show --catalog examples/assembly-line/plm-catalog.json --json
twinopsctl plm get 1004711 --catalog examples/assembly-line/plm-catalog.json
```

## REST adapter

Base URL + paths:

| Method | Path | Body / response |
|--------|------|-----------------|
| GET | `/items` | list or `{ "items": [...] }` (+ ETag) |
| GET | `/items/{id}` | single item |
| PUT | `/items/{id}` | optional write for `bump` (If-Match → 409) |

```bash
twinopsctl plm show --url http://127.0.0.1:9090 --json
twinopsctl plm get 1004711 --url http://127.0.0.1:9090 --token "$TOKEN"
```

## Adding a vendor adapter

Implement `PlmAdapter` (or put a REST façade in front of Teamcenter/Windchill)
and keep proprietary SDKs **outside** this repository.
