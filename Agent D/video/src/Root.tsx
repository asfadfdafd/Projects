import React from 'react';
import {Composition} from 'remotion';
import {ArchivAIVideo} from './Video';
import {FPS, H, W} from './theme';
import {ORDER, TEASER_ORDER, totalFrames} from './timeline';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ArchivAIDemo"
        component={ArchivAIVideo}
        durationInFrames={totalFrames(ORDER)}
        fps={FPS}
        width={W}
        height={H}
        defaultProps={{order: ORDER}}
      />
      <Composition
        id="ArchivAITeaser"
        component={ArchivAIVideo}
        durationInFrames={totalFrames(TEASER_ORDER)}
        fps={FPS}
        width={W}
        height={H}
        defaultProps={{order: TEASER_ORDER}}
      />
    </>
  );
};
