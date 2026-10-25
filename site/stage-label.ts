/** Text the screen reader reads on the mannequin: what is worn and how to turn it. */
export function stageLabel(names: readonly string[]): string {
  const wearing = names.length ? `vestindo ${names.join(' e ')}` : 'sem roupa escolhida';
  return `Manequim 3D ${wearing}. Arraste ou use as setas do teclado para girar.`;
}
