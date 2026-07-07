import fs from 'fs';

fs.mkdirSync('./public/icons', { recursive: true });

function makeSVG(size) {
  const r = size / 2;
  const cx = r;
  const cy = r;
  const hr = r * 0.55;

  const hexPoints = Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 3) * i - Math.PI / 6;
    return { x: cx + hr * Math.cos(a), y: cy + hr * Math.sin(a) };
  });

  const pts = hexPoints.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');

  const edges = [[0, 3], [1, 4], [2, 5]]
    .map(([a, b]) => {
      const sw = (size * 0.025).toFixed(1);
      return `<line x1="${hexPoints[a].x.toFixed(1)}" y1="${hexPoints[a].y.toFixed(1)}" x2="${hexPoints[b].x.toFixed(1)}" y2="${hexPoints[b].y.toFixed(1)}" stroke="#60a5fa" stroke-width="${sw}"/>`;
    })
    .join('');

  const dots = hexPoints
    .map(p => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${(size * 0.045).toFixed(1)}" fill="#93c5fd"/>`)
    .join('');

  const fontSize = (size * 0.18).toFixed(0);
  const rx = (size * 0.18).toFixed(0);
  const sw = (size * 0.025).toFixed(1);

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">
  <rect width="${size}" height="${size}" rx="${rx}" fill="#0f172a"/>
  <polygon points="${pts}" fill="none" stroke="#3b82f6" stroke-width="${sw}"/>
  ${edges}
  ${dots}
  <text x="${cx}" y="${cy + size * 0.07}" text-anchor="middle" font-family="system-ui,sans-serif" font-size="${fontSize}" font-weight="700" fill="#f1f5f9">MN</text>
</svg>`;
}

fs.writeFileSync('./public/icons/icon-192.svg', makeSVG(192));
fs.writeFileSync('./public/icons/icon-512.svg', makeSVG(512));

// Also write PNG-compatible files (browsers accept SVG as icon source via manifest)
// Copy as .png-named files so the manifest can reference them by conventional names
fs.copyFileSync('./public/icons/icon-192.svg', './public/icons/icon-192x192.png.svg');
fs.copyFileSync('./public/icons/icon-512.svg', './public/icons/icon-512x512.png.svg');

console.log('Icons written: icon-192.svg, icon-512.svg');
