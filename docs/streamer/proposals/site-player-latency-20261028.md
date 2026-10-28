# Site patch: live player latency (for Codex to deploy on subzerone.live)

Owner, 2026-10-28: replies and events feel 1-2 minutes late. Measured on the pod: chat -> agent ~2 s, -> reply queued
~2.6 s (median), TTS sentence-streamed, HLS 2 s segments. The site player (`web/live.html`, branch
`claude/live-control-20261027`, after `b9f0e86`) used hls.js `{maxBufferLength:20, liveSyncDurationCount:5}` with no
maximum latency: it starts 10 s behind and drifts further after every stall (Cloudflare quick tunnel), never catching up.

`site-player-latency-20261028.patch` (applies to `web/live.html` at `b9f0e86`; JS syntax checked):
- hls.js: `liveSyncDurationCount 2` (~4 s behind), `liveMaxLatencyDurationCount 5` (jump forward past ~10 s),
  `maxLiveSyncPlaybackRate 1.15` (gentle catch-up), `maxBufferLength 10`, `backBufferLength 10`;
- native HLS (Safari/iOS): every 2 s, more than 10 s behind the live edge -> jump to edge - 4 s (not while paused).

Kimi: APPROVE (slightly more rebuffering on marginal links). Apply on the site branch, then deploy as usual:
`git apply docs/streamer/proposals/site-player-latency-20261028.patch` from the site checkout root.

Also open (owner's call): the site sends chat as plain text without a name, and the pod relay forwards every message
as nick "viewer", so SUB-01 cannot greet people by name and the regulars registry sees one person. A name field on the
page (kept in localStorage, sent with each message) plus the relay passing it through would fix both.
