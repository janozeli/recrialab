/**
 * Cloudflare Web Analytics: counts visits to the site.
 * No cookie and no personal data. The token comes from the dashboard (Web Analytics > recrialab.com) and is
 * public: it ships in the HTML of any site that uses the beacon. When empty, nothing is loaded.
 */
export const BEACON_TOKEN = '6ed43d34957a49fcb90ec8e43f7db523'; // gitleaks:allow (public beacon token, shipped in the JS of any site)

const BEACON_SRC = 'https://static.cloudflareinsights.com/beacon.min.js';

/** Counts only on the published domain; localhost and previews stay out of the report. */
export function beaconAttrs(token: string, hostname: string): Record<string, string> | null {
  if (!token || !/(^|\.)recrialab\.com$/.test(hostname)) return null;
  return { src: BEACON_SRC, 'data-cf-beacon': JSON.stringify({ token, spa: false }) };
}

/** Loads the beacon after `load`, so it does not compete for bandwidth with the mannequin on a phone. */
export function startAnalytics(token = BEACON_TOKEN) {
  const attrs = beaconAttrs(token, location.hostname);
  if (!attrs) return;
  const inject = () => {
    const script = document.createElement('script');
    script.defer = true;
    for (const [name, value] of Object.entries(attrs)) script.setAttribute(name, value);
    document.head.append(script);
  };
  if (document.readyState === 'complete') inject();
  else addEventListener('load', inject, { once: true });
}
