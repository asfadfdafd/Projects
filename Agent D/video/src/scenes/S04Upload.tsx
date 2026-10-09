import React from 'react';
import {AbsoluteFill, Sequence} from 'remotion';
import {SPLIT} from '../layout';
import {BrowserFrame} from '../components/BrowserFrame';
import {Clip, Shot} from '../components/Shot';
import {FeatureRow, Kicker, Title} from '../components/Type';

const CLIP_UPLOAD = 180; // 02_upload.mp4 — 6.13 с (184 кадра), берём с запасом

export const S04Upload: React.FC<{duration: number}> = ({duration}) => {
  return (
    <AbsoluteFill>
      <div
        style={{
          position: 'absolute',
          left: SPLIT.frameX,
          top: SPLIT.frameY,
        }}
      >
        <BrowserFrame
          width={SPLIT.frameW}
          height={SPLIT.frameContentH}
          url="archivai.local/upload"
        >
          <Sequence durationInFrames={CLIP_UPLOAD}>
            <Clip src="clips/02_upload.mp4" />
          </Sequence>
          <Sequence from={CLIP_UPLOAD} durationInFrames={duration - CLIP_UPLOAD}>
            <Shot
              src="shots/upload_ready.png"
              duration={duration - CLIP_UPLOAD}
              focus={{x: 0.5, y: 0.62, from: 1.02, to: 1.1}}
            />
          </Sequence>
        </BrowserFrame>
      </div>

      <div
        style={{
          position: 'absolute',
          left: SPLIT.textX,
          top: 236,
          width: SPLIT.textW,
        }}
      >
        <Kicker delay={0}>Шаг 1 · Загрузка</Kicker>
        <Title delay={8} size={50}>
          Положите сканы — дальше система сама
        </Title>
        <div style={{display: 'flex', flexDirection: 'column', gap: 16, marginTop: 40}}>
          <FeatureRow
            title="Фото, JPG, PNG, TIFF"
            note="Многостраничное дело собирается в один документ"
            delay={30}
          />
          <FeatureRow
            title="Хоть вся папка целиком"
            note="Или система сама заберёт сканы из указанного хранилища"
            delay={48}
          />
          <FeatureRow
            title="Файлы остаются у вас"
            note="Хранятся на вашем сервере, посторонним они недоступны"
            delay={66}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
