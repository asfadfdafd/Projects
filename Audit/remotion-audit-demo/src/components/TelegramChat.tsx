import React from 'react';
import {interpolate, useCurrentFrame} from 'remotion';
import {theme} from '../theme';
import {ChatMessage, MessageDef} from './ChatMessage';
import {TypingIndicator} from './TypingIndicator';

interface TelegramChatProps {
  messages: MessageDef[];
  botName?: string;
  botSubtitle?: string;
  // Кадры, в которые показывается typing indicator (перед следующим сообщением бота)
  typingFrames?: Array<{startFrame: number; endFrame: number}>;
}

export const TelegramChat: React.FC<TelegramChatProps> = ({
  messages,
  botName = 'Chat_Audit',
  botSubtitle = 'бот',
  typingFrames = [],
}) => {
  const frame = useCurrentFrame();

  // Показывать ли typing indicator
  const isTyping = typingFrames.some(
    ({startFrame, endFrame}) => frame >= startFrame && frame < endFrame
  );

  // Видимые сообщения
  const visibleMessages = messages.filter((m) => frame >= m.startFrame);

  return (
    <div style={{
      width: '100%',
      height: '100%',
      background: theme.bgTelegram,
      borderRadius: 24,
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      fontFamily: 'SF Pro Text, Inter, system-ui, sans-serif',
    }}>
      {/* Шапка чата */}
      <div style={{
        background: theme.bgHeader,
        padding: '16px 20px',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        borderBottom: `1px solid ${theme.border}`,
        flexShrink: 0,
      }}>
        {/* Аватар */}
        <div style={{
          width: 52,
          height: 52,
          borderRadius: '50%',
          background: `linear-gradient(135deg, ${theme.accent}, #1a7fc1)`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 24,
          flexShrink: 0,
        }}>
          🤖
        </div>
        <div>
          <div style={{fontSize: 22, fontWeight: 700, color: theme.textPrimary}}>
            {botName}
          </div>
          <div style={{fontSize: 16, color: isTyping ? theme.accentGreen : theme.textSecondary}}>
            {isTyping ? 'печатает...' : botSubtitle}
          </div>
        </div>
        {/* Иконки шапки */}
        <div style={{marginLeft: 'auto', display: 'flex', gap: 20, opacity: 0.5}}>
          <span style={{fontSize: 22, color: theme.textPrimary}}>🔍</span>
          <span style={{fontSize: 22, color: theme.textPrimary}}>⋮</span>
        </div>
      </div>

      {/* Область сообщений */}
      <div style={{
        flex: 1,
        padding: '16px 20px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-end',
        gap: 2,
        overflowY: 'hidden',
      }}>
        {visibleMessages.map((msg, i) => (
          <ChatMessage key={i} {...msg} />
        ))}
        {isTyping && <TypingIndicator />}
      </div>

      {/* Поле ввода (декоративное) */}
      <div style={{
        background: theme.bgHeader,
        padding: '12px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        borderTop: `1px solid ${theme.border}`,
        flexShrink: 0,
      }}>
        <div style={{
          flex: 1,
          background: theme.bgTelegram,
          borderRadius: 24,
          padding: '10px 16px',
          fontSize: 18,
          color: theme.textSecondary,
        }}>
          Сообщение...
        </div>
        <div style={{
          width: 44,
          height: 44,
          borderRadius: '50%',
          background: theme.accent,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 20,
        }}>
          🎤
        </div>
      </div>
    </div>
  );
};
