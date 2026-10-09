import React from 'react';
import {useCurrentFrame} from 'remotion';
import {C} from '../theme';
import {countTo, riseIn} from '../lib/anim';

/** Карточка с числом, которое докручивается до значения. */
export const Kpi: React.FC<{
  value: number;
  label: string;
  suffix?: string;
  delay?: number;
  decimals?: number;
  tone?: 'light' | 'navy';
  size?: number;
}> = ({value, label, suffix = '', delay = 0, decimals = 0, tone = 'light', size = 72}) => {
  const frame = useCurrentFrame();
  const navy = tone === 'navy';
  return (
    <div
      style={{
        ...riseIn(frame, delay, 22),
        padding: '26px 30px',
        borderRadius: 16,
        backgroundColor: navy ? 'rgba(255,255,255,0.05)' : C.white,
        border: `1px solid ${navy ? 'rgba(255,255,255,0.10)' : C.line}`,
        boxShadow: navy ? 'none' : '0 16px 40px -26px rgba(17,27,49,0.5)',
        minWidth: 232,
      }}
    >
      <div
        style={{
          fontSize: size,
          fontWeight: 800,
          letterSpacing: -2.4,
          lineHeight: 1,
          color: navy ? C.white : C.ink,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {countTo(frame, value, delay + 6, 42, decimals)}
        <span style={{fontSize: size * 0.5, color: C.orange}}>{suffix}</span>
      </div>
      <div
        style={{
          marginTop: 10,
          fontSize: 19,
          fontWeight: 600,
          letterSpacing: 0.4,
          color: navy ? 'rgba(255,255,255,0.6)' : C.inkMuted,
        }}
      >
        {label}
      </div>
    </div>
  );
};
