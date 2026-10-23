#!/usr/bin/env python3
"""Cut a short highlights reel from the streamer recording: every spoken line (with padding) plus the induced
incidents of a rehearsal, concatenated in time order. Evidence for review, not a broadcast asset.

    python scripts/streamer_highlights.py --streamer-dir /home/unreal/.sub01-private/streamer \
        --since <unix seconds> [--until <unix seconds>] [--max-seconds 300] --out highlights.mp4

Segments are matched to wall-clock time with ffprobe (file mtime minus duration = segment start).
"""
import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


def probe_duration(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def segments(recordings):
    found = []
    for path in sorted(recordings.glob('*.mp4')):
        duration = probe_duration(path)
        if duration <= 0:
            continue
        end = path.stat().st_mtime
        found.append((end - duration, end, path))
    return found


def windows(streamer_dir, since, until):
    """(start, end, label) windows worth keeping, in time order."""
    out = []
    timeline = streamer_dir / 'speech' / 'timeline.jsonl'
    if timeline.exists():
        for line in timeline.read_text().splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            start, end = item.get('start_utc'), item.get('end_utc')
            if isinstance(start, (int, float)) and isinstance(end, (int, float)) and since <= start <= until:
                out.append((start - 2.0, end + 1.5, f"speech:{item.get('tag', '')}"))
    rehearsal = streamer_dir / 'rehearsal.jsonl'
    if rehearsal.exists():
        for line in rehearsal.read_text().splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if item.get('kind') == 'inject' and since <= item.get('t', 0) <= until:
                out.append((item['t'] - 3.0, item['t'] + 12.0, f"inject:{item.get('event')}"))
    out.sort()
    merged = []
    for start, end, label in out:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]), merged[-1][2] + '+' + label)
        else:
            merged.append((start, end, label))
    return merged


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--streamer-dir', required=True)
    p.add_argument('--since', type=float, required=True)
    p.add_argument('--until', type=float, default=time.time())
    p.add_argument('--max-seconds', type=float, default=300)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    streamer_dir = Path(args.streamer_dir)
    segs = segments(streamer_dir / 'recordings')
    wins = windows(streamer_dir, args.since, args.until)
    total, parts, plan = 0.0, [], []
    with tempfile.TemporaryDirectory() as tmp:
        for i, (start, end, label) in enumerate(wins):
            if total >= args.max_seconds:
                break
            for seg_start, seg_end, path in segs:
                if start >= seg_start and start < seg_end:
                    offset = max(0.0, start - seg_start)
                    length = min(end, seg_end) - start
                    if length < 1.0:
                        continue
                    part = Path(tmp) / f'part{i:03d}.mp4'
                    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{offset:.2f}', '-i', str(path), '-t', f'{length:.2f}',
                                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-c:a', 'aac', '-b:a', '96k',
                                    '-vf', 'scale=1280:720', str(part)], check=False)
                    if part.exists() and part.stat().st_size > 0:
                        parts.append(part)
                        total += length
                        plan.append({'label': label, 'start_utc': start, 'seconds': round(length, 1), 'segment': path.name})
                    break
        if not parts:
            raise SystemExit('no highlight windows found in the recordings')
        listing = Path(tmp) / 'list.txt'
        listing.write_text(''.join(f"file '{p}'\n" for p in parts))
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing), '-c', 'copy', args.out], check=True)
    Path(args.out + '.json').write_text(json.dumps({'parts': plan, 'seconds': round(total, 1)}, indent=1))
    print(json.dumps({'out': args.out, 'parts': len(parts), 'seconds': round(total, 1)}))


if __name__ == '__main__':
    main()
