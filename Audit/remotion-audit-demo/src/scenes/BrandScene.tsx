import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

export const BrandScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const bgP   = spring({frame,          fps, config: {damping: 20, stiffness: 60}});
  const lineP = spring({frame: frame - 15, fps, config: {damping: 18, stiffness: 80}});
  const nameP = spring({frame: frame - 30, fps, config: {damping: 15, stiffness: 70}});

  return (
    <AbsoluteFill style={{backgroundColor: '#0A0A0F', fontFamily: 'Inter, system-ui, sans-serif'}}>

      {/* Radial glow */}
      <div style={{
        position: 'absolute', inset: 0,
        background: `radial-gradient(ellipse 60% 50% at 50% 50%, rgba(99,102,241,${interpolate(bgP, [0, 1], [0, 0.18])}) 0%, transparent 70%)`,
      }} />

      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>

        {/* Top line */}
        <div style={{
          width: interpolate(lineP, [0, 1], [0, 160]),
          height: 2,
          background: 'linear-gradient(90deg, transparent, #6366F1, transparent)',
          marginBottom: 28,
        }} />

        {/* JI Studio */}
        <div style={{
          opacity: interpolate(nameP, [0, 1], [0, 1]),
          transform: `scale(${interpolate(nameP, [0, 1], [0.75, 1])})`,
          display: 'flex', alignItems: 'baseline', gap: 10,
        }}>
          <span style={{fontSize: 110, fontWeight: 900, color: '#FFFFFF', letterSpacing: 8}}>
            JI
          </span>
          <span style={{
            fontSize: 110, fontWeight: 900,
            background: 'linear-gradient(135deg, #6366F1, #00D9FF)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
            letterSpacing: 8,
          }}>
            Studio
          </span>
        </div>

        {/* Bottom line */}
        <div style={{
          width: interpolate(lineP, [0, 1], [0, 160]),
          height: 2,
          background: 'linear-gradient(90deg, transparent, #6366F1, transparent)',
          marginTop: 28,
        }} />

      </div>
    </AbsoluteFill>
  );
};
