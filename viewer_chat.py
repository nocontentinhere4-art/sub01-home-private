"""Repeated viewer requests are allowed only on the dedicated local relay ingress."""
class _AllowRepeats:
    def seen(self, text):
        return False

_ALLOW_REPEATS = _AllowRepeats()

def dedupe_for_peer(ws, normal_dedupe):
    # Actual socket peer only: forwarding headers never grant the exception.
    request = getattr(ws, '_req', None)
    return _ALLOW_REPEATS if getattr(request, 'remote', None) == '127.0.0.2' else normal_dedupe
