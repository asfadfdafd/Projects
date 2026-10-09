import {FPS} from './theme';

export const sec = (s: number) => Math.round(s * FPS);

export type SceneId =
  | 'intro'
  | 'problem'
  | 'how'
  | 'upload'
  | 'process'
  | 'verify'
  | 'search'
  | 'ask'
  | 'entities'
  | 'agent'
  | 'control'
  | 'why'
  | 'outro';

/** Длительность каждой сцены в секундах. Меняйте здесь — таймлайн пересчитается сам. */
export const SCENE_SECONDS: Record<SceneId, number> = {
  intro: 8,
  problem: 10,
  how: 9,
  upload: 14,
  process: 13,
  verify: 15,
  search: 18,
  ask: 18,
  entities: 13,
  agent: 16,
  control: 12,
  why: 11,
  outro: 8,
};

/**
 * Порядок сцен в ролике.
 *
 * Сцена `ask` (вопрос ассистенту) собрана и готова, но в монтаж не включена:
 * в записи экрана ответ ассистента получился на «грязном» распознавании и
 * выглядел неубедительно. Когда будет запись на чистом документе — достаточно
 * вернуть 'ask' в этот массив после 'search', и сцена снова встанет в ролик.
 */
export const ORDER: SceneId[] = [
  'intro',
  'problem',
  'how',
  'upload',
  'process',
  'verify',
  'search',
  'entities',
  'agent',
  'control',
  'why',
  'outro',
];

/** Короткая версия для соцсетей / первого касания. */
export const TEASER_ORDER: SceneId[] = [
  'intro',
  'problem',
  'search',
  'entities',
  'agent',
  'outro',
];

export type Slot = {id: SceneId; from: number; durationInFrames: number};

export const buildTimeline = (order: SceneId[]): Slot[] => {
  let cursor = 0;
  return order.map((id) => {
    const durationInFrames = sec(SCENE_SECONDS[id]);
    const slot: Slot = {id, from: cursor, durationInFrames};
    cursor += durationInFrames;
    return slot;
  });
};

export const totalFrames = (order: SceneId[]) =>
  order.reduce((acc, id) => acc + sec(SCENE_SECONDS[id]), 0);
