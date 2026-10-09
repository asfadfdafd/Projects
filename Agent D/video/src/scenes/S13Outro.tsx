import React from 'react';
import {AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {C} from '../theme';
import {NavyPanel} from '../components/NavyPanel';
import {ArchivAI} from '../components/Wordmark';
import {pop, riseIn} from '../lib/anim';

export const S13Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const lineW = interpolate(frame - 26, [0, 26], [0, 300], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill>
      {/* fadeIn=0 — предыдущая сцена уже тёмная, лишний переход не нужен */}
      <NavyPanel fadeIn={0}>
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
          <div style={{...pop(frame, fps, 4, 0.92), textAlign: 'center'}}>
            <ArchivAI size={118} tone="navy" tagline />
          </div>

          <div
            style={{
              marginTop: 40,
              height: 2,
              width: lineW,
              background: `linear-gradient(90deg, transparent, ${C.orange}, transparent)`,
            }}
          />

          <div
            style={{
              ...riseIn(frame, 40, 22),
              marginTop: 38,
              fontSize: 29,
              fontWeight: 500,
              color: 'rgba(255,255,255,0.78)',
              textAlign: 'center',
              maxWidth: 1000,
              lineHeight: 1.45,
            }}
          >
            Ставится на ваш сервер. Открытый код.
            <br />
            Готовы показать на ваших документах.
          </div>

          <div
            style={{
              ...riseIn(frame, 62, 20),
              marginTop: 66,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 16,
            }}
          >
            <div
              style={{
                fontSize: 17,
                letterSpacing: 3,
                textTransform: 'uppercase',
                color: 'rgba(255,255,255,0.42)',
                fontWeight: 600,
              }}
            >
              Разработано
            </div>
            <Img
              src={staticFile('logo/ji_studio_light.png')}
              style={{height: 52, opacity: 0.94}}
            />
          </div>
        </AbsoluteFill>
      </NavyPanel>
    </AbsoluteFill>
  );
};
