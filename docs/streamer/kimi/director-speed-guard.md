# Kimi review (2026-10-24): director speed guard

Incident: a director launched while the voice model was loading ran at 0.70x for minutes (inputs "Thread message queue
blocking", output 42-49 fps, live latency growing); a manual restart gave 1.02x at 60 fps, with and without cam2 in the
graph. The guard measures output media seconds per wall second between 30 s watchdog ticks (ffmpeg's `speed=` is a run
average); 3 consecutive ticks below 0.95x relaunch ffmpeg, at most once per 10 minutes (then `held`); state shows
`window_speed` and `slow_checks`.

First request (`q-speed-guard.txt` long form): no answer, the model spent its 16000-token budget reasoning. Second request
(short form, 315 s), verbatim:

> 1. **Medium — `unknown` does not break the required consecutive-slow streak.** `speed_decision()` preserves
> `slow_checks` when `speed is None`, so `slow → unknown → slow → unknown → slow` reaches the limit and relaunches despite
> never having three consecutive ticks below 0.95x. It can also retain a streak through a long held/unknown period and
> restart on the first slow sample after the cooldown. Reset the counter on `"unknown"` (unless the intended policy is
> explicitly "three slow samples"), and add an interleaved-unknown test.
>
> No double-restart, relaunch-counter reset, or cooldown-loop bug is otherwise evident in the shown code.

Applied: `unknown` resets the streak; the interleaved test is in `tests/test_streamer_director.py`.
