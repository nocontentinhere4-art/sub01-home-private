// Paint at the viewport's aspect ratio so recorded privacy frames stay legible.
export function paintPrivacyScreen(canvas, width, height) {
  const scale = Math.min(1, 1600 / Math.max(width, height), Math.sqrt(750000 / (width * height)));
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const ctx = canvas.getContext('2d');
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  const background = ctx.createLinearGradient(0, 0, width, height);
  background.addColorStop(0, '#202824');
  background.addColorStop(1, '#101512');
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = 'rgba(162,173,164,.055)';
  ctx.lineWidth = 1;
  for (let x = -height; x < width; x += 72) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x + height, height); ctx.stroke();
  }
  ctx.textAlign = 'center';
  const center = height * .5;
  ctx.fillStyle = '#ecb37f';
  ctx.font = '14px monospace';
  ctx.fillText('SUB-01 / PRIVACY MODE', width / 2, center - 62);
  ctx.fillStyle = '#e9e4d8';
  ctx.font = `500 ${Math.min(64, width * .115)}px sans-serif`;
  ctx.fillText('OCCUPIED.', width / 2, center);
  ctx.fillStyle = '#a2ada4';
  ctx.font = '16px sans-serif';
  const words = 'Even a simulated brain needs a minute.'.split(' ');
  const lines = []; let line = '';
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (line && ctx.measureText(next).width > width - 48) { lines.push(line); line = word; }
    else line = next;
  }
  if (line) lines.push(line);
  lines.forEach((text, index) => ctx.fillText(text, width / 2, center + 42 + index * 24));
}
