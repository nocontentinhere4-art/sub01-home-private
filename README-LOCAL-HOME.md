# SUB-01 private home development

This repository is for the new inhabited home only. Work and validation stay on localhost. Do not link it to the production Railway service, change production variables, merge it into the public SUB-01 repository, or deploy it without a separate explicit instruction from the owner.

The source snapshot includes the brain/server needed to run locally. See docs/inhabited-home.md for the implemented home and device tests. Previous production rollout was reverted; the public site uses its original deployment.

Start with HOME_ENABLED=1, HOME_ENTRYPOINT=1, BROWSE=1, MIND=0, CLIPS=0 and a local-only SUB01_ADMIN_TOKEN. Bind live_server.py to 127.0.0.1. Keep local runtime data outside Git.

`python scripts/start_home_local.py` enforces loopback binding and disables paid integrations. Default time is the real Tokyo clock. For a separate nighttime test use `--port 8801 --start 23:00 --time-scale 2 --data-dir /tmp/sub01-night-test`; the original clock ignores a custom start at scale 1. Keep these test instances separate from the main local runtime.

Day/night lighting now follows that same clock, including moving sunlight and lit pendant/bedside fixtures. `node tests/js/home_lighting_check.mjs` checks the full daily cycle; home/API/growth tests returned 11 passed. The 23:00 room was visually checked at approximately 46 fps after loading on this Mac. This is one machine, not a general performance guarantee. Local Chromium remains blocked by this Mac's sandbox; the guest Linux computer boots using verified cached assets.
