import React from 'react';
import {AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {C} from '../theme';
import {pop, riseIn} from '../lib/anim';
import {ArchivAI} from '../components/Wordmark';
import {Chip} from '../components/Type';

export const S01Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  return (
    <AbsoluteFill>
      {/* Скан на заднем плане — намёк на предметную область */}
      <div
        style={{
          position: 'absolute',
          right: -60,
          top: -40,
          width: 720,
          height: 1160,
          opacity: interpolate(frame, [0, 40], [0, 0.14], {extrapolateRight: 'clamp'}),
          transform: `rotate(6deg) scale(${interpolate(frame, [0, 240], [1.04, 1.12])})`,
          maskImage: 'radial-gradient(closest-side, black 45%, transparent 100%)',
          WebkitMaskImage: 'radial-gradient(closest-side, black 45%, transparent 100%)',
        }}
      >
        <Img
          src={staticFile('shots/scan_source.png')}
          style={{width: '100%', height: '100%', objectFit: 'cover'}}
        />
      </div>

      <AbsoluteFill
        style={{
          justifyContent: 'center',
          paddingLeft: 150,
          paddingRight: 700,
        }}
      >
        <div style={{...riseIn(frame, 0, 16)}}>
          <Chip tone="orange" delay={0}>
            РАБОТАЕТ НА ВАШЕМ СЕРВЕРЕ · РУССКИЙ И КАЗАХСКИЙ
          </Chip>
        </div>

        <div style={{...pop(frame, fps, 10, 0.94), marginTop: 34}}>
          <ArchivAI size={104} tagline={false} />
        </div>

        <h1
          style={{
            ...riseIn(frame, 26, 30),
            margin: '34px 0 0',
            fontSize: 74,
            lineHeight: 1.06,
            fontWeight: 800,
            letterSpacing: -2.2,
            color: C.ink,
            maxWidth: 1010,
          }}
        >
          Архив, который можно{' '}
          <span style={{color: C.orange}}>спросить</span>.
        </h1>

        <p
          style={{
            ...riseIn(frame, 44, 24),
            margin: '28px 0 0',
            fontSize: 30,
            lineHeight: 1.48,
            color: C.inkMuted,
            maxWidth: 880,
          }}
        >
          Сканы XX века превращаются в текст, имена, даты и места — и документы
          наконец можно искать обычными словами.
        </p>

        <div style={{display: 'flex', gap: 14, marginTop: 40, flexWrap: 'wrap'}}>
          <Chip delay={60}>Распознавание текста</Chip>
          <Chip delay={70}>Поиск по смыслу</Chip>
          <Chip delay={80}>Связи между делами</Chip>
          <Chip delay={90}>Настройка без программиста</Chip>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
