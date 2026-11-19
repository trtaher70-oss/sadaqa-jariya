import React from 'react';
import {AbsoluteFill, Audio, Easing, interpolate, random, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {B, GeoPattern, SADAQA, Star8, useFonts} from './brand';

/** Short Quran reel for @sadaqa.tr: hook line on top, the verse text page by page synced to the recitation. */
export type AyahWord = {t: string; s: number; e: number};
export type AyahPage = {s: number; e: number; text: string; ref: string; size?: number; words?: AyahWord[]};
export type AyahProps = {
  hook: string;
  kind: string; // دعاء / تذكير
  audio: {src: string; at: number}[]; // seconds from video start
  pages: AyahPage[];
  total: number; // seconds incl. outro
  outroDur: number;
  reciter: string;
};

const d = B.deen;
const ease = Easing.bezier(0.22, 1, 0.36, 1);
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

const fontFor = (t: string) => {
  const n = t.length;
  return n < 45 ? 96 : n < 80 ? 86 : n < 120 ? 76 : n < 170 ? 68 : 60;
};

const Background: React.FC = () => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = f / fps;
  const glow = 0.5 + 0.12 * Math.sin(t * 1.3);
  return (
    <AbsoluteFill style={{background: `radial-gradient(ellipse at 50% 46%, ${d.olive} 0%, ${d.oliveDark} 48%, ${d.ink} 100%)`}}>
      <AbsoluteFill style={{transform: `rotate(${t * 0.6}deg) scale(1.55)`}}>
        <GeoPattern color={d.gold} opacity={0.09} size={170} />
      </AbsoluteFill>
      <div style={{position: 'absolute', left: 90, right: 90, top: 560, height: 820, borderRadius: '50%',
        background: `radial-gradient(ellipse, rgba(220,203,164,${0.16 * glow}) 0%, rgba(194,165,107,0) 70%)`}} />
      {Array.from({length: 46}, (_, i) => {
        const x = random(`x${i}`) * 1080;
        const sp = 18 + random(`s${i}`) * 40;
        const y = (((random(`y${i}`) * 2100 - t * sp) % 2100) + 2100) % 2100 - 90;
        const r = 2 + random(`r${i}`) * 4;
        const tw = 0.25 + 0.55 * Math.abs(Math.sin(t * (0.6 + random(`t${i}`)) + i));
        return <div key={i} style={{position: 'absolute', left: x, top: y, width: r, height: r, borderRadius: '50%', background: d.sand, opacity: tw * 0.55, boxShadow: `0 0 ${r * 3}px ${d.gold}`}} />;
      })}
      <AbsoluteFill style={{background: 'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.55) 100%)'}} />
    </AbsoluteFill>
  );
};

const Ornament: React.FC<{w: number; o: number}> = ({w, o}) => (
  <div style={{display: 'flex', alignItems: 'center', gap: 18, opacity: o}}>
    <div style={{width: w, height: 2, background: `linear-gradient(90deg, rgba(194,165,107,0), ${d.gold})`}} />
    <Star8 size={34} stroke={d.gold} fill={d.gold} sw={1} />
    <div style={{width: w, height: 2, background: `linear-gradient(270deg, rgba(194,165,107,0), ${d.gold})`}} />
  </div>
);

const Page: React.FC<{p: AyahPage}> = ({p}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const len = (p.e - p.s) * fps;
  const inn = interpolate(f, [0, 0.55 * fps], [0, 1], {...clamp, easing: ease});
  const out = interpolate(f, [len - 0.3 * fps, len], [1, 0], clamp);
  const o = Math.min(inn, out);
  const now = p.s + f / fps; // absolute seconds (word timings are absolute)
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', top: 120}}>
      <div style={{opacity: o, transform: `translateY(${(1 - inn) * 26}px)`, filter: `blur(${(1 - inn) * 6}px)`,
        display: 'flex', flexDirection: 'column', alignItems: 'center', width: 960}}>
        <div style={{fontFamily: 'Amiri', fontWeight: 700, fontSize: p.size ?? fontFor(p.text), lineHeight: 2.05, color: d.off, direction: 'rtl',
          textAlign: 'center', textShadow: '0 4px 26px rgba(0,0,0,0.65)'}}>
          {p.words
            ? p.words.map((w, i) => {
                // each word lights up as it is recited; the current word glows gold
                const lit = interpolate(now, [w.s - 0.05, w.s + 0.12], [0, 1], clamp);
                const cur = now >= w.s - 0.05 && now < w.e + 0.05 ? interpolate(now, [w.s - 0.05, w.s + 0.12], [0, 1], clamp) : 0;
                return (
                  <React.Fragment key={i}>
                    <span style={{color: cur > 0 ? d.sand : d.off, opacity: 0.32 + 0.68 * lit,
                      textShadow: cur > 0 ? `0 0 ${28 * cur}px rgba(194,165,107,${0.75 * cur}), 0 4px 26px rgba(0,0,0,0.65)` : '0 4px 26px rgba(0,0,0,0.65)'}}>{w.t}</span>
                    {i < p.words!.length - 1 ? ' ' : ''}
                  </React.Fragment>
                );
              })
            : p.text}
        </div>
        <div style={{fontFamily: 'Amiri', fontWeight: 700, fontSize: 42, color: d.gold, marginTop: 26, direction: 'rtl'}}>{p.ref}</div>
      </div>
    </AbsoluteFill>
  );
};

const Outro: React.FC<{dur: number}> = ({dur}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const sp = interpolate(f, [0, 0.7 * fps], [0, 1], {...clamp, easing: ease});
  const t2 = interpolate(f, [0.35 * fps, 0.95 * fps], [0, 1], {...clamp, easing: ease});
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', direction: 'rtl'}}>
      <div style={{position: 'relative', width: 260, height: 260, opacity: sp, transform: `scale(${0.7 + 0.3 * sp}) rotate(${(1 - sp) * -30 + f * 0.15}deg)`}}>
        <Star8 size={260} stroke={d.gold} sw={5} style={{position: 'absolute', inset: 0}} />
        <Star8 size={170} stroke={d.sand} sw={3} style={{position: 'absolute', left: 45, top: 45, transform: 'rotate(22.5deg)', opacity: 0.8}} />
        <Star8 size={64} stroke={d.gold} fill={d.gold} sw={2} style={{position: 'absolute', left: 98, top: 98}} />
      </div>
      <div style={{fontFamily: 'Amiri', fontWeight: 700, fontSize: 70, color: d.off, marginTop: 50, opacity: t2, transform: `translateY(${(1 - t2) * 20}px)`}}>شاركها…</div>
      <div style={{fontFamily: 'Amiri', fontWeight: 700, fontSize: 62, color: d.sand, opacity: t2, transform: `translateY(${(1 - t2) * 20}px)`}}>لعلها تكون صدقة جارية لك</div>
      <div style={{width: 240, height: 3, background: d.gold, opacity: t2 * 0.7, margin: '40px 0 26px'}} />
      <div style={{fontFamily: 'Amiri', fontWeight: 700, fontSize: 60, color: d.gold, opacity: t2, direction: 'ltr'}}>{SADAQA.handle}</div>
    </AbsoluteFill>
  );
};

export const Ayah: React.FC<AyahProps> = (p) => {
  useFonts();
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const fr = (s: number) => Math.round(s * fps);
  const outroAt = p.total - p.outroDur;
  const mainEnd = fr(outroAt);
  const hookIn = interpolate(f, [0, 0.4 * fps], [0.55, 1], {...clamp, easing: ease});
  const mainOut = interpolate(f, [mainEnd, mainEnd + 0.4 * fps], [1, 0], clamp);
  const prog = interpolate(f, [0, mainEnd], [0, 1], clamp);
  return (
    <AbsoluteFill style={{background: d.ink}}>
      <Background />
      {p.audio.map((a, i) => (
        <Sequence key={i} from={fr(a.at)}>
          <Audio src={staticFile(a.src)} />
        </Sequence>
      ))}
      <AbsoluteFill style={{opacity: mainOut}}>
        {/* hook (always visible so a looping viewer knows what this is) */}
        <div style={{position: 'absolute', top: 250, left: 60, right: 60, display: 'flex', flexDirection: 'column', alignItems: 'center',
          opacity: Math.max(0.0001, hookIn), transform: `translateY(${(1 - hookIn) * -20}px)`}}>
          <div style={{fontFamily: 'IBM Plex Sans Arabic', fontWeight: 600, fontSize: 36, color: d.gold, letterSpacing: 1, marginBottom: 14,
            border: `2px solid rgba(194,165,107,0.6)`, borderRadius: 40, padding: '2px 30px', background: 'rgba(18,24,17,0.45)'}}>{p.kind}</div>
          <div style={{fontFamily: 'Amiri', fontWeight: 700, fontSize: p.hook.length > 26 ? 74 : 84, lineHeight: 1.5, color: d.off, direction: 'rtl', textAlign: 'center',
            textShadow: '0 4px 20px rgba(0,0,0,0.6)'}}>{p.hook}</div>
          <div style={{marginTop: 22}}><Ornament w={170} o={0.9} /></div>
        </div>
        {p.pages.map((pg, i) => (
          <Sequence key={i} from={fr(pg.s)} durationInFrames={Math.max(1, fr(pg.e) - fr(pg.s))}>
            <Page p={pg} />
          </Sequence>
        ))}
        {/* reciter + progress */}
        <div style={{position: 'absolute', top: 1500, left: 0, right: 0, textAlign: 'center', fontFamily: 'IBM Plex Sans Arabic', fontWeight: 600,
          fontSize: 32, color: d.sand, opacity: 0.75 * hookIn, direction: 'rtl'}}>بصوت {p.reciter}</div>
        <div style={{position: 'absolute', top: 1560, left: 240, right: 240, height: 4, borderRadius: 2, background: 'rgba(220,203,164,0.18)'}}>
          <div style={{position: 'absolute', right: 0, top: 0, bottom: 0, width: `${prog * 100}%`, borderRadius: 2, background: d.gold}} />
        </div>
        <div style={{position: 'absolute', left: 40, top: 76, height: 56, display: 'flex', alignItems: 'center', gap: 12, opacity: 0.85, direction: 'ltr'}}>
          <div style={{position: 'relative', width: 50, height: 50}}>
            <Star8 size={50} stroke={d.gold} sw={3} style={{position: 'absolute', inset: 0}} />
            <Star8 size={18} stroke={d.gold} fill={d.gold} sw={1} style={{position: 'absolute', left: 16, top: 16}} />
          </div>
          <div style={{fontFamily: 'Amiri', fontWeight: 700, fontSize: 40, color: d.off, textShadow: '0 2px 8px rgba(0,0,0,0.6)'}}>{SADAQA.handle}</div>
        </div>
      </AbsoluteFill>
      <Sequence from={mainEnd}>
        <Outro dur={p.outroDur} />
      </Sequence>
    </AbsoluteFill>
  );
};
