# Synthetic MES replay fixture

Two fab lots and their OSAT split/merge flow, generated deterministically by:

```bash
python -m fabtwin mes-synth --out factory/mes_smoke \
  --seed 20261106 --lots 2 --days 6
```

The manifest labels every file `evidence_class: assumed`, `synthetic: true`
and `measured: false`. The scenario `scenarios/mes_line_replay.yaml` verifies
the manifest hashes, byte counts, row counts and column contracts before it
derives cycle time, queue time, WIP, throughput and tool utilization from the
event timestamps.

These files are a test fixture. Do not register them in the catalog and do not
cite them as measured line data. Regenerate the directory rather than editing
a CSV by hand; a changed file without a matching manifest hash is rejected.

For a provider extract, use `python -m fabtwin mes-manifest` and the
[ingest checklist](../../docs/mes-ingest-checklist.md). Do not relax this
fixture's manifest or treat it as the measured template. Check the fixture
with `python -m fabtwin mes-check factory/mes_smoke/manifest.json --no-report`
so no acceptance report is written into this directory.
