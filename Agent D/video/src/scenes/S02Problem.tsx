import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {C} from '../theme';
import {riseIn} from '../lib/anim';
import {Kicker, Title, FeatureRow} from '../components/Type';

const PAINS = [
  {
    title: 'Скан — это картинка',
    note: 'Внутри файла нет текста: найти документ по содержанию невозможно',
  },
  {
    title: 'Вход только через опись',
    note: 'Найти можно лишь то, что кто-то заранее описал вручную',
  },
  {
    title: 'Описание — это месяцы работы',
    note: 'Имена, даты и организации выписываются от руки по каждому делу',
  },
];

export const S02Problem: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{padding: '96px 90px'}}>
      <Kicker delay={0} color={C.navyMuted}>
        Проблема
      </Kicker>
      <Title delay={8} size={60} maxWidth={1200}>
        Оцифровали — но пользоваться всё равно нельзя
      </Title>

      <div style={{display: 'flex', gap: 64, marginTop: 60, alignItems: 'center'}}>
        <div
          style={{
            ...riseIn(frame, 20, 30),
            width: 430,
            flexShrink: 0,
            position: 'relative',
          }}
        >
          <div
            style={{
              transform: 'rotate(-2.2deg)',
              borderRadius: 14,
              overflow: 'hidden',
              border: `1px solid ${C.line}`,
              boxShadow: '0 40px 80px -34px rgba(17,27,49,0.55)',
              backgroundColor: C.white,
            }}
          >
            <Img
              src={staticFile('shots/scan_source.png')}
              style={{width: '100%', display: 'block', filter: 'saturate(0.92)'}}
            />
          </div>
          <div
            style={{
              ...riseIn(frame, 46, 14),
              position: 'absolute',
              right: -26,
              bottom: 34,
              padding: '12px 20px',
              borderRadius: 999,
              backgroundColor: C.navy,
              color: C.white,
              fontSize: 20,
              fontWeight: 700,
              letterSpacing: 0.6,
              boxShadow: '0 20px 44px -20px rgba(17,27,49,0.7)',
            }}
          >
скан.jpg · текста внутри нет
          </div>
        </div>

        <div style={{flex: 1, display: 'flex', flexDirection: 'column', gap: 18}}>
          {PAINS.map((p, i) => (
            <FeatureRow
              key={p.title}
              title={p.title}
              note={p.note}
              delay={34 + i * 18}
              dot="#D9534F"
              check={false}
            />
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
