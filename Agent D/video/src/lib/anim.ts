import {Easing, interpolate, spring} from 'remotion';

export const EASE = Easing.bezier(0.22, 1, 0.36, 1);

/** Мягкое появление: прозрачность + подъём снизу. */
export const riseIn = (frame: number, delay = 0, distance = 26, dur = 22) => {
  const t = interpolate(frame - delay, [0, dur], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: EASE,
  });
  return {
    opacity: t,
    transform: `translateY(${(1 - t) * distance}px)`,
  };
};

/** Пружинный масштаб — для логотипов и крупных чисел. */
export const pop = (frame: number, fps: number, delay = 0, from = 0.9) => {
  const s = spring({
    frame: frame - delay,
    fps,
    config: {damping: 200, mass: 0.6},
  });
  return {
    opacity: interpolate(s, [0, 1], [0, 1]),
    transform: `scale(${interpolate(s, [0, 1], [from, 1])})`,
  };
};

/** Затемнение по краям сцены, чтобы стыки не «щёлкали». */
export const sceneFade = (frame: number, duration: number, edge = 12) =>
  interpolate(
    frame,
    [0, edge, duration - edge, duration],
    [0, 1, 1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE},
  );

/** Плавный «наезд» камеры (Ken Burns) для статичных скриншотов. */
export const kenBurns = (
  frame: number,
  duration: number,
  fromScale = 1,
  toScale = 1.07,
  panX = 0,
  panY = 0,
) => {
  const t = interpolate(frame, [0, duration], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.quad),
  });
  const scale = interpolate(t, [0, 1], [fromScale, toScale]);
  return {
    transform: `scale(${scale}) translate(${panX * t}%, ${panY * t}%)`,
  };
};

/** Счётчик, который «докручивается» до значения. */
export const countTo = (
  frame: number,
  value: number,
  delay = 0,
  dur = 40,
  decimals = 0,
) => {
  const v = interpolate(frame - delay, [0, dur], [0, value], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: EASE,
  });
  return v.toFixed(decimals);
};

/** Печатающийся текст. */
export const typed = (frame: number, text: string, delay = 0, cps = 26) => {
  const chars = Math.max(0, Math.floor(((frame - delay) / 30) * cps));
  return text.slice(0, chars);
};
