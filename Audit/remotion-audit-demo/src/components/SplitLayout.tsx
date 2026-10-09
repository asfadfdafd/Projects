import React from 'react';

interface SplitLayoutProps {
  left: React.ReactNode;
  right: React.ReactNode;
  leftWidth?: string;
  vertical?: boolean;
}

export const SplitLayout: React.FC<SplitLayoutProps> = ({
  left, right, leftWidth = '44%', vertical = false,
}) => {
  if (vertical) {
    return (
      <div style={{
        width: '100%', height: '100%',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center',
        padding: '36px 60px 32px',
        boxSizing: 'border-box',
        gap: 36,
      }}>
        <div style={{flexShrink: 0, display: 'flex', justifyContent: 'center'}}>
          {left}
        </div>
        <div style={{flex: 1, width: '100%', display: 'flex', flexDirection: 'column',
          justifyContent: 'flex-start', overflow: 'hidden'}}>
          {right}
        </div>
      </div>
    );
  }

  return (
    <div style={{
      width: '100%', height: '100%',
      display: 'flex', alignItems: 'center',
      gap: 60, padding: '40px 80px', boxSizing: 'border-box',
    }}>
      <div style={{
        width: leftWidth, height: '100%',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        {left}
      </div>
      <div style={{flex: 1, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
        {right}
      </div>
    </div>
  );
};
