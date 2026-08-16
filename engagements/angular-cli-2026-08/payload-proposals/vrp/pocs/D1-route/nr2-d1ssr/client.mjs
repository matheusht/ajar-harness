// node http client (curl-independent)
const base = 'http://localhost:50881';
for (const p of ['/dashboard', '/y', '/']) {
  try {
    const r = await fetch(base + p);
    const d = await r.json();
    console.log(`GET ${p} -> markerFired=${d.markerFired} marker=${d.attackerMarker} routes=[${d.routes}]`);
  } catch (e) { console.log(`GET ${p} -> FAIL ${e.message}`); }
}
