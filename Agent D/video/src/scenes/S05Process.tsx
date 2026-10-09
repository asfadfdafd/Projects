import React from 'react';
import {AbsoluteFill, Sequence, interpolate, useCurrentFrame} from 'remotion';
import {C} from '../theme';
import {SPLIT_R} from '../layout';
import {BrowserFrame} from '../components/BrowserFrame';
import {Shot} from '../components/Shot';
import {Kicker, Lead, Title} from '../components/Type';
import {Pipeline} from '../components/Pipeline';
import {EASE, riseIn} from '../lib/anim';

const SWITCH = 190; // кадр, на котором «Processing…» превращается в готовый разбор

const STEPS = [
  {label: 'Распознавание'},
  {label: 'Язык'},
  {label: 'Вид документа'},
  {label: 'Описание'},
  {label: 'Имена и даты'},
  {label: 'Поиск'},
];

export const S05Process: React.FC<{duration: number}> = ({duration}) => {
  const frame = useCurrentFrame();
  const done = interpolate(frame - SWITCH, [0, 18], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: EASE,
  });

  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', left: SPLIT_R.frameX, top: SPLIT_R.frameY}}>
        <BrowserFrame
          width={SPLIT_R.frameW}
          height={SPLIT_R.frameContentH}
          url="archivai.local/documents/stenogramma1931"
        >
          <Sequence durationInFrames={SWITCH + 18}>
            <Shot
              src="shots/doc_processing.png"
              duration={SWITCH + 18}
              focus={{x: 0.62, y: 0.35, from: 1.02, to: 1.07}}
            />
          </Sequence>
          <Sequence from={SWITCH} durationInFrames={duration - SWITCH}>
            <div style={{opacity: done, width: '100%', height: '100%'}}>
              <Shot
                src="shots/doc_done.png"
                duration={duration - SWITCH}
                focus={{x: 0.66, y: 0.34, from: 1.02, to: 1.08}}
              />
            </div>
          </Sequence>

          {/* Плашка статуса поверх скриншота */}
          <div
            style={{
              position: 'absolute',
              left: 26,
              bottom: 26,
              padding: '13px 22px',
              borderRadius: 999,
              fontSize: 21,
              fontWeight: 700,
              color: C.white,
              backgroundColor: done > 0.5 ? C.green : C.navy,
              boxShadow: '0 20px 44px -22px rgba(17,27,49,0.8)',
            }}
          >
            {done > 0.5 ? '✓ Готово' : 'Обработка…'}
          </div>
        </BrowserFrame>
      </div>

      <div
        style={{position: 'absolute', left: SPLIT_R.textX, top: 190, width: SPLIT_R.textW}}
      >
        <Kicker delay={0}>Шаг 2 · Обработка</Kicker>
        <Title delay={8} size={50}>
          Распознаёт текст и сразу разбирает дело
        </Title>
        <Lead delay={18} size={24} maxWidth={660}>
          Система читает скан, определяет язык и вид документа, составляет короткое
          описание и выписывает людей, организации, места и даты.
        </Lead>

        <div style={{marginTop: 44, transform: 'scale(0.86)', transformOrigin: 'left top'}}>
          <Pipeline steps={STEPS} delay={30} stepFrames={22} compact />
        </div>

        <div
          style={{
            ...riseIn(frame, SWITCH + 10, 18),
            marginTop: 34,
            padding: '20px 24px',
            borderRadius: 14,
            backgroundColor: C.greenSoft,
            border: '1px solid #C4E8D5',
            fontSize: 22,
            lineHeight: 1.45,
            color: '#136341',
            maxWidth: 660,
          }}
        >
          Ничего не берётся из воздуха: видно, из какого места документа взято
          каждое поле, и любое из них можно поправить.
        </div>
      </div>
    </AbsoluteFill>
  );
};
