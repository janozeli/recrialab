# Modelos de referência

Cópias dos modelos 3D em etapas anteriores do ajuste. As ferramentas comparam a peça publicada com
elas, por exemplo para saber se a estampa esticou, e por isso elas ficam aqui como arquivos em vez de
depender do histórico do git. `manifest.json` tem o sha256 de cada arquivo, e `site/reference.test.ts`
reprova arquivo alterado, faltando ou sobrando.

## Originais

| Pasta | O que é | Quem usa |
|---|---|---|
| `originals/tripo/` | peças de baixo (001 a 015) como o Tripo entregou, só com menos triângulos e sem fragmentos soltos | `stretch.py` (verificação de estampa), `pant_leg_cloth.py` |
| `originals/before-hood/` | peças com capuz ou gola (030, 033 a 037) antes de rodar `hood.py` pela primeira vez (a 034 já com a manga assentada por `cloth.py`, que roda antes de `hood.py`) | `hood.py` e `hood.py --check` (limite de encolhimento) |
| `originals/before-drape/` | peças de cima (016 a 038) e o short 008 antes de `drape.py` e `zipper.py` | `drape.py`, `zipper.py` |
