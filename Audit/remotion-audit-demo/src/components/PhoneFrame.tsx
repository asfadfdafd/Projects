import React from 'react';
import {theme} from '../theme';

interface PhoneFrameProps {
  children: React.ReactNode;
  width?: number;
  height?: number;
}

// Стилизованный телефонный фрейм вокруг Telegram-чата
export const PhoneFrame: React.FC<PhoneFrameProps> = ({
  children,
  width = 480,
  height = 900,
}) => {
  const borderWidth = 14;
  const borderRadius = 52;

  return (
    <div style={{
      width,
      height,
      borderRadius,
      background: '#1a1a2e',
      border: `${borderWidth}px solid #2a2a3e`,
      boxShadow: `
        0 0 0 2px #3a3a5e,
        0 40px 80px rgba(0,0,0,0.6),
        inset 0 0 20px rgba(255,255,255,0.02)
      `,
      position: 'relative',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Вырез камеры */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: '50%',
        transform: 'translateX(-50%)',
        width: 120,
        height: 32,
        background: '#1a1a2e',
        borderRadius: '0 0 20px 20px',
        zIndex: 10,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
      }}>
        <div style={{width: 10, height: 10, borderRadius: '50%', background: '#2a2a4e'}} />
        <div style={{width: 6, height: 6, borderRadius: '50%', background: '#1e3a5f'}} />
      </div>

      {/* Содержимое */}
      <div style={{
        flex: 1,
        overflow: 'hidden',
        borderRadius: borderRadius - borderWidth,
        marginTop: 8,
      }}>
        {children}
      </div>

      {/* Индикатор Home */}
      <div style={{
        position: 'absolute',
        bottom: 10,
        left: '50%',
        transform: 'translateX(-50%)',
        width: 120,
        height: 5,
        borderRadius: 3,
        background: 'rgba(255,255,255,0.2)',
        zIndex: 10,
      }} />
    </div>
  );
};
