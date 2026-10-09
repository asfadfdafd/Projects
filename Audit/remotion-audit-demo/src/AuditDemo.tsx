import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile} from 'remotion';
import {VIDEO, sec} from './theme';
import {Intro}             from './scenes/Intro';
import {FaqScene}          from './scenes/FaqScene';
import {FunnelScene}       from './scenes/FunnelScene';
import {ConsultationScene} from './scenes/ConsultationScene';
import {BackendScene}      from './scenes/BackendScene';
import {Outro}             from './scenes/Outro';
import {BrandScene}        from './scenes/BrandScene';

// ── Тайминг сцен ─────────────────────────────────────────────────
// Все значения в кадрах (fps = 30).
// Чтобы изменить длительность — правьте VIDEO.scenes в theme.ts.
const S = VIDEO.scenes;

const INTRO_START  = 0;
const FAQ_START    = sec(S.intro);
const FUNNEL_START = FAQ_START    + sec(S.faq);
const CONS_START   = FUNNEL_START + sec(S.funnel);
const BACK_START   = CONS_START   + sec(S.consultation);
const OUTRO_START  = BACK_START   + sec(S.backend);
const BRAND_START  = OUTRO_START  + sec(S.outro);

export const TOTAL_FRAMES =
  sec(S.intro + S.faq + S.funnel + S.consultation + S.backend + S.outro + S.brand);

// ── Главная композиция ────────────────────────────────────────────
export const AuditDemo: React.FC = () => (
  <AbsoluteFill style={{background: '#0d1117'}}>

    <Audio
      loop
      src={staticFile('music.mp3')}
      volume={(f) =>
        f < 30 ? f / 30 :
        f > TOTAL_FRAMES - 60 ? (TOTAL_FRAMES - f) / 60 : 1
      }
    />

    <Sequence from={INTRO_START} durationInFrames={sec(S.intro)}>
      <Intro />
    </Sequence>

    <Sequence from={FAQ_START} durationInFrames={sec(S.faq)}>
      <FaqScene />
    </Sequence>

    <Sequence from={FUNNEL_START} durationInFrames={sec(S.funnel)}>
      <FunnelScene />
    </Sequence>

    <Sequence from={CONS_START} durationInFrames={sec(S.consultation)}>
      <ConsultationScene />
    </Sequence>

    <Sequence from={BACK_START} durationInFrames={sec(S.backend)}>
      <BackendScene />
    </Sequence>

    <Sequence from={OUTRO_START} durationInFrames={sec(S.outro)}>
      <Outro />
    </Sequence>

    <Sequence from={BRAND_START} durationInFrames={sec(S.brand)}>
      <BrandScene />
    </Sequence>

  </AbsoluteFill>
);
