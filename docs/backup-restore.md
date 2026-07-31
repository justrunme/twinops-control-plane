# Backup and restore (SQLite control-plane state)

When `twinopsctl serve --db /path/twinops.sqlite` is used, TwinOps persists:

- twin metadata
- timeline events
- latest drift / observed / proposal
- audit trail

## Backup (online-safe copy)

```bash
# Prefer SQLite online backup while the API is stopped, or use the CLI:
twinopsctl state backup --db /tmp/twinops-e2e-demo/db/twinops.sqlite \
  --out /tmp/twinops-backup.sqlite

# Equivalent with sqlite3 (API stopped):
sqlite3 /path/twinops.sqlite ".backup '/path/twinops-backup.sqlite'"
```

Also archive composed stage / proposal artifacts if you need a full demo restore:

```bash
tar czf /tmp/twinops-work.tgz /path/to/work-dir
```

## Restore

```bash
# Stop the live API / sidecar first.
twinopsctl state restore --db /path/twinops.sqlite \
  --from /tmp/twinops-backup.sqlite

# Restart:
twinopsctl serve --example examples/assembly-line --db /path/twinops.sqlite
```

After restore, `GET /api/timeline` and `GET /api/audit` should show prior events.

## What is not in SQLite

- OpenUSD stage files under `--work-dir`
- MQTT broker state
- Streaming sidecar session (ephemeral)
- Helm / Kubernetes cluster state

Back those up separately if needed for a full lab rebuild.
