// Render one Ayah reel: node render_one.mjs <props.json> <out.mp4> <cover.jpg> <coverFrame>
import {bundle} from '@remotion/bundler';
import {renderMedia, renderStill, selectComposition} from '@remotion/renderer';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const [propsFile, out, cover, coverFrame] = process.argv.slice(2);
const props = JSON.parse(fs.readFileSync(propsFile, 'utf8'));
const serveUrl = await bundle({entryPoint: path.resolve('src/index.ts'), publicDir: path.resolve('public')});
const comp = await selectComposition({serveUrl, id: 'Ayah', inputProps: props});
let last = -1;
await renderMedia({
  serveUrl, composition: comp, inputProps: props, codec: 'h264', crf: 18, pixelFormat: 'yuv420p',
  audioCodec: 'aac', audioBitrate: '192k', outputLocation: out, concurrency: Math.max(1, os.cpus().length), x264Preset: 'medium',
  onProgress: ({progress}) => { const p = Math.floor(progress * 4); if (p !== last) { last = p; console.log(`render ${p * 25}%`); } },
});
await renderStill({serveUrl, composition: comp, inputProps: props, frame: Number(coverFrame), output: cover, imageFormat: 'jpeg', jpegQuality: 92});
console.log('done', out);
