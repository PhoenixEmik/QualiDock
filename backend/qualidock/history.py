"""Bounded history summaries; scientific inputs/artifacts remain in full manifests."""
from functools import cmp_to_key

FIELDS = ('id', 'name', 'mode', 'state', 'stage', 'created_at', 'updated_at',
          'started_at', 'finished_at', 'threads', 'sample_count', 'error')


def page(runs, revision, *, offset=0, limit=25, search='', state='all', mode='all', order='created-desc'):
    if offset < 0 or not 1 <= limit <= 100 or len(search) > 120:
        raise ValueError('Invalid history pagination or search')
    if state not in {'all', 'active', 'issues', 'queued', 'running', 'completed', 'partial', 'failed', 'cancelled', 'interrupted'} or mode not in {'all', 'fastqc', 'both', 'multiqc'} or order not in {'created-asc', 'created-desc', 'finished-asc', 'finished-desc'}:
        raise ValueError('Invalid history filters')
    def matches(run):
        states = {'queued','running'} if state == 'active' else {'failed','partial','interrupted'} if state == 'issues' else {state}
        return ((state == 'all' or run['state'] in states) and (mode == 'all' or run['mode'] == mode)
                and search.strip().casefold() in (run['name'] + ' ' + run['id']).casefold())
    def compare(a, b):
        key = 'finished_at' if order.startswith('finished') else 'created_at'
        left, right = a.get(key), b.get(key)
        if not left or not right:
            return ((a['id'] > b['id']) - (a['id'] < b['id'])) if left == right else 1 if not left else -1
        difference = (left > right) - (left < right)
        return difference * (1 if order.endswith('asc') else -1) or (a['id'] > b['id']) - (a['id'] < b['id'])
    selected = sorted(filter(matches, runs.values()), key=cmp_to_key(compare))
    offset = min(offset, max(0, (len(selected) - 1) // limit * limit))
    return {'revision': revision, 'offset': offset, 'limit': limit, 'total': len(selected), 'overall_total': len(runs),
            'items': [{**{key: run.get(key) for key in FIELDS}, 'input_count': len(run.get('inputs', []))}
                      for run in selected[offset:offset + limit]]}


def invalidation(revision):
    return {'revision': revision}
