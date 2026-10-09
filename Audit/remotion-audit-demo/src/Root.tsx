import React from 'react';
import {Composition} from 'remotion';
import {AuditDemo, TOTAL_FRAMES} from './AuditDemo';
import {VIDEO} from './theme';

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="AuditDemo"
      component={AuditDemo}
      durationInFrames={TOTAL_FRAMES}
      fps={VIDEO.fps}
      width={VIDEO.width}
      height={VIDEO.height}
    />
    <Composition
      id="AuditDemoV"
      component={AuditDemo}
      durationInFrames={TOTAL_FRAMES}
      fps={VIDEO.fps}
      width={1080}
      height={1920}
    />
  </>
);
