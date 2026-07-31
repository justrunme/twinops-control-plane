# Releasing TwinOps

Experimental project — keep releases small and honest.

## Checklist

1. `make install && make verify-all`
2. Bump version in:
   - `python/twinops/__init__.py`
   - `pyproject.toml`
   - `deploy/helm/twinops-operator/Chart.yaml` (`appVersion`)
   - Docker tags in `Makefile` / `docs/demo.md`
   - CLI tests that hardcode the version string
3. Move `CHANGELOG.md` Unreleased notes into `## X.Y.Z — YYYY-MM-DD`
4. Open a PR, merge to `main`
5. Tag + GitHub release:

```bash
gh release create vX.Y.Z --title "TwinOps X.Y.Z" --notes-file - <<'EOF'
## TwinOps X.Y.Z

<short honest summary>

Still experimental — mock PLM, mock Kit stream, anonymous MQTT for local demos only.
EOF
```

6. Tag push triggers [publish-images.yml](.github/workflows/publish-images.yml) →
   `ghcr.io/justrunme/twinops-live:X.Y.Z` and `twinops-operator:X.Y.Z`
   (see [docs/images.md](docs/images.md); set package visibility if pulls should be public).
7. Optionally refresh the portfolio blurb on `justrunme-site` if the public story changed.
