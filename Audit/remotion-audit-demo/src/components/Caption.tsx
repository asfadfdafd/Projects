import React from 'react';
import {interpolate, useCurrentFrame, spring, useVideoConfig} from 'remotion';
import {theme} from '../theme';

interface CaptionProps {
  text: string;
  icon?: string;
  startFrame: number;
  durationFrames?: number;
  position?: 'bottom' | 'top' | 'center';
  color?: string;
}

export const Caption: React.FC<CaptionProps> = ({
  text, icon = '💡', startFrame, durationFrames = 120,
  position = 'bottom', color = theme.accentGold,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const isV = height > width;

  const appear = spring({frame: frame - startFrame, fps, config: {damping: 18, stiffness: 120}});
  const fadeOut = durationFrames
    ? interpolate(frame, [startFrame + durationFrames - 20, startFrame + durationFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})
    : 1;

  if (frame < startFrame || frame > startFrame + durationFrames) return null;

  const bottomPos = isV ? 80 : 60;

  const positionStyle: React.CSSProperties =
    position === 'bottom'
      ? {bottom: bottomPos, left: '50%', transform: `translateX(-50%) translateY(${(1 - appear) * 30}px)`}
      : position === 'top'
      ? {top: bottomPos, left: '50%', transform: `translateX(-50%) translateY(${-(1 - appear) * 30}px)`}
      : {top: '50%', left: '50%', transform: `translate(-50%, -50%) scale(${appear})`};

  return (
    <div style={{
      position: 'absolute',
      ...positionStyle,
      opacity: appear * fadeOut,
      background: 'rgba(13,17,23,0.92)',
      border: `2px solid ${color}`,
      borderRadius: 16,
      padding: isV ? '20px 32px' : '18px 36px',
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      boxShadow: `0 0 32px ${color}44`,
      whiteSpace: isV ? 'normal' : 'nowrap',
      maxWidth: isV ? '88%' : undefined,
      textAlign: isV ? 'center' : undefined,
      zIndex: 100,
    }}>
      {icon && <span style={{fontSize: isV ? 36 : 32, flexShrink: 0}}>{icon}</span>}
      <span style={{
        fontSize: isV ? 30 : 32,
        fontWeight: 600,
        color: theme.textPrimary,
        fontFamily: 'SF Pro Display, Inter, system-ui, sans-serif',
        letterSpacing: '-0.3px',
        lineHeight: isV ? 1.4 : undefined,
      }}>
        {text}
      </span>
    </div>
  );
};
