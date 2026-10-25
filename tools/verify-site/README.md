# Testes em celular

Scripts Playwright que usam o build real do site como uma pessoa no celular e salvam capturas de tela e
um relatório. Servem `site/dist/` numa porta local; rode `cd site && bun run build` antes.

```sh
npm i -g playwright@1.56.1 && npx playwright install chromium webkit
node tools/verify-site/drive.mjs --profile budget-android
```

## `drive.mjs`: o site no celular

```sh
node tools/verify-site/drive.mjs [--profile pixel|budget-android|iphone] [--look 004.024] \
  [--url https://recrialab.com] [--out pasta]
```

| Perfil | Motor | Emula | Reprova se |
|---|---|---|---|
| `budget-android` | Chromium | Moto G4, CPU 4× mais lenta, 4G lento (1,6 Mbps, 150 ms) | manequim > 30 s, look completo > 60 s, > 10 MB |
| `pixel` | Chromium | Pixel 7 | manequim > 15 s, look completo > 30 s, > 20 MB |
| `iphone` | WebKit | iPhone 13 | manequim > 15 s, look completo > 30 s, > 20 MB |

O script abre um look pelo link, troca uma peça e confere o link novo, abre a página Sobre, lê
`/build.json` (commit igual ao `HEAD` e sem mudanças locais), compara a saturação de uma peça de
referência (a bermuda laranja 015) com a foto e reprova qualquer erro de console ou requisição falha. No
`pixel` ele também roda `layout.mjs` em celular pequeno, deitado, tablet e desktop. Capturas e relatório
ficam em `site/verify-out/<perfil>/`: `1-look.png`, `2-swap.png`, `3-about.png`, `screen-*.png` e
`report.json`.

FPS e tarefas longas saem no relatório, mas não reprovam: o CI desenha WebGL por software.

## `layout.mjs`: tela e toque

Medido na página real, não no CSS: provador numa tela só, palco com pelo menos metade da altura (70%
deitado), pelo menos 3 peças à vista junto dele, Salvar, Abrir e Sobre sempre à vista, como links
discretos (sem fundo, sombra nem borda), nenhum texto sobre o manequim além de aviso de erro, alvos de
toque de no mínimo 44 px, texto de no mínimo 13 px, nada cortado, coberto ou fora da tela.

## `showcase.mjs`: fotos de cada peça

`node tools/verify-site/showcase.mjs [--pieces 016,031] [--crop collar]`

Veste cada peça no build e fotografa frente, perfil e costas, uma linha por peça em
`site/verify-out/showcase/showcase.png`. Serve para comparar com as fotos dos brechós depois de
mexer numa peça.

## `visual-qa.mjs`: fotos da inspeção visual

```sh
node tools/verify-site/visual-qa.mjs [--plan all|ci|pairs] [--looks 016,004.016] [--changed 008] \
  [--part 0/4] [--beauty]
```

Fotografa cada look de 14 pontos em volta do manequim (8 na altura do peito, 4 de baixo, 2 de cima) com
as máscaras e camadas do site e guarda, por vista, a máscara de classes, a profundidade da roupa e a
textura sem luz. `tools/visual-qa/measure.py` mede os defeitos nessas fotos (veja o README da pasta).
