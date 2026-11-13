# Modelos de referência

Cópias dos modelos 3D em etapas anteriores do ajuste. As ferramentas comparam a peça publicada com
elas, por exemplo para saber se a estampa esticou, e por isso elas ficam aqui como arquivos em vez de
depender do histórico do git. `manifest.json` tem o sha256 de cada arquivo, e `site/reference.test.ts`
reprova arquivo alterado, faltando ou sobrando.

## Originais

| Pasta | O que é | Quem usa |
|---|---|---|
| `originals/tripo/` | peças de baixo (001 a 015) como o Tripo entregou, só com menos triângulos e sem fragmentos soltos; a 014 como `project_print.py` a montou (a estampa é pintada nessa forma) | `stretch.py` (verificação de estampa), `pant_leg_cloth.py` |
| `originals/tripo-shape/` | a forma da 014 e da 006 que o Tripo gerou vestida no manequim neutro, sem textura, reduzida a 60 mil triângulos (gerações pagas autorizadas pela dona do projeto, 65 créditos cada: a 014 em 26/10/2026 e a 006 em 27/10/2026; três image-to-image de 15 créditos e um multiview-to-model de 20); a da 030 da mesma forma, sobre a pose B, com até 60 mil triângulos (piloto autorizado em 27/10/2026, 65 créditos) | `project_print.py` (014, 006), `project_top.py` (030), `sleeve_tear.py` (peça refeita: a malha do main não é o antes dela) |
| `originals/tripo-views/` | as três vistas (frente, lado esquerdo, costas) que o Tripo gerou da 030 vestida nos renders do manequim neutro, de onde saiu a forma acima: a estampa é pintada a partir delas | `project_top.py` |
| `originals/print-source/` | a 014 e a 006 que o Tripo gerou da foto antes (as de `originals/tripo/` até então), de onde vem a estampa; a 030 publicada antes de ser refeita, de onde vem a cor do que nenhuma vista mostra | `project_print.py`, `print_check.py` (verificação da estampa projetada), `project_top.py` |
| `originals/before-hood/` | peças com capuz ou gola (033 a 037) antes de rodar `hood.py` pela primeira vez (a 034 e a 036 já com a manga assentada por `cloth.py`, que roda antes de `hood.py`; a 033 com o lado de dentro da manga esquerda e a lateral afastados do braço por `arm_clear.py`, o mesmo deslocamento da peça publicada; a 036 com `--keep-side`, a partir da `before-hood/036.glb` anterior, sha256 9d284948…) | `hood.py` e `hood.py --check` (limite de encolhimento) |
| `originals/before-drape/` | peças de cima (016 a 038) e o short 008 antes de `drape.py` e `zipper.py` | `drape.py`, `zipper.py` |

## Calibração

`calibration/<caso>/before/` e `after/` guardam, nos mesmos caminhos de `site/assets/`, a peça como estava quando o
defeito foi visto e depois de consertada. `python3 tools/fit/calibration.py` roda as verificações do caso numa cópia
temporária do repositório, com cada estado no lugar do publicado (`site/assets/` não é tocado); cada verificação tem
de reprovar o antes e aprovar o depois. Roda no CI, no job `fit`: quando uma trava aperta e o depois deixa de passar,
o PR que apertou fica vermelho e atualiza o depois. Os casos medidos nas fotos do site (`calibration.py --visual`, com `measure.py`) montam o site e o fotografam na cópia, e rodam no job `visual-qa`.

| Caso | Defeito | Verificações que separam |
|---|---|---|
| `arm-stump-022/` | a 022 publicada antes do recorte do braço na barra da manga: a manga 5 cm à frente do braço e a máscara escondendo o braço em triângulos longos, que sob a manga acabava num toco serrilhado com o fundo à vista | `poke_through.py 022`: furos 15.957 → 3.688 raios (teto da 022 em `TOP_HOLES`); nas fotos do site (`--visual`), `measure.py --ci` no look 007.022: o antes reprova em fenda do braço (`arm_gap`) 28,2 cm² (vista eye-180, limite 4); o depois fica dentro dos limites |
| `bridge-013/` | tira de tecido pendurada no vão entre as pernas da calça 013, descendo até o tênis | `cuff.py 013` (103,9 → 0 cm²) |
| `hip-014/` | quadril da calça 014 do lado de fora da barra das peças de cima: as tabelas de camadas o esconderam em fiapos que mostravam o fundo, e o cós furava as blusas | `layer_check.py` nos 23 pares da 014: por peça, a soma dos pares contra `layer_baseline.json` (8.859 → 2.248 pontas; nenhum par passava de 1.500); nas fotos do site (`--visual`), `measure.py --ci` nos looks 014.022 e 014.035: o antes reprova em pedaço solto 2,4 cm² na 014.022 (vista eye-90) e corpo furando 13,6 cm² na 014.035 (vista high-0); o depois fica dentro dos limites |
| `projected-014/` | calça 014 refeita no manequim neutro: barra moldada sobre o tênis como polaina, listras laterais mais largas, quebradas onde o quadril encontra as pernas, e as listras da outra perna no lado de dentro | `shoe.py 014` (158 → 1,0 cm²); `print_check.py 014` (largura ×1,13 e ×1,30 → ×0,93; quebra 36 e 27 → 3,4 e 7,3 mm; branco por dentro 3,3 e 3,8% → 0%) |
| `hem-hole-002/` | furo de 9,6 cm na barra da calça 002, deixado pelo gerador: vestida como tecido, o corpo aparece por ele de trás, e a 002 do main o tinha e passava em tudo | `close_holes.py --check 002` (1 → 0 furos na barra) |
| `waistband-004/` | cós de trás da calça 004, vestida inteira como tecido, escorregou 1,4 cm pela lombar e dobrou, com o avesso escuro à vista; a região da cintura do `stretch.py` deixava passar | `stretch.py 004`: por setor de 30° do cós, a borda desceu 1,4 cm (limite 0,5) e os 7 cm de cima esticaram 33% (limite 30) |
| `torn-sleeve-022/` | 63 faces tiradas da manga direita da 022, de 2 a 9 cm acima da barra: o recorte do braço por vista tira o braço de vista atrás do rasgo, e só o braço recortado sem pano na frente o denuncia | `poke_through.py 022`: furos acima do teto de `TOP_HOLES`; `sleeve_tear.py 022`: 63 faces de área zero, borda aberta 288,2 → 423,5 cm |
| `hem-hole-030/` | a 030 refeita no manequim neutro, primeira passada: furo de 25 cm acima da barra da frente onde o forro foi apagado, e uma tira do antebraço gerado pendurada no punho esquerdo até 1,11 m | `sleeve_tear.py 030`: borda aberta 409,8 cm, 301 arestas e 5 laços → 327,5, 285 e 4 |
| `torn-sleeve-020/` | 17 faces da manga direita da 020 com área zero, de 0,4 a 3,2 cm acima da barra: de baixo, o braço atrás do rasgo parece o braço subindo na manga, que a medida visual deixa de fora | `sleeve_tear.py 020`: 17 faces de área zero |
| `cuff-tip-021/` | ponta do punho esquerdo da 021 pendurada 4 cm abaixo da borda, um V bege sobre o braço | `cuff_tip.py --check` |
| `slit-033/` | fenda para o fundo entre a manga esquerda da jaqueta 033 e a lateral, onde o braço escondido estaria, vista de frente com o short 003 | nas fotos do site (`--visual`), `measure.py --ci` no look 003.033: o antes reprova em fenda do braço (`arm_gap`) 5,2 cm² (limite 4); o depois mede 0 |
| `notch-016/` | uma face de 0,7 cm² tirada da barra da frente da 016: a borda aberta ganha uma aresta e menos de 0,05 cm, que só os cm arredondavam para o mesmo valor | `sleeve_tear.py 016`: 101 → 102 arestas de borda |
| `cords-009/` | cordões pendurados na frente da saia 009, que o 3D desenhou onde a foto tem botões | `cords.py --measure --max 10` (203,4 cm² → abaixo de 10) |
| `inside-body-007/` | saia 007 como o Tripo a fez no manequim dele: 5,4% do corpo neutro coberto fica dentro dela, 13,8% no quadril | `penetration.py` contra `penetration.json` (5,4 → 0,1%); `poke_through.py 007` (43 → 3 pontas, limite 30) |
| `inside-body-006/` | jeans 006 como o Tripo os fez no manequim dele: 13,9% do corpo neutro coberto fica dentro deles, 82,9% na cintura | `penetration.py` contra `penetration.json` (13,9 → 0%); `poke_through.py 006` (248 → 9 pontas, limite 30) |
| `midriff-006/` | tronco à vista entre os jeans 006 e as peças curtas 016 e 020: o cós do 006 do Tripo ficava dentro do corpo, e a máscara cortava o tronco numa linha que o pano não alcançava | nas fotos do site (`--visual`), `measure.py --ci` nos looks 006.016 e 006.020: o antes reprova em barriga 77,7 cm² na 006.016 (vista low-0) e 98,0 na 006.020 (low-180), e em rasgo 8,2 na 006.020; o depois fica dentro dos limites |
| `large-jackets/` | jaquetas 036 e 038 grandes demais para o corpo: manga passando dos dedos, barra no gancho | `site/fit.test.ts`: `-t 'long sleeves'` pega os dois testes de manga (no braço de perfil e terminando no pulso); `-t 'no lining hanging'`, o forro abaixo da barra; `layer_check.py` nos 30 pares das duas: o corpo fura 036 em 13.556 pontas somadas e 038 em 13.441 (com a 006 regerada no manequim neutro) (linhas de base 3.685 e 6.438); `back_inside.py`: o avesso visto de trás 206 cm² na 036 e 22 na 038 (registrados 116 e 18); nas fotos do site (`--visual`), `measure.py --ci` nos looks 006.036 e 008.038: com as tabelas de camadas do 006 e do 008 geradas para as jaquetas de antes, o antes reprova em pedaço solto 1,5 cm² na 006.036 e junção 8,4 na 008.038; o depois fica dentro dos limites |

Estado de cada arquivo:

| Arquivo | Estado |
|---|---|
| `arm-stump-022/before/` | a 022 e as máscaras dela antes do recorte na barra da manga (sem `sleeve_line`); tabela de camadas do 007 com o par da 022 gerado para essa 022 |
| `arm-stump-022/after/` | iguais aos publicados |
| `bridge-013/before/` | a 013 com a ponte, como foi vista |
| `bridge-013/after/` | a 013 logo depois do conserto da ponte; não é a publicada, que mudou depois |
| `hip-014/before/` | a 014 de uma rodada de conserto que não foi publicada, com a tabela de camadas e a máscara dela |
| `hip-014/after/` | iguais aos publicados |
| `projected-014/before/` | a 014 com a barra moldada sobre o tênis e as listras largas e quebradas, como foi vista |
| `projected-014/after/` | GLB igual ao publicado |
| `hem-hole-002/before/` | a 002 publicada antes de ser vestida inteira, com o furo |
| `hem-hole-002/after/` | GLB igual ao publicado |
| `waistband-004/before/` | a 004 da primeira versão vestida inteira, como foi vista |
| `waistband-004/after/` | GLB igual ao publicado |
| `torn-sleeve-022/before/` | a 022 publicada com 63 faces da manga direita tiradas |
| `torn-sleeve-022/after/` | GLB igual ao publicado |
| `hem-hole-030/before/` | a 030 do primeiro head do PR que a refez (forro apagado, tira no punho) |
| `hem-hole-030/after/` | GLB igual ao publicado |
| `torn-sleeve-020/before/` | a 020 publicada com 17 faces da manga direita reduzidas a área zero |
| `torn-sleeve-020/after/` | GLB igual ao publicado |
| `cuff-tip-021/before/` | a 021 com a ponta do punho pendurada, como foi vista |
| `cuff-tip-021/after/` | GLB igual ao publicado |
| `slit-033/before/` | a 033 publicada antes de `arm_clear.py`, com as máscaras e a tabela de camadas do 003 dela |
| `slit-033/after/` | iguais aos publicados |
| `notch-016/before/` | a 016 publicada sem a face 1677, na barra da frente |
| `notch-016/after/` | GLB igual ao publicado |
| `cords-009/before/`, `inside-body-007/before/` | iguais a `originals/tripo/` |
| `cords-009/after/`, `inside-body-007/after/` | GLB igual ao publicado |
| `inside-body-006/before/`, `midriff-006/before/` | os jeans 006 de antes da forma gerada no manequim neutro, com a máscara e a tabela de camadas deles |
| `inside-body-006/after/`, `midriff-006/after/` | GLB igual ao publicado |
| `large-jackets/before/` | 036 e 038 grandes demais, como foram vistas, com as máscaras delas; tabelas de camadas do 006 e do 008 com os pares da 036 e da 038 geradas para essas jaquetas (as do main apontam para as publicadas) |
| `large-jackets/after/` 036 | a 036 publicada com a manga vestida como tecido e o punho sobre a palma |
| `large-jackets/after/` 038 | GLB igual ao publicado; máscaras da época do conserto |

Ficaram de fora o quadrado branco na braguilha da 006 (o conserto veio do shader e do gerador da máscara, então o antes e
o depois guardados dão os mesmos números com o corpo de hoje) e as pontas sob o braço (máscaras feitas para o braço
antigo do manequim). `stretch.py` não separa a ponte da 013 (meio 11,0% → 5,4%, limite 15%): ela mede outra coisa, a
estampa esticada.
