from collections import Counter


def reconcile(intake, ledger):
    copies = ledger['copies']
    total = {key: sum(row[key] for row in copies) for key in ('requested', 'licensed', 'denied', 'pending')}
    restored = sum(row['restored'] for row in ledger['reversals'])
    shared_kept = sum(row['shared_kept'] for row in ledger['reversals'])
    accounts = ledger['accounts']
    source_ok = intake['received'] == intake['accepted'] + len(intake['duplicates']) + intake['isolated']
    orders_ok = all(r['requested'] == r['licensed'] + r['denied'] + r['pending'] for r in copies)
    reasons = Counter()
    footprints = []
    for row in copies:
        reasons.update(row['reasons'])
        if row['reasons']:
            footprints.append({'entry': row['entry'], 'line': row['line'], 'reasons': row['reasons']})
    active = [row for row in copies if row['entry'] not in ledger['cancelled']]
    # 实际合印页数 = 各合印组并集之和；同页被多单获准只扣一次
    printed = sum(group['printed_pages'] for group in ledger['print_groups'])
    effective = printed
    quota_ok = all(a['limit'] == a['used'] + a['available'] for a in accounts.values())
    quota_ok = quota_ok and sum(a['used'] for a in accounts.values()) == printed
    # 毛许可（各单获准页之和）= 有效合印页 + 撤销返还 + 仍被别单共用、暂不退还的页
    gross_ok = total['licensed'] == effective + restored + shared_kept
    return dict(total, restored=restored, shared_kept=shared_kept, effective=effective,
                balanced=source_ok and orders_ok and quota_ok and gross_ok,
                source_ok=source_ok, quota_ok=quota_ok, gross_ok=gross_ok,
                accounts=accounts, print_groups=ledger['print_groups'], reasons=dict(reasons),
                explanations=footprints,
                cancellation_errors=[row for row in ledger['reversals'] if row['reason']],
                active_licensed=sum(row['licensed'] for row in active))
