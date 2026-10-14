// Real Minecraft protocol client. Viewer transport follows prismarine-viewer's MIT example.
const mineflayer = require('mineflayer');
const { pathfinder, Movements, goals } = require('mineflayer-pathfinder');
const { WorldView } = require('prismarine-viewer/viewer/lib/worldView');
const express = require('express');
const http = require('node:http');
const path = require('node:path');
const readline = require('node:readline');
const { Vec3 } = require('vec3');
const { supportsPlayer, escapeTarget, placementSite } = require('./spatial.cjs');
const { harvestResource } = require('./resources.cjs');
const { viewerBootstrap } = require('./viewer_bootstrap.cjs');
const { instrumentViewerBundle } = require('./viewer_readiness.cjs');
const { entityPacket } = require('./item_rendering.cjs');
const fs = require('node:fs');
const { nativeInput } = require('./native_input.cjs');
const serverPort = Number(process.env.SUB01_MC_SERVER_PORT || 25569);
const viewerPort = Number(process.env.SUB01_MC_VIEW_PORT || 8803);
if (![serverPort,viewerPort].every(port => Number.isInteger(port) && port >= 1024 && port <= 65535) || serverPort === viewerPort)
  throw new Error('Use distinct private Minecraft server and viewer ports');
const app = express();
const server = http.createServer(app);
const io = require('socket.io')(server);
const viewerPublic = path.join(path.dirname(require.resolve('prismarine-viewer')), 'public');
const viewerEntry = instrumentViewerBundle(fs.readFileSync(path.join(viewerPublic, 'index.js'), 'utf8'));
app.get('/index.js', (_request, response) => response.type('application/javascript').send(viewerEntry));
app.use(express.static(viewerPublic));
server.listen(viewerPort, '127.0.0.1');
let bot = null, active = false, connected = false, busy = false, generation = 0;
const idleViewer = viewerBootstrap({isActive: () => active, connect,
  release: () => bot?.quit('Initial idle viewer released')});
let lastHealth = 20, lastItems = 0;
const emit = (value) => process.stdout.write(JSON.stringify(value) + '\n');
const operator = nativeInput({player:()=>connected?bot:null,isActive:()=>active,isBusy:()=>busy,emit,Vec3});
setInterval(()=>operator.tick(),25);
const hostiles = new Set(['zombie', 'skeleton', 'creeper', 'spider', 'enderman']);
function visibleWood() {
  // Mineflayer checks matching against palette entries without a position.
  // Visibility can only be tested after resolving actual world blocks.
  const positions = bot.findBlocks({ matching: b => b.name.endsWith('_log'), maxDistance: 12, count: 48 });
  const visible = positions.map(p => bot.blockAt(p)).filter(b => b && bot.canSeeBlock(b));
  return visible.find(b => bot.canDigBlock(b)) || visible[0] || null;
}
function visibleSoil() {
  const positions = bot.findBlocks({ matching: b => ['dirt', 'grass_block'].includes(b.name), maxDistance: 6, count: 64 });
  return positions.filter(p => !supportsPlayer(p, bot.entity.position))
    .map(p => bot.blockAt(p)).find(b => b && bot.canSeeBlock(b)) || null;
}
function observation() {
  if (!connected || !bot?.entity) return { type: 'state', connected: false, active, busy };
  const inventory = bot.inventory.items().map(i => ({ name: i.name, count: i.count }));
  const wood = visibleWood();
  const threats = Object.values(bot.entities).filter(e => hostiles.has(e.name) && e.position.distanceTo(bot.entity.position) < 12);
  return { type: 'state', connected, active, busy, health: bot.health, food: bot.food,
    position: bot.entity.position.toArray(), yaw: bot.entity.yaw, pitch: bot.entity.pitch,
    inventory, wood: wood ? { name: wood.name, position: wood.position.toArray() } : null,
    threats: threats.map(e => ({ name: e.name, distance: e.position.distanceTo(bot.entity.position) })),
    time: bot.time?.timeOfDay ?? 0 };
}
function connect() {
  if (bot || (!active && !idleViewer.allowed())) return;
  bot = mineflayer.createBot({ host: '127.0.0.1', port: serverPort, username: 'SUB01',
    auth: 'offline', version: '1.20.1', hideErrors: true });
  bot.loadPlugin(pathfinder);
  bot.once('spawn', () => {
    if (!active && !idleViewer.allowed()) { bot?.quit('Idle viewer lease expired'); return; }
    connected = true;
    const movements = new Movements(bot);
    movements.canDig = false;
    movements.allow1by1towers = false;
    movements.allowParkour = false;
    movements.maxDropDown = 2;
    bot.pathfinder.setMovements(movements);
    lastHealth = bot.health;
    lastItems = bot.inventory.items().reduce((n, i) => n + i.count, 0);
    emit(observation());
  });
  bot.on('health', () => {
    if (active && bot.health < lastHealth) emit({ type: 'feedback', reward: -0.5, event: 'damage', health: bot.health });
    lastHealth = bot.health;
  });
  bot.on('death', () => { if (active) emit({ type: 'feedback', reward: -1, event: 'death' }); });
  bot.on('error', error => emit({ type: 'error', message: String(error.message).slice(0, 200) }));
  bot.on('end', () => {
    operator.stop();bot = null; connected = false; busy = false; io.disconnectSockets();
    if (active) setTimeout(connect, 1500);
  });
}
io.on('connection', socket => {
  const current = bot;
  if (!connected || !current?.entity) return;
  socket.emit('version', current.version);
  const Item = require('prismarine-item')(current.registry);
  const textureExists = name => fs.existsSync(path.join(viewerPublic, name));
  const transport = {on: socket.on.bind(socket), emit: (event, packet) =>
    socket.emit(event, event === 'entity' ? entityPacket(packet,current,Item,textureExists) : packet)};
  const world = new WorldView(current.world, 2, current.entity.position, transport);
  world.init(current.entity.position);
  const position = () => {
    if (!current.entity) return;
    socket.emit('position', { pos: current.entity.position, yaw: current.entity.yaw,
      pitch: current.entity.pitch, addMesh: false });
    world.updatePosition(current.entity.position);
  };
  current.on('move', position);
  world.listenToBot(current);
  const itemUpdated = entity => {
    if (entity.name === 'item') transport.emit('entity', {id:entity.id,name:entity.name,
      pos:entity.position,width:entity.width,height:entity.height});
  };
  current.on('entityUpdate',itemUpdated);
  // Upstream ignores our player on spawn but still forwards its movement,
  // creating a fallback entity cube directly in the first-person camera.
  const moved = world.listeners[current.username].entityMoved;
  current.removeListener('entityMoved', moved);
  world.listeners[current.username].entityMoved = e => { if (e !== current.entity) moved(e); };
  current.on('entityMoved', world.listeners[current.username].entityMoved);
  position();
  socket.on('disconnect', () => {
    current.removeListener('move', position);
    world.removeListenersFromBot(current);
    current.removeListener('entityUpdate',itemUpdated);
  });
});
async function walkTo(position, horizontalOnly = false) {
  const player = bot;
  let timer;
  try {
    await Promise.race([
      player.pathfinder.goto(horizontalOnly
        ? new goals.GoalNearXZ(position[0], position[2], 2)
        : new goals.GoalNear(...position, 2)),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('path timeout')), 6000); })
    ]);
  } finally { clearTimeout(timer); player?.pathfinder.setGoal(null); }
}
async function act(command) {
  if (!active || !connected || busy) return;
  const allowed = new Set(['explore', 'mine_wood', 'gather_soil', 'place_block', 'eat', 'escape']);
  if (!allowed.has(command.action)) return;
  busy = true;
  const ownGeneration = generation;
  const player = bot;
  let reward = 0;
  try {
    if (command.action === 'mine_wood' || command.action === 'gather_soil') {
      const block = command.action === 'mine_wood' ? visibleWood() : visibleSoil();
      if (!await harvestResource(player, block, walkTo,
        () => generation === ownGeneration && active)) return;
      reward = 0.15;
    } else if (command.action === 'place_block') {
      const item = bot.inventory.items().find(i => /(_log|_planks|dirt|cobblestone)$/.test(i.name));
      const site = placementSite(player.entity.position,
        p => player.blockAt(new Vec3(p.x, p.y, p.z)), b => player.canSeeBlock(b));
      if (!item || !site) throw new Error('no reachable free build position');
      await bot.equip(item, 'hand');
      if (generation !== ownGeneration || !active) return;
      await player.placeBlock(site.support, new Vec3(0, 1, 0));
      reward = 0.2;
    } else if (command.action === 'eat') {
      const item = bot.inventory.items().find(i => ['apple', 'bread', 'carrot', 'cooked_beef'].includes(i.name));
      if (!item) throw new Error('no food');
      await bot.equip(item, 'hand'); await bot.consume(); reward = 0.3;
    } else if (command.action === 'escape') {
      const threat = Object.values(bot.entities).filter(e => hostiles.has(e.name))
        .sort((a, b) => a.position.distanceTo(bot.entity.position) - b.position.distanceTo(bot.entity.position))[0];
      if (!threat) throw new Error('threat no longer nearby');
      const target = escapeTarget(bot.entity.position, threat.position);
      await bot.look(Math.atan2(bot.entity.position.x - target[0], bot.entity.position.z - target[2]), 0);
      if (generation !== ownGeneration || !active) return;
      await walkTo(target);
      reward = .1;
    } else {
      const turn = Math.max(-Math.PI, Math.min(Math.PI, Number(command.turn) || 0));
      await bot.look(bot.entity.yaw + turn, 0);
      const p = bot.entity.position;
      await walkTo([p.x - Math.sin(bot.entity.yaw) * 6, p.y, p.z - Math.cos(bot.entity.yaw) * 6]);
      reward = 0.05;
    }
    if (generation === ownGeneration) emit({ type: 'feedback', action: command.action, reward, event: 'completed' });
  } catch (error) {
    if (generation === ownGeneration) emit({ type: 'feedback', action: command.action,
      reward: -0.08, event: String(error.message).slice(0, 100) });
  } finally { if (generation === ownGeneration) busy = false; player?.clearControlStates(); }
}
readline.createInterface({ input: process.stdin }).on('line', line => {
  if (line.length > 4096) return;
  try {
    const message = JSON.parse(line);
    if (message.type === 'viewer_bootstrap') idleViewer.request();
    else if (message.type === 'viewer_release') idleViewer.finish();
    else if (message.type === 'active') {
      operator.stop();active = message.value === true; generation++;
      idleViewer.finish();
      if (active) connect();
      else { bot?.pathfinder.setGoal(null); bot?.clearControlStates(); bot?.quit('Console put away'); }
    } else if (message.type === 'operator_input') operator.accept(message).catch(error=>emit({type:'input_receipt',consumer_id:message.consumer_id,focus_event_id:message.focus_event_id,input_id:message.input_id,accepted:false,reason:String(error.message).slice(0,100)}));
    else if (message.type === 'action') act(message);
  } catch (error) { emit({ type: 'error', message: String(error.message).slice(0, 100) }); }
});
setInterval(() => {
  if (connected) {
    const count = bot.inventory.items().reduce((n, i) => n + i.count, 0);
    if (active && count > lastItems) emit({ type: 'feedback', reward: 0.25, event: 'item collected' });
    lastItems = count;
  }
  emit(observation());
}, 1000);
process.stdin.on('end', () => { bot?.quit(); io.close(); server.close(); process.exit(0); });
