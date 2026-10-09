import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C} from '../theme';
import {BrowserFrame} from '../components/BrowserFrame';
import {Shot} from '../components/Shot';
import {Caption, Kicker, Lead, Title} from '../components/Type';
import {riseIn} from '../lib/anim';

const FRAME_W = 800;
const FRAME_H = 690;

const PROMPTS = [
  'Ищи больше по смыслу, чем по отдельным словам',
  'Покажи, как менялось число приказов по годам',
  'Добавь вид документа «протокол» и перепроверь дела',
  'Объедини одинаковые фамилии',
];

const RESULTS = [
  'Поиск: больше по смыслу',
  'Показывать 10 дел вместо 5',
  'Добавлен вид: протокол',
];

export const S10Agent: React.FC<{duration: number}> = ({duration}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          right: 96,
          top: Math.round((1080 - (FRAME_H + 46)) / 2),
        }}
      >
        <BrowserFrame width={FRAME_W} height={FRAME_H} url="archivai.local/agent">
          <Shot
            src="shots/agent.png"
            duration={duration}
            fit="cover"
            position="top center"
            focus={{x: 0.5, y: 0.22, from: 1.0, to: 1.08}}
          />
        </BrowserFrame>
      </div>

      <div style={{position: 'absolute', left: 90, top: 176, width: 780}}>
        <Kicker delay={0}>Шаг 6 · Настройка</Kicker>
        <Title delay={8} size={50}>
          Настройка системы — обычными словами
        </Title>
        <Lead delay={18} size={24} maxWidth={720}>
          Не нужно звать программиста. Напишите обычной фразой, как система должна
          работать, — она перенастроится и покажет, что именно изменилось.
        </Lead>

        <div style={{display: 'flex', flexDirection: 'column', gap: 12, marginTop: 34}}>
          {PROMPTS.map((p, i) => (
            <div
              key={p}
              style={{
                ...riseIn(frame, 40 + i * 20, 16),
                alignSelf: 'flex-start',
                padding: '14px 22px',
                borderRadius: 14,
                borderTopLeftRadius: 4,
                backgroundColor: C.navy,
                color: C.white,
                fontSize: 22,
                fontWeight: 500,
                maxWidth: 720,
                boxShadow: '0 18px 40px -24px rgba(17,27,49,0.7)',
              }}
            >
              {p}
            </div>
          ))}
        </div>

        <div
          style={{
            ...riseIn(frame, 140, 18),
            marginTop: 30,
            display: 'flex',
            gap: 10,
            flexWrap: 'wrap',
          }}
        >
          {RESULTS.map((d, i) => (
            <span
              key={d}
              style={{
                ...riseIn(frame, 146 + i * 12, 10),
                padding: '10px 18px',
                borderRadius: 999,
                fontSize: 20,
                fontWeight: 650,
                backgroundColor: C.greenSoft,
                color: '#137A4A',
                border: '1px solid #C4E8D5',
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {d}
            </span>
          ))}
        </div>
      </div>

      <Caption delay={duration - 130} accent={C.green} bottom={44}>
        Каждое изменение видно в списке настроек и возвращается обратно одной кнопкой
      </Caption>
    </AbsoluteFill>
  );
};
