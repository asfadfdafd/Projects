import React from 'react';
import {AbsoluteFill, Sequence} from 'remotion';
import {C} from '../theme';
import {BrowserFrame} from '../components/BrowserFrame';
import {Shot} from '../components/Shot';
import {Kicker, Lead, Title} from '../components/Type';
import {Kpi} from '../components/Kpi';
import {frameHeight} from '../layout';

const FRAME_W = 940;
const SWITCH = 200;

export const S11Control: React.FC<{duration: number}> = ({duration}) => {
  const h = frameHeight(FRAME_W);
  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          right: 74,
          top: Math.round((1080 - (h + 46)) / 2),
        }}
      >
        <BrowserFrame width={FRAME_W} height={h} url="archivai.local/dashboard">
          <Sequence durationInFrames={SWITCH}>
            <Shot
              src="shots/dashboard_crop.png"
              duration={SWITCH}
              focus={{x: 0.5, y: 0.22, from: 1.0, to: 1.07}}
            />
          </Sequence>
          <Sequence from={SWITCH} durationInFrames={duration - SWITCH}>
            <Shot
              src="shots/usage.png"
              duration={duration - SWITCH}
              focus={{x: 0.5, y: 0.3, from: 1.02, to: 1.09}}
            />
          </Sequence>
        </BrowserFrame>
      </div>

      <div style={{position: 'absolute', left: 90, top: 216, width: 760}}>
        <Kicker delay={0}>Контроль</Kicker>
        <Title delay={8} size={50}>
          Одна сводка — и полный журнал действий
        </Title>
        <Lead delay={18} size={23} maxWidth={700}>
          Все цифры считаются одинаково, поэтому сводка на экране и выгруженный
          отчёт всегда сходятся между собой.
        </Lead>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 16,
            marginTop: 36,
            maxWidth: 660,
          }}
        >
          <Kpi value={7} label="Документов обработано" delay={34} size={62} />
          <Kpi value={19} label="Имён, мест и дат найдено" delay={46} size={62} />
          <Kpi value={11} label="Людей определено" delay={58} size={62} />
          <Kpi value={70} label="Обращений к документам" delay={70} size={62} />
        </div>

        <div
          style={{
            marginTop: 30,
            fontSize: 22,
            color: C.inkMuted,
            paddingLeft: 20,
            borderLeft: `3px solid ${C.orange}`,
            maxWidth: 640,
            lineHeight: 1.45,
          }}
        >
          Кто искал, что открывал, кто входил — включая неудачные попытки входа.
        </div>
      </div>
    </AbsoluteFill>
  );
};
