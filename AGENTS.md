# Private local home

The owner requires this work to stay private and on localhost. Do not deploy, connect this repository to Railway, modify the live SUB-01 site or its configuration, create public PRs, or publish these home changes without a separate explicit owner instruction. Keep credentials and local runtime data out of Git. Continue improving the real functioning home against the SimbasJungles visual reference; a video or standalone mockup is not completion.

## Reference priority

The primary visual reference, reaffirmed by the owner on 2026-10-13, is https://x.com/SimbasJungles/status/2109095401273938072. Use it as the acceptance reference for the home's visual direction and first-person experience. Ainthropos, Yokohara, Hmlet and other references are supporting references for individual details and techniques; they must not replace this direction. Inspect the actual reference before making visual comparisons, and never claim that a result matches it without viewing the result.

The owner explicitly raised the total private Runpod budget to $20 on 2026-10-13, including previous use. The owner authorized an additional bounded hour on the same private recovery pod; its verified current automatic stop is 2026-10-14 00:09:49 UTC (2026-10-14 02:09:49 Europe/Rome), epoch 1791936589. The $20 total cap still includes all previous use. Authorized home compute includes the existing source pod and its private A40 recovery replacement; do not touch the separate brain pod. This does not authorize public deployment. Heavy Blender, Unreal and rendering work belongs on the server, not on the owner's overheating Mac.

## Authorized migration window — 14 October 2026

The owner explicitly authorized replacement migration while keeping the $20 total cap and automatic stop. Automatic migration returned no available instances. The equivalent manual A40 replacement is `5ldnm4vax9kelh` (`sub01-home-private-migration-20261014`), GPU count 1, with a verified fixed stop at **2026-10-14 00:37:44 UTC**, epoch **1791938264**. Provider stopAfter, its embedded rootfs guard and a local identity-bound guard enforce that deadline. The previous pod `80lf8giw6ft61v` may run temporarily in CPU-only mode solely to transfer selected house/engine/PC/world data under the same deadline; stop it immediately after copying. No VM, Minecraft, CI or renderer on that 0.5 CPU / 512 MB source. This is a new migration operation, not a renewal of the prior rendering hour. The original source pod and brain remain untouched. Keep secrets out of transferred NFS files; preserve the existing source data and do not delete incomplete target artifacts as proof of success.

## Browser access

The owner requires the configured `playwright-isolated` Microsoft Playwright MCP server for Chrome interaction and research. Use its isolated browser without importing personal Chrome cookies or storage. If its tools are unavailable, report that limitation instead of substituting personal Chrome, another browser connector or a standalone Playwright script. Native app interaction, filesystem work, Runpod APIs and native Unreal captures remain available within the authorized private scope.
