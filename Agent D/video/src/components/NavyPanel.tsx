import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {C} from '../theme';

/** Тёмная подложка для финальных сцен — контраст после светлой части ролика. */
export const NavyPanel: React.FC<{children?: React.ReactNode; fadeIn?: number}> = ({
  children,
  fadeIn = 14,
}) => {
  const frame = useCurrentFrame();
  const o =
    fadeIn > 0
      ? interpolate(frame, [0, fadeIn], [0, 1], {extrapolateRight: 'clamp'})
      : 1;
  return (
    <AbsoluteFill style={{opacity: o}}>
      <AbsoluteFill style={{backgroundColor: C.navy}} />
      <AbsoluteFill
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, rgba(255,255,255,0.055) 1px, transparent 0)',
          backgroundSize: '38px 38px',
        }}
      />
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(1000px 620px at 80% 15%, rgba(232,123,53,0.22), transparent 62%)',
        }}
      />
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(900px 560px at 10% 90%, rgba(47,107,216,0.20), transparent 62%)',
        }}
      />
      {children}
    </AbsoluteFill>
  );
};
