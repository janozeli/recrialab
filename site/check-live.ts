// After a deploy: confirms that recrialab.com serves exactly this commit.
const expected = process.env.GITHUB_SHA ?? Bun.spawnSync(['git', 'rev-parse', 'HEAD']).stdout.toString().trim();
for (const host of ['https://recrialab.com', 'https://www.recrialab.com']) {
  let seen = '';
  for (let attempt = 0; attempt < 10; attempt++) {
    const response = await fetch(`${host}/build.json`, { cache: 'no-store' }).catch(() => null);
    seen = response?.ok ? (await response.json()).commit : `HTTP ${response?.status ?? 'error'}`;
    if (seen === expected) break;
    await Bun.sleep(3000);
  }
  if (seen !== expected) {
    console.error(`${host} serves ${seen}, expected ${expected}`);
    process.exit(1);
  }
  console.log(`${host} ok: ${expected.slice(0, 7)}`);
}

// Visits are only counted if the published JS of each page carries the BEACON_TOKEN of analytics.ts (the dashboard's
// automatic injection does not apply to a Worker).
const { BEACON_TOKEN } = await import('./analytics');
for (const path of ['/', '/sobre']) {
  const page = `https://recrialab.com${path}`;
  const html = await fetch(page, { cache: 'no-store' }).then(r => r.text()).catch(() => '');
  const scripts = [...html.matchAll(/<script[^>]+src="([^"]+)"/g)].map(m => new URL(m[1], page).href);
  const bodies = await Promise.all(scripts.map(src => fetch(src).then(r => r.text()).catch(() => '')));
  if (!BEACON_TOKEN || !bodies.some(js => js.includes(BEACON_TOKEN))) {
    console.error(`${page}: published JS lacks the Web Analytics token; no visit is counted`);
    process.exit(1);
  }
  console.log(`${page} ok: Web Analytics counting`);
}
