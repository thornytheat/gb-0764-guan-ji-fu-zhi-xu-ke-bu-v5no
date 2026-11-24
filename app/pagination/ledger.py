from app.problem import MESSAGES
from .spans import normalize, pages_in, clip, subtract, union


def _group_key(row, chosen):
    # 同一年度、同一馆、同一刊物、同一条款才能共用一份复本；任一不同即分组各自扣页
    return f"{row['received'][:4]}/{row['org']['code']}/{row['journal']['issn']}/{chosen['id']}"


def _grant(row, chosen, state, pools):
    quota_id = chosen['pool']
    pool_key = f"{row['received'][:4]}/{quota_id}"
    account = state['accounts'].setdefault(
        pool_key, {'limit': pools[quota_id], 'used': 0, 'gross': 0})
    group = state['groups'].setdefault(_group_key(row, chosen), {
        'pool': pool_key, 'printed': [], 'members': []})

    intervals = normalize(row['pages'])
    start, end = row['journal']['pages']
    inside, outside = clip(intervals, start, end)
    # 组内已落印并集之外的页才需要新占额度；重叠页随复本共用，直接获准
    fresh = subtract(inside, group['printed'])
    allowance = account['limit'] - account['used']
    charged, exhausted = _take(fresh, allowance)

    overlap = subtract(inside, fresh)
    granted = union(overlap, charged)
    shortage = subtract(inside, granted)

    charged_pages = pages_in(charged)
    account['used'] += charged_pages
    account['gross'] += charged_pages
    group['printed'] = union(group['printed'], charged)
    group['members'].append(row['entry'])

    reasons = {}
    if outside:
        reasons['OUTSIDE_ARTICLE'] = pages_in(outside)
    if shortage:
        reasons['QUOTA'] = pages_in(shortage)
    return {'entry': row['entry'], 'line': row['line'], 'received': row['received'],
            'org': row['org']['code'], 'license': chosen['id'], 'pool': pool_key,
            'group': _group_key(row, chosen), 'requested': pages_in(intervals),
            'licensed': pages_in(granted), 'denied': pages_in(outside) + pages_in(shortage),
            'pending': 0, 'normalized': intervals, 'granted': granted, 'outside': outside,
            'shortage': shortage, 'shared': pages_in(overlap), 'newly_charged': charged_pages,
            'reasons': reasons, 'notes': {code: MESSAGES[code] for code in reasons}}


def _take(intervals, allowance):
    # fresh 段已在刊物页界内，这里只按剩余额度从最低页开始切分
    charged, exhausted = [], []
    for span_start, span_end in intervals:
        taken = min(allowance, span_end - span_start)
        if taken:
            charged.append([span_start, span_start + taken])
        if span_start + taken < span_end:
            exhausted.append([span_start + taken, span_end])
        allowance -= taken
    return charged, exhausted


def _cancel(row, state):
    target = state['active'].get(row['target'])
    code = row.get('ruling')
    if not code and target is None:
        code = 'REPEATED_CANCEL' if row['target'] in state['released'] else 'UNKNOWN_TARGET'
    if not code and row['org']['code'] != target['org']:
        code = 'WRONG_ORG'
    if not code and row['received'][:4] != target['received'][:4]:
        code = 'BOUNDARY'
    restored = shared_kept = 0
    if not code:
        state['active'].pop(row['target'])
        state['released'].add(row['target'])
        group = state['groups'][target['group']]
        before = pages_in(group['printed'])
        group['members'].remove(row['target'])
        survivors = [item for item in state['orders']
                     if item['entry'] in group['members'] and item.get('group') == target['group']]
        group['printed'] = union(*[item['granted'] for item in survivors]) if survivors else []
        restored = before - pages_in(group['printed'])
        shared_kept = target['licensed'] - restored
        state['accounts'][target['pool']]['used'] -= restored
    return {'entry': row['entry'], 'line': row['line'], 'target': row['target'],
            'restored': restored, 'shared_kept': shared_kept, 'reason': code,
            'target_line': target['line'] if target else None}


def allocate(verdicts, pools):
    state = {'accounts': {}, 'groups': {}, 'active': {}, 'released': set(),
             'orders': [], 'reversals': []}
    for row in verdicts:
        if row['action'] == 'cancel':
            state['reversals'].append(_cancel(row, state))
            continue
        chosen = row['license']
        if chosen:
            result = _grant(row, chosen, state, pools)
        else:
            intervals = normalize(row['pages'])
            total = pages_in(intervals)
            code = row['ruling'] or 'NO_LICENSE'
            denied = total if code == 'NO_LICENSE' else 0
            pending = total - denied
            result = {'entry': row['entry'], 'line': row['line'], 'received': row['received'],
                      'org': row['org']['code'] if row['org'] else None,
                      'license': None, 'pool': None, 'group': None, 'requested': total,
                      'licensed': 0, 'denied': denied, 'pending': pending,
                      'normalized': intervals, 'granted': [], 'outside': [], 'shortage': [],
                      'shared': 0, 'newly_charged': 0, 'reasons': {code: total},
                      'notes': {code: MESSAGES[code]}}
        state['orders'].append(result)
        if result['licensed']:
            state['active'][row['entry']] = result

    groups = [{'group': key, 'pool': item['pool'], 'entries': list(item['members']),
               'printed': item['printed'], 'printed_pages': pages_in(item['printed'])}
              for key, item in sorted(state['groups'].items())]
    accounts = {key: dict(value, available=value['limit'] - value['used'])
                for key, value in sorted(state['accounts'].items())}
    return {'copies': state['orders'], 'reversals': state['reversals'],
            'accounts': accounts, 'print_groups': groups,
            'cancelled': sorted(state['released'])}
