/** Геометрия кадра. Соотношение сторон записей экрана — 1600×892. */
export const CLIP_AR = 892 / 1600;

export const frameHeight = (width: number) => Math.round(width * CLIP_AR);

/** Высота служебной полоски браузера. */
export const CHROME_H = 46;

const split = (() => {
  const frameW = 980;
  const frameContentH = frameHeight(frameW);
  const frameTotalH = frameContentH + CHROME_H;
  return {
    frameX: 80,
    frameW,
    frameContentH,
    frameTotalH,
    frameY: Math.round((1080 - frameTotalH) / 2),
    textX: 1130,
    textW: 710,
  };
})();

const splitR = (() => {
  const frameW = 940;
  const frameContentH = frameHeight(frameW);
  const frameTotalH = frameContentH + CHROME_H;
  return {
    frameW,
    frameContentH,
    frameTotalH,
    frameX: 1920 - 80 - frameW,
    frameY: Math.round((1080 - frameTotalH) / 2),
    textX: 90,
    textW: 700,
  };
})();

const hero = (() => {
  const frameW = 1230;
  const frameContentH = frameHeight(frameW);
  return {
    frameW,
    frameContentH,
    frameTotalH: frameContentH + CHROME_H,
    frameX: Math.round((1920 - frameW) / 2),
    frameY: 196,
  };
})();

/** Раскладка «рамка слева — текст справа». */
export const SPLIT = split;
/** Раскладка «текст слева — рамка справа». */
export const SPLIT_R = splitR;
/** Раскладка «большая рамка по центру» — заголовок сверху, подпись снизу. */
export const HERO = hero;
