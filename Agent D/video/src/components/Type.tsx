import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C} from '../theme';
import {riseIn} from '../lib/anim';

/** Надзаголовок: «ШАГ 3 · ВЕРИФИКАЦИЯ» */
export const Kicker: React.FC<{
  children: React.ReactNode;
  delay?: number;
  color?: string;
}> = ({children, delay = 0, color = C.orange}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        ...riseIn(frame, delay, 14),
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        fontSize: 21,
        fontWeight: 700,
        letterSpacing: 3.2,
        textTransform: 'uppercase',
        color,
      }}
    >
      <span style={{width: 34, height: 3, borderRadius: 3, backgroundColor: color}} />
      {children}
    </div>
  );
};

export const Title: React.FC<{
  children: React.ReactNode;
  delay?: number;
  size?: number;
  color?: string;
  maxWidth?: number;
}> = ({children, delay = 6, size = 62, color = C.ink, maxWidth}) => {
  const frame = useCurrentFrame();
  return (
    <h1
      style={{
        ...riseIn(frame, delay, 24),
        margin: '18px 0 0',
        fontSize: size,
        lineHeight: 1.08,
        fontWeight: 800,
        letterSpacing: -1.4,
        color,
        maxWidth,
      }}
    >
      {children}
    </h1>
  );
};

export const Lead: React.FC<{
  children: React.ReactNode;
  delay?: number;
  size?: number;
  maxWidth?: number;
  color?: string;
}> = ({children, delay = 12, size = 27, maxWidth = 700, color = C.inkMuted}) => {
  const frame = useCurrentFrame();
  return (
    <p
      style={{
        ...riseIn(frame, delay, 20),
        margin: '20px 0 0',
        fontSize: size,
        lineHeight: 1.5,
        fontWeight: 400,
        color,
        maxWidth,
      }}
    >
      {children}
    </p>
  );
};

/** Строка-фича с точкой-маркером и галочкой, появляется по очереди. */
export const FeatureRow: React.FC<{
  title: string;
  note?: string;
  delay?: number;
  dot?: string;
  check?: boolean;
  tone?: 'light' | 'navy';
}> = ({title, note, delay = 0, dot = C.orange, check = true, tone = 'light'}) => {
  const frame = useCurrentFrame();
  const navy = tone === 'navy';
  const checkIn = Math.min(1, Math.max(0, (frame - delay - 16) / 10));
  return (
    <div
      style={{
        ...riseIn(frame, delay, 18),
        display: 'flex',
        alignItems: 'center',
        gap: 18,
        padding: '18px 22px',
        borderRadius: 14,
        backgroundColor: navy ? 'rgba(255,255,255,0.05)' : C.white,
        border: `1px solid ${navy ? 'rgba(255,255,255,0.10)' : C.line}`,
        boxShadow: navy ? 'none' : '0 10px 26px -18px rgba(17,27,49,0.45)',
      }}
    >
      <span
        style={{
          width: 11,
          height: 11,
          borderRadius: 11,
          backgroundColor: dot,
          flexShrink: 0,
        }}
      />
      <div style={{flex: 1}}>
        <div
          style={{
            fontSize: 25,
            fontWeight: 650,
            color: navy ? C.white : C.ink,
            letterSpacing: -0.3,
          }}
        >
          {title}
        </div>
        {note ? (
          <div
            style={{
              fontSize: 19,
              marginTop: 4,
              color: navy ? 'rgba(255,255,255,0.62)' : C.inkMuted,
            }}
          >
            {note}
          </div>
        ) : null}
      </div>
      {check ? (
        <span
          style={{
            fontSize: 22,
            color: C.green,
            opacity: checkIn,
            transform: `scale(${0.7 + checkIn * 0.3})`,
          }}
        >
          ✓
        </span>
      ) : null}
    </div>
  );
};

/** Нижняя плашка-подпись, как в референсном ролике. */
export const Caption: React.FC<{
  children: React.ReactNode;
  delay?: number;
  accent?: string;
  bottom?: number;
}> = ({children, delay = 0, accent = C.orange, bottom = 62}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom,
        display: 'flex',
        justifyContent: 'center',
        ...riseIn(frame, delay, 22),
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          padding: '16px 30px',
          borderRadius: 999,
          backgroundColor: C.navy,
          color: C.white,
          fontSize: 26,
          fontWeight: 600,
          letterSpacing: -0.2,
          boxShadow: '0 26px 54px -22px rgba(17,27,49,0.7)',
        }}
      >
        <span
          style={{
            width: 10,
            height: 10,
            borderRadius: 10,
            backgroundColor: accent,
            flexShrink: 0,
          }}
        />
        {children}
      </div>
    </div>
  );
};

/** Маленький тег-«чип». */
export const Chip: React.FC<{
  children: React.ReactNode;
  delay?: number;
  tone?: 'light' | 'navy' | 'orange' | 'green';
}> = ({children, delay = 0, tone = 'light'}) => {
  const frame = useCurrentFrame();
  const palette = {
    light: {bg: C.white, fg: C.ink, br: C.line},
    navy: {bg: C.navy, fg: C.white, br: C.navy},
    orange: {bg: C.orangeSoft, fg: '#B65A19', br: '#F6D9C3'},
    green: {bg: C.greenSoft, fg: '#137A4A', br: '#C4E8D5'},
  }[tone];
  return (
    <span
      style={{
        ...riseIn(frame, delay, 12),
        display: 'inline-flex',
        alignItems: 'center',
        padding: '11px 20px',
        borderRadius: 999,
        fontSize: 21,
        fontWeight: 600,
        backgroundColor: palette.bg,
        color: palette.fg,
        border: `1px solid ${palette.br}`,
      }}
    >
      {children}
    </span>
  );
};
