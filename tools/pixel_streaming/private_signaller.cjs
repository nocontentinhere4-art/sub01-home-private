/** Private adapter around Epic's official UE5.8 signalling library.
 * Run on the authorized Runpod only, behind an authenticated Jupyter proxy.
 * This process never starts an engine, opens a public listener, or starts TURN.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { createRequire } = require('node:module');
const infra = process.argv[2];
if (!infra || !path.isAbsolute(infra)) throw new Error('Supply absolute official infrastructure directory');
const fromInfra = createRequire(path.join(infra, 'package.json'));
const express = fromInfra('express');
const { SignallingServer, InitLogging } = fromInfra('@epicgames-ps/lib-pixelstreamingsignalling-ue5.8');
const app = express();
app.disable('x-powered-by');
app.use((req, res, next) => {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Referrer-Policy', 'no-referrer');
  next();
});
const www = path.join(infra, 'SignallingWebServer', 'www');
if (!fs.existsSync(path.join(www, 'player.html'))) throw new Error('Build official frontend first');
// Epic's reference frontend reads its signalling URL from the `ss` query setting.
// Set it before the official bundle executes so a stripped proxy prefix cannot
// accidentally direct the WebSocket to Jupyter's unauthenticated origin root.
app.get(['/', '/player.html'], (req, res) => {
  const html = fs.readFileSync(path.join(www, 'player.html'), 'utf8');
  const bootstrap = `<script>(function(){var u=new URL(location.href);var p=u.pathname.replace(/player\\.html$/, '');if(!p.endsWith('/'))p+='/';u.searchParams.set('ss',(u.protocol==='https:'?'wss:':'ws:')+'//'+u.host+p);history.replaceState(null,'',u.href);})();</script>`;
  res.type('html').send(html.replace(/<head(?:\s[^>]*)?>/i, match => match + bootstrap));
});
app.use(express.static(www, { dotfiles: 'deny' }));
const server = http.createServer(app);
let peerOptions = {};
if (process.env.SUB01_PRIVATE_PEER_OPTIONS_FILE) {
  const peerFile = process.env.SUB01_PRIVATE_PEER_OPTIONS_FILE;
  const mode = fs.statSync(peerFile).mode & 0o777;
  if (mode & 0o077) throw new Error('Private peer options must be owner-readable only');
  peerOptions = JSON.parse(fs.readFileSync(peerFile, 'utf8'));
}
InitLogging({ logDir: '/workspace/sub01-home-private/streaming/logs', logMessagesToConsole: false, logLevelConsole: 'info', logLevelFile: 'info' });
const signalling = new SignallingServer({
  httpServer: server,
  streamerPort: 8891,
  streamerWsOptions: { host: '127.0.0.1' },
  peerOptions,
  maxSubscribers: 1,
  playerKeepaliveTimeout: 30000
});
app.get('/private-status', (req, res) => res.json({
  privateLoopback: true,
  officialLibrary: 'UE5.8',
  expires: null,
  mediaRelayConfigured: Boolean(peerOptions.iceServers?.some(s => [].concat(s.urls || []).some(u => /^turns?:/.test(u))))
}));
server.listen(8890, '127.0.0.1', () => console.log('Private official signalling listener ready on loopback only'));
process.on('SIGTERM', () => process.exit(0));
process.on('SIGINT', () => process.exit(0));
