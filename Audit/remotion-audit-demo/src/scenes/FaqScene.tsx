import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';
import {TelegramChat} from '../components/TelegramChat';
import {PhoneFrame} from '../components/PhoneFrame';
import {Caption} from '../components/Caption';
import {SplitLayout} from '../components/SplitLayout';
import {MessageDef} from '../components/ChatMessage';

// Сцена 1 — FAQ-консультация (35 секунд = 1050 кадров)
// Контент взят из реальной демонстрации бота (видео 2, 7.7с)
export const FaqScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const isV = height > width;

  const fadeIn  = interpolate(frame, [0, 20],    [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const fadeOut = interpolate(frame, [1030, 1050], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const messages: MessageDef[] = [
    // Приветствие после /start
    {
      isBot: true,
      startFrame: 20,
      time: '14:03',
      text: 'Здравствуйте! Я — консультант аудиторской компании.\n\nМы предоставляем услуги по различным видам аудита: обязательный, инициативный, налоговый и другие.\n\nЕсли есть вопрос — задайте его, и я сделаю всё возможное, чтобы ответить. Если хотите заказать аудит — нажмите кнопку ниже.',
    },
    // Пользователь спрашивает цену
    {
      isBot: false,
      startFrame: 150,
      time: '14:03',
      text: 'Сколько стоит аудит?',
    },
    // Бот отвечает по базе знаний
    {
      isBot: true,
      startFrame: 240,
      time: '14:03',
      text: 'Стоимость аудита зависит от нескольких факторов: вид аудита, выручка компании, численность персонала и стандарт отчётности.\n\nБазовая цена начинается от 350 000 ₸ для инициативного аудита и варьируется от этих факторов.\n\nЧтобы получить точную цену — пройдите короткую анкету (12 вопросов). Это займёт меньше 2 минут.',
    },
    // Вопрос о надбавках
    {
      isBot: false,
      startFrame: 500,
      time: '14:03',
      text: 'С чем связаны надбавки?',
    },
    {
      isBot: true,
      startFrame: 590,
      time: '14:03',
      text: 'Надбавки связаны с несколькими факторами:\n\n• Срочность: менее 30 дней — +40% к стоимости\n• Выручка и численность сотрудников\n• Количество юридических лиц и периодов\n• Нотариальные услуги и переводы документов\n\nЕсли нужна точная цена — пройдите анкету, и я рассчитаю её за минуту.',
    },
    // Пользователь хочет проконсультироваться
    {
      isBot: false,
      startFrame: 820,
      time: '14:04',
      text: 'хочу проконсультироваться',
    },
    {
      isBot: true,
      startFrame: 900,
      time: '14:04',
      text: '📅 Запишитесь на бесплатную консультацию со специалистом:\n\ncal.com/dauren-as-000-fk1rn/nnn-детальный-аудит\n\nВыберите удобное время — подтверждение придёт сюда в Telegram.',
    },
  ];

  const typingFrames = [
    {startFrame: 170, endFrame: 240},
    {startFrame: 520, endFrame: 590},
    {startFrame: 845, endFrame: 900},
  ];

  const annotationSpring = spring({frame: frame - 10, fps, config: {damping: 18, stiffness: 80}});

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at 70% 40%, #0d1f3c 0%, ${theme.bg} 70%)`,
        opacity: fadeIn * fadeOut,
      }}
    >
      <SplitLayout
        vertical={isV}
        left={
          <PhoneFrame width={isV ? 690 : 440} height={isV ? 680 : 860}>
            <TelegramChat messages={messages} typingFrames={typingFrames} />
          </PhoneFrame>
        }
        right={
          <div style={{display: 'flex', flexDirection: 'column', gap: isV ? 28 : 28,
            opacity: annotationSpring,
            transform: isV ? `translateY(${(1 - annotationSpring) * 20}px)` : `translateX(${(1 - annotationSpring) * 40}px)`}}>

            <div>
              <div style={{
                fontSize: isV ? 24 : 18, color: theme.accent, fontWeight: 600,
                fontFamily: 'SF Pro Text, Inter, system-ui',
                textTransform: 'uppercase', letterSpacing: 2, marginBottom: isV ? 14 : 12,
              }}>
                Шаг 1 из 4
              </div>
              <h2 style={{
                fontSize: isV ? 54 : 52, fontWeight: 800, color: theme.textPrimary,
                fontFamily: 'SF Pro Display, Inter, system-ui',
                margin: 0, lineHeight: 1.15, letterSpacing: '-1px',
              }}>
                FAQ-консультант
              </h2>
              <p style={{
                fontSize: isV ? 30 : 24, color: theme.textSecondary, margin: isV ? '14px 0 0' : '14px 0 0',
                fontFamily: 'SF Pro Text, Inter, system-ui', lineHeight: 1.5,
              }}>
                Отвечает на вопросы о ценах, видах аудита и надбавках — строго по базе знаний компании.
              </p>
            </div>

            <div style={{display: isV ? 'grid' : 'flex', flexDirection: isV ? undefined : 'column',
              gridTemplateColumns: isV ? '1fr 1fr' : undefined, gap: isV ? 16 : 0}}>
              {[
                {icon: '🧠', title: 'Умный консультант', desc: 'Отвечает строго по знаниям вашей компании'},
                {icon: '⚡', title: 'Ответ за 3 секунды', desc: 'На любой вопрос клиента, круглосуточно'},
                {icon: '🔒', title: 'Только факты', desc: 'Бот не придумывает — только то, что есть в базе'},
                {icon: '📅', title: 'Запись онлайн', desc: 'Клиент сам выбирает время без участия менеджера'},
              ].map((card, i) => {
                const s = spring({frame: frame - 60 - i * 30, fps, config: {damping: 18, stiffness: 100}});
                return (
                  <div key={i} style={{
                    background: theme.bgCard, border: `1px solid ${theme.border}`,
                    borderRadius: 16, padding: isV ? '20px 20px' : '18px 22px',
                    display: 'flex', gap: 14, alignItems: 'flex-start',
                    marginBottom: isV ? 0 : 8,
                    opacity: s, transform: `translateX(${(1 - s) * 30}px)`,
                  }}>
                    <span style={{fontSize: isV ? 30 : 28}}>{card.icon}</span>
                    <div>
                      <div style={{fontSize: isV ? 26 : 20, fontWeight: 700, color: theme.textPrimary,
                        fontFamily: 'SF Pro Display, Inter, system-ui'}}>
                        {card.title}
                      </div>
                      <div style={{fontSize: isV ? 22 : 17, color: theme.textSecondary, marginTop: 4,
                        fontFamily: 'SF Pro Text, Inter, system-ui'}}>
                        {card.desc}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        }
      />

      <Caption text="Цена не называется — бот предлагает анкету для точного расчёта" icon="💡"
        startFrame={240} durationFrames={250} color={theme.accentGold} />
      <Caption text="Клиент сам выбирает удобное время для консультации" icon="📅"
        startFrame={900} durationFrames={150} color="#a78bfa" />
    </AbsoluteFill>
  );
};
