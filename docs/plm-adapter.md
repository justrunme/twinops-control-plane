# Mock PLM adapter

TwinOps keeps PLM integration **vendor-neutral**. Milestone demos use a JSON
catalog + CLI instead of Teamcenter / Windchill / etc.

## Catalog

```text
examples/assembly-line/plm-catalog.json
```

Each item maps `itemId` → revision / lifecycle / OpenUSD prim.

## CLI

```bash
make install

# list catalog
twinopsctl plm show --example examples/assembly-line

# compare catalog vs twin.yaml
twinopsctl plm compare --example examples/assembly-line

# engineering change on Robot01
twinopsctl plm bump 1004711 --example examples/assembly-line
twinopsctl plm compare --example examples/assembly-line

# write catalog → twin.yaml (review the diff!)
twinopsctl plm sync --example examples/assembly-line --dry-run
twinopsctl plm sync --example examples/assembly-line

# emit PLM-only desired fragment
twinopsctl plm desired --example examples/assembly-line --out /tmp/plm-desired.yaml
```

## Demo flow

Safe one-command demo (temp copy, does not mutate the repo):

```bash
make plm-demo
```

Manual flow:

1. `plm bump 1004711` → catalog revision C→D  
2. `plm compare` → DRIFT vs manifest  
3. `plm sync` → manifest catches up  
4. `twinopsctl build` / `make drift` → OpenUSD overlays reflect the new revision  

## Non-goals

- No proprietary PLM SDK bindings yet
- Catalog is the mock system of record for demos only
