"""Physical FIFO history checks, independent of either cycle implementation."""
from collections import defaultdict


def check_fifo(p, times):
    queues = defaultdict(list)
    for i, r in enumerate(p['router']):
        queues[tuple(r['key'])].append(dict(
            credit=i, first=r['first'], arrival=times[r['first']]['finish'],
            consumers=r['users'],
            consumer_start=min(times[j]['start'] for j in r['users']),
            release=max(times[j]['start'] for j in r['users'])))
    violations = []
    count = 0
    service_overruns = 0
    for key, entries in queues.items():
        entries.sort(key=lambda r: (r['arrival'], r['first'], r['credit']))
        previous = None
        serviced = {}
        for row in entries:
            if row['consumer_start'] < row['arrival']:
                raise ValueError('FIFO consumer before physical arrival')
            if previous and row['consumer_start'] < previous['release']:
                count += 1
                violations.append(dict(queue=key, head=previous, bypass=row))
            # Prefix maximum catches bypass past any older head.
            if previous is None or row['release'] > previous['release']:
                previous = row
            for tick in {times[j]['start'] for j in row['consumers']}:
                if tick in serviced and serviced[tick] != row['credit']:
                    service_overruns += 1
                serviced[tick] = row['credit']
    violations.sort(key=lambda v: v['bypass']['consumer_start'])
    return dict(status='FAIL_FIFO_HEAD_ORDER' if count or service_overruns else 'PASS_FIFO_HEAD_ORDER',
                queues=len(queues), entries=len(p['router']), violations=count,
                input_service_overruns=service_overruns, examples=violations[:20],
                assumption='One ordered FIFO per physical input port/VC, one head '
                'per tick; pending multicast branches retain the head until all consume')
