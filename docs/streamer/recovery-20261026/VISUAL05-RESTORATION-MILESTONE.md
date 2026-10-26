# Visual05 failure and verified restoration — 26 October 2026

The exactly reviewed visual05 attempt ran once and failed before capture. Its one-shot authorization is consumed. The independent verification at 21:15:51 UTC established successful final restoration, while preserving FAILED and independent_technical_pass false. No frames were accepted; visual and performance acceptance remain NOT_ASSESSED.

## Actual startup and diagnostic failure

The native log records all three activity clips ready at 21:15:13.851 UTC. The safe-graph CVar and expected cache stores were observed, but the mandatory Verbose cache-graph parse proof was absent. The supervisor therefore rejected the run with `DDC evidence: graph parse missing/different/repeated`; observed readiness does not override this failure.

Installed Unix startup source, CommonUnixMain lines 264–282, adds quotation marks around an argument containing spaces. The supplied LogCmds argument already contained quotation marks. The actual LogInit command line consequently contains `-LogCmds=""LogDerivedDataCache Verbose,LogConfig Log,LogConsoleManager Verbose""`. Installed FParse source consumes the first opening quote and treats the immediately following quote as the end, yielding an empty value. This source-and-log diagnosis explains why the requested Verbose parse evidence was unavailable; it is not a retroactive pass or permission to weaken the gate.

A separate sticky cleanup identity/wait failure was recorded for native PID 5515. The native log also records an X11 shutdown error. Later cleanup recorded the native child reaped with return code 143. The independent final census and restoration establish the eventual settled state without erasing the intermediate lifecycle failure. A fresh attempt06 logging/lifecycle correction is under separate design review; this archive authorizes no execution and does not assert a completed correction.

## Independently verified final state

The independent receipt checks 121 latest-generation files and two preserved generations. Generation-0002 manifest SHA256 is 037744c433f58f86a37a7cf06673fb51af13ddc4baa6dc758915f7e13f3486aa. Original, imported and visual05 project manifests remain exact with 5640, 5643 and 5643 files respectively.

The source ancestor is restored to device 66, inode 2149578155, root UID 0/GID 1001, mode 0710. The canonical original FIFO is restored to device 66, inode 4303368925, UID/GID 1001, mode 0600. The actual UID 1001 probe confirmed restored access. The complete ten-process credential census includes the bounded verification controllers and confirms final process settlement. STOP remains held and no measurement lease exists. No separate recovery operation is required.

This remains a failed reconstructed-fixture experiment. Clip readiness is not proof of seated contact, natural posture, image quality, continuous animation, voice/head integration, measured 60 fps, physical input, original historical backend state or owner look acceptance. No visual image review was performed because the capture prerequisite was not reached.

## Kimi review

The complete verbatim exact visual05 question and answer are preserved with this archive. Answer SHA256 51dd8f9f12ee332fc5ecc7efcc348594f8db5d48b570d9a6cbb84d86751391f3 authorized exactly one execution and is consumed. This documentation/evidence-only commit requires its own exact frozen-payload review. Its new commit-review question and eventual answer stay outside the payload to avoid circular review. No previous execution or design approval is reused.

## Evidence

The accompanying independent verification, failure readback, DDC log inspection, installed logging-source excerpts and source/module pin readback are preserved verbatim. The file named visual06-logging-pin-read.json is supporting read-only provenance for the diagnosis, not proof of attempt06 execution. The foreground transport receipt records transport outcome only. No source tree or frozen runtime bundle is modified by this milestone.
