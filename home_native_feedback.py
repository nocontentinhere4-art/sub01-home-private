"""Ephemeral physical-consumer evidence; never persisted as a seated result."""
import time
import uuid


class NativeFeedback:
    TTL = 3.0
    # Protocol identifiers; native must establish the corresponding physical hit.
    SEATS = {'desk': 'desk_chair', 'sofa': 'sofa', 'bed': 'bed'}

    def __init__(self, clock=time.monotonic, required=False):
        self.clock = clock
        self.required = required is True
        self.epoch = None
        self.report = None
        self.received = None
        self.consumer_id = None
        self.report_id = None
        self.retired_consumers = set()

    def accept(self, data, *, sequence, activity, target, nodes):
        if not isinstance(data, dict) or set(data) - {'epoch', 'sequence', 'activity', 'node', 'phase', 'chair', 'bind', 'consumer_id', 'report_id'}:
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
        ordered = 'consumer_id' in data or 'report_id' in data
        consumer, report_id = None, None
        if ordered:
            value, report_id = data.get('consumer_id'), data.get('report_id')
            if (not isinstance(value, str) or len(value) not in (32, 36)
                    or type(report_id) is not int or not 1 <= report_id <= 2**53 - 1):
                raise ValueError('Expected consumer UUID and monotonic report integer')
            try:
                consumer = str(uuid.UUID(value))
            except ValueError:
                raise ValueError('Expected consumer UUID') from None
            if consumer in self.retired_consumers:
                raise RuntimeError('Native consumer was superseded')
        if self.consumer_id is not None:
            if not ordered:
                raise RuntimeError('Ordered native consumer requires report identity')
            if consumer == self.consumer_id and report_id <= self.report_id:
                raise RuntimeError('Native report is older than accepted evidence')
        if consumer != self.consumer_id and not data.get('bind'):
            raise RuntimeError('New native consumer requires explicit binding')
        if (consumer != self.consumer_id and self.consumer_id is not None
                and len(self.retired_consumers) >= 128):
            raise RuntimeError('Native consumer retirement bound reached')
        if data.get('bind'):
            if phase != 'walking':
                raise ValueError('Bind requires walking phase')
            self.epoch, self.report, self.received = epoch, None, None
            self.required = True
        elif self.epoch != epoch:
            raise RuntimeError('Native consumer is not bound to this epoch')
        if ordered:
            if consumer != self.consumer_id and self.consumer_id is not None:
                self.retired_consumers.add(self.consumer_id)
            self.consumer_id, self.report_id = consumer, report_id
        self.report = {k: data.get(k) for k in ('epoch', 'sequence', 'activity', 'node', 'phase', 'chair')}
        self.received = self.clock()

    def ready(self, *, sequence, activity, target):
        if self.epoch is None:
            return not self.required  # Only an explicitly browser-only home can use its timer.
        report = self.report or {}
        return (self.received is not None and 0 <= self.clock() - self.received <= self.TTL
                and report.get('epoch') == self.epoch and report.get('sequence') == sequence
                and report.get('activity') == activity and report.get('node') == target
                and report.get('phase') == ('seated' if target in self.SEATS else 'arrived'))

    def view(self, *, sequence, activity, target):
        fresh = self.received is not None and 0 <= self.clock() - self.received <= self.TTL
        current = (fresh and (self.report or {}).get('sequence') == sequence
                   and (self.report or {}).get('activity') == activity
                   and ((self.report or {}).get('phase') not in {'arrived', 'seated'}
                        or (self.report or {}).get('node') == target))
        return {'bound': self.epoch is not None,
                'required': self.required,
                'awaiting_binding': self.required and self.epoch is None,
                'phase': (self.report or {}).get('phase') if current else None,
                'fresh': fresh,
                'physical_ready': self.epoch is not None and self.ready(
                    sequence=sequence, activity=activity, target=target)}
