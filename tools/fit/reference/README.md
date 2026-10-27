# Modelos de referência

Cópias dos modelos 3D em etapas anteriores do ajuste. As ferramentas comparam a peça publicada com
elas, por exemplo para saber se a estampa esticou, e por isso elas ficam aqui como arquivos em vez de
depender do histórico do git. `manifest.json` tem o sha256 de cada arquivo, e `site/reference.test.ts`
reprova arquivo alterado, faltando ou sobrando.

## Originais

| Pasta | O que é | Quem usa |
|---|---|---|
| `originals/tripo/` | peças de baixo (001 a 015) como o Tripo entregou, só com menos triângulos e sem fragmentos soltos; a 014 como `project_print.py` a montou (a estampa é pintada nessa forma) | `stretch.py` (verificação de estampa), `pant_leg_cloth.py` |
| `originals/tripo-shape/` | a forma da 014 que o Tripo gerou vestida no manequim neutro, sem textura, reduzida a 60 mil triângulos (geração paga autorizada pela dona do projeto em 26/10/2026: três image-to-image de 15 créditos e um multiview-to-model de 20, 65 créditos) | `project_print.py` |
| `originals/print-source/` | a 014 que o Tripo gerou da foto antes (a de `originals/tripo/` até então), de onde vem a estampa | `project_print.py`, `print_check.py` (verificação da estampa projetada) |
| `originals/before-hood/` | peças com capuz ou gola (030, 033 a 037) antes de rodar `hood.py` pela primeira vez (a 034 e a 036 já com a manga assentada por `cloth.py`, que roda antes de `hood.py`; a 036 com `--keep-side`, a partir da `before-hood/036.glb` anterior, sha256 9d284948…) | `hood.py` e `hood.py --check` (limite de encolhimento) |
| `originals/before-drape/` | peças de cima (016 a 038) e o short 008 antes de `drape.py` e `zipper.py` | `drape.py`, `zipper.py` |

## Calibração

`calibration/<caso>/before/` e `after/` guardam, nos mesmos caminhos de `site/assets/`, a peça como estava quando o
defeito foi visto e depois de consertada. `python3 tools/fit/calibration.py` roda as verificações do caso numa cópia
temporária do repositório, com cada estado no lugar do publicado (`site/assets/` não é tocado); cada verificação tem
de reprovar o antes e aprovar o depois. Roda no CI, no job `fit`: quando uma trava aperta e o depois deixa de passar,
o PR que apertou fica vermelho e atualiza o depois.

| Caso | Defeito | Verificações que separam |
|---|---|---|
| `bridge-013/` | tira de tecido pendurada no vão entre as pernas da calça 013, descendo até o tênis | `cuff.py 013` (103,9 → 0 cm²) |
| `hip-014/` | quadril da calça 014 do lado de fora da barra das peças de cima: as tabelas de camadas o esconderam em fiapos que mostravam o fundo, e o cós furava as blusas | `layer_check.py` nos 23 pares da 014: por peça, a soma dos pares contra `layer_baseline.json` (8.859 → 2.248 pontas; nenhum par passava de 1.500) |
| `projected-014/` | calça 014 refeita no manequim neutro: barra moldada sobre o tênis como polaina, listras laterais mais largas, quebradas onde o quadril encontra as pernas, e as listras da outra perna no lado de dentro | `shoe.py 014` (158 → 1,0 cm²); `print_check.py 014` (largura ×1,13 e ×1,30 → ×0,93; quebra 36 e 27 → 3,4 e 7,3 mm; branco por dentro 3,3 e 3,8% → 0%) |
| `waistband-004/` | cós de trás da calça 004, vestida inteira como tecido, escorregou 1,4 cm pela lombar e dobrou, com o avesso escuro à vista; a região da cintura do `stretch.py` deixava passar | `stretch.py 004`: por setor de 30° do cós, a borda desceu 1,4 cm (limite 0,5) e os 7 cm de cima esticaram 33% (limite 30) |
| `large-jackets/` | jaquetas 036 e 038 grandes demais para o corpo: manga passando dos dedos, barra no gancho | `site/fit.test.ts`: `-t 'long sleeves'` pega os dois testes de manga (no braço de perfil e terminando no pulso); `-t 'no lining hanging'`, o forro abaixo da barra |

Estado de cada arquivo:

| Arquivo | Estado |
|---|---|
| `bridge-013/before/` | a 013 com a ponte, como foi vista |
| `bridge-013/after/` | a 013 logo depois do conserto da ponte; não é a publicada, que mudou depois |
| `hip-014/before/` | a 014 de uma rodada de conserto que não foi publicada, com a tabela de camadas e a máscara dela |
| `hip-014/after/` | iguais aos publicados |
| `projected-014/before/` | a 014 com a barra moldada sobre o tênis e as listras largas e quebradas, como foi vista |
| `projected-014/after/` | GLB igual ao publicado |
| `waistband-004/before/` | a 004 da primeira versão vestida inteira, como foi vista |
| `waistband-004/after/` | GLB igual ao publicado |
| `large-jackets/before/` | 036 e 038 grandes demais, como foram vistas |
| `large-jackets/after/` 036 | a 036 publicada com a manga vestida como tecido e o punho sobre a palma |
| `large-jackets/after/` 038 | GLB igual ao publicado; máscaras da época do conserto |

Ficaram de fora o quadrado branco na braguilha da 006 (o conserto veio do shader e do gerador da máscara, então o antes e
o depois guardados dão os mesmos números com o corpo de hoje) e as pontas sob o braço (máscaras feitas para o braço
antigo do manequim). `stretch.py` não separa a ponte da 013 (meio 11,0% → 5,4%, limite 15%): ela mede outra coisa, a
estampa esticada.
