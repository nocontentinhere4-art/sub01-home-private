import socket
import threading
import time
import pytest
from scripts.local_port import wait_for_local_port


def listener():
    sock=socket.socket()
    sock.bind(('127.0.0.1',0))
    sock.listen()
    return sock


def test_waits_for_previous_listener_to_close():
    sock=listener(); port=sock.getsockname()[1]
    thread=threading.Thread(target=lambda: (time.sleep(.06),sock.close()))
    thread.start()
    try:
        assert wait_for_local_port(port,timeout=1,interval=.01) is True
        assert wait_for_local_port(port,timeout=1) is False
    finally:
        thread.join();sock.close()


def test_busy_port_fails_with_a_bounded_explanation():
    sock=listener()
    try:
        with pytest.raises(TimeoutError,match='still in use'):
            wait_for_local_port(sock.getsockname()[1],timeout=.03,interval=.005)
    finally:
        sock.close()
