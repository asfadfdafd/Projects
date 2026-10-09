import React from 'react';
import {AbsoluteFill, Sequence} from 'remotion';
import {C} from '../theme';
import {HERO} from '../layout';
import {BrowserFrame} from '../components/BrowserFrame';
import {Clip} from '../components/Shot';
import {Caption, Kicker, Title} from '../components/Type';

const CLIP_VERIFY = 146; // 06_verify.mp4 — 5 с (150 кадров), берём с запасом
const MID = 300;

export const S06Verify: React.FC<{duration: number}> = ({duration}) => {
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', left: HERO.frameX, top: 74}}>
        <Kicker delay={0}>Шаг 3 · Проверка человеком</Kicker>
        <Title delay={6} size={46}>
          Последнее слово — за архивистом
        </Title>
      </div>

      <div style={{position: 'absolute', left: HERO.frameX, top: HERO.frameY}}>
        <BrowserFrame
          width={HERO.frameW}
          height={HERO.frameContentH}
          url="archivai.local/documents"
        >
          <Sequence durationInFrames={CLIP_VERIFY}>
            <Clip src="clips/06_verify.mp4" />
          </Sequence>
          <Sequence from={CLIP_VERIFY} durationInFrames={duration - CLIP_VERIFY}>
            <Clip src="clips/05_doc_detail.mp4" />
          </Sequence>
        </BrowserFrame>
      </div>

      <Sequence durationInFrames={CLIP_VERIFY}>
        <Caption delay={12} bottom={48}>
          Скан, короткое описание и выписанные имена — на одном экране
        </Caption>
      </Sequence>
      <Sequence from={CLIP_VERIFY} durationInFrames={MID - CLIP_VERIFY}>
        <Caption delay={10} accent={C.blue} bottom={48}>
          Фамилия распознана с ошибкой — архивист правит её прямо в карточке
        </Caption>
      </Sequence>
      <Sequence from={MID} durationInFrames={duration - MID}>
        <Caption delay={10} accent={C.green} bottom={48}>
          Отметка «Проверено» — дело прошло через специалиста; правки видны в журнале
        </Caption>
      </Sequence>
    </AbsoluteFill>
  );
};
