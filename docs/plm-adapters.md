# PLM adapter SDK

TwinOps talks to PLM through a small protocol — not a vendor SDK.

```text
PlmAdapter
  ├── FilePlmAdapter   (JSON catalog on disk)
  ├── RestPlmAdapter   (generic HTTP)
  ├── MockPlmAdapter   (demo helper; same catalog as File)
  └── TeamcenterStub / WindchillStub  (shape only)
```

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
| GET | `/items` | list or `{ "items": [...] }` |
| GET | `/items/{id}` | single item |
| PUT | `/items/{id}` | optional write for `bump` |

Generic item document:

```json
{
  "id": "1004711",
  "revision": "B",
  "lifecycle": "Released",
  "metadata": {
    "prim": "/World/Factory/LineA/Robot01",
    "name": "Robot01"
  }
}
```

TwinOps catalog fields (`itemId`, `prim`, …) are also accepted.

```bash
twinopsctl plm show --url http://127.0.0.1:9090 --json
twinopsctl plm get 1004711 --url http://127.0.0.1:9090 --token "$TOKEN"
```

## Adding a vendor adapter

Implement `PlmAdapter` (or put a REST façade in front of Teamcenter/Windchill)
and keep proprietary SDKs **outside** this repository.
