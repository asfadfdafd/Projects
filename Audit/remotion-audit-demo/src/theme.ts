// Дизайн-система проекта
export const theme = {
  // Фоны
  bg:          '#0d1117',   // основной фон
  bgCard:      '#161b22',   // фон карточек/панелей
  bgTelegram:  '#17212b',   // фон Telegram-чата
  bgHeader:    '#1c2733',   // шапка чата

  // Пузыри сообщений
  bubbleUser:  '#2b5278',   // сообщение клиента (правый, синий)
  bubbleBot:   '#182533',   // сообщение бота (левый, тёмный)

  // Текст
  textPrimary:   '#e6edf3', // основной текст
  textSecondary: '#8b949e', // вторичный текст
  textTime:      '#6b7789', // время сообщения

  // Акценты
  accent:      '#2AABEE',   // Telegram blue
  accentGreen: '#3dc67c',   // успех / галочки
  accentGold:  '#f0b429',   // выделение / подписи
  accentRed:   '#e05252',   // предупреждения

  // Служебные
  border:      '#30363d',
  shadow:      'rgba(0,0,0,0.5)',
};

// Метрики видео
export const VIDEO = {
  width:  1920,
  height: 1080,
  fps:    30,
  // Длительности сцен в секундах (для удобного редактирования)
  scenes: {
    intro:        8,
    faq:         35,
    funnel:      80,
    consultation: 25,
    backend:      20,
    outro:        12,
    brand:         6,
  },
};

// Вспомогательные функции
export const sec = (s: number) => s * VIDEO.fps; // секунды → кадры
