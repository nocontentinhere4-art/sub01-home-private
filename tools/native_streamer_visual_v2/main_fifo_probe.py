#!/usr/bin/env python3
"""Read the game's main-view FIFO for a while and check the v24 contract (a go/no-go helper; standard library only).

    python3 tools/native_streamer_visual_v2/main_fifo_probe.py [--fifo PATH] [--seconds 30] [--contract main|any]
                                                               [--save DIR --save-count 3] [--force]

Use it ONLY while nobody else reads the FIFO: a FIFO's readers split its bytes, so a second reader breaks frames for both. It refuses
when another process holds the path open for reading (/proc scan; --force skips the check) and never creates or replaces the FIFO.
Run it as root on the pod: another user's descriptors are invisible, so it also refuses when processes cannot be checked. The
scan is advisory (a reader may open the FIFO after it): it is repeated every RESCAN_S s and at the end; `other_reader_seen` true
(with `other_readers_during_run`) means the run's numbers do not count, false means none was SEEN (not proof). Exclusivity comes
from the procedure: the director must not be reading main.mjpeg (x11 mode, or stopped), and its own FIFO tap must not be draining it.

It opens the FIFO O_RDONLY|O_NONBLOCK (no writer yet = EOF, tolerated), polls, and walks whole JPEGs by their markers (header segments
by length, entropy data to the EOI; a frame whose tail never came, or garbage, resyncs on the next SOI). `--contract main` checks every
whole frame against install_v24.py's contract: SOI, the JFIF APP0 first, ONE COM "seq=<n>" second, no other APPn/COM, SOF0 (baseline)
1920x1080, EOI. `--contract any` only counts frames (cam2). The summary (JSON): frames, contract failures, cuts, a truncated tail,
sequences (first, last, distinct, missing, out of order), frame rates (first to last frame, and `*_window` = first frame to the END
of the run, so a writer that stopped early shows; `trailing_idle_ms`), inter-frame arrival gaps (p50/p95/p99/max ms; a frame's
arrival is the read that completed it, so frames completed by one read share it: `max_frames_per_read`) and the longest silence
between reads, the trailing one included. `--save` keeps the first whole frames as .jpg files for a visual check against the windowed
game (never replacing a file, never through a link). The FIFO is opened first (O_NOFOLLOW) and checked with fstat.
"""
from __future__ import annotations

import argparse
import errno
import json
import os
import select
import stat
import sys
import time
from pathlib import Path

DEFAULT_FIFO = '/home/unreal/.sub01-private/streamer/main.mjpeg'
WIDTH, HEIGHT, COM_PREFIX = 1920, 1080, b'seq='
CHUNK = 1 << 20
RESCAN_S = 5.0   # the other-readers scan is repeated this often during a run (and once at its end)


def other_readers(path: Path, proc: Path = Path('/proc'), target: tuple | None = None) -> tuple:
    """-> (PIDs other than this one holding `path` open for reading (O_RDONLY or O_RDWR), from /proc/<pid>/fd and fdinfo;
    the number of processes whose descriptors this user may not list: another user's reader would be invisible).
    `target` = (st_dev, st_ino) of the FIFO already opened (else `path` is stat'ed)."""
    if target is None:
        info = os.stat(path)
        target = (info.st_dev, info.st_ino)
    found, unchecked = [], 0
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            try:
                fds = list((entry / 'fd').iterdir())
            except PermissionError:
                unchecked += 1
                continue
            for fd in fds:
                try:
                    st = os.stat(fd)
                except OSError:
                    continue
                if (st.st_dev, st.st_ino) != tuple(target):
                    continue
                flags = 0
                for line in (entry / 'fdinfo' / fd.name).read_text().splitlines():
                    if line.startswith('flags:'):
                        flags = int(line.split()[1], 8)
                if flags & os.O_ACCMODE in (os.O_RDONLY, os.O_RDWR):
                    found.append(int(entry.name))
                    break
        except OSError:
            continue
    return found, unchecked


def check_contract(frame: bytes) -> tuple:
    """-> (ok, seq or None, reason) for one JPEG; never raises. Checked: SOI ... EOI, every header segment's length within the frame
    (before the EOI), the JFIF APP0 first, ONE COM "seq=<1..19 digits>" second, no other APPn/COM, exactly one SOF0 (baseline)
    1920x1080, an SOS. The entropy data is the frame cutter's part (any marker but RST/EOI there cuts the frame)."""
    if len(frame) < 6 or frame[:2] != b'\xff\xd8' or frame[-2:] != b'\xff\xd9':
        return False, None, 'not SOI ... EOI'
    pos, segments, seq, sof, sos, end = 2, 0, None, None, False, len(frame) - 2
    while pos + 4 <= end:
        if frame[pos] != 0xFF:
            return False, seq, 'not a marker where one must be'
        marker = frame[pos + 1]
        length = (frame[pos + 2] << 8) | frame[pos + 3]
        if length < 2 or pos + 2 + length > end:
            return False, seq, 'a segment length out of bounds'
        if marker == 0xDA:
            sos = True
            break
        body = frame[pos + 4:pos + 2 + length]
        segments += 1
        if segments == 1 and marker != 0xE0:
            return False, seq, 'APP0 is not the first segment'
        if segments == 1 and not body.startswith(b'JFIF\0'):
            return False, seq, 'APP0 is not JFIF'
        if segments == 2:
            digits = body[len(COM_PREFIX):]
            if marker != 0xFE or not body.startswith(COM_PREFIX) or not 1 <= len(digits) <= 19 or not digits.isdigit():
                return False, seq, 'the second segment is not COM "seq=<n>"'
            seq = int(digits)
        elif segments > 2 and (0xE0 <= marker <= 0xEF or marker == 0xFE):
            return False, seq, 'another APPn/COM segment'
        elif marker in (0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return False, seq, 'not baseline'
        elif marker == 0xC0:
            if sof is not None:
                return False, seq, 'two SOF0'
            if len(body) < 5:
                return False, seq, 'SOF0 too short'
            sof = ((body[3] << 8) | body[4], (body[1] << 8) | body[2])
        pos += 2 + length
    if not sos:
        return False, seq, 'no SOS'
    if sof != (WIDTH, HEIGHT):
        return False, seq, f'SOF0 {sof} is not {WIDTH}x{HEIGHT}'
    return True, seq, ''


class Walker:
    """Incremental frame cutter: feed bytes, get whole frames; cuts and garbage resync on the next SOI."""

    def __init__(self):
        self.buffer = bytearray()
        self.cuts = self.garbage = 0

    def drop_partial(self) -> None:
        """The writer closed (EOF): a frame it had not finished can never complete (it never resumes a tail): count it as a cut."""
        if self.buffer:
            self.cuts += 1
            self.buffer.clear()

    def _soi(self, start: int) -> int:
        return self.buffer.find(b'\xff\xd8\xff', start)

    def feed(self, data: bytes) -> list:
        self.buffer += data
        frames = []
        while True:
            start = self._soi(0)
            if start < 0:
                keep = 2 if self.buffer.endswith(b'\xff\xd8') else 1 if self.buffer.endswith(b'\xff') else 0
                if len(self.buffer) > keep:
                    self.garbage += 1
                del self.buffer[:len(self.buffer) - keep]
                return frames
            if start:
                self.garbage += 1
                del self.buffer[:start]
            end, complete = self._walk()
            fresh = self._soi(2)   # a NEW frame's SOI after this one's start (FF D8 FF never occurs inside an encoder's frame)
            if fresh > 0 and (end is None or end > fresh):
                # the writer restarted (it closed on a cut and reopened with no EOF seen in between): this frame can never complete,
                # and a walk that ran past the new SOI would glue two frames together
                self.cuts += 1
                del self.buffer[:fresh]
                continue
            if end is None:
                return frames                    # unfinished: wait for more bytes
            if not complete:                     # a cut frame: resync on the next SOI after this one
                self.cuts += 1
                nxt = self._soi(2)
                del self.buffer[:nxt if nxt > 0 else end]   # (end >= 2: from the cut on, a next SOI still arriving is kept)
                continue
            frames.append(bytes(self.buffer[:end]))
            del self.buffer[:end]

    def _walk(self) -> tuple:
        """-> (end, True) for a whole frame, (cut position, False) for a cut one, (None, False) when more bytes are needed."""
        b, n, pos = self.buffer, len(self.buffer), 2
        while True:
            if pos + 4 > n:
                return None, False
            if b[pos] != 0xFF:
                return pos, False
            marker = b[pos + 1]
            if marker == 0xD8:
                return pos, False
            length = (b[pos + 2] << 8) | b[pos + 3]
            if length < 2:
                return pos, False
            if pos + 2 + length > n:
                return None, False
            pos += 2 + length
            if marker == 0xDA:
                break
        while True:
            hit = b.find(b'\xff', pos)
            if hit < 0 or hit + 1 >= n:
                return None, False
            nxt = b[hit + 1]
            if nxt == 0x00 or 0xD0 <= nxt <= 0xD7:
                pos = hit + 2
                continue
            if nxt == 0xD9:
                return hit + 2, True
            return hit, False                    # another marker (an SOI of the next frame): this one was cut


def percentile(values: list, q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def open_save_dir(directory: Path) -> int:
    """-> a descriptor of the --save directory (created 0700 when absent), opened O_DIRECTORY|O_NOFOLLOW: every frame is then written
    through this held descriptor, so the path cannot be swapped for a link afterwards. Raises OSError for anything else."""
    try:
        directory.mkdir(mode=0o700, parents=True)
    except FileExistsError:
        pass   # an existing directory is used; anything else fails the O_DIRECTORY open below
    return os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)


def save_frame(dir_fd: int, name: str, frame: bytes) -> str | None:
    """Write one frame in the held directory without following a link and without replacing anything (-> name, or None if it exists)."""
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644, dir_fd=dir_fd)
    except FileExistsError:
        return None
    with os.fdopen(fd, 'wb') as handle:
        handle.write(frame)
    return name


def probe(path: Path, seconds: float, contract: str, save: tuple | None, save_count: int, force: bool) -> dict:
    """`save` = (the held --save directory descriptor, its path for the report) or None."""
    try:   # open first (never through a link), then check what was opened: no window between the check and the open
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            raise
        raise SystemExit(f'refused: {path} cannot be opened as a FIFO ({os.strerror(exc.errno)}; a link is never followed)')
    try:
        info = os.fstat(fd)
        if not stat.S_ISFIFO(info.st_mode):
            raise SystemExit(f'refused: {path} is not a FIFO (this tool never creates or replaces it)')
        if not force:
            readers, unchecked = other_readers(path, target=(info.st_dev, info.st_ino))
            if readers:
                raise SystemExit(f'refused: other readers hold {path} (pids {readers}); a second reader would split frames (--force to skip)')
            if unchecked:
                raise SystemExit(f'refused: {unchecked} processes are not visible to this user, so another reader could be missed (run it as '
                                 'root, or --force when you know nobody else reads the FIFO)')
    except BaseException:
        os.close(fd)
        raise
    walker, frames, seqs, arrivals, failures, saved, save_skipped = Walker(), 0, [], [], {}, [], 0
    read_bytes, last_read, longest_stall, eof_reads, writer_seen, max_per_read = 0, None, 0.0, 0, False, 0
    # The scan above is advisory (a reader may still open the FIFO after it): it is repeated every RESCAN_S s and at the end, and a
    # reader seen at any time voids the run (its numbers then do not count for the go/no-go).
    target, intruders, rescan_at = (info.st_dev, info.st_ino), set(), time.monotonic() + RESCAN_S
    poller = select.poll()
    poller.register(fd, select.POLLIN)
    started = time.monotonic()
    try:
        while time.monotonic() - started < seconds:
            if not force and time.monotonic() >= rescan_at:
                intruders.update(other_readers(path, target=target)[0])
                rescan_at = time.monotonic() + RESCAN_S
            poller.poll(100)
            try:
                data = os.read(fd, CHUNK)
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    continue
                raise
            now = time.monotonic()
            if not data:                          # EOF: no writer (yet, or any more)
                eof_reads += 1
                walker.drop_partial()             # a frame cut by the writer's close: the next writer starts with a fresh SOI
                time.sleep(0.05)
                continue
            writer_seen = True
            if last_read is not None:
                longest_stall = max(longest_stall, now - last_read)
            last_read = now
            read_bytes += len(data)
            whole = walker.feed(data)
            max_per_read = max(max_per_read, len(whole))
            for frame in whole:
                frames += 1
                arrivals.append(now)
                ok, seq, why = check_contract(frame) if contract == 'main' else (True, None, '')
                if not ok:
                    failures[why] = failures.get(why, 0) + 1
                if seq is not None:
                    seqs.append(seq)
                if save is not None and len(saved) < save_count:
                    written = save_frame(save[0], f'frame-{len(saved) + save_skipped:02d}{"-seq%d" % seq if seq is not None else ""}.jpg', frame)
                    if written:
                        saved.append(f'{save[1]}/{written}')
                    else:
                        save_skipped += 1
        if not force:
            intruders.update(other_readers(path, target=target)[0])   # the last look, while this probe still holds its descriptor
    finally:
        os.close(fd)
    ended = time.monotonic()
    elapsed = (arrivals[-1] - arrivals[0]) if len(arrivals) > 1 else 0.0
    window = (ended - arrivals[0]) if arrivals else 0.0   # first frame to the END of the run: a writer that stopped early counts
    if last_read is not None:
        longest_stall = max(longest_stall, ended - last_read)   # the trailing silence too
    gaps = [(b - a) * 1000 for a, b in zip(arrivals, arrivals[1:])]
    distinct = sorted(set(seqs))
    out_of_order = sum(1 for a, b in zip(seqs, seqs[1:]) if b <= a)
    missing = (distinct[-1] - distinct[0] + 1 - len(distinct)) if distinct else 0
    return {'schema': 'sub01.main-fifo-probe.v1', 'fifo': str(path), 'contract': contract, 'seconds': seconds, 'writer_seen': writer_seen,
            'bytes': read_bytes, 'frames': frames, 'contract_failures': failures, 'cuts': walker.cuts, 'garbage_runs': walker.garbage,
            'tail_bytes': len(walker.buffer), 'fps': round((frames - 1) / elapsed, 2) if elapsed > 0 else 0.0,
            'fps_window': round((frames - 1) / window, 2) if window > 0 and frames > 1 else 0.0,
            'trailing_idle_ms': round((ended - arrivals[-1]) * 1000, 2) if arrivals else None,
            'seq': {'first': seqs[0] if seqs else None, 'last': seqs[-1] if seqs else None, 'distinct': len(distinct), 'missing': missing,
                    'out_of_order': out_of_order, 'unique_fps': round((len(distinct) - 1) / elapsed, 2) if elapsed > 0 and distinct else 0.0,
                    'unique_fps_window': round((len(distinct) - 1) / window, 2) if window > 0 and distinct else 0.0},
            # arrival = the time of the read that completed the frame: frames completed by one read share it (max_frames_per_read)
            'arrival_gap_ms': {'p50': round(percentile(gaps, .5), 2), 'p95': round(percentile(gaps, .95), 2), 'p99': round(percentile(gaps, .99), 2),
                               'max': round(max(gaps), 2) if gaps else 0.0},
            'max_frames_per_read': max_per_read, 'longest_read_stall_ms': round(longest_stall * 1000, 2), 'eof_reads': eof_reads, 'saved': saved,
            'save_skipped_existing': save_skipped,
            # the scans can show another reader, never prove there was none (one could open and close between two scans)
            'other_reader_seen': None if force else bool(intruders), 'other_readers_during_run': sorted(intruders)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--fifo', type=Path, default=Path(DEFAULT_FIFO))
    parser.add_argument('--seconds', type=float, default=30.0)
    parser.add_argument('--contract', choices=('main', 'any'), default='main')
    parser.add_argument('--save', type=Path, help='directory for the first whole frames (.jpg)')
    parser.add_argument('--save-count', type=int, default=3)
    parser.add_argument('--force', action='store_true', help='skip the other-reader check (only when you know nobody else reads it)')
    args = parser.parse_args(argv)
    save = None
    if args.save is not None:
        try:
            save = (open_save_dir(args.save), str(args.save))
        except OSError as exc:
            print(json.dumps({'schema': 'sub01.main-fifo-probe.v1', 'status': 'refused',
                              'reason': f'--save {args.save} is not a usable plain directory ({os.strerror(exc.errno) if exc.errno else exc})'}))
            return 2
    try:
        report = probe(args.fifo, args.seconds, args.contract, save, args.save_count, args.force)
    except SystemExit as stop:
        print(json.dumps({'schema': 'sub01.main-fifo-probe.v1', 'status': 'refused', 'reason': str(stop)}))
        return 2
    except FileNotFoundError:
        print(json.dumps({'schema': 'sub01.main-fifo-probe.v1', 'status': 'refused', 'reason': f'{args.fifo} does not exist'}))
        return 2
    finally:
        if save is not None:
            os.close(save[0])
    report['status'] = 'ok'
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
