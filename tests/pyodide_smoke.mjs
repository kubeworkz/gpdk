// Run the website's browser bundle in Pyodide, the way gridworkz.com does.
//
//   node tests/pyodide_smoke.mjs <bundle dir>
//
// Checks every browser file against its manifest hash, loads the Pyodide
// packages and wheels the manifest lists, unpacks the source, then:
// - reruns two published scenarios with no overrides and requires every
//   observation to equal the published value at the store's 15 digits;
// - reruns them with overrides and requires the results to move the right way.
// Needs the `pyodide` npm package; packages load from Pyodide's CDN.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadPyodide } from 'pyodide';

const bundle = process.argv[2];
if (!bundle) { console.error('usage: node tests/pyodide_smoke.mjs <bundle dir>'); process.exit(2); }
const read = (p) => readFileSync(join(bundle, p));
const manifest = JSON.parse(read('browser/manifest.json'));
let failed = 0;
const check = (ok, what) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${what}`); if (!ok) failed++; };

for (const f of [manifest.source, ...manifest.wheels]) {
  const sha = createHash('sha256').update(read(f.path)).digest('hex');
  check(sha === f.sha256, `${f.path} matches its manifest hash`);
}

const t0 = Date.now();
const py = await loadPyodide();
await py.loadPackage(manifest.pyodide_packages);
for (const f of [manifest.source, ...manifest.wheels]) py.FS.writeFile(`/tmp/${f.path.split('/').pop()}`, read(f.path));
py.globals.set('root', manifest.root);
py.globals.set('source', `/tmp/${manifest.source.path.split('/').pop()}`);
py.globals.set('wheels', manifest.wheels.map((w) => `/tmp/${w.path.split('/').pop()}`));
await py.runPythonAsync(`
import site, sys, zipfile
for w in wheels:
    zipfile.ZipFile(w).extractall(site.getsitepackages()[0])
zipfile.ZipFile(source).extractall(root)
sys.path.insert(0, root)
`);
console.log(`Pyodide ${py.version} ready in ${Date.now() - t0} ms`);

const run = async (id, overrides) => {
  py.globals.set('scenario', `${manifest.root}/${manifest.scenarios[id]}`);
  py.globals.set('overrides', JSON.stringify(overrides ?? null));
  const t = Date.now();
  const out = JSON.parse(await py.runPythonAsync(`
import json
from fabtwin.browser import run_scenario
json.dumps(run_scenario(scenario, json.loads(overrides)))`));
  return { out, ms: Date.now() - t };
};
const key = (o) => `${o.entity_type}|${o.entity_id}|${o.metric}`;
const value = (r, k) => r.observations.find((o) => key(o) === k)?.value;

for (const id of ['grx930_yield_wafer_map_28nm', 'g100_factory_28nm']) {
  const published = JSON.parse(read(`runs/${id}/observations.json`));
  const { out, ms } = await run(id);
  const mine = new Map(out.observations.map((o) => [key(o), o.value]));
  // The store writes values at 15 significant digits (fabtwin/run.py _number).
  const at15 = (v) => Number(Number(v).toPrecision(15));
  const same = published.length === mine.size && published.every((o) => mine.has(key(o)) && at15(mine.get(key(o))) === o.value);
  check(same, `${id}: ${mine.size} observations equal the published run (${ms} ms)`);
}

const base = (await run('grx930_yield_wafer_map_28nm')).out;
const worse = (await run('grx930_yield_wafer_map_28nm', { yield: { 'defects.density_per_cm2': 0.2 } })).out;
const k = 'wafer_map|grx930|die_yield_mean';
check(value(worse, k) < value(base, k), `higher defect density lowers die yield (${value(base, k)} -> ${value(worse, k)})`);

const fab = (await run('g100_factory_28nm', { factory: { 'tool_groups.litho.tools': 4 } })).out;
const u = 'tool_group|baseline:litho|tool_utilization';
check(value(fab, u) < 0.7, `a fourth scanner lowers baseline litho utilization (${value(fab, u)})`);

if (failed) { console.error(`${failed} check(s) failed`); process.exit(1); }
console.log('browser bundle runs in Pyodide and reproduces the published runs');
