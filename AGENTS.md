# Repository guide

For anyone working in this repository, people and coding agents alike.

## Project

ReCriaLab is a mobile-first 3D fitting room for thrift-store clothes, live at https://recrialab.com. The
site (`site/`) is TypeScript and three.js with no framework, built with Bun and served as static assets
by a Cloudflare Worker (`site/wrangler.jsonc`). The garments are GLB models generated from photos and
fitted to a neutral mannequin by the Python tools in `tools/fit/`.

| Path | Contents |
|---|---|
| `site/` | the fitting room (`index.html`, `dressup.ts`), the About page (`sobre.html`, `about.ts`) and the tests (`*.test.ts`) |
| `site/assets/` | garments (GLB), body occlusion masks, layer tables, photos and thumbnails |
| `tools/fit/` | fitting the garments to the mannequin and measuring the result (Python 3) |
| `tools/visual-qa/` | measuring visual defects in renders of the mannequin from many angles |
| `tools/verify-site/` | Playwright scripts: emulated phones, layout, per-garment renders and visual QA renders |
| `tools/known-issues.yaml` | open fit issues; an exception above a limit must name one (see Conventions) |

## Commands

In `site/`:

```sh
bun install --frozen-lockfile
bun run dev      # http://localhost:3000
bun run check    # TypeScript of the site (tests and scripts run under Bun, outside the check)
bun run test     # unit and integrity tests
bun run build    # builds dist/ and writes the commit to build.json
```

From the repository root, after a build:

```sh
python3 -m pip install -r tools/fit/requirements.txt -r tools/visual-qa/requirements.txt
npm i -g playwright@1.56.1 && npx playwright install chromium webkit
node tools/verify-site/drive.mjs --profile budget-android   # the site on an emulated low-end Android
```

## Conventions

- Code, identifiers, comments, tests, CLI output and this guide are in English. The other docs and all
  on-screen text are in Brazilian Portuguese.
- Every fix comes with the test or measure that keeps the defect from coming back. Numeric limits live in
  the test itself; a limit is never raised to make a garment pass.
- A garment can stay outside a general limit in three ways:
  - a per-garment baseline, the recorded value, which may only go down (for example `BOTTOM_HOLES` in
    `tools/fit/poke_through.py` and `tools/fit/penetration.json`);
  - an exception above the limit, valid only while an open issue in `tools/known-issues.yaml` names the
    garment; the check verifies this (`site/fit.test.ts`, `tools/fit/stretch.py`,
    `tools/visual-qa/measure.py`), and the issue leaves the file in the change that fixes it;
  - in visual QA only, a defect accepted by a person, with a cap and a reason, under `_accepted` in
    `tools/visual-qa/defects.json`.
- Dictionaries, sets and lists of garments in `tools/` keep one item per line, so changes to different
  garments do not conflict (`site/one-per-line.test.ts`).
- Every Python import in `tools/` is in that folder's `requirements.txt` (`site/dependencies.test.ts`).
- Changing a 3D garment must not distort its print: compare front, side and back with the garment's
  photo (`node tools/verify-site/showcase.mjs --pieces 016`).

## Rules and checks

| Area | Rule | Check |
|---|---|---|
| Collection | 38 garments, each with a model, mask and pose; layer tables match the GLB hashes; size, triangles and textures within the phone budget; nothing left over in `assets/` | `site/integrity.test.ts` |
| Build | nothing left over in `dist/`, commit written to `/build.json` | `site/verify-dist.ts`, `site/check-live.ts` |
| Thumbnails | each selector thumbnail is the 3D garment rendered with the stage light; the test fails a thumbnail that is out of date with its GLB or tone | `site/thumbnails.test.ts` |
| Tops | rest on the shoulders, chest and nape; sleeves on the arm down to the wrist; hoods and collars lie on the back; the high collar of 035 sits outside the neck, closed as in the photo; no loose bits; the inside does not show from behind more than recorded; the arm clip under short sleeves never opens a slit to the background from a site camera | `site/fit.test.ts`, `tools/fit/hood.py`, `tools/fit/back_inside.py`, `tools/fit/sleeve.py` |
| Bottoms | waistband at the waist, no tear on the front, no loose cloth at the shin, no black texture patches, print not stretched, gap and penetration that only go down | `site/fit.test.ts`, `tools/fit/holes.py`, `tools/fit/cuff.py`, `tools/fit/texture.py`, `tools/fit/stretch.py`, `tools/fit/penetration.py` |
| Body and clothes | the body does not poke through the clothes or show hollow under them; torso, neck and arm clipped at the waistband, collar and sleeve hem line, with the same numbers in the shader and the generator | `tools/fit/poke_through.py`, `site/body-poses.test.ts` |
| Layering | the bottom is clipped at the top's hem, with no jagged edge and without poking through the top, in all 345 pairs; where the bottom is single-sided only its front faces count, in the tables and in the measure, as the site draws it | `tools/fit/layer_check.py`, `site/garment-hem.test.ts` |
| Visual QA | defects measured in 14 views around the mannequin, each garment worn with one from the other group (top or bottom) | `tools/visual-qa/measure.py` |
| Interface | the fitting room fits one screen; touch targets of at least 44 px and text of at least 13 px; nothing cut off or covered, from a small phone to desktop; the stage toolbar never covers the mannequin, also on the enlarged stage, which is taller than the normal one and keeps at least 3 pieces in view that dress on a tap | `tools/verify-site/layout.mjs` |
| Phones | a look opens from its link, swapping a garment works, the About page opens, colour stays close to the photo, no console errors, within time and data budgets on a low-end Android, a Pixel and an iPhone | `tools/verify-site/drive.mjs` |
| Text and accessibility | short garment names, no obvious instructions on screen, AA contrast | `site/ux.test.ts`, `site/a11y.test.ts` |
| Secrets | no committed keys | gitleaks in `.github/workflows/site-ci.yml` |

## Pull requests

Every pull request runs `.github/workflows/site-ci.yml` (check, tests, build, secrets and fit) and
`.github/workflows/site-e2e.yml` (emulated phones and visual QA). Both skip what the change does not
reach (`site/ci-filter.ts`). Before opening a pull request, run `bun run check`, `bun run test` and
`bun run build` in `site/`; if you changed a garment, render it (`tools/verify-site/showcase.mjs`) and
compare with the thrift-store photo. Merging into `main` deploys the site through Cloudflare Workers
Builds.
