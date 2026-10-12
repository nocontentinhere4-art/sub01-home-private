# SUB-01 private home development

This repository is for the new inhabited home only. Work and validation stay on localhost. Do not link it to the production Railway service, change production variables, merge it into the public SUB-01 repository, or deploy it without a separate explicit instruction from the owner.

The source snapshot includes the brain/server needed to run locally. See docs/inhabited-home.md for the implemented home and device tests. Previous production rollout was reverted; the public site uses its original deployment.

Start with HOME_ENABLED=1, HOME_ENTRYPOINT=1, BROWSE=1, MIND=0, CLIPS=0 and a local-only SUB01_ADMIN_TOKEN. Bind live_server.py to 127.0.0.1. Keep local runtime data outside Git.
