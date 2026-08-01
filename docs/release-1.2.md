# TwinOps 1.2.0 — production hardening

Theme release after v1.1 streaming foundation.

## What shipped

- **Helm/live ENTRYPOINT fix** — `twinopsctl` + `args: [serve, ...]` (no double command)
- Operator / live image tags synced to **1.2.0**; `examples.hostPath` off by default
- **CI deploy smoke**: Helm render + live container `/api/health`
- **Real media paths**: software aiortc track + host **ffmpeg h264_nvenc** MPEG-TS bridge
- Streaming sidecar image published on release tags
- **DigitalTwin `artifactSource`**: ConfigMap or HTTP `.tar.gz`/`.zip` with `status.artifactDigest`
- Optional **pxr / usd-core** validation (`make usd-validate`, CI job)
- Manual GPU workflow for self-hosted runners
- README lifecycle visual; removed unmeasured “70%” claim

## Verify

```bash
make install
make test
make streaming-sidecar-smoke
make deploy-smoke          # needs docker + helm
# optional:
pip install -e '.[usd]' && make usd-validate
```

## Still not a plant platform

No NVCF, multi-tenant streaming, proprietary PLM SDK, or fleet dashboard.
Use as an executable reference architecture with a hardened deploy path.
