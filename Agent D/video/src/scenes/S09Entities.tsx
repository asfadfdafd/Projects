import React from 'react';
import {AbsoluteFill} from 'remotion';
import {C} from '../theme';
import {BrowserFrame} from '../components/BrowserFrame';
import {Shot} from '../components/Shot';
import {Chip, Kicker, Lead, Title} from '../components/Type';
import {frameHeight} from '../layout';

const FRAME_W = 1010;

export const S09Entities: React.FC<{duration: number}> = ({duration}) => {
  const h = frameHeight(FRAME_W);
  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          right: 70,
          top: Math.round((1080 - (h + 46)) / 2),
        }}
      >
        <BrowserFrame width={FRAME_W} height={h} url="archivai.local/entities">
          <Shot
            src="shots/entity_graph_crop.png"
            duration={duration}
            focus={{x: 0.5, y: 0.55, from: 1.02, to: 1.14}}
          />
        </BrowserFrame>
      </div>

      <div style={{position: 'absolute', left: 90, top: 250, width: 700}}>
        <Kicker delay={0}>Шаг 5 · Связи</Kicker>
        <Title delay={8} size={50}>
          Люди, места, организации — и связи между ними
        </Title>
        <Lead delay={18} size={24} maxWidth={660}>
          Разные написания одной фамилии сводятся автоматически. По схеме видно,
          кто с кем встречается в делах и через какие документы.
        </Lead>
        <div style={{display: 'flex', gap: 12, marginTop: 36, flexWrap: 'wrap'}}>
          <Chip delay={40} tone="navy">
            Люди
          </Chip>
          <Chip delay={48}>Организации</Chip>
          <Chip delay={56}>Места</Chip>
          <Chip delay={64}>Даты</Chip>
          <Chip delay={72} tone="green">
            Выгрузка в таблицу
          </Chip>
        </div>
        <div
          style={{
            marginTop: 34,
            paddingLeft: 20,
            borderLeft: `3px solid ${C.orange}`,
            fontSize: 22,
            lineHeight: 1.45,
            color: C.inkMuted,
            maxWidth: 620,
          }}
        >
          «МЕНДЕШЕВ» и «МЕН ЕШЕВ» собираются в одну карточку — при этом написание
          из самого документа сохраняется.
        </div>
      </div>
    </AbsoluteFill>
  );
};
