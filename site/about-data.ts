/**
 * Record of the project: events, curated looks, editorial and team. The `/sobre` page is built
 * from it. Only real records go in: a section without entries is not shown.
 * To turn the images saved by students into looks: `bun about-look.ts images/*.png`.
 */

export type Workshop = {
  /** ISO date (`2026-11-08`); orders the timeline. */
  date: string;
  title: string;
  place: string;
  text: string;
  /** Photos without faces and audio (.m4a or .mp3), imported from `assets/`. */
  photos?: { src: string; alt: string }[];
  audio?: { src: string; caption: string };
  /** Profiles of who took part (thrift stores, venue). */
  links?: Link[];
};

export type CuratedLook = {
  /** Same code as `?look=` and the PNG (`004.024`). */
  look: string;
  /** Credit without personal data: class, nickname or initials. */
  credit: string;
  /** Workshop it came from, by its `date`. */
  workshop?: string;
  note?: string;
};

export type Link = { label: string; href: string };
/** Groups of the team, in the order shown on the page. */
export const TEAM_AREAS = ['Coordenação e produção', 'Moda', 'Audiovisual e roteiro', 'Design e tecnologia', 'Brechós parceiros'] as const;
export type Person = { name: string; role: string; area: (typeof TEAM_AREAS)[number] };

export type EditorialPhoto = { src: string; alt: string; looks?: string[] };

export const ABOUT = {
  workshops: [
    {
      date: '2026-10-11',
      title: 'Território de Grife no Pico Kaya',
      place: 'Pico Kaya, Jundiaí',
      text: 'Evento de arrecadação para as oficinas nas escolas públicas: feira com quatro brechós, exibição do documentário Território de Grife (Mateus Oliveira, 2024) com roda de conversa sobre moda periférica, identidade e consumo, e discotecagem com os DJs GPUNK e JUSZ.',
      links: [
        { label: '@moska.brecho', href: 'https://www.instagram.com/moska.brecho/' },
        { label: '@vtugarimpo', href: 'https://www.instagram.com/vtugarimpo/' },
        { label: '@gusttonbrecho', href: 'https://www.instagram.com/gusttonbrecho/' },
        { label: '@calorenta.brecho', href: 'https://www.instagram.com/calorenta.brecho/' },
        { label: '@pico_kaya', href: 'https://www.instagram.com/pico_kaya/' },
      ],
    },
  ] as Workshop[],
  looks: [] as CuratedLook[],
  editorial: [] as EditorialPhoto[],
  /** Credits of the project team. */
  advisor: 'Prof. Dr. Hermes Renato Hildebrand',
  team: [
    { name: 'Mayara Pereira', role: 'Coordenação geral e pesquisa', area: 'Coordenação e produção' },
    { name: 'Brunna Aprigio', role: 'Produção executiva', area: 'Coordenação e produção' },
    { name: 'Iolanda Russo', role: 'Direção de produção e mediação educativa', area: 'Coordenação e produção' },
    { name: 'Otávio Pigatto', role: 'Eventos e logística', area: 'Coordenação e produção' },
    { name: 'Gabriela Souza', role: 'Assistente de produção', area: 'Coordenação e produção' },
    { name: 'Isadora Cardoso', role: 'Fotografia de moda', area: 'Moda' },
    { name: 'Hector Deganello', role: 'Mídias sociais e artes visuais', area: 'Design e tecnologia' },
    { name: 'Lucas Marzagão', role: 'Desenvolvimento de mídias interativas', area: 'Design e tecnologia' },
    { name: 'Livia Nara', role: 'Styling e direção de arte de moda', area: 'Moda' },
    { name: 'Luísa da Cruz Firmino', role: 'Styling e direção de arte de moda', area: 'Moda' },
    { name: 'Moska', role: 'Curadoria de moda e acervo, Jundiaí', area: 'Brechós parceiros' },
    { name: 'VTU', role: 'Curadoria de moda e acervo, Jundiaí', area: 'Brechós parceiros' },
    { name: 'Elisa Valderano', role: 'Captação audiovisual', area: 'Audiovisual e roteiro' },
    { name: 'Sophia Medina', role: 'Montagem e edição', area: 'Audiovisual e roteiro' },
    { name: 'Beatriz Rodrigues', role: 'Roteiro e pesquisa', area: 'Audiovisual e roteiro' },
    { name: 'Oli', role: 'Ilustração e design digital', area: 'Design e tecnologia' },
  ] as Person[],
};
