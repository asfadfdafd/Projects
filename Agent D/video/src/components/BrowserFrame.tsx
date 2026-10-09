import React from 'react';
import {C} from '../theme';

/**
 * Аккуратная рамка браузера, в которой живут записи экрана и скриншоты.
 * Ширина задаётся снаружи, высота считается по 16:9-подобной пропорции контента.
 */
export const BrowserFrame: React.FC<{
  width: number;
  height: number;
  url?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
  radius?: number;
}> = ({width, height, url = 'archivai.local', children, style, radius = 18}) => {
  const bar = 46;
  return (
    <div
      style={{
        width,
        height: height + bar,
        borderRadius: radius,
        overflow: 'hidden',
        backgroundColor: C.white,
        border: `1px solid ${C.line}`,
        boxShadow:
          '0 44px 90px -28px rgba(17,27,49,0.35), 0 8px 24px -12px rgba(17,27,49,0.18)',
        ...style,
      }}
    >
      <div
        style={{
          height: bar,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '0 18px',
          backgroundColor: '#F7F9FC',
          borderBottom: `1px solid ${C.line}`,
        }}
      >
        {['#E7756B', '#E9B44C', '#67C08A'].map((dot) => (
          <div
            key={dot}
            style={{width: 11, height: 11, borderRadius: 11, backgroundColor: dot}}
          />
        ))}
        <div
          style={{
            marginLeft: 14,
            height: 24,
            flex: 1,
            maxWidth: 380,
            borderRadius: 12,
            backgroundColor: C.white,
            border: `1px solid ${C.line}`,
            display: 'flex',
            alignItems: 'center',
            padding: '0 12px',
            fontSize: 13,
            color: C.inkMuted,
            letterSpacing: 0.2,
          }}
        >
          {url}
        </div>
      </div>
      <div style={{width, height, position: 'relative', overflow: 'hidden'}}>
        {children}
      </div>
    </div>
  );
};
