# Container images

TwinOps publishes demo images to GitHub Container Registry on `v*` tags:

| Image | Dockerfile | Notes |
| --- | --- | --- |
| `ghcr.io/justrunme/twinops-live` | `Dockerfile.live` | Live API + built web UI |
| `ghcr.io/justrunme/twinops-operator` | `Dockerfile.operator` | Manager + embedded `twinopsctl` |

Workflow: [`.github/workflows/publish-images.yml`](../.github/workflows/publish-images.yml)

## Local build

```bash
make docker-live
make docker-operator
```

## Pull (after a tagged release)

```bash
docker pull ghcr.io/justrunme/twinops-live:0.5.6
docker pull ghcr.io/justrunme/twinops-operator:0.5.6
```

Packages may start as private under the GitHub org — set visibility to public
in package settings if you want anonymous pulls.

## Honesty

Images are for demos and labs. Live image binds `0.0.0.0:8080` by default —
set `TWINOPS_API_TOKEN` / Helm Secret before shared use.
