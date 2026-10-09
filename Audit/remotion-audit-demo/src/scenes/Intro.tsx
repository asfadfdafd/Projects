import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';

export const Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const isV = height > width;

  const titleSpring  = spring({frame, fps, config: {damping: 18, stiffness: 80}});
  const subtitleDelay = spring({frame: frame - 20, fps, config: {damping: 18, stiffness: 80}});
  const line1Delay   = spring({frame: frame - 50, fps, config: {damping: 18, stiffness: 100}});
  const line2Delay   = spring({frame: frame - 70, fps, config: {damping: 18, stiffness: 100}});
  const line3Delay   = spring({frame: frame - 90, fps, config: {damping: 18, stiffness: 100}});

  const fadeOut = interpolate(frame, [225, 240], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  const features = [
    {icon: '💬', text: 'FAQ на базе знаний компании'},
    {icon: '📋', text: '12-шаговая анкета + расчёт цены'},
    {icon: '📄', text: 'КП + договор за 2 минуты'},
  ];
  const springs = [line1Delay, line2Delay, line3Delay];

  return (
    <AbsoluteFill style={{
      background: `radial-gradient(ellipse at 30% 50%, #0d1f3c 0%, ${theme.bg} 70%)`,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      opacity: fadeOut,
      padding: isV ? '60px' : 0,
      boxSizing: 'border-box',
    }}>
      {/* Бейдж */}
      <div style={{
        background: `${theme.accent}22`, border: `1px solid ${theme.accent}55`,
        borderRadius: 100, padding: isV ? '8px 20px' : '8px 24px',
        marginBottom: isV ? 24 : 32,
        opacity: subtitleDelay, transform: `translateY(${(1 - subtitleDelay) * 16}px)`,
      }}>
        <span style={{
          fontSize: isV ? 18 : 22, color: theme.accent,
          fontFamily: 'SF Pro Text, Inter, system-ui',
          letterSpacing: 1, textTransform: 'uppercase', fontWeight: 600,
        }}>
          MVP · Sales Bot · Telegram
        </span>
      </div>

      {/* Заголовок */}
      <h1 style={{
        fontSize: isV ? 72 : 88,
        fontWeight: 800, color: theme.textPrimary,
        fontFamily: 'SF Pro Display, Inter, system-ui',
        margin: 0, textAlign: 'center', lineHeight: 1.1, letterSpacing: '-2px',
        opacity: titleSpring, transform: `translateY(${(1 - titleSpring) * 30}px)`,
        maxWidth: isV ? 940 : 1200,
      }}>
        Автоматизация бизнеса.<br/>
        <span style={{color: theme.accent}}>Аудит</span>
      </h1>

      {/* Подзаголовок */}
      <p style={{
        fontSize: isV ? 28 : 36, color: '#c9d1d9',
        fontFamily: 'SF Pro Text, Inter, system-ui',
        margin: isV ? '24px 0 40px' : '32px 0 56px',
        textAlign: 'center',
        opacity: subtitleDelay, transform: `translateY(${(1 - subtitleDelay) * 16}px)`,
        maxWidth: isV ? 900 : 860, lineHeight: 1.55, fontWeight: 400,
      }}>
        От первого сообщения клиента — до подписанного договора.<br/>
        Без участия менеджера. 24/7.
      </p>

      {/* Список возможностей */}
      <div style={{
        display: 'flex', flexDirection: isV ? 'column' : 'row',
        gap: isV ? 20 : 32,
        width: isV ? '100%' : undefined, maxWidth: isV ? 840 : undefined,
      }}>
        {features.map((f, i) => (
          <div key={i} style={{
            background: theme.bgCard, border: `1px solid ${theme.border}`,
            borderRadius: 20, padding: isV ? '18px 28px' : '20px 32px',
            display: 'flex', alignItems: 'center', gap: 14,
            opacity: springs[i], transform: `translateY(${(1 - springs[i]) * 20}px)`,
          }}>
            <span style={{fontSize: isV ? 28 : 32}}>{f.icon}</span>
            <span style={{
              fontSize: isV ? 22 : 26, color: '#c9d1d9',
              fontFamily: 'SF Pro Text, Inter, system-ui', fontWeight: 500,
            }}>
              {f.text}
            </span>
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
