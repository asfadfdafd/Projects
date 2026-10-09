import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {C} from '../theme';
import {Caption, Chip, Kicker, Lead, Title} from '../components/Type';
import {Pipeline} from '../components/Pipeline';
import {riseIn} from '../lib/anim';

const STEPS = [
  {label: 'Скан', note: 'фото или PDF'},
  {label: 'Распознавание', note: 'русский · казахский'},
  {label: 'Разбор', note: 'вид · дата · суть'},
  {label: 'Имена и даты', note: 'люди · места'},
  {label: 'Проверка', note: 'архивистом'},
  {label: 'Поиск', note: 'обычными словами'},
];

export const S03How: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{padding: '104px 90px', justifyContent: 'center'}}>
      <Kicker delay={0}>Как это работает</Kicker>
      <Title delay={8} size={58} maxWidth={1300}>
        От скана до ответа — один процесс
      </Title>
      <Lead delay={16} maxWidth={1120}>
        Вы загружаете скан. Дальше система сама распознаёт текст, определяет вид
        документа, выписывает имена, даты и места — и дело становится доступным
        для поиска.
      </Lead>

      <div style={{marginTop: 58}}>
        <Pipeline steps={STEPS} delay={30} stepFrames={20} />
      </div>

      <div style={{display: 'flex', gap: 14, marginTop: 52, flexWrap: 'wrap'}}>
        <Chip delay={170} tone="navy">
          Всё на вашем сервере
        </Chip>
        <Chip delay={180}>Интернет для работы не нужен</Chip>
        <Chip delay={190}>Без подписок и лицензий</Chip>
      </div>

      <div
        style={{
          ...riseIn(frame, 200, 14),
          marginTop: 22,
          fontSize: 20,
          color: C.inkMuted,
        }}
      >
        Для технической службы: n8n, PostgreSQL и языковые модели — всё с открытым
        кодом, ставится одной командой.
      </div>

      <Caption delay={215} accent={C.green}>
        Документы никуда не отправляются — они не покидают учреждение
      </Caption>
    </AbsoluteFill>
  );
};
