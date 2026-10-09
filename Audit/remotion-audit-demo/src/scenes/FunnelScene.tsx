import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';
import {TelegramChat} from '../components/TelegramChat';
import {PhoneFrame} from '../components/PhoneFrame';
import {Caption} from '../components/Caption';
import {SplitLayout} from '../components/SplitLayout';
import {MessageDef} from '../components/ChatMessage';

// Сцена 2 — Воронка: 12-шаговая анкета → КП → договор (80 секунд = 2400 кадров)
// Реальный диалог из видео-демо: компания "Гугл", CEO Даурен, итог ₸1 250 000
export const FunnelScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const isV = height > width;

  const fadeIn  = interpolate(frame, [0, 20],    [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const fadeOut = interpolate(frame, [2380, 2400], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const messages: MessageDef[] = [
    // Запуск воронки
    {isBot: false, startFrame: 20,  time: '13:56', text: '/start'},
    {isBot: true,  startFrame: 100, time: '13:56',
      text: 'Здравствуйте! Я — консультант аудиторской компании.\n\nЕсли готовы заказать аудит — начнём с анкеты. Это займёт меньше 2 минут.'},

    // Начало анкеты
    {isBot: true,  startFrame: 280, time: '13:56',
      text: '📋 Отлично! Задам 12 коротких вопросов — по ним рассчитаю точную стоимость и пришлю коммерческое предложение.\n\nВопрос 1/12. Название вашей компании?'},
    {isBot: false, startFrame: 390, time: '13:56', text: 'Гугл'},

    {isBot: true,  startFrame: 460, time: '13:56', text: 'Вопрос 2/12. Контактное лицо (ФИО, должность)?'},
    {isBot: false, startFrame: 550, time: '13:56', text: 'Даурен, CEO'},

    {isBot: true,  startFrame: 620, time: '13:56', text: 'Вопрос 3/12. Email для связи?'},
    {isBot: false, startFrame: 710, time: '13:56', text: 'dauren@gmail.com'},

    // Тип аудита
    {isBot: true,  startFrame: 780, time: '13:57',
      text: 'Вопрос 4/12. Вид аудита? Ответьте цифрой:\n1 — Обязательный\n2 — Инициативный\n3 — Аудит недропользователя\n4 — Налоговый\n5 — Due diligence'},
    {isBot: false, startFrame: 870, time: '13:57', text: '1'},

    // Параметры
    {isBot: true,  startFrame: 940, time: '13:57',
      text: 'Вопрос 6/12. Стандарт отчётности?\n1 — НСФО\n2 — МСФО'},
    {isBot: false, startFrame: 1020, time: '13:57', text: '1'},

    {isBot: true,  startFrame: 1080, time: '13:57',
      text: 'Вопрос 8/12. За сколько дней нужен результат?\n(менее 30 — срочный тариф)'},
    {isBot: false, startFrame: 1160, time: '13:57', text: '24'},

    {isBot: true,  startFrame: 1230, time: '13:57',
      text: 'Вопрос 9/12. Годовая выручка?\n1 — до ₸100 млн\n2 — ₸100 млн – 1 млрд\n3 — 1 – 10 млрд\n4 — свыше ₸10 млрд'},
    {isBot: false, startFrame: 1310, time: '13:57', text: '2'},

    // Завершение анкеты
    {isBot: true,  startFrame: 1380, time: '13:57',
      text: '✅ Спасибо! Анкета заполнена.\nСчитаю стоимость — это займёт меньше минуты...'},

    // КП — реальный текст из видео
    {isBot: true,  startFrame: 1560, time: '13:57',
      text: 'Здравствуйте, Гугл! 🎯\n\nНаша компания предлагает услугу обязательного аудита за последний год по стандарту НСФО (1 юридическое лицо).\n\nУчитываем срочность: завершим за 24 дня.\n\n💰 Итоговая стоимость: 1 250 000 ₸\n\nГотовы оформить договор?'},

    // Согласие клиента
    {isBot: false, startFrame: 1850, time: '13:58', text: '✅ Согласен — оформить договор'},

    // Генерация договора
    {isBot: true,  startFrame: 1940, time: '13:58',
      text: '🎉 Отлично! Формирую договор...'},
    {isBot: true,  startFrame: 2100, time: '13:58',
      text: '📄 Договор № AUD-2026-0002 на сумму 1 250 000 ₸\n\nСсылка для электронной подписи придёт следующим сообщением.\n\nЕсли есть вопросы по договору — просто напишите сюда.'},
  ];

  const typingFrames = [
    {startFrame: 50,   endFrame: 100},
    {startFrame: 220,  endFrame: 280},
    {startFrame: 415,  endFrame: 460},
    {startFrame: 575,  endFrame: 620},
    {startFrame: 735,  endFrame: 780},
    {startFrame: 895,  endFrame: 940},
    {startFrame: 1045, endFrame: 1080},
    {startFrame: 1185, endFrame: 1230},
    {startFrame: 1335, endFrame: 1380},
    {startFrame: 1410, endFrame: 1560},
    {startFrame: 1880, endFrame: 1940},
    {startFrame: 1960, endFrame: 2100},
  ];

  const steps = [
    {icon: '👤', label: 'Контактные данные',  activeFrom: 280},
    {icon: '📋', label: 'Тип и параметры',    activeFrom: 780},
    {icon: '⏱️', label: 'Срочность (24 дня)', activeFrom: 1080},
    {icon: '🧮', label: 'Расчёт КП',          activeFrom: 1380},
    {icon: '💰', label: 'КП: ₸1 250 000',     activeFrom: 1560},
    {icon: '📄', label: 'Договор отправлен',  activeFrom: 2100},
  ];

  const annotationSpring = spring({frame: frame - 10, fps, config: {damping: 18, stiffness: 80}});

  return (
    <AbsoluteFill style={{
      background: `radial-gradient(ellipse at 65% 35%, #0d2a1f 0%, ${theme.bg} 70%)`,
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
          <div style={{display: 'flex', flexDirection: 'column', gap: isV ? 22 : 20,
            opacity: annotationSpring,
            transform: isV ? `translateY(${(1 - annotationSpring) * 20}px)` : `translateX(${(1 - annotationSpring) * 40}px)`}}>

            <div>
              <div style={{fontSize: isV ? 24 : 18, color: theme.accentGreen, fontWeight: 600,
                fontFamily: 'SF Pro Text, Inter, system-ui',
                textTransform: 'uppercase', letterSpacing: 2, marginBottom: isV ? 12 : 12}}>
                Шаг 2 из 4
              </div>
              <h2 style={{fontSize: isV ? 52 : 48, fontWeight: 800, color: theme.textPrimary,
                fontFamily: 'SF Pro Display, Inter, system-ui',
                margin: 0, lineHeight: 1.15, letterSpacing: '-1px'}}>
                Воронка продаж
              </h2>
              <p style={{fontSize: isV ? 28 : 22, color: theme.textSecondary, margin: isV ? '12px 0 0' : '10px 0 16px',
                fontFamily: 'SF Pro Text, Inter, system-ui', lineHeight: 1.5}}>
                Анкета (12 вопросов) → КП → Договор
              </p>
            </div>

            {/* Шаги воронки */}
            <div style={{display: isV ? 'grid' : 'flex', flexDirection: isV ? undefined : 'column',
              gridTemplateColumns: isV ? '1fr 1fr' : undefined, gap: isV ? 12 : 10}}>
              {steps.map((step, i) => {
                const isActive = frame >= step.activeFrom;
                const s = spring({frame: frame - step.activeFrom, fps, config: {damping: 18, stiffness: 120}});
                return (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    background: isActive ? `${theme.accentGreen}18` : theme.bgCard,
                    border: `1px solid ${isActive ? theme.accentGreen + '55' : theme.border}`,
                    borderRadius: 12, padding: isV ? '14px 16px' : '14px 18px',
                    opacity: 0.35 + (isActive ? s * 0.65 : 0),
                    transform: isActive ? `scale(${0.97 + s * 0.03})` : 'scale(0.97)',
                  }}>
                    <span style={{fontSize: isV ? 24 : 24}}>{step.icon}</span>
                    <span style={{fontSize: isV ? 22 : 20, fontWeight: 600,
                      color: isActive ? theme.textPrimary : theme.textSecondary,
                      fontFamily: 'SF Pro Text, Inter, system-ui', lineHeight: 1.2}}>
                      {step.label}
                    </span>
                    {isActive && (
                      <span style={{marginLeft: 'auto', fontSize: isV ? 20 : 18, color: theme.accentGreen}}>✓</span>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Срочный тариф */}
            {frame >= 1160 && (
              <div style={{
                background: `${theme.accentGold}15`, border: `1px solid ${theme.accentGold}40`,
                borderRadius: 14, padding: isV ? '16px 20px' : '14px 18px',
                opacity: spring({frame: frame - 1160, fps, config: {damping: 18, stiffness: 100}}),
              }}>
                <div style={{fontSize: isV ? 26 : 19, fontWeight: 700, color: theme.accentGold,
                  fontFamily: 'SF Pro Display, Inter, system-ui', marginBottom: 4}}>
                  ⚡ Срочный тариф активирован
                </div>
                <div style={{fontSize: isV ? 22 : 16, color: theme.textSecondary, fontFamily: 'SF Pro Text, Inter, system-ui'}}>
                  24 дня {'<'} 30 → надбавка +40% учтена в расчёте
                </div>
              </div>
            )}

            {/* Итоговая цена */}
            {frame >= 1560 && (
              <div style={{
                background: `${theme.accentGreen}15`, border: `1px solid ${theme.accentGreen}50`,
                borderRadius: 14, padding: isV ? '16px 20px' : '14px 18px',
                opacity: spring({frame: frame - 1560, fps, config: {damping: 18, stiffness: 100}}),
              }}>
                <div style={{fontSize: isV ? 22 : 16, color: theme.textSecondary, fontFamily: 'SF Pro Text, Inter, system-ui', marginBottom: 4}}>
                  Обязательный аудит · НСФО · 1 год · срочно
                </div>
                <div style={{fontSize: isV ? 40 : 28, fontWeight: 800, color: theme.accentGreen,
                  fontFamily: 'SF Pro Display, Inter, system-ui', letterSpacing: '-0.5px'}}>
                  ₸ 1 250 000
                </div>
              </div>
            )}
          </div>
        }
      />

      <Caption text="12 вопросов — цена рассчитывается по правилам из БД" icon="📋"
        startFrame={280} durationFrames={300} color={theme.accentGold} />
      <Caption text="Срочность 24 дня → автоматически +40% к стоимости" icon="⏱️"
        startFrame={1160} durationFrames={300} color={theme.accentGold} />
      <Caption text="КП сформировано. Ждём одного слова клиента." icon="💰"
        startFrame={1560} durationFrames={280} color={theme.accent} />
      <Caption text="Договор сгенерирован и отправлен автоматически" icon="📄"
        startFrame={2100} durationFrames={300} color={theme.accentGreen} />
    </AbsoluteFill>
  );
};
