# Recovery03 and visual04 evidence milestone — 26 October 2026

Visual attempt04 failed during warmup with zero accepted frame events. Its cleanup and restoration subsequently completed and were independently verified at 20:35:33 UTC. This is a preservation and restoration milestone, not visual or performance acceptance. No native run is authorized by this document.

## Recovery03

The separately reviewed one-shot recovery restored the source ancestor to mode 0710 and the original canonical FIFO (device 66, inode 4303368925, UID/GID 1001, mode 0600). Independent verification recorded 629 preserved files and 24 successful recovery events. Original, imported and attempt03 project manifests remained exact with 5640, 5643 and 5643 files respectively. The retired experiment FIFO had inode 2177729005. Both historical attempt03 preservation generations remained intact. STOP remained held and no measurement lease existed. This recovery authorization has been consumed.

## Visual04 result and evidence limits

The one-shot visual04 review was consumed by its single execution. The native environment used UE_SKIP_UBT_SDK_SETUP=1, with the five pinned source/module/build receipts and the absent manual SDK environment file checked immediately before launch. This skips the observed guarded SDK validation route; it does not establish SDK correctness or guarantee suppression of every helper route. The existing unattended flag remained in place.

Startup advanced into derived-data cache initialization. Process discovery observed PID 5256, start ticks 61853357, comm zen, UID/GID 1001, empty supplementary groups, zero capabilities and NoNewPrivs=1, with native PID 5220 as parent. The credentialed inspection failed because the short-lived process disappeared before the second identity read. No successful exact executable authentication was returned for that process. The native log's zen service-status command is corroborating context, not a replacement for authenticated process identity. The strict observer retained this failure rather than accepting an unverified descendant.

The log also announced a detached cache server launch and three local shader workers. These log messages do not establish an authenticated shader-worker process census. Earlier cleanup records include exact-child wait failures; the later completed cleanup and independent verification establish the final restored state, without erasing the earlier sticky experiment failure.

Independent visual04 verification checked 122 latest-generation preserved files, two preservation generations, and complete project manifests: original 5640 files, imported 5643 files, experiment 5643 files. The latest generation-0002 manifest SHA256 is 586cb297ac08e544a620dedbdb2f5cb53fcce91b8c783563a27a10585e6fa944. The source ancestor and canonical FIFO were restored to the identities and permissions above. An actual credentialed UID 1001 access probe confirmed restored access. A full ten-process credential census, including the bounded verification controllers, established the post-run process state. STOP was held and the measurement lease absent.

The independent result is POSTRUN_INDEPENDENTLY_VERIFIED with reported_status FAILED and independent_technical_pass false. Frame readback is null. Visual and performance acceptance are NOT_ASSESSED. There are no new accepted frames, seated-contact findings, measured 60 fps results, head/voice acceptance, physical-input acceptance or complete-system acceptance. Original resume20/21 state remains missing; no substitute historical state is asserted. Any later native attempt requires a fresh exact review; attempt04 must not be rerun under its consumed approval.

## Kimi review

The archive includes the complete verbatim recovery03/SDK design consultation and exact visual04 consultation. Their original bounded authorizations are preserved as history and have been consumed; the SDK design discussion was not standalone execution permission. This evidence-only private commit requires a separate complete review of its exact frozen files. The accompanying commit-review question and answer are kept outside this frozen payload to avoid a self-referential packet. No runtime deployment, new design approval, recovery operation or publication is part of this milestone.

## Evidence

- recovery03-independent-verification.json: independent recovery receipt.
- visual04-independent-verification.json: independent post-run verification.
- visual04-failure-inspect.json: full bounded failure and lifecycle readback, including SDK prelaunch pins and native log context.
- visual04-foreground-transport-receipt.json: bounded foreground transport receipt; not a technical-pass certificate.
- ../kimi/recovery03-sdk-design-20261026-2020-question.txt and matching answer.json: verbatim prior consultation.
- ../kimi/visual04-exact-20261026-2030-question.txt and matching answer.json: verbatim exact one-shot consultation.
