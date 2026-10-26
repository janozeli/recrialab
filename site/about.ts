import { shortDate, lookHref, lookLabel, lookPieces } from './about-model';
import { startAnalytics } from './analytics';
import { ABOUT, TEAM_AREAS, type Link } from './about-data';

/** Static page: no three.js, only HTML and the photos of the catalog pieces. */
function h<K extends keyof HTMLElementTagNameMap>(
  tag: K, props: Partial<HTMLElementTagNameMap[K]> & { class?: string } = {}, ...children: (Node | string | null)[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  const { class: cls, ...rest } = props;
  if (cls) el.className = cls;
  Object.assign(el, rest);
  for (const child of children) if (child !== null) el.append(child);
  return el;
}

const withLabel = <T extends Element>(el: T, label: string) => (el.setAttribute('aria-label', label), el);
/** Map pin before the place: read at a glance, with no "Local:" label. */
function pin() {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = '<path d="M12 21s-6-5.5-6-11a6 6 0 0 1 12 0c0 5.5-6 11-6 11z"/><circle cx="12" cy="10" r="2"/>';
  return svg;
}
const profile = (l: Link) => h('a', { href: l.href, rel: 'noopener' }, l.label);

function workshops() {
  const list = [...ABOUT.workshops].sort((a, b) => a.date.localeCompare(b.date));
  return h('ol', { class: 'm-timeline' }, ...list.map(o => h('li', { class: 'm-workshop' },
    h('header', { class: 'm-workshop-head' },
      h('p', { class: 'm-date' }, h('time', { dateTime: o.date }, shortDate(o.date))),
      h('h3', {}, o.title),
      h('p', { class: 'm-place' }, pin(), o.place)),
    h('p', {}, o.text),
    o.photos?.length ? h('div', { class: 'm-photos' }, ...o.photos.map(f =>
      h('img', { src: f.src, alt: f.alt, loading: 'lazy', decoding: 'async' }))) : null,
    o.links?.length ? h('ul', { class: 'm-profiles' }, ...o.links.map(l => h('li', {}, profile(l)))) : null,
    o.audio ? h('figure', { class: 'm-audio' },
      h('audio', { src: o.audio.src, controls: true, preload: 'none' }),
      h('figcaption', {}, o.audio.caption)) : null,
  )));
}

function looks() {
  return h('ul', { class: 'm-looks' }, ...ABOUT.looks.map(l => h('li', { class: 'm-look' },
    withLabel(h('a', { href: lookHref(l.look), class: 'm-look-link' },
      h('span', { class: 'm-pieces' }, ...lookPieces(l.look).map(p =>
        h('img', { src: p.photo, alt: p.name, loading: 'lazy', decoding: 'async', width: 160, height: 160 }))),
      h('span', { class: 'm-label' }, lookLabel(l.look)),
    ), `${lookLabel(l.look)}, abrir no provador`),
    h('p', { class: 'm-credit' }, l.credit),
    l.note ? h('p', { class: 'm-note' }, l.note) : null,
    h('ul', { class: 'm-names' }, ...lookPieces(l.look).map(p => h('li', {}, p.name))),
  )));
}

function editorial() {
  return h('div', { class: 'm-photos m-editorial' }, ...ABOUT.editorial.map(f =>
    h('img', { src: f.src, alt: f.alt, loading: 'lazy', decoding: 'async' })));
}

/** Every entry has the same two rows, name and role, so the grid stays even (about.css). */
const member = (name: string, role: string) => h('li', {}, h('strong', {}, name), h('span', {}, role));

function team() {
  return h('div', { class: 'm-team-groups' },
    h('ul', { class: 'm-team m-advisor' }, member(ABOUT.advisor, 'Orientação')),
    ...TEAM_AREAS.map(area => h('div', { class: 'm-team-group' },
      h('h3', {}, area),
      h('ul', { class: 'm-team' }, ...ABOUT.team.filter(p => p.area === area).map(p => member(p.name, p.role))))));
}

/** A section without real records stays hidden: no placeholder and no made-up example. */
function fill(id: string, entries: unknown[], build: () => Node) {
  if (!entries.length) return;
  const section = document.querySelector<HTMLElement>(`#${id}`)!;
  section.append(build());
  section.hidden = false;
}

fill('events', ABOUT.workshops, workshops);
fill('looks', ABOUT.looks, looks);
fill('editorial', ABOUT.editorial, editorial);
document.querySelector('#team')!.append(team());
startAnalytics();
