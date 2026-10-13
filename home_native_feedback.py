"""Ephemeral physical-consumer evidence; never persisted as a seated result."""
import time


class NativeFeedback:
    TTL = 3.0
    # Protocol identifiers; native must establish the corresponding physical hit.
    SEATS = {'desk': 'desk_chair', 'sofa': 'sofa', 'bed': 'bed'}

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.epoch = None
        self.report = None
        self.received = None

    def accept(self, data, *, sequence, activity, target, nodes):
        if not isinstance(data, dict) or set(data) - {'epoch', 'sequence', 'activity', 'node', 'phase', 'chair', 'bind'}:
            raise ValueError('Invalid native feedback')
        epoch, phase = data.get('epoch'), data.get('phase')
        if (not isinstance(epoch, str) or not 1 <= len(epoch) <= 64
                or not isinstance(phase, str) or phase not in {'walking', 'arrived', 'seated', 'blocked'}
                or not isinstance(data.get('node'), str) or data['node'] not in nodes
                or type(data.get('sequence')) is not int
                or not isinstance(data.get('activity'), str)
                or type(data.get('bind', False)) is not bool):
            raise ValueError('Invalid native feedback')
        if data['sequence'] != sequence or data['activity'] != activity:
            raise RuntimeError('Native command changed')
        if phase in {'arrived', 'seated'} and data['node'] != target:
            raise RuntimeError('Native destination changed')
        chair = data.get('chair')
        if chair is not None and (not isinstance(chair, str) or len(chair) > 128):
            raise ValueError('Invalid chair identity')
        if phase == 'seated' and (target not in self.SEATS or chair != self.SEATS[target]):
            raise ValueError('Known physical seat identity required')
        if data.get('bind'):
            if phase != 'walking':
                raise ValueError('Bind requires walking phase')
            self.epoch, self.report, self.received = epoch, None, None
        elif self.epoch != epoch:
            raise RuntimeError('Native consumer is not bound to this epoch')
        self.report = {k: data.get(k) for k in ('epoch', 'sequence', 'activity', 'node', 'phase', 'chair')}
        self.received = self.clock()

    def ready(self, *, sequence, activity, target):
        if self.epoch is None:
            return True  # Browser-only mode retains its existing transition.
        report = self.report or {}
        return (self.received is not None and 0 <= self.clock() - self.received <= self.TTL
                and report.get('epoch') == self.epoch and report.get('sequence') == sequence
                and report.get('activity') == activity and report.get('node') == target
                and report.get('phase') == ('seated' if target in self.SEATS else 'arrived'))

    def view(self, *, sequence, activity, target):
        fresh = self.received is not None and 0 <= self.clock() - self.received <= self.TTL
        return {'bound': self.epoch is not None,
                'phase': (self.report or {}).get('phase') if fresh else None,
                'fresh': fresh,
                'physical_ready': self.epoch is not None and self.ready(
                    sequence=sequence, activity=activity, target=target)}
