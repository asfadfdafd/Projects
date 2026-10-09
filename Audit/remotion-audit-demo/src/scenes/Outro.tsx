import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';

export const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const isV = height > width;

  const fadeIn    = interpolate(frame, [0, 20], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const headerS   = spring({frame,          fps, config: {damping: 18, stiffness: 80}});
  const subtitleS = spring({frame: frame - 15, fps, config: {damping: 18, stiffness: 80}});

  const completed = [
    {icon: '💬', text: 'FAQ на базе знаний компании'},
    {icon: '📋', text: '12-шаговая анкета (контакт, тип, параметры)'},
    {icon: '⏱️', text: 'Срочный тариф: < 30 дней → +40% авто'},
    {icon: '🧮', text: 'Расчёт цены по правилам из БД'},
    {icon: '📊', text: 'Коммерческое предложение автоматически'},
    {icon: '📄', text: 'Генерация и отправка договора файлом'},
    {icon: '📅', text: 'Запись на консультацию онлайн'},
    {icon: '🔔', text: 'Telegram-уведомление команде о броне'},
  ];

  const next = [
    {icon: '✍️', text: 'Электронная подпись договора'},
    {icon: '🗂️', text: 'Интеграция с 1С / внутренней CRM'},
    {icon: '📱', text: 'Instagram Direct и WhatsApp каналы'},
  ];

  const brandingCard = (
    <div style={{
      background: theme.bgCard, border: `1px solid ${theme.border}`,
      borderRadius: 16, padding: isV ? '14px 18px' : '18px 20px',
      display: 'flex', alignItems: 'center', gap: 14,
      opacity: spring({frame: frame - 150, fps, config: {damping: 18, stiffness: 80}}),
    }}>
      <div style={{
        width: 44, height: 44, borderRadius: 14,
        background: `linear-gradient(135deg, ${theme.accent}, #1a7fc1)`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 22, flexShrink: 0,
      }}>🤖</div>
      <div>
        <div style={{fontSize: isV ? 17 : 19, fontWeight: 700, color: theme.textPrimary,
          fontFamily: 'SF Pro Display, Inter, system-ui'}}>
          Chat_Audit — Sales Bot MVP
        </div>
        <div style={{fontSize: isV ? 14 : 15, color: theme.textSecondary, marginTop: 3,
          fontFamily: 'SF Pro Text, Inter, system-ui'}}>
          Автоматизация продаж · 24/7
        </div>
      </div>
    </div>
  );

  return (
    <AbsoluteFill style={{
      background: `radial-gradient(ellipse at 50% 40%, #0d1f3c 0%, ${theme.bg} 65%)`,
      opacity: fadeIn,
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      padding: isV ? '48px 60px 40px' : '48px 80px 40px',
      boxSizing: 'border-box', gap: 0,
    }}>

      {/* Заголовок */}
      <div style={{
        textAlign: 'center', marginBottom: isV ? 28 : 40,
        opacity: headerS, transform: `translateY(${(1 - headerS) * 16}px)`,
      }}>
        <div style={{
          display: 'inline-block',
          background: `${theme.accentGreen}18`, border: `1px solid ${theme.accentGreen}50`,
          borderRadius: 100, padding: '6px 22px', marginBottom: 16,
          fontSize: 16, color: theme.accentGreen, fontWeight: 600,
          fontFamily: 'SF Pro Text, Inter, system-ui',
          textTransform: 'uppercase', letterSpacing: 2,
          opacity: subtitleS,
        }}>
          MVP реализован
        </div>
        <h2 style={{
          fontSize: isV ? 42 : 52, fontWeight: 800, color: theme.textPrimary,
          fontFamily: 'SF Pro Display, Inter, system-ui', margin: 0, letterSpacing: '-1px',
        }}>
          Что уже работает — и что дальше
        </h2>
      </div>

      {isV ? (
        /* ── Вертикальный макет ── */
        <div style={{display: 'flex', flexDirection: 'column', width: '100%', flex: 1, gap: 24}}>
          {/* Реализовано */}
          <div>
            <div style={{
              fontSize: 22, color: theme.accentGreen, fontWeight: 700,
              fontFamily: 'SF Pro Text, Inter, system-ui',
              textTransform: 'uppercase', letterSpacing: 2, marginBottom: 20, textAlign: 'center',
              opacity: spring({frame: frame - 10, fps, config: {damping: 18, stiffness: 80}}),
            }}>
              Реализовано
            </div>
            <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14}}>
              {completed.map((item, i) => {
                const s = spring({frame: frame - 20 - i * 15, fps, config: {damping: 18, stiffness: 120}});
                return (
                  <div key={i} style={{
                    background: `${theme.accentGreen}0d`, border: `1px solid ${theme.accentGreen}30`,
                    borderRadius: 14, padding: '18px 18px',
                    display: 'flex', alignItems: 'center', gap: 12,
                    opacity: s, transform: `translateY(${(1 - s) * 12}px)`,
                  }}>
                    <span style={{fontSize: 24, flexShrink: 0}}>{item.icon}</span>
                    <span style={{fontSize: 22, color: '#c9d1d9',
                      fontFamily: 'SF Pro Text, Inter, system-ui', fontWeight: 500, lineHeight: 1.3}}>
                      {item.text}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Следующие этапы */}
          <div>
            <div style={{
              fontSize: 22, color: theme.accent, fontWeight: 700,
              fontFamily: 'SF Pro Text, Inter, system-ui',
              textTransform: 'uppercase', letterSpacing: 2, marginBottom: 20, textAlign: 'center',
              opacity: spring({frame: frame - 10, fps, config: {damping: 18, stiffness: 80}}),
            }}>
              Следующие этапы
            </div>
            <div style={{display: 'flex', flexDirection: 'column', gap: 14}}>
              {next.map((item, i) => {
                const s = spring({frame: frame - 60 - i * 30, fps, config: {damping: 18, stiffness: 120}});
                return (
                  <div key={i} style={{
                    background: theme.bgCard, border: `1px solid ${theme.border}`,
                    borderRadius: 14, padding: '18px 22px',
                    display: 'flex', alignItems: 'center', gap: 14,
                    opacity: s, transform: `translateX(${(1 - s) * 20}px)`,
                  }}>
                    <span style={{fontSize: 28}}>{item.icon}</span>
                    <span style={{fontSize: 26, color: '#c9d1d9',
                      fontFamily: 'SF Pro Text, Inter, system-ui', fontWeight: 500}}>
                      {item.text}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {brandingCard}
        </div>
      ) : (
        /* ── Горизонтальный макет ── */
        <div style={{display: 'flex', gap: 32, width: '100%', flex: 1, alignItems: 'stretch'}}>

          {/* Левая: сетка 2×4 */}
          <div style={{flex: 1, display: 'flex', flexDirection: 'column'}}>
            <div style={{
              fontSize: 15, color: theme.accentGreen, fontWeight: 700,
              fontFamily: 'SF Pro Text, Inter, system-ui',
              textTransform: 'uppercase', letterSpacing: 2, marginBottom: 16, textAlign: 'center',
              opacity: spring({frame: frame - 10, fps, config: {damping: 18, stiffness: 80}}),
            }}>
              Реализовано
            </div>
            <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gridAutoRows: '1fr', gap: 12, flex: 1}}>
              {completed.map((item, i) => {
                const s = spring({frame: frame - 20 - i * 15, fps, config: {damping: 18, stiffness: 120}});
                return (
                  <div key={i} style={{
                    background: `${theme.accentGreen}0d`, border: `1px solid ${theme.accentGreen}30`,
                    borderRadius: 12, padding: '16px',
                    display: 'flex', alignItems: 'center', gap: 10,
                    opacity: s, transform: `translateY(${(1 - s) * 12}px)`,
                  }}>
                    <span style={{fontSize: 20, flexShrink: 0}}>{item.icon}</span>
                    <span style={{fontSize: 17, color: '#c9d1d9',
                      fontFamily: 'SF Pro Text, Inter, system-ui', fontWeight: 500, lineHeight: 1.3}}>
                      {item.text}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Разделитель */}
          <div style={{
            width: 1, alignSelf: 'stretch',
            background: `linear-gradient(to bottom, transparent, ${theme.border}, transparent)`,
            flexShrink: 0,
            opacity: spring({frame: frame - 30, fps, config: {damping: 18, stiffness: 60}}),
          }} />

          {/* Правая: дорожная карта */}
          <div style={{width: 380, display: 'flex', flexDirection: 'column', justifyContent: 'space-between'}}>
            <div style={{
              fontSize: 15, color: theme.accent, fontWeight: 700,
              fontFamily: 'SF Pro Text, Inter, system-ui',
              textTransform: 'uppercase', letterSpacing: 2, marginBottom: 16, textAlign: 'center',
              opacity: spring({frame: frame - 10, fps, config: {damping: 18, stiffness: 80}}),
            }}>
              Следующие этапы
            </div>
            <div style={{display: 'flex', flexDirection: 'column', gap: 12, flex: 1}}>
              {next.map((item, i) => {
                const s = spring({frame: frame - 60 - i * 30, fps, config: {damping: 18, stiffness: 120}});
                return (
                  <div key={i} style={{
                    background: theme.bgCard, border: `1px solid ${theme.border}`,
                    borderRadius: 14, padding: '16px 20px',
                    display: 'flex', alignItems: 'center', gap: 12,
                    opacity: s, transform: `translateX(${(1 - s) * 20}px)`,
                  }}>
                    <span style={{fontSize: 24}}>{item.icon}</span>
                    <span style={{fontSize: 20, color: '#c9d1d9',
                      fontFamily: 'SF Pro Text, Inter, system-ui', fontWeight: 500}}>
                      {item.text}
                    </span>
                  </div>
                );
              })}
            </div>
            <div style={{marginTop: 32}}>{brandingCard}</div>
          </div>
        </div>
      )}
    </AbsoluteFill>
  );
};
