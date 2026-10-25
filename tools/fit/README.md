# Ferramentas de caimento

Scripts em Python que ajustam as roupas 3D ao manequim do site e medem o resultado.

O Tripo, que transformou as fotos em 3D, entrega cada roupa já vestida num manequim próprio, com outras
proporções: ombro mais alto, pescoço reto, coxas mais finas. Colocada direto no manequim do site
(`site/assets/body/`), a roupa flutua, afunda no corpo ou deixa o corpo atravessar o tecido. Estes
scripts corrigem isso peça por peça sem distorcer a estampa, e cada correção tem uma medida que roda no
CI e impede o problema de voltar.

```sh
python3 -m pip install -r tools/fit/requirements.txt
```

Os scripts leem e gravam os modelos em `site/assets/garments/` e as máscaras em `site/assets/masks/`
(caminhos em `paths.py`). Depois de mexer numa peça, gere de novo as máscaras e as camadas dela com
`install.py` e compare frente, perfil e costas com a foto:

```sh
node tools/verify-site/showcase.mjs --pieces NNN
```

## Adicionar uma peça

O acervo tem 38 peças, e esse número está fixado nos testes (`site/integrity.test.ts`) e nos
totais dos 345 pares (`layer_check.py`). Uma peça nova, de número `NNN`, passa por:

1. **Arquivos:** o GLB do gerador em `site/assets/garments/NNN.glb` e a foto do brechó em
   `site/assets/photos/NNN.webp`. Peça de baixo: uma cópia do GLB original também em
   `reference/originals/tripo/`, com o hash em `reference/manifest.json`.
2. **Cadastro no site:** a entrada em `site/catalog-data.ts` (nome curto, `slot`, miniatura e foto), o
   import `garmentNNN` em `site/dressup.ts` e o filtro em `site/catalog-tags.ts`.
3. **Caimento:** os scripts das tabelas abaixo, na ordem, até as medidas do CI passarem.
4. **Máscaras e camadas:** `python3 tools/fit/install.py NNN` (peça de baixo: `--bottom NNN`) e o
   import das máscaras novas em `site/body-masks.ts`.
5. **Tom e miniatura:** `python3 tools/visual-qa/tone.py DIR --fit` lê as fotos que
   `visual-qa.mjs --beauty` gravou em DIR e grava o ganho de cor em `site/garment-tones.ts`;
   `bun thumbnails.ts`, dentro de `site/`, desenha a miniatura e atualiza `thumbnails.lock.json`.
6. **Conferência:** atualize os totais fixados nos testes (38 peças, 23 de cima, 15 de baixo, 345
   pares), rode `bun run test` e as medidas do CI e compare frente, perfil e costas com a foto (`node tools/verify-site/showcase.mjs --pieces NNN`).

## Ajuste das peças de cima

Na ordem em que costumam rodar:

| Script | O que faz |
|---|---|
| `drape.py` | abaixa a peça até apoiar no ombro e faz a lateral cair reta do ponto mais largo do tronco, sem colar na cintura (quanto cada peça desce fica em `drops.json`) |
| `shoulder.py` | arredonda a ponta do ombro, que ficava quadrada acima do braço |
| `top_cloth.py` | deixa a peça cair com o próprio peso, como tecido, até a gola encostar na nuca |
| `resize.py` | diminui por igual as jaquetas grandes demais para o corpo |
| `repose_sleeves.py` | gira ombro, braço e antebraço da peça para a manga acompanhar o braço do manequim |
| `cloth.py` | faz o mesmo e depois deixa o antebraço da manga assentar como tecido em volta do braço e da mão, com o corpo como colisor (simulador Newton): para o punho elástico que, centrado na mão, atravessaria o pulso (034) |
| `hood.py` | deita nas costas o capuz e a gola que ficavam em pé atrás da nuca (`--check` confere o limite de encolhimento) |
| `lining.py` | apaga o forro pendurado abaixo da barra da frente |
| `top_over_bottom.py` | puxa para fora a barra das jaquetas que entrava na cintura das peças de baixo; com `--columns`, a barra canelada (037) anda só na frente e só em z, coluna a coluna, para ficar 8 mm à frente da peça de baixo mais da frente, com a dobra de dentro junto |

## Ajuste das peças de baixo

| Script | O que faz |
|---|---|
| `displacement_field.py` | empurra para fora do corpo a parte da peça que entrava nele, com um deslocamento suave |
| `leg_shape.py` | refaz cada perna da calça no formato da perna do corpo, com a mesma quantidade de tecido |
| `separate_legs.py` | separa as pernas das calças que o gerador entregou grudadas e fecha a parede de dentro |
| `shin_tube.py` | refaz a canela dessas calças como um tubo em volta da perna |
| `pant_leg_cloth.py` | ajusta a perna da calça ao corpo como tecido, num passo só |
| `waistband.py` | levanta o meio do cós que afundou em V |
| `hem.py` | encurta uma peça cortando a malha 3D numa altura (saia 009) |
| `zipper.py` | fecha a braguilha do short 008 |
| `crotch.py` | remove o tecido que o gerador deixou entre as coxas do short 008 |
| `cords.py` | remove os cordões que o gerador pendurou na frente da saia 009 |
| `fringe.py`, `slivers.py`, `islands.py` | aparam as pontas da franja, as lascas soltas e os pedaços da malha 3D desligados da peça |

## Máscaras e camadas

A máscara de uma peça lista os triângulos do corpo que ficam escondidos sob ela; a tabela de camadas
lista os triângulos da peça de baixo que somem sob cada peça de cima (mais em `site/README.md`).

| Script | O que faz |
|---|---|
| `install.py` | gera de novo as máscaras (poses B e C) e as tabelas de camadas de uma peça (`--bottom` para peça de baixo) |
| `gen_mask.py` | calcula a máscara de uma peça |
| `gen_layers.py`, `layer_tables.py` | calculam e gravam as tabelas de camadas (`site/assets/layers/`), uma linha por peça de cima |
| `waist.py`, `collar.py` | medem a altura do cós e da gola em volta do corpo; o site corta o corpo nessa linha, pixel a pixel |
| `top_hem.py` | mede a barra da peça de cima em volta do corpo, a mesma linha usada em `site/garment-hem.ts` |
| `strap.py` | esconde o ombro que atravessa a alça das regatas (chamado por `install.py`) |
| `mask_io.py`, `garment.py`, `glb_patch.py` | leitura e escrita de máscaras e GLBs |

`layer_tables.py` também resolve conflito de merge nas tabelas: rode-o depois de mesclar e ele refaz só
os pares cujo hash mudou.

## Medidas que rodam no CI

| Script | Reprova |
|---|---|
| `poke_through.py` | corpo atravessando a roupa ou aparecendo oco sob ela |
| `layer_check.py` | peça de baixo com borda serrilhada sob a barra da de cima ou que a atravessa, nos 345 pares |
| `holes.py` | rasgo na frente das peças de baixo mostrando o corpo |
| `crotch.py --measure` | tecido no vão entre as coxas do short 008 |
| `cuff.py` | tecido solto fora da perna da calça, da canela para baixo |
| `texture.py` | mancha preta na textura entre as pernas, onde o gerador não enxergou a roupa |
| `cords.py --measure` | cordões na frente da saia 009 |
| `penetration.py` | roupa mais folgada ou mais enfiada no corpo que o valor registrado em `penetration.json`, que só pode baixar |
| `stretch.py` | estampa esticada em relação ao modelo original, região por região |
| `hood.py --check` | capuz ou gola achatados além do limite em relação ao modelo original |

`metric.py` e `anchors.py` só medem folga e apoio, para diagnóstico, sem reprovar nada. `arm.py` mexe
no manequim, não nas peças: deixa antebraço e mão das poses B e C no comprimento de uma pessoa.

## Referência

`reference/` guarda os GLBs de antes de cada ajuste (veja o README da
pasta). `site/reference.test.ts` reprova qualquer arquivo alterado, faltando ou sobrando.
