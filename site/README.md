# Site: provador e página Sobre

Aqui está o código do provador e da página Sobre de https://recrialab.com. O site é estático: o build
junta numa pasta o HTML, o JavaScript e os modelos 3D, e um Cloudflare Worker serve esses arquivos
(`wrangler.jsonc`).

## Como rodar

Precisa do Bun 1.4 ou mais novo e de Python 3 (o CI usa 3.13), porque parte dos testes
chama `python3`.

```sh
bun install --frozen-lockfile
bun run dev      # http://localhost:3000
bun run check    # confere os tipos do TypeScript
bun run test     # roda a suíte do repositório
bun run build    # gera a pasta dist/
```

O build grava o commit atual em `dist/build.json`. Por isso ele e parte dos testes precisam de um
clone do git e não rodam numa cópia baixada em ZIP.

Os testes daqui cobrem o repositório inteiro, não só o site: conferem os arquivos 3D, as ferramentas de
`tools/` e a documentação. A lista de regras e do teste que garante cada uma está no
[`AGENTS.md`](../AGENTS.md).

## Como o manequim veste as roupas

São 38 peças reais (23 de cima e 15 de baixo) e um manequim sem gênero nem rosto em duas poses: a
padrão e uma com as pernas mais afastadas, usada só por cinco calças largas. Nos arquivos elas se chamam
B (padrão) e C (pernas afastadas): `pose-b.glb` e `pose-c.glb`.

Uma roupa 3D vestida no manequim deixa o corpo aparecer através do tecido em alguns pontos. Para isso
não acontecer, cada peça traz uma **máscara**: a lista de triângulos do corpo que ficam escondidos sob
ela. O mesmo vale entre duas peças: quando a de cima cobre a de baixo, uma **tabela de camadas** diz
quais triângulos da peça de baixo somem. Cada peça de baixo tem uma tabela, com uma linha para cada
peça de cima: 15 × 23 = 345 pares.

| Pasta | O que tem |
|---|---|
| `assets/garments/` | os modelos 3D das peças (`NNN.glb`) |
| `assets/body/` | o manequim nas poses B e C e `poses.json`, que diz quais calças usam a pose C |
| `assets/masks/` | as máscaras, por pose e por peça |
| `assets/layers/` | as tabelas de camadas, uma por peça de baixo |
| `assets/photos/` | a foto de cada peça no brechó |
| `assets/thumbnails/` | a miniatura de cada peça no seletor |

## Onde está cada coisa

| Arquivo | O que faz |
|---|---|
| `main.ts`, `dressup.ts` | abre a página e monta o provador: palco 3D, escolha de peças, filtros, salvar e abrir looks |
| `catalog-data.ts`, `catalog-tags.ts` | o acervo (nome, tipo, miniatura e foto de cada peça) e os filtros por tipo |
| `body-poses.ts`, `body-masks.ts`, `body-occlusion.ts` | as duas poses do manequim e as máscaras que escondem o corpo sob cada peça |
| `garment-layer-data.ts`, `garment-hem.ts` | as tabelas de camadas e o acabamento da peça de baixo na barra da de cima |
| `fabric.ts`, `garment-tones.ts` | material, luz e o ajuste de cor de cada peça, os mesmos no palco e nas miniaturas |
| `camera-motion.ts` | o giro automático do manequim e a volta para a frente, respeitando quem prefere menos movimento |
| `look-code.ts`, `look-export.ts` | o código do look (`004.024`) e a imagem PNG salva |
| `about.ts`, `about-data.ts`, `about-model.ts` | a página Sobre e o seu conteúdo (eventos, looks e equipe) |
| `thumbnails.ts`, `thumbnail-render.ts` | desenham as miniaturas a partir dos modelos 3D |
| `verify-dist.ts`, `check-live.ts` | conferem o pacote antes de publicar e o site no ar depois |

## Salvar e abrir looks

O provador não tem servidor e não guarda dados de quem usa. O look viaja de duas formas:

- **No link:** o endereço muda a cada troca de peça (`/?look=004.024`).
- **Na imagem:** o botão Salvar gera um PNG de 1080×1350 com `LOOK 004 + 024` no canto e o mesmo código
  escondido no arquivo (um bloco `tEXt` chamado `recrialab-look`). O botão Abrir lê essa imagem e veste
  as mesmas peças.

## Página Sobre

`/sobre` apresenta o projeto e a equipe e não carrega o 3D. O conteúdo fica em `about-data.ts`, e uma
seção sem conteúdo não aparece. Para incluir looks salvos pelos alunos, `bun about-look.ts images/*.png`
lê as imagens e imprime as entradas prontas para colar na lista `looks` de `about-data.ts`.

## Miniaturas

As miniaturas do seletor são as próprias peças 3D, desenhadas com a mesma luz do palco. Quando um modelo,
o ajuste de cor ou o desenho das miniaturas muda, rode `bun thumbnails.ts` (refaz só as desatualizadas)
e faça commit das imagens e do `thumbnails.lock.json`.

## Estatísticas de visita

No endereço recrialab.com, as duas páginas ativam o Cloudflare Web Analytics quando acabam de abrir. Ele
conta visitas sem cookie e sem dado pessoal. O token público fica em `BEACON_TOKEN` (`analytics.ts`).

## Publicar

Cada merge em `main` publica o site pelo Workers Builds da Cloudflare (`bun install --frozen-lockfile &&
bun run build`, depois `npx wrangler deploy`). De uma máquina com acesso à conta, `bun run deploy` faz o
mesmo passo a passo: confere tipos, testes, build e pacote, publica e confere o site no ar. Para voltar à
versão anterior: `bunx wrangler rollback`.
