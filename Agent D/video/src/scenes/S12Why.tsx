import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C} from '../theme';
import {NavyPanel} from '../components/NavyPanel';
import {Kicker, Title} from '../components/Type';
import {riseIn} from '../lib/anim';

const TILES = [
  {
    title: 'Без подписок и лицензий',
    note: 'Открытый код: не нужно платить за каждое рабочее место и продлевать доступ.',
  },
  {
    title: 'Работает на вашем сервере',
    note: 'Документы не покидают учреждение, для работы не нужен интернет.',
  },
  {
    title: 'Русский и казахский',
    note: 'Печатный и рукописный текст XX века, в том числе смешанные документы.',
  },
  {
    title: 'Меняется без программиста',
    note: 'Настройки задаются обычными фразами, порядок обработки можно перестроить.',
  },
];

export const S12Why: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      {/* Подложка уже тёмная на уровне таймлайна — здесь просто держим цвет */}
      <NavyPanel fadeIn={0}>
        <AbsoluteFill style={{padding: '104px 96px', justifyContent: 'center'}}>
          <Kicker delay={6}>Почему ArchivAI</Kicker>
          <Title delay={12} size={56} color={C.white} maxWidth={1300}>
            Архив остаётся вашим — целиком
          </Title>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 22,
              marginTop: 56,
              maxWidth: 1500,
            }}
          >
            {TILES.map((t, i) => (
              <div
                key={t.title}
                style={{
                  ...riseIn(frame, 30 + i * 14, 24),
                  padding: '30px 32px',
                  borderRadius: 18,
                  backgroundColor: 'rgba(255,255,255,0.055)',
                  border: '1px solid rgba(255,255,255,0.11)',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 14,
                    fontSize: 30,
                    fontWeight: 750,
                    color: C.white,
                    letterSpacing: -0.5,
                  }}
                >
                  <span
                    style={{
                      width: 12,
                      height: 12,
                      borderRadius: 12,
                      backgroundColor: C.orange,
                    }}
                  />
                  {t.title}
                </div>
                <div
                  style={{
                    marginTop: 12,
                    fontSize: 22,
                    lineHeight: 1.45,
                    color: 'rgba(255,255,255,0.66)',
                  }}
                >
                  {t.note}
                </div>
              </div>
            ))}
          </div>
        </AbsoluteFill>
      </NavyPanel>
    </AbsoluteFill>
  );
};
