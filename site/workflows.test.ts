// The workflows run without deprecation warnings: every action on a Node 24 release and every job on a pinned image.
import { test, expect } from 'bun:test';
import { readdirSync, readFileSync } from 'node:fs';

const DIR = new URL('../.github/workflows/', import.meta.url);
const workflows = readdirSync(DIR).filter(f => f.endsWith('.yml')).map(f => [f, readFileSync(new URL(f, DIR), 'utf8')]);

// First major of each action that runs on Node 24; older ones run on the deprecated Node 20 and warn on every job.
const NODE24: Record<string, number> = {
  'actions/checkout': 5,
  'actions/setup-node': 5,
  'actions/setup-python': 6,
  'actions/upload-artifact': 6,
  'gitleaks/gitleaks-action': 3,
  'oven-sh/setup-bun': 2,
};

test('every action is on a Node 24 release', () => {
  const old: string[] = [];
  for (const [f, text] of workflows) {
    for (const [, action, major] of text.matchAll(/uses:\s*([\w.-]+\/[\w.-]+)@v(\d+)/g)) {
      expect(NODE24[action!], `${action} in ${f}: add its first Node 24 major to NODE24`).toBeDefined();
      if (Number(major) < NODE24[action!]!) old.push(`${f}: ${action}@v${major}`);
    }
  }
  expect(old).toEqual([]);
});

test('every job runs on a pinned image, not on ubuntu-latest, which moves under the CI', () => {
  for (const [f, text] of workflows) {
    const images = [...text.matchAll(/runs-on:\s*(\S+)/g)].map(m => m[1]);
    expect(images.length, f).toBeGreaterThan(0);
    expect(images.filter(i => !/^ubuntu-\d\d\.\d\d$/.test(i!)), f).toEqual([]);
  }
});
