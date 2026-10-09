import React from 'react';
import {AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame} from 'remotion';
import {MUSIC_FILE, MUSIC_VOLUME} from './theme';
import {buildTimeline, SceneId, Slot} from './timeline';
import {Stage, StageMark} from './components/Stage';
import {NavyPanel} from './components/NavyPanel';
import {sceneFade} from './lib/anim';

import {S01Intro} from './scenes/S01Intro';
import {S02Problem} from './scenes/S02Problem';
import {S03How} from './scenes/S03How';
import {S04Upload} from './scenes/S04Upload';
import {S05Process} from './scenes/S05Process';
import {S06Verify} from './scenes/S06Verify';
import {S07Search} from './scenes/S07Search';
import {S08Ask} from './scenes/S08Ask';
import {S09Entities} from './scenes/S09Entities';
import {S10Agent} from './scenes/S10Agent';
import {S11Control} from './scenes/S11Control';
import {S12Why} from './scenes/S12Why';
import {S13Outro} from './scenes/S13Outro';

const SCENES: Record<SceneId, React.FC<{duration: number}>> = {
  intro: () => <S01Intro />,
  problem: () => <S02Problem />,
  how: () => <S03How />,
  upload: ({duration}) => <S04Upload duration={duration} />,
  process: ({duration}) => <S05Process duration={duration} />,
  verify: ({duration}) => <S06Verify duration={duration} />,
  search: ({duration}) => <S07Search duration={duration} />,
  ask: ({duration}) => <S08Ask duration={duration} />,
  entities: ({duration}) => <S09Entities duration={duration} />,
  agent: ({duration}) => <S10Agent duration={duration} />,
  control: ({duration}) => <S11Control duration={duration} />,
  why: () => <S12Why />,
  outro: () => <S13Outro />,
};

const DARK_SCENES: SceneId[] = ['why', 'outro'];

/** Обёртка, которая гасит сцену на стыках, чтобы монтаж был мягким. */
const Fade: React.FC<{duration: number; children: React.ReactNode}> = ({
  duration,
  children,
}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{opacity: sceneFade(frame, duration, 11)}}>
      {children}
    </AbsoluteFill>
  );
};

export const ArchivAIVideo: React.FC<{order: SceneId[]}> = ({order}) => {
  const slots: Slot[] = buildTimeline(order);
  const total = slots.reduce((a, s) => a + s.durationInFrames, 0);
  const frame = useCurrentFrame();

  // Момент, с которого ролик уходит в тёмную часть.
  const firstDark = slots.find((s) => DARK_SCENES.includes(s.id));
  const darkFrom = firstDark ? firstDark.from : total + 999;
  const darkMix = interpolate(frame, [darkFrom - 16, darkFrom], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill>
      {/* Постоянная подложка: светлая в основной части, тёмная в финале.
          Сцены растворяются именно в неё, поэтому стыки не «мигают». */}
      <Stage />
      <AbsoluteFill style={{opacity: darkMix}}>
        <NavyPanel fadeIn={0} />
      </AbsoluteFill>

      {slots.map((slot) => {
        const Scene = SCENES[slot.id];
        return (
          <Sequence
            key={slot.id}
            from={slot.from}
            durationInFrames={slot.durationInFrames}
            name={slot.id}
          >
            <Fade duration={slot.durationInFrames}>
              <Scene duration={slot.durationInFrames} />
            </Fade>
          </Sequence>
        );
      })}

      <AbsoluteFill style={{opacity: 1 - darkMix}}>
        <StageMark />
      </AbsoluteFill>

      {MUSIC_FILE ? (
        <Audio
          src={staticFile(MUSIC_FILE)}
          volume={(f) =>
            interpolate(
              f,
              [0, 30, total - 60, total],
              [0, MUSIC_VOLUME, MUSIC_VOLUME, 0],
              {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
            )
          }
        />
      ) : null}
    </AbsoluteFill>
  );
};
