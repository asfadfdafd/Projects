import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';

export interface MessageDef {
  text: string;
  isBot: boolean;
  startFrame: number; // кадр появления (относительно начала сцены)
  time?: string;      // время, например '10:24'
}

interface ChatMessageProps extends MessageDef {}

export const ChatMessage: React.FC<ChatMessageProps> = ({text, isBot, startFrame, time = '10:24'}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const appear = spring({
    frame: frame - startFrame,
    fps,
    config: {damping: 20, stiffness: 150, mass: 0.8},
  });

  if (frame < startFrame) return null;

  const opacity = interpolate(frame - startFrame, [0, 8], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const translateY = interpolate(appear, [0, 1], [12, 0]);

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isBot ? 'flex-start' : 'flex-end',
        marginBottom: 6,
        opacity,
        transform: `translateY(${translateY}px)`,
      }}
    >
      <div style={{
        maxWidth: '72%',
        background: isBot ? theme.bubbleBot : theme.bubbleUser,
        borderRadius: isBot
          ? '18px 18px 18px 4px'
          : '18px 18px 4px 18px',
        padding: '10px 14px 6px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
        position: 'relative',
      }}>
        {/* Имя отправителя (только для бота) */}
        {isBot && (
          <div style={{
            fontSize: 18,
            fontWeight: 700,
            color: theme.accent,
            marginBottom: 4,
            fontFamily: 'SF Pro Display, Inter, system-ui',
          }}>
            Chat_Audit
          </div>
        )}
        {/* Текст сообщения */}
        <div style={{
          fontSize: 24,
          color: theme.textPrimary,
          lineHeight: 1.5,
          fontFamily: 'SF Pro Text, Inter, system-ui',
          whiteSpace: 'pre-line',
        }}>
          {text}
        </div>
        {/* Время */}
        <div style={{
          fontSize: 16,
          color: theme.textTime,
          textAlign: 'right',
          marginTop: 4,
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
          gap: 4,
        }}>
          {time}
          {!isBot && (
            <span style={{color: theme.accentGreen, fontSize: 18}}>✓✓</span>
          )}
        </div>
      </div>
    </div>
  );
};
