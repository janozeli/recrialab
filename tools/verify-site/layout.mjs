// Layout and touch checks, measured on the real site (not in the CSS).

/** Extra screens besides the profile's device: small phone, landscape, tablet and desktop. */
export const SCREENS = {
  'small-phone': { viewport: { width: 360, height: 640 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
  'phone-landscape': { viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true, deviceScaleFactor: 3 },
  tablet: { viewport: { width: 820, height: 1180 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
  'desktop-1024': { viewport: { width: 1024, height: 700 } },
  'desktop-1366': { viewport: { width: 1366, height: 768 } },
};

/** Layout problems common to both pages. Runs inside the page. */
function commonProblems() {
  const out = [];
  const vw = innerWidth, vh = innerHeight;
  const visible = el => {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && +cs.opacity > 0
      && !el.closest('[hidden], [inert], .sr-only, dialog:not([open])');
  };
  const name = el => (el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder') || '').trim().replace(/\s+/g, ' ').slice(0, 40);
  if (document.documentElement.scrollWidth > vw + 1) out.push(`page scrolls sideways (${document.documentElement.scrollWidth} px in ${vw})`);
  const dialog = document.querySelector('dialog[open]');
  for (const el of document.querySelectorAll('button, a[href], input:not([type=file]), select, textarea, [role=button]')) {
    if (!visible(el)) continue;
    if (dialog && !dialog.contains(el)) continue;
    // An input inside a label is touched through the whole label, which is the target.
    const target = el.tagName === 'INPUT' && el.closest('label') ? el.closest('label') : el;
    const r = target.getBoundingClientRect();
    // Touch: 44 × 44 px (WCAG 2.5.5, Apple HIG).
    if (r.width < 43.5 || r.height < 43.5) out.push(`touch target ${Math.round(r.width)}×${Math.round(r.height)} px: "${name(el)}"`);
    // Off screen only counts inside a scrolling row.
    const scroller = el.closest('.clothes-grid');
    if (!scroller && (r.right > vw + 1 || r.left < -1 || r.bottom > vh + 1 || r.top < -1) && getComputedStyle(document.body).overflowY !== 'visible'
      && document.documentElement.scrollHeight <= vh + 1) out.push(`button off screen: "${name(el)}"`);
    // Covered by another element (for example the piece row over the buttons in fullscreen).
    const cx = Math.min(Math.max(r.left + r.width / 2, 1), vw - 1), cy = Math.min(Math.max(r.top + r.height / 2, 1), vh - 1);
    const box = scroller?.getBoundingClientRect();
    const inside = !box || (cx > box.left && cx < box.right && cy > box.top && cy < box.bottom);
    if (inside && cx > r.left && cx < r.right && cy > r.top && cy < r.bottom) {
      const top = document.elementFromPoint(cx, cy);
      if (top && !target.contains(top) && !top.contains(target)) out.push(`"${name(el)}" covered by ${top.tagName.toLowerCase()}.${top.className}`);
    }
  }
  const texts = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (texts.nextNode()) {
    const el = texts.currentNode.parentElement;
    if (!texts.currentNode.textContent.trim() || !el || seen.has(el) || el.closest('svg') || !visible(el)) continue;
    seen.add(el);
    if (dialog && !dialog.contains(el)) continue;
    const cs = getComputedStyle(el);
    if (parseFloat(cs.fontSize) < 13) out.push(`text at ${cs.fontSize}: "${name(el)}"`);
    // Text that does not fit its box.
    if (el.scrollWidth > el.clientWidth + 1 && cs.textOverflow !== 'ellipsis' && cs.display !== 'inline') out.push(`text cut off: "${name(el)}"`);
  }
  return [...new Set(out)];
}

/** Visible text over the mannequin, in any element (an instruction badge, a confirmation bubble after dressing).
 * Only the error notice may show there; the labels of the stage toolbar are controls, not text over the figure. */
function textOnStage() {
  const out = [];
  const texts = document.createTreeWalker(document.querySelector('#stage'), NodeFilter.SHOW_TEXT);
  while (texts.nextNode()) {
    const el = texts.currentNode.parentElement, t = texts.currentNode.textContent.trim();
    if (!t || !el.getBoundingClientRect().width || el.closest('.sr-only, [hidden], .stage-tools')) continue;
    let vis = true;
    for (let a = el; a; a = a.parentElement) { const cs = getComputedStyle(a); if (+cs.opacity === 0 || cs.visibility === 'hidden' || cs.display === 'none') vis = false; }
    if (vis && !/não foi possível|recarregue/i.test(t)) out.push(t.slice(0, 40));
  }
  return out;
}

/** Right after dressing a garment: nothing written over the mannequin. */
export async function auditStageOnDress(page) {
  return (await page.evaluate(textOnStage)).map(t => `text over the mannequin when dressing: "${t}"`);
}

/** Fitting room: a single screen, a large mannequin and garments in view at the same time, actions and About reachable. */
function fittingRoomProblems() {
  const out = [];
  const vw = innerWidth, vh = innerHeight;
  if (document.documentElement.scrollHeight > vh + 1) out.push(`fitting room scrolls vertically (${document.documentElement.scrollHeight} px in ${vh})`);
  const stage = document.querySelector('#stage').getBoundingClientRect();
  if (stage.top < -1 || stage.bottom > vh + 1 || stage.left < -1 || stage.right > vw + 1) out.push('stage goes off screen');
  // A large mannequin: in portrait the stage has at least half the height; in landscape, almost all of it.
  const minimum = vh > vw ? .5 : .7;
  if (stage.height < vh * minimum) out.push(`stage at ${Math.round(stage.height / vh * 100)}% of the height (minimum ${minimum * 100}%)`);
  const onScreen = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.left >= -1 && r.right <= vw + 1 && r.top >= -1 && r.bottom <= vh + 1; };
  const cards = [...document.querySelectorAll('#clothes-grid [data-piece]')].filter(onScreen).length;
  if (cards < 3) out.push(`only ${cards} whole garments in view next to the mannequin (minimum 3)`);
  for (const sel of ['#export-look', '#import-look', 'a[href="/sobre"]', '#zoom-stage', '#expand-stage', '[data-reset]']) {
    const el = document.querySelector(sel);
    if (!el || !onScreen(el)) out.push(`${sel} is not in view`);
  }
  // In view, but not highlighted: no background, no shadow, small type. Save and Open sit in the stage toolbar with no
  // border of their own; the About link may have a thin outline (the toolbar's family), never a fill.
  for (const [sel, border] of [['#export-look', 0], ['#import-look', 0], ['a[href="/sobre"]', 1.5]]) {
    const cs = getComputedStyle(document.querySelector(sel));
    const bg = cs.backgroundColor.match(/[\d.]+/g)?.map(Number) ?? [];
    if ((bg.length === 4 ? bg[3] : bg.length ? 1 : 0) > 0 || cs.boxShadow !== 'none' || parseFloat(cs.borderTopWidth) > border || parseFloat(cs.fontSize) > 18)
      out.push(`${sel} highlighted: background ${cs.backgroundColor}, shadow ${cs.boxShadow}, border ${cs.borderTopWidth}, type ${cs.fontSize}`);
  }
  return out;
}

/** The stage toolbar never covers the dressed figure (its screen box, written by dressup.ts in data-figure). */
function toolbarOverFigure() {
  const stage = document.querySelector('#stage'), tools = document.querySelector('#stage-tools');
  const figure = stage.dataset.figure?.split(' ').map(Number);
  if (!figure) return ['the stage does not report where the figure is (data-figure)'];
  const s = stage.getBoundingClientRect(), t = tools.getBoundingClientRect();
  const [x0, y0, x1, y1] = [figure[0] + s.left, figure[1] + s.top, figure[2] + s.left, figure[3] + s.top];
  const overlap = Math.min(x1, t.right) - Math.max(x0, t.left) > 0 && Math.min(y1, t.bottom) - Math.max(y0, t.top) > 0;
  return overlap ? [`the stage toolbar covers the mannequin (toolbar from x ${Math.round(t.left)}, figure up to x ${Math.round(x1)})`] : [];
}

/** Enlarged stage: a taller stage (a larger mannequin) with the pieces still in view and swappable, the toolbar clear of
 *  the figure, and Esc brings the page back. */
function expandedWardrobe() {
  const vw = innerWidth, vh = innerHeight;
  const onScreen = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.left >= -1 && r.right <= vw + 1 && r.top >= -1 && r.bottom <= vh + 1; };
  return {
    cards: [...document.querySelectorAll('#clothes-grid [data-piece]')].filter(onScreen).length,
    chips: [...document.querySelectorAll('#chips [data-slot]')].filter(onScreen).length,
    scroll: document.documentElement.scrollHeight > vh + 1,
  };
}

export async function auditExpandedStage(page) {
  const out = [];
  const stageHeight = () => page.evaluate(() => document.querySelector('#stage').getBoundingClientRect().height);
  const normal = await stageHeight();
  await page.locator('#expand-stage').click();
  await page.waitForTimeout(400);
  const expanded = await stageHeight();
  if (expanded < normal * 1.1) out.push(`enlarged stage ${Math.round(expanded)} px tall, normal ${Math.round(normal)} px (minimum +10%)`);
  const strip = await page.evaluate(expandedWardrobe);
  if (strip.cards < 3) out.push(`only ${strip.cards} whole garments in view on the enlarged stage (minimum 3)`);
  if (strip.chips < 2) out.push('the top and bottom tabs are not both in view on the enlarged stage');
  if (strip.scroll) out.push('the enlarged stage scrolls the page');
  out.push(...await page.evaluate(commonProblems), ...await page.evaluate(toolbarOverFigure));
  // Swapping a piece without leaving: the first visible garment not worn becomes worn.
  const card = page.locator('#clothes-grid [data-piece][aria-pressed="false"]:visible').first();
  const id = await card.getAttribute('data-piece');
  await card.click();
  try {
    await page.locator(`#clothes-grid [data-piece="${id}"][aria-pressed="true"]`).waitFor({ timeout: 20_000 });
  } catch { out.push(`tapping piece ${id} on the enlarged stage does not dress it`); }
  if (!(await page.evaluate(() => document.querySelector('.app').classList.contains('stage-expanded')))) out.push('swapping a piece leaves the enlarged stage');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
  if (await page.evaluate(() => document.querySelector('.app').classList.contains('stage-expanded'))) out.push('Esc does not leave the enlarged stage');
  if (!(await page.locator('#filters').isVisible())) out.push('the wardrobe does not come back after the enlarged stage');
  return out;
}

export async function auditFittingRoom(page) {
  return [...await page.evaluate(commonProblems), ...await page.evaluate(fittingRoomProblems), ...await page.evaluate(toolbarOverFigure),
    ...(await page.evaluate(textOnStage)).map(t => `text over the mannequin: "${t}"`)];
}

/** Filters by type (in place of search): "Saia" under EMBAIXO shows only the skirts. */
export async function auditFilters(page) {
  const out = [];
  await page.locator('#chips [data-slot="bottom"]').click();
  await page.locator('#filters [data-filter="Saia"]').click();
  const names = await page.$$eval('#clothes-grid [data-piece]', els => els.map(e => e.getAttribute('aria-label')));
  if (!names.length || names.some(n => !/saia/i.test(n))) out.push(`the Saia filter showed [${names}]`);
  out.push(...await page.evaluate(commonProblems));
  await page.locator('#filters [data-filter="Saia"]').click();
  const all = await page.locator('#clothes-grid [data-piece]').count();
  if (all <= names.length) out.push('tapping the active filter does not show everything again');
  if (await page.locator('input[type=search]').count()) out.push('a search field is present: the collection uses filters');
  await page.locator('#chips [data-slot="top"]').click();
  return out;
}

export async function auditAbout(page) {
  const out = await page.evaluate(commonProblems);
  const back = page.locator('a[href="/"]:visible', { hasText: /provador/i });
  if (!(await back.count())) out.push('about page without a visible link reading "provador"');
  // Real content only: no sample badge nor placeholder ("… entram aqui").
  const empty = await page.locator('main :visible', { hasText: /\bexemplo\b|entram? aqui|em breve/i }).count();
  if (empty) out.push('about page with sample content or a placeholder');
  // Team: every entry the same height, so the grid stays even whatever the length of the role.
  const heights = await page.$$eval('.m-team-group li', els => els.map(e => ({ h: Math.round(e.getBoundingClientRect().height), name: e.querySelector('strong')?.textContent })));
  const tallest = Math.max(...heights.map(x => x.h)), shortest = Math.min(...heights.map(x => x.h));
  if (!heights.length) out.push('about page without the team');
  else if (tallest - shortest > 1) out.push(`team entries of different heights (${shortest} to ${tallest} px): ${heights.filter(x => x.h !== shortest).map(x => x.name).join(', ')}`);
  // The role rows are reserved, so a longer role would spill over the next entry without changing the height.
  const spilled = await page.$$eval('.m-team-group li span', els => els.filter(e => e.scrollHeight > e.clientHeight + 1).map(e => e.textContent));
  if (spilled.length) out.push(`team roles longer than their two lines: ${spilled.join(', ')}`);
  return out;
}
