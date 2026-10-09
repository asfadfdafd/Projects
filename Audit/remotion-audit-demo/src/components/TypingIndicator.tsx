import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {theme} from '../theme';

// Анимированные три точки «бот печатает»
export const TypingIndicator: React.FC = () => {
  const frame = useCurrentFrame();

  const dot = (delay: number) =>
    interpolate(
      (frame + delay) % 24,
      [0, 8, 16, 24],
      [0.3, 1, 0.3, 0.3],
      {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}
    );

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '14px 18px',
      background: theme.bubbleBot,
      borderRadius: '18px 18px 18px 4px',
      width: 'fit-content',
      marginBottom: 8,
    }}>
      {[0, 8, 16].map((delay, i) => (
        <div
          key={i}
          style={{
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: theme.textSecondary,
            opacity: dot(delay),
          }}
        />
      ))}
    </div>
  );
};
