import React from 'react';
import {AbsoluteFill, Img, OffthreadVideo, staticFile, useCurrentFrame} from 'remotion';
import {kenBurns} from '../lib/anim';

type Focus = {
  /** нормализованные координаты центра интереса (0..1) */
  x?: number;
  y?: number;
  from?: number;
  to?: number;
};

/**
 * Статичный скриншот с лёгким наездом камеры.
 * `focus` задаёт, к какой точке кадра тянемся.
 */
export const Shot: React.FC<{
  src: string;
  duration: number;
  focus?: Focus;
  fit?: 'cover' | 'contain';
  position?: string;
  style?: React.CSSProperties;
}> = ({src, duration, focus, fit = 'cover', position = 'top center', style}) => {
  const frame = useCurrentFrame();
  const x = focus?.x ?? 0.5;
  const y = focus?.y ?? 0.35;
  const from = focus?.from ?? 1.0;
  const to = focus?.to ?? 1.06;
  const panX = (0.5 - x) * 18;
  const panY = (0.5 - y) * 14;
  const kb = kenBurns(frame, duration, from, to, panX, panY);
  return (
    <AbsoluteFill style={{overflow: 'hidden', ...style}}>
      <Img
        src={staticFile(src)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: fit,
          objectPosition: position,
          ...kb,
        }}
      />
    </AbsoluteFill>
  );
};

/** Запись экрана внутри рамки. Всегда играет с первого кадра клипа. */
export const Clip: React.FC<{
  src: string;
  style?: React.CSSProperties;
  scale?: number;
  originY?: string;
}> = ({src, style, scale = 1, originY = 'top'}) => (
  <AbsoluteFill style={{overflow: 'hidden', ...style}}>
    <OffthreadVideo
      src={staticFile(src)}
      muted
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        objectPosition: 'top center',
        transform: `scale(${scale})`,
        transformOrigin: `center ${originY}`,
      }}
    />
  </AbsoluteFill>
);
