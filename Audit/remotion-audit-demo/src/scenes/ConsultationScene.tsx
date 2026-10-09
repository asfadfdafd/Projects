import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';
import {TelegramChat} from '../components/TelegramChat';
import {PhoneFrame} from '../components/PhoneFrame';
import {Caption} from '../components/Caption';
import {SplitLayout} from '../components/SplitLayout';
import {MessageDef} from '../components/ChatMessage';

// Сцена 3 — Запись на консультацию через Cal.com (25 секунд = 750 кадров)
// Реальная бронь из видео: ponedeljnik 22 ijunja 2026, 16:00–16:15
export const ConsultationScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const isV = height > width;

  const fadeIn  = interpolate(frame, [0, 20],    [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const fadeOut = interpolate(frame, [730, 750], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const messages: MessageDef[] = [
    {isBot: false, startFrame: 20,  time: '14:04', text: 'хочу поговорить'},
    {isBot: true,  startFrame: 110, time: '14:04',
      text: '📅 Запишитесь на бесплатную консультацию со специалистом:\n\ncal.com/dauren-as-000-fk1rn/nnn-детальный-аудит\n\nВыберите удобное время — подтверждение придёт сюда в Telegram.'},
    // Подтверждение брони (пришло автоматически из Cal.com)
    {isBot: true,  startFrame: 420, time: '14:12',
      text: '✅ Встреча запланирована!\n\n📅 Понедельник, 22 июня 2026 г.\n🕐 16:00 – 16:15 (GMT+05:00)\n👥 NNN детальный аудит\n📍 Cal Video\n\nПодтверждение отправлено на email.'},
  ];

  const typingFrames = [
    {startFrame: 45, endFrame: 110},
  ];

  const annotationSpring = spring({frame: frame - 10, fps, config: {damping: 18, stiffness: 80}});
  const confirmSpring = spring({frame: frame - 430, fps, config: {damping: 18, stiffness: 100}});

  // Cal.com карточка встречи
  const calCardSpring = spring({frame: frame - 440, fps, config: {damping: 18, stiffness: 80}});

  return (
    <AbsoluteFill style={{
      background: `radial-gradient(ellipse at 60% 60%, #1a0d2e 0%, ${theme.bg} 70%)`,
      opacity: fadeIn * fadeOut,
    }}>
      <SplitLayout
        vertical={isV}
        left={
          <PhoneFrame width={isV ? 690 : 440} height={isV ? 680 : 860}>
            <TelegramChat messages={messages} typingFrames={typingFrames} />
          </PhoneFrame>
        }
        right={
          <div style={{display: 'flex', flexDirection: 'column', gap: isV ? 24 : 24,
            opacity: annotationSpring,
            transform: isV ? `translateY(${(1 - annotationSpring) * 20}px)` : `translateX(${(1 - annotationSpring) * 40}px)`}}>

            <div>
              <div style={{fontSize: isV ? 24 : 18, color: '#a78bfa', fontWeight: 600,
                fontFamily: 'SF Pro Text, Inter, system-ui',
                textTransform: 'uppercase', letterSpacing: 2, marginBottom: isV ? 12 : 12}}>
                Шаг 3 из 4
              </div>
              <h2 style={{fontSize: isV ? 52 : 48, fontWeight: 800, color: theme.textPrimary,
                fontFamily: 'SF Pro Display, Inter, system-ui',
                margin: 0, lineHeight: 1.15, letterSpacing: '-1px'}}>
                Запись на консультацию
              </h2>
              <p style={{fontSize: isV ? 28 : 22, color: theme.textSecondary, margin: isV ? '12px 0 0' : '12px 0 0',
                fontFamily: 'SF Pro Text, Inter, system-ui', lineHeight: 1.5}}>
                Клиент сомневается — бот отправляет ссылку для записи. Без участия менеджера.
              </p>
            </div>

            {/* Схема шагов */}
            <div style={{display: isV ? 'grid' : 'flex', flexDirection: isV ? undefined : 'column',
              gridTemplateColumns: isV ? '1fr 1fr' : undefined, gap: isV ? 14 : 16}}>
              {[
                {icon: '💬', text: 'Клиент пишет «хочу поговорить»', frame: 20},
                {icon: '🔗', text: 'Бот отправляет ссылку для записи', frame: 110},
                {icon: '🖱️', text: 'Клиент выбирает слот в календаре', frame: 250},
                {icon: '📩', text: 'Telegram + email уведомления автоматически', frame: 420},
              ].map((item, i) => {
                const s = spring({frame: frame - item.frame, fps, config: {damping: 18, stiffness: 120}});
                const isVisible = frame >= item.frame;
                return (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: isV ? 14 : 16,
                    opacity: isVisible ? s : 0,
                    transform: `translateX(${isVisible ? (1 - s) * 20 : 20}px)`,
                  }}>
                    <div style={{
                      width: isV ? 52 : 50, height: isV ? 52 : 50, borderRadius: 14,
                      background: `${theme.accent}20`, border: `1px solid ${theme.accent}40`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: isV ? 26 : 24, flexShrink: 0,
                    }}>
                      {item.icon}
                    </div>
                    <span style={{fontSize: isV ? 24 : 20, color: theme.textPrimary,
                      fontFamily: 'SF Pro Text, Inter, system-ui', fontWeight: 500, lineHeight: 1.3}}>
                      {item.text}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Cal.com карточка встречи */}
            {frame >= 440 && (
              <div style={{
                background: theme.bgCard, border: `1px solid ${theme.border}`,
                borderRadius: 18, padding: isV ? '20px 24px' : '20px 24px',
                opacity: calCardSpring, transform: `translateY(${(1 - calCardSpring) * 16}px)`,
              }}>
                <div style={{display: 'flex', alignItems: 'center', gap: 12, marginBottom: isV ? 16 : 14}}>
                  <div style={{
                    width: 40, height: 40, borderRadius: '50%',
                    background: `${theme.accentGreen}30`, border: `1px solid ${theme.accentGreen}60`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20,
                  }}>✅</div>
                  <div style={{fontSize: isV ? 24 : 18, fontWeight: 700, color: theme.accentGreen,
                    fontFamily: 'SF Pro Display, Inter, system-ui'}}>
                    Встреча запланирована
                  </div>
                </div>
                {[
                  {label: 'Что',   value: 'NNN детальный аудит'},
                  {label: 'Когда', value: 'Пн, 22 июня 2026 · 16:00–16:15'},
                  {label: 'Кто',   value: 'Dauren_as 000 + Даурен'},
                  {label: 'Где',   value: 'Cal Video'},
                ].map(({label, value}) => (
                  <div key={label} style={{display: 'flex', gap: 14, marginBottom: isV ? 10 : 6}}>
                    <div style={{fontSize: isV ? 22 : 16, color: theme.textSecondary, width: isV ? 70 : 50, flexShrink: 0,
                      fontFamily: 'SF Pro Text, Inter, system-ui'}}>{label}</div>
                    <div style={{fontSize: isV ? 22 : 17, color: theme.textPrimary,
                      fontFamily: 'SF Pro Text, Inter, system-ui'}}>{value}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        }
      />

      <Caption text="Клиент сам выбирает время. Менеджер не нужен." icon="📅"
        startFrame={250} durationFrames={200} color="#a78bfa" />
      <Caption text="Встреча забронирована. Уведомление пришло в Telegram." icon="✅"
        startFrame={420} durationFrames={300} color={theme.accentGreen} />
    </AbsoluteFill>
  );
};
