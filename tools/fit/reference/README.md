# Modelos de referência

Cópias dos modelos 3D em etapas anteriores do ajuste. As ferramentas comparam a peça publicada com
elas, por exemplo para saber se a estampa esticou, e por isso elas ficam aqui como arquivos em vez de
depender do histórico do git. `manifest.json` tem o sha256 de cada arquivo, e `site/reference.test.ts`
reprova arquivo alterado, faltando ou sobrando.

## Originais

| Pasta | O que é | Quem usa |
|---|---|---|
| `originals/tripo/` | peças de baixo (001 a 015) como o Tripo entregou, só com menos triângulos e sem fragmentos soltos | `stretch.py` (verificação de estampa), `pant_leg_cloth.py` |
| `originals/before-hood/` | peças com capuz ou gola (030, 033 a 037) antes de rodar `hood.py` pela primeira vez (a 034 e a 036 já com a manga assentada por `cloth.py`, que roda antes de `hood.py`; a 036 com `--keep-side`, a partir da `before-hood/036.glb` anterior, sha256 9d284948…) | `hood.py` e `hood.py --check` (limite de encolhimento) |
| `originals/before-drape/` | peças de cima (016 a 038) e o short 008 antes de `drape.py` e `zipper.py` | `drape.py`, `zipper.py` |

## Calibração

`calibration/<caso>/before/` e `after/` guardam, nos mesmos caminhos de `site/assets/`, a peça como estava quando o
defeito foi visto e depois de consertada. `python3 tools/fit/calibration.py` põe cada estado no lugar do publicado,
roda as verificações do caso e devolve os arquivos; cada verificação tem de reprovar o antes e aprovar o depois.

| Caso | Defeito | Verificações que separam |
|---|---|---|
| `bridge-013/` | tira de tecido pendurada no vão entre as pernas da calça 013, descendo até o tênis | `cuff.py` (103,9 → 0 cm²); no pente fino, o corpo furando de 13,1 cm² cai abaixo do limite |
| `large-jackets/` | jaquetas 036 e 038 grandes demais para o corpo: manga passando dos dedos, barra no gancho | `site/fit.test.ts` (mangas no pulso e forro abaixo da barra) |

Ficaram de fora o quadrado branco na braguilha da 006 (o conserto veio do shader e do gerador da máscara, então o antes e
o depois guardados dão os mesmos números com o corpo de hoje) e as pontas sob o braço (máscaras feitas para o braço
antigo do manequim). `stretch.py` não separa a ponte da 013 (meio 11,0% → 5,4%, limite 15%): ela mede outra coisa, a
estampa esticada.
