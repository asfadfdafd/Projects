import React from 'react';
import {AbsoluteFill, Sequence} from 'remotion';
import {C} from '../theme';
import {HERO} from '../layout';
import {BrowserFrame} from '../components/BrowserFrame';
import {Clip, Shot} from '../components/Shot';
import {Caption, Kicker, Title} from '../components/Type';

const TYPE_END = 159; // 04a_search_type.mp4 — 5.43 с (163 кадра), ускоренный набор запроса
const RESULTS_END = TYPE_END + 250; // 04b_search_results.mp4 — 8.5 с (255 кадров)

export const S07Search: React.FC<{duration: number}> = ({duration}) => {
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', left: HERO.frameX, top: 74}}>
        <Kicker delay={0}>Шаг 4 · Поиск</Kicker>
        <Title delay={6} size={46}>
          Спрашивайте словами, а не шифром дела
        </Title>
      </div>

      <div style={{position: 'absolute', left: HERO.frameX, top: HERO.frameY}}>
        <BrowserFrame
          width={HERO.frameW}
          height={HERO.frameContentH}
          url="archivai.local/search"
        >
          <Sequence durationInFrames={TYPE_END}>
            <Clip src="clips/04a_search_type.mp4" />
          </Sequence>
          <Sequence from={TYPE_END} durationInFrames={RESULTS_END - TYPE_END}>
            <Clip src="clips/04b_search_results.mp4" />
          </Sequence>
          <Sequence from={RESULTS_END} durationInFrames={duration - RESULTS_END}>
            <Shot
              src="shots/search_results.png"
              duration={duration - RESULTS_END}
              focus={{x: 0.44, y: 0.12, from: 1.1, to: 1.4}}
            />
          </Sequence>
        </BrowserFrame>
      </div>

      <Sequence durationInFrames={TYPE_END}>
        <Caption delay={12}>
          «документы с упоминанием москвы» — обычная фраза, а не поисковый код
        </Caption>
      </Sequence>
      <Sequence from={TYPE_END} durationInFrames={RESULTS_END - TYPE_END}>
        <Caption delay={10} accent={C.blue}>
          Ищет и по смыслу, и по словам — на русском, казахском и английском
        </Caption>
      </Sequence>
      <Sequence from={RESULTS_END} durationInFrames={duration - RESULTS_END}>
        <Caption delay={8} accent={C.green}>
          Рядом с каждым делом — насколько оно подходит под запрос
        </Caption>
      </Sequence>
    </AbsoluteFill>
  );
};
