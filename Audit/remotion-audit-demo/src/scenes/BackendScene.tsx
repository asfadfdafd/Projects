import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {theme} from '../theme';

// Сцена 4 — Взгляд изнутри: CRM + n8n (20 секунд = 600 кадров)
export const BackendScene: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const isV = height > width;

  const fadeIn  = interpolate(frame, [0, 20],    [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const fadeOut = interpolate(frame, [580, 600], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const titleSpring = spring({frame, fps, config: {damping: 18, stiffness: 80}});

  // Строки таблицы БД
  const leads = [
    {id: 1, name: 'Даурен, CEO', company: 'Гугл',          state: 'contract_sent', price: '₸1 250 000'},
    {id: 2, name: 'Айгуль',      company: 'ТОО Астра',     state: 'proposal_sent', price: '₸620 000'},
    {id: 3, name: 'Марат',       company: 'КазМунайГаз',   state: 'booked',        price: '—'},
    {id: 4, name: 'Алиса',       company: 'СПК Тараз',     state: 'faq',           price: '—'},
  ];

  const stateColor = (s: string) => {
    if (s === 'contract_sent') return theme.accentGreen;
    if (s === 'proposal_sent') return theme.accent;
    if (s === 'booked')        return '#a78bfa';
    return theme.textSecondary;
  };

  const nodes = [
    {icon: '⚡', label: 'Входящее сообщение'},
    {icon: '🔧', label: 'Обработка запроса'},
    {icon: '🚦', label: 'Определение намерения'},
    {icon: '🧠', label: 'Консультация по базе знаний'},
    {icon: '📋', label: 'Заполнение анкеты'},
    {icon: '🧮', label: 'Расчёт стоимости'},
    {icon: '📄', label: 'Формирование договора'},
    {icon: '📧', label: 'Уведомление команде'},
  ];

  return (
    <AbsoluteFill style={{
      background: `radial-gradient(ellipse at 50% 30%, #0a1a0a 0%, ${theme.bg} 70%)`,
      opacity: fadeIn * fadeOut,
      padding: isV ? '56px 60px 48px' : '40px 80px',
      boxSizing: 'border-box',
    }}>
      {/* Заголовок */}
      <div style={{
        marginBottom: isV ? 36 : 40,
        opacity: titleSpring,
        transform: `translateY(${(1 - titleSpring) * 20}px)`,
      }}>
        <div style={{fontSize: isV ? 24 : 18, color: theme.accentGreen, fontWeight: 600,
          fontFamily: 'SF Pro Text, Inter, system-ui',
          textTransform: 'uppercase', letterSpacing: 2, marginBottom: isV ? 12 : 8}}>
          Сцена 4 из 4
        </div>
        <h2 style={{fontSize: isV ? 60 : 52, fontWeight: 800, color: theme.textPrimary,
          fontFamily: 'SF Pro Display, Inter, system-ui', margin: 0, letterSpacing: '-1px'}}>
          Все заявки под контролем. Автоматически.
        </h2>
      </div>

      <div style={{display: 'flex', flexDirection: isV ? 'column' : 'row', gap: isV ? 32 : 48, flex: 1}}>

        {/* CRM-таблица */}
        <div style={isV ? {width: '100%'} : {flex: 1}}>
          <div style={{
            fontSize: 18, color: theme.textSecondary, marginBottom: 12,
            fontFamily: 'SF Pro Text, Inter, system-ui', display: 'flex', alignItems: 'center', gap: 8,
            opacity: spring({frame: frame - 20, fps, config: {damping: 18, stiffness: 100}}),
          }}>
            <span style={{color: theme.accentGreen}}>●</span> База клиентов
          </div>

          <div style={{
            background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 16, overflow: 'hidden',
            opacity: spring({frame: frame - 30, fps, config: {damping: 18, stiffness: 100}}),
          }}>
            <div style={{display: 'grid', gridTemplateColumns: isV ? '36px 1fr 1fr 160px 150px' : '40px 1fr 1fr 160px 140px',
              padding: isV ? '16px 20px' : '14px 20px', background: `${theme.border}55`,
              borderBottom: `1px solid ${theme.border}`, gap: isV ? 14 : 16}}>
              {['#', 'Контакт', 'Компания', 'Состояние', 'Сумма'].map((h) => (
                <div key={h} style={{fontSize: isV ? 20 : 16, color: theme.textSecondary, fontWeight: 600,
                  fontFamily: 'SF Pro Text, Inter, system-ui', textTransform: 'uppercase', letterSpacing: 1}}>
                  {h}
                </div>
              ))}
            </div>

            {leads.map((lead, i) => {
              const s = spring({frame: frame - 60 - i * 40, fps, config: {damping: 18, stiffness: 120}});
              return (
                <div key={i} style={{
                  display: 'grid', gridTemplateColumns: isV ? '36px 1fr 1fr 160px 150px' : '40px 1fr 1fr 160px 140px',
                  padding: isV ? '18px 20px' : '16px 20px',
                  borderBottom: i < leads.length - 1 ? `1px solid ${theme.border}` : 'none',
                  gap: isV ? 14 : 16, opacity: s, transform: `translateX(${(1 - s) * 20}px)`,
                }}>
                  <div style={{fontSize: isV ? 22 : 18, color: theme.textSecondary, fontFamily: 'SF Pro Text, Inter, system-ui'}}>{lead.id}</div>
                  <div style={{fontSize: isV ? 22 : 18, color: theme.textPrimary, fontWeight: 600, fontFamily: 'SF Pro Text, Inter, system-ui'}}>{lead.name}</div>
                  <div style={{fontSize: isV ? 22 : 18, color: theme.textSecondary, fontFamily: 'SF Pro Text, Inter, system-ui'}}>{lead.company}</div>
                  <div style={{fontSize: isV ? 18 : 16, padding: '4px 12px', borderRadius: 20, background: `${stateColor(lead.state)}20`,
                    border: `1px solid ${stateColor(lead.state)}50`, color: stateColor(lead.state),
                    fontFamily: 'SF Pro Text, Inter, system-ui', fontWeight: 600, textAlign: 'center', alignSelf: 'center'}}>
                    {lead.state}
                  </div>
                  <div style={{fontSize: isV ? 22 : 18, color: lead.price === '—' ? theme.textSecondary : theme.accentGreen,
                    fontFamily: 'SF Pro Text, Inter, system-ui', fontWeight: lead.price !== '—' ? 700 : 400}}>
                    {lead.price}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* n8n-схема */}
        <div style={isV ? {width: '100%'} : {width: 420}}>
          <div style={{
            fontSize: isV ? 22 : 18, color: theme.textSecondary, marginBottom: isV ? 16 : 12,
            fontFamily: 'SF Pro Text, Inter, system-ui', display: 'flex', alignItems: 'center', gap: 8,
            opacity: spring({frame: frame - 20, fps, config: {damping: 18, stiffness: 100}}),
          }}>
            <span style={{color: '#f97316'}}>●</span> Шаги автоматизации
          </div>

          <div style={{
            display: isV ? 'grid' : 'flex',
            flexDirection: isV ? undefined : 'column',
            gridTemplateColumns: isV ? '1fr 1fr' : undefined,
            gap: isV ? 12 : 8,
          }}>
            {nodes.map((node, i) => {
              const s = spring({frame: frame - 50 - i * 25, fps, config: {damping: 18, stiffness: 120}});
              return (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  background: theme.bgCard, border: `1px solid ${theme.border}`,
                  borderRadius: 12, padding: isV ? '16px 18px' : '12px 18px',
                  opacity: s, transform: `translateX(${(1 - s) * 20}px)`,
                }}>
                  <span style={{fontSize: isV ? 26 : 22}}>{node.icon}</span>
                  <span style={{fontSize: isV ? 24 : 18, color: theme.textPrimary,
                    fontFamily: 'SF Pro Text, Inter, system-ui', fontWeight: 500}}>
                    {node.label}
                  </span>
                  {!isV && i < nodes.length - 1 && (
                    <span style={{marginLeft: 'auto', color: theme.textSecondary, fontSize: 16}}>↓</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
