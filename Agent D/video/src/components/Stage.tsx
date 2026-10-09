import React from 'react';
import {AbsoluteFill} from 'remotion';
import {C, FONT} from '../theme';

/**
 * Постоянный фон ролика: фирменный светлый холст ArchivAI
 * с еле заметной сеткой и тёплым оранжевым свечением.
 * Живёт под всеми сценами, поэтому монтаж выглядит непрерывным.
 */
export const Stage: React.FC<{children?: React.ReactNode; tone?: 'light' | 'navy'}> = ({
  children,
  tone = 'light',
}) => {
  const navy = tone === 'navy';
  return (
    <AbsoluteFill
      style={{
        fontFamily: FONT,
        backgroundColor: navy ? C.navy : C.bg,
        color: navy ? C.white : C.ink,
      }}
    >
      <AbsoluteFill
        style={{
          backgroundImage: `radial-gradient(circle at 1px 1px, ${
            navy ? 'rgba(255,255,255,0.06)' : 'rgba(17,27,49,0.055)'
          } 1px, transparent 0)`,
          backgroundSize: '38px 38px',
        }}
      />
      <AbsoluteFill
        style={{
          background: navy
            ? 'radial-gradient(1100px 620px at 78% 18%, rgba(232,123,53,0.16), transparent 65%)'
            : 'radial-gradient(1200px 700px at 82% 12%, rgba(232,123,53,0.13), transparent 62%)',
        }}
      />
      <AbsoluteFill
        style={{
          background: navy
            ? 'radial-gradient(900px 600px at 12% 88%, rgba(47,107,216,0.18), transparent 62%)'
            : 'radial-gradient(900px 600px at 8% 92%, rgba(17,27,49,0.07), transparent 62%)',
        }}
      />
      {children}
    </AbsoluteFill>
  );
};

/** Тонкая подпись бренда в углу кадра. */
export const StageMark: React.FC<{tone?: 'light' | 'navy'}> = ({tone = 'light'}) => (
  <div
    style={{
      position: 'absolute',
      right: 64,
      bottom: 46,
      fontSize: 20,
      letterSpacing: 2.4,
      fontWeight: 600,
      color: tone === 'navy' ? 'rgba(255,255,255,0.42)' : 'rgba(22,35,60,0.34)',
    }}
  >
    JI STUDIO
  </div>
);
