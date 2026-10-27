# Inspeção visual

Procura o que faz uma peça parecer errada nas fotos que `tools/verify-site/visual-qa.mjs` tira do site
rodando. Cada medida busca um tipo de defeito em 14 vistas por look, em volta do manequim: frente,
perfil, costas, de baixo e de cima.

```sh
python3 -m pip install -r tools/visual-qa/requirements.txt
npm i -g playwright@1.56.1 && npx playwright install chromium   # uma vez
cd site && bun run build && cd ..
node tools/verify-site/visual-qa.mjs --plan ci
python3 tools/visual-qa/measure.py site/verify-out/visual-qa        # tabela por look
python3 tools/visual-qa/measure.py site/verify-out/visual-qa --ci   # reprova defeito novo ou já resolvido
```

## Medidas

O limite vale para toda peça, na pior das 14 vistas (`LIMITS` em `measure.py`):

| Medida | Reprova acima de | O que é |
|---|---|---|
| `midriff` | 20 cm² | tronco à vista entre a peça de cima e a de baixo |
| `junction` | 6 cm² | borda serrilhada da peça de baixo logo abaixo da barra da de cima |
| `threads` | 12 cm² | pontas finas soltas: franja pontuda, fio, barra serrilhada |
| `pokes` | 2 cm² | corpo atravessando a roupa, com o tecido logo atrás dele |
| `tear` | 4 cm² | corpo visto por um furo ou rasgo (o braço subindo na manga, visto de baixo pela barra a até 1 cm do braço de fora, não conta) |
| `see_through` | 4 cm² | fundo à vista onde o corpo estaria |
| `arm_gap` | 4 cm² | fundo à vista onde o braço estaria, do cotovelo à axila, sem exigir roupa em volta (a fenda sob a manga curta, aberta embaixo); faixa com menos de 5 px de largura no contorno não conta |
| `loose` | 1 cm² | pedaço de roupa solto no ar |
| `dark_patch` | 6% | textura mais escura que o mais escuro da foto da peça |
| `waistband` | 4 cm | cós afundado no meio em relação às laterais |
| `tone` | 15% | brilho visto de frente diferente do da foto da peça |

## Defeitos conhecidos

`defects.json` lista, por medida, os looks que ainda passam do limite. Cada um aponta um problema em
aberto de `tools/known-issues.yaml` ou fica em `_accepted`, com quem aceitou e um limite (o que a foto da
peça já tem, como pele por um rasgo). Com `--ci`, defeito fora da lista reprova, e defeito listado que
sumiu também: tire-o da lista na mesma mudança que o resolveu.

## Tom das peças

`tone.py` compara o brilho de cada peça no palco com a foto e grava o ajuste de cor de cada peça em
`site/garment-tones.ts` (`--fit`). Usa as fotos de `visual-qa.mjs --beauty` com as 38 peças.
