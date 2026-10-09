import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {C} from '../theme';
import {EASE, riseIn} from '../lib/anim';

export type Step = {label: string; note?: string};

/**
 * Горизонтальный конвейер обработки: шаги загораются по очереди,
 * между ними бежит соединительная линия.
 */
export const Pipeline: React.FC<{
  steps: Step[];
  delay?: number;
  stepFrames?: number;
  tone?: 'light' | 'navy';
  compact?: boolean;
}> = ({steps, delay = 0, stepFrames = 26, tone = 'light', compact = false}) => {
  const frame = useCurrentFrame();
  const navy = tone === 'navy';
  return (
    <div style={{display: 'flex', alignItems: 'stretch', gap: 0}}>
      {steps.map((s, i) => {
        const start = delay + i * stepFrames;
        const on = interpolate(frame - start, [0, 16], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: EASE,
        });
        const lineOn = interpolate(frame - start - 10, [0, stepFrames], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
          easing: EASE,
        });
        return (
          <React.Fragment key={s.label}>
            <div
              style={{
                ...riseIn(frame, start, 14),
                minWidth: compact ? 180 : 214,
                padding: compact ? '16px 18px' : '22px 24px',
                borderRadius: 14,
                backgroundColor: navy
                  ? `rgba(255,255,255,${0.04 + on * 0.06})`
                  : C.white,
                border: `1px solid ${
                  navy
                    ? `rgba(255,255,255,${0.08 + on * 0.16})`
                    : on > 0.6
                      ? '#F0CDAF'
                      : C.line
                }`,
                boxShadow: navy
                  ? 'none'
                  : `0 12px 30px -20px rgba(17,27,49,${0.2 + on * 0.3})`,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  fontSize: compact ? 20 : 23,
                  fontWeight: 700,
                  color: navy ? C.white : C.ink,
                  letterSpacing: -0.2,
                }}
              >
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: 10,
                    backgroundColor: on > 0.6 ? C.orange : navy ? '#3A4763' : C.line,
                  }}
                />
                {s.label}
              </div>
              {s.note ? (
                <div
                  style={{
                    marginTop: 6,
                    fontSize: compact ? 16 : 18,
                    color: navy ? 'rgba(255,255,255,0.6)' : C.inkMuted,
                  }}
                >
                  {s.note}
                </div>
              ) : null}
            </div>
            {i < steps.length - 1 ? (
              <div
                style={{
                  alignSelf: 'center',
                  width: compact ? 26 : 34,
                  height: 3,
                  borderRadius: 3,
                  backgroundColor: navy ? 'rgba(255,255,255,0.12)' : C.line,
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    width: `${lineOn * 100}%`,
                    backgroundColor: C.orange,
                  }}
                />
              </div>
            ) : null}
          </React.Fragment>
        );
      })}
    </div>
  );
};
