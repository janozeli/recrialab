import { shortDate, lookHref, lookLabel, lookPieces } from './about-model';
import { startAnalytics } from './analytics';
import { ABOUT, type Link } from './about-data';

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
const profile = (l: Link) => h('a', { href: l.href, rel: 'noopener' }, l.label);

function workshops() {
  const list = [...ABOUT.workshops].sort((a, b) => a.date.localeCompare(b.date));
  return h('ol', { class: 'm-timeline' }, ...list.map(o => h('li', { class: 'm-workshop' },
    h('p', { class: 'm-date' }, h('time', { dateTime: o.date }, shortDate(o.date))),
    h('h3', {}, o.title),
    h('p', { class: 'm-place' }, o.place),
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

function team() {
  return h('div', {},
    h('p', { class: 'm-advisor' }, 'Orientação: ', h('strong', {}, ABOUT.advisor)),
    h('ul', { class: 'm-team' }, ...ABOUT.team.map(p =>
      h('li', {}, h('strong', {}, p.name), h('span', {}, p.role), p.link ? profile(p.link) : null))));
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
