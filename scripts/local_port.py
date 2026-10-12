"""Bounded startup wait for a previous localhost listener to finish closing."""
import errno
import socket
import time


def wait_for_local_port(port, timeout=8.0, interval=.05):
    deadline = time.monotonic() + timeout
    waited = False
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(('127.0.0.1', port))
            return waited
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            waited = True
            if time.monotonic() >= deadline:
                raise TimeoutError(f'Local port {port} is still in use; close the previous local server first.') from error
            time.sleep(min(interval, max(0, deadline-time.monotonic())))
