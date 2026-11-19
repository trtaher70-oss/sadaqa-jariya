import React, {useEffect, useState} from 'react';
import {continueRender, delayRender, staticFile} from 'remotion';

export type Niche = 'deen' | 'gta';
/** Which account the render is for: prv60 (YouTube + default) or the user's religious Instagram account. */
export type Account = 'prv60' | 'sadaqa';
export const SADAQA = {
  handle: '@sadaqa.tr', name: 'صدقة جارية', full: 'صدقة جارية أو علم ينتفع به',
  outro: 'شاركه… لعله يكون صدقة جارية لك',
};

export const B = {
  deen: {
    ink: '#121811', oliveDark: '#1E2A1C', olive: '#34432D', gold: '#C2A56B', sand: '#DCCBA4', off: '#F5F0E6',
    title: 'Amiri', cap: 'IBM Plex Sans Arabic', quran: 'Amiri',
    tagline: 'مقتطفات نافعة', outro: 'تابع للمزيد من الفوائد', name: 'prv60',
  },
  gta: {
    black: '#0B0B12', night: '#160B24', pink: '#FF2D87', cyan: '#1FD6F0', orange: '#FF8A2B', white: '#FFFFFF',
    title: 'Tajawal', cap: 'Tajawal', quran: 'Amiri',
    tagline: 'تختيم • أخبار • تحليل', outro: 'تابع عشان ما يفوتك شي', name: 'PRV60',
  },
} as const;

const FONTS: [string, string, string][] = [
  ['Amiri', 'fonts/Amiri-Bold.ttf', '700'],
  ['Amiri', 'fonts/Amiri-Regular.ttf', '400'],
  ['IBM Plex Sans Arabic', 'fonts/IBMPlexSansArabic-Bold.ttf', '700'],
  ['IBM Plex Sans Arabic', 'fonts/IBMPlexSansArabic-SemiBold.ttf', '600'],
  ['Tajawal', 'fonts/Tajawal-ExtraBold.ttf', '800'],
  ['Tajawal', 'fonts/Tajawal-Black.ttf', '900'],
];

let loaded: Promise<unknown> | null = null;

/** Blocks rendering until every brand font is loaded (no fallback-font frames). */
export const useFonts = () => {
  const [handle] = useState(() => delayRender('fonts'));
  useEffect(() => {
    loaded ??= Promise.all(
      FONTS.map(([fam, file, weight]) =>
        new FontFace(fam, `url(${staticFile(file)})`, {weight}).load().then((f) => (document.fonts as any).add(f)),
      ),
    );
    loaded.then(() => continueRender(handle)).catch((e) => {
      console.error(e);
      continueRender(handle);
    });
  }, [handle]);
};

// Keep digits / Latin runs left-to-right inside Arabic text
export const Smart: React.FC<{text: string}> = ({text}) => {
  const parts = text.split(/([0-9A-Za-z][0-9A-Za-z.,:\-–/ ]*[0-9A-Za-z]|[0-9A-Za-z])/g);
  return (
    <>
      {parts.map((p, i) =>
        /[0-9A-Za-z]/.test(p) ? (
          <span key={i} dir="ltr" style={{unicodeBidi: 'isolate', display: 'inline-block'}}>{p}</span>
        ) : (
          <React.Fragment key={i}>{p}</React.Fragment>
        ),
      )}
    </>
  );
};

/** 8-point star (two overlapping squares) — the deen brand motif. */
export const Star8: React.FC<{size: number; stroke: string; fill?: string; sw?: number; style?: React.CSSProperties}> = ({
  size, stroke, fill = 'none', sw = 3, style,
}) => {
  const r = size / 2 - sw;
  const ri = (r * Math.cos(Math.PI / 4)) / Math.cos(Math.PI / 8);
  const pts = Array.from({length: 16}, (_, k) => {
    const a = (Math.PI / 8) * k - Math.PI / 2;
    const rr = k % 2 ? ri : r;
    return `${size / 2 + rr * Math.cos(a)},${size / 2 + rr * Math.sin(a)}`;
  }).join(' ');
  return (
    <svg width={size} height={size} style={style}>
      <polygon points={pts} fill={fill} stroke={stroke} strokeWidth={sw} />
    </svg>
  );
};

export const GeoPattern: React.FC<{color: string; opacity?: number; size?: number}> = ({color, opacity = 0.1, size = 150}) => {
  const s = size;
  const star = (cx: number, cy: number, r: number) => {
    const ri = (r * Math.cos(Math.PI / 4)) / Math.cos(Math.PI / 8);
    return Array.from({length: 16}, (_, k) => {
      const a = (Math.PI / 8) * k - Math.PI / 2;
      const rr = k % 2 ? ri : r;
      return `${cx + rr * Math.cos(a)},${cy + rr * Math.sin(a)}`;
    }).join(' ');
  };
  return (
    <svg width="100%" height="100%" style={{position: 'absolute', inset: 0}}>
      <defs>
        <pattern id="geo" width={s} height={s} patternUnits="userSpaceOnUse">
          <polygon points={star(s / 2, s / 2, s * 0.42)} fill="none" stroke={color} strokeWidth={1.6} opacity={opacity} />
          {[[0, 0], [s, 0], [0, s], [s, s]].map(([x, y], i) => (
            <polygon key={i} points={star(x, y, s * 0.18)} fill="none" stroke={color} strokeWidth={1.2} opacity={opacity} />
          ))}
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#geo)" />
    </svg>
  );
};
