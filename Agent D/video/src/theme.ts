import {loadFont} from '@remotion/google-fonts/Inter';

// Inter покрывает кириллицу — это тот же шрифтовой характер, что и в UI ArchivAI.
const {fontFamily} = loadFont('normal', {
  weights: ['400', '500', '600', '700', '800'],
  subsets: ['cyrillic', 'cyrillic-ext', 'latin', 'latin-ext'],
});

/** Запасная цепочка — если шрифт почему-то не подгрузился, кириллица всё равно нарисуется. */
export const FONT = `${fontFamily}, Inter, -apple-system, "Segoe UI", Roboto, sans-serif`;

/**
 * Палитра снята пипеткой прямо со скриншотов продукта,
 * чтобы ролик и интерфейс были одного цвета.
 */
export const C = {
  navy: '#111B31', // сайдбар ArchivAI
  navySoft: '#1B2743',
  navyMuted: '#41506E',
  orange: '#E87B35', // акцент / кнопка Upload
  orangeSoft: '#FDEEE3',
  bg: '#F2F5F9', // фон рабочей области
  bgDeep: '#E7ECF4',
  white: '#FFFFFF',
  ink: '#16233C',
  inkMuted: '#6B7A93',
  line: '#DFE5EE',
  green: '#1F9D63',
  greenSoft: '#E6F5ED',
  blue: '#2F6BD8',
} as const;

export const FPS = 30;
export const W = 1920;
export const H = 1080;

/**
 * Фоновая музыка.
 * Положите трек в public/audio/ и впишите сюда имя файла, например 'audio/music.mp3'.
 * Пока здесь null — ролик рендерится без звука.
 */
export const MUSIC_FILE = null as string | null;
export const MUSIC_VOLUME = 0.22;
