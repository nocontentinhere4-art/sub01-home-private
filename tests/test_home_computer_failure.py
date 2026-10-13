"""Loss of the actual worker must not leave an apparently live cached desktop."""
import asyncio
from types import SimpleNamespace
from home_computer import Computer


def test_dead_guest_clears_pixels_text_and_input_capability(tmp_path, monkeypatch):
    monkeypatch.delenv('HOME_COMPUTER_ORIGIN', raising=False)
    c = Computer(tmp_path)
    c.ready, c.status, c.output, c.last_command = True, 'ready', 'private terminal text', 'uname -a'
    c.display = {'kind': 'graphical', 'available': True, 'keyboard_available': True}
    c.framebuffer_png = b'old real guest pixels'
    c.process = SimpleNamespace(returncode=1)
    assert asyncio.run(c.graphical_input({'type': 'vga-keyboard', 'scancodes': [30, 158]})) is False
    state = c.view()
    assert not state['ready'] and state['status'] == 'offline'
    assert state['output'] == '' and state['last_command'] == ''
    assert c.framebuffer_png is None and not state['display']['available']
    assert not state['display'].get('keyboard_available')
