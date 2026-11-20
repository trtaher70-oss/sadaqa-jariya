// Umm al-Qura Hijri date for each day: node hijri.mjs 2026-11-20 400  →  {"2026-11-20":[1448,5,10], ...}
const [start, n] = process.argv.slice(2);
const f = new Intl.DateTimeFormat('en-u-ca-islamic-umalqura-nu-latn', {timeZone: 'UTC', year: 'numeric', month: 'numeric', day: 'numeric'});
const out = {};
const d0 = new Date(start + 'T12:00:00Z');
for (let i = 0; i < Number(n); i++) {
  const d = new Date(d0.getTime() + i * 864e5);
  const p = Object.fromEntries(f.formatToParts(d).map(x => [x.type, x.value]));
  out[d.toISOString().slice(0, 10)] = [parseInt(p.year), parseInt(p.month), parseInt(p.day)];
}
console.log(JSON.stringify(out));
