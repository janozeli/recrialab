import { test, expect } from 'bun:test';
import { beaconAttrs } from './analytics';

test('the beacon loads only with a token and on the published domain', () => {
  expect(beaconAttrs('', 'recrialab.com')).toBeNull();
  expect(beaconAttrs('abc', 'localhost')).toBeNull();
  expect(beaconAttrs('abc', 'recrialab.com.evil.net')).toBeNull();
  for (const host of ['recrialab.com', 'www.recrialab.com']) {
    const attrs = beaconAttrs('abc', host);
    expect(attrs?.src).toBe('https://static.cloudflareinsights.com/beacon.min.js');
    expect(JSON.parse(attrs['data-cf-beacon']).token).toBe('abc');
  }
});
