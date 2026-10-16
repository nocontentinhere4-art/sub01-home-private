"""Copy one immutable atomic-save inode without racing pathname replacement."""
import hashlib, os
from pathlib import Path

def copy_snapshot(source, destination, requested_epoch):
    source, destination = Path(source), Path(destination)
    def identity(s):
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    with source.open('rb') as stream:
        before = os.fstat(stream.fileno())
        assert before.st_size > 1024 * 1024 and before.st_mtime >= requested_epoch - 1, 'Fresh atomic saved inode required'
        digest = hashlib.sha256()
        with destination.open('wb') as output:
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
                digest.update(block)
            output.flush()
            os.fsync(output.fileno())
        after = os.fstat(stream.fileno())
        assert identity(before) == identity(after), 'Pinned snapshot inode mutated in place'
        assert destination.stat().st_size == before.st_size
        expected = digest.hexdigest()
        assert hashlib.sha256(destination.read_bytes()).hexdigest() == expected, 'Copied snapshot digest mismatch'
        current = source.stat()
        return {'source': str(source), 'bytes': before.st_size, 'sha256': expected,
                'atomic_save_completed_after_request': True,
                'pinned_source_fd': {'dev': before.st_dev, 'ino': before.st_ino, 'size': before.st_size,
                                     'mtime_ns': before.st_mtime_ns, 'ctime_ns': before.st_ctime_ns},
                'source_fd_unchanged_through_copy': True,
                'source_ctime_changed_after_open': before.st_ctime_ns != after.st_ctime_ns,
                'source_nlink_before_after': [before.st_nlink,after.st_nlink],
                'pathname_replaced_after_open': (current.st_dev,current.st_ino) != (before.st_dev,before.st_ino)}
