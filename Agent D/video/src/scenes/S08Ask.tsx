/**
 * Сцена «Вопрос архиву» — СЕЙЧАС НЕ В МОНТАЖЕ.
 *
 * В имеющейся записи экрана ответ ассистента построен на скане с шумным
 * распознаванием и в кадре выглядит нечитаемо. Сцена оставлена готовой:
 * запишите диалог на документе с чистым текстом, замените
 * public/clips/08_answer.mp4 и верните 'ask' в ORDER в src/timeline.ts.
 */
import React from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame} from 'remotion';
import {C} from '../theme';
import {SPLIT} from '../layout';
import {BrowserFrame} from '../components/BrowserFrame';
import {Clip, Shot} from '../components/Shot';
import {FeatureRow, Kicker, Title} from '../components/Type';
import {riseIn} from '../lib/anim';

const EMPTY = 60;
const ASK_END = EMPTY + 185; // 07_ask.mp4 — 6.3 с (189 кадров), ускоренный набор вопроса

export const S08Ask: React.FC<{duration: number}> = ({duration}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', left: SPLIT.frameX, top: SPLIT.frameY}}>
        <BrowserFrame
          width={SPLIT.frameW}
          height={SPLIT.frameContentH}
          url="archivai.local/chat"
        >
          <Sequence durationInFrames={EMPTY}>
            <Shot
              src="shots/ask_empty.png"
              duration={EMPTY}
              focus={{x: 0.5, y: 0.2, from: 1.02, to: 1.06}}
            />
          </Sequence>
          <Sequence from={EMPTY} durationInFrames={ASK_END - EMPTY}>
            <Clip src="clips/07_ask.mp4" />
          </Sequence>
          <Sequence from={ASK_END} durationInFrames={duration - ASK_END}>
            <Clip src="clips/08_answer.mp4" />
          </Sequence>
        </BrowserFrame>

        {/* Выноска к цитате в ответе */}
        <div
          style={{
            ...riseIn(frame, ASK_END + 40, 20),
            position: 'absolute',
            left: 40,
            bottom: -26,
            padding: '14px 24px',
            borderRadius: 999,
            backgroundColor: C.navy,
            color: C.white,
            fontSize: 21,
            fontWeight: 650,
            boxShadow: '0 24px 48px -22px rgba(17,27,49,0.75)',
          }}
        >
          (1) архив.jpg — ссылка открывает сам документ
        </div>
      </div>

      <div
        style={{position: 'absolute', left: SPLIT.textX, top: 214, width: SPLIT.textW}}
      >
        <Kicker delay={0}>Вопрос архиву</Kicker>
        <Title delay={8} size={50}>
          Ответ — только из ваших документов
        </Title>
        <div style={{display: 'flex', flexDirection: 'column', gap: 15, marginTop: 36}}>
          <FeatureRow
            title="Каждый ответ со ссылкой"
            note="Нажмите на источник — откроется нужный скан"
            delay={30}
          />
          <FeatureRow
            title="Ничего не придумывает"
            note="Нет этого в архиве — так и скажет"
            delay={48}
          />
          <FeatureRow
            title="Спрашивать можно на любом языке"
            note="Русский, казахский, английский — в одной беседе"
            delay={66}
          />
          <FeatureRow
            title="Беседа сохраняется"
            note="Можно уточнять и возвращаться к прошлым вопросам"
            delay={84}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
