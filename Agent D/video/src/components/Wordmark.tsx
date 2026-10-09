import React from 'react';
import {C} from '../theme';

/** Логотип ArchivAI, набранный шрифтом — масштабируется без потерь. */
export const ArchivAI: React.FC<{
  size?: number;
  tone?: 'light' | 'navy';
  tagline?: boolean;
  style?: React.CSSProperties;
}> = ({size = 96, tone = 'light', tagline = true, style}) => {
  const navy = tone === 'navy';
  return (
    <div style={{display: 'inline-block', ...style}}>
      <div
        style={{
          fontSize: size,
          fontWeight: 800,
          letterSpacing: -size * 0.03,
          lineHeight: 1,
          color: navy ? C.white : C.navy,
        }}
      >
        Archiv<span style={{color: C.orange}}>AI</span>
      </div>
      {tagline ? (
        <div
          style={{
            marginTop: size * 0.14,
            fontSize: size * 0.19,
            letterSpacing: size * 0.028,
            fontWeight: 500,
            textTransform: 'lowercase',
            color: navy ? 'rgba(255,255,255,0.58)' : C.inkMuted,
          }}
        >
          open-source archive intelligence
        </div>
      ) : null}
    </div>
  );
};
