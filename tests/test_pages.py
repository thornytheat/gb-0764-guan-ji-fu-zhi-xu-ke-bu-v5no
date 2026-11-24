from app.pagination.spans import normalize, split_limit, pages_in, subtract, intersect
from app.pagination.ledger import allocate
from app.registry.catalog import load_register


def copy(dirty, entry):
    return next(row for row in dirty['pages']['copies'] if row['entry']==entry)


def test_page_union_before_debit(dirty):
    c=copy(dirty,'C01')
    assert (c['normalized'],c['granted'],c['outside'])==([[1,9]],[[3,9]],[[1,3]])


def test_page_union_needs_no_per_page_expansion():
    assert normalize('9000000-9999999;1-4;5;3-6')==[[1,7],[9000000,10000000]]


def test_quota_allocates_lowest_pages(dirty):
    c=copy(dirty,'C02')
    # 第 8 页已被 C01 获准、随复本共用；额度池只剩 4 页，再从最低新页 9 满足到 12
    assert (c['granted'],c['shortage'])==([[8,13]],[[13,16]])
    assert (c['shared'],c['newly_charged'])==(1,4)


def test_shared_page_is_granted_to_every_order_without_double_debit():
    # 同馆、同刊、同条款、同年度的两单，申请页在 14-15 重叠
    base={'action':'copy','received':'2026-11-05','org':{'code':'00123'},
          'journal':{'issn':'2049-3630','pages':[3,20]},'ruling':None,'reasons':[]}
    first=dict(base,entry='S01',line=1,pages='14-19',license={'id':'NORTH-2','pool':'NORTH'})
    second=dict(base,entry='S02',line=2,pages='8-15',license={'id':'NORTH-2','pool':'NORTH'})
    result=allocate([first,second],{'NORTH':14})
    a,b=result['copies']
    assert (a['licensed'],b['licensed'])==(6,8)
    assert pages_in(intersect(a['granted'],b['granted']))==2
    assert b['shared']==2 and b['newly_charged']==6
    group=result['print_groups'][0]
    # 两单获准页之和为 14，但实际合印并集只有 12 页，额度池只扣 12
    assert group['printed_pages']==12 and result['accounts']['2026/NORTH']['used']==12


def test_different_terms_or_journals_never_share_authorization():
    row={'action':'copy','received':'2026-11-05','org':{'code':'00007'},
         'journal':{'issn':'2049-3630','pages':[3,20]},'ruling':None,'reasons':[]}
    a=dict(row,entry='T01',line=1,pages='3-6',license={'id':'NET-1','pool':'NET'})
    b=dict(row,entry='T02',line=2,pages='3-6',license={'id':'PORT-A','pool':'PORT'})
    result=allocate([a,b],{'NET':8,'PORT':5})
    assert len(result['print_groups'])==2
    assert [g['printed_pages'] for g in result['print_groups']]==[4,4]
    assert result['accounts']['2026/NET']['used']==4
    assert result['accounts']['2026/PORT']['used']==4


def test_distinct_libraries_keep_separate_unions_even_in_one_pool():
    row={'action':'copy','received':'2026-11-05',
         'journal':{'issn':'2049-3630','pages':[3,20]},'ruling':None,'reasons':[],
         'license':{'id':'NET-1','pool':'NET'}}
    a=dict(row,entry='L01',line=1,pages='3-6',org={'code':'00123'})
    b=dict(row,entry='L02',line=2,pages='3-6',org={'code':'00007'})
    result=allocate([a,b],{'NET':6})
    groups={g['entries'][0]:g for g in result['print_groups']}
    assert set(groups)=={'L01','L02'}
    # 同页各印一份、互不分摊：L01 先占 4 页，池剩 2 页，L02 仅获准 2 页
    assert groups['L01']['printed_pages']==4 and groups['L02']['printed_pages']==2
    assert result['copies'][1]['shortage']==[[5,7]]
    assert result['accounts']['2026/NET']['used']==6


def test_released_union_pages_return_to_quota_for_later_orders():
    base={'action':'copy','received':'2026-11-05','org':{'code':'00123'},
          'journal':{'issn':'2049-3630','pages':[3,20]},'ruling':None,'reasons':[],
          'license':{'id':'NORTH-2','pool':'NORTH'}}
    first=dict(base,entry='V01',line=1,pages='3-12')
    cancel={'action':'cancel','entry':'K01','line':2,'received':'2026-11-06',
            'org':{'code':'00123'},'target':'V01','ruling':None,'reasons':[]}
    later=dict(base,entry='V02',line=3,pages='3-12',received='2026-11-07')
    result=allocate([first,cancel,later],{'NORTH':10})
    assert result['reversals'][0]['restored']==10
    assert result['copies'][1]['licensed']==10 and result['copies'][1]['newly_charged']==10
    assert result['accounts']['2026/NORTH']['used']==10


def test_cancel_of_last_order_releases_whole_union():
    base={'action':'copy','received':'2026-11-05','org':{'code':'00123'},
          'journal':{'issn':'2049-3630','pages':[3,20]},'ruling':None,'reasons':[],
          'license':{'id':'NORTH-2','pool':'NORTH'}}
    first=dict(base,entry='U01',line=1,pages='14-19')
    second=dict(base,entry='U02',line=2,pages='8-15')
    cancel={'action':'cancel','entry':'K01','line':3,'received':'2026-11-06',
            'org':{'code':'00123'},'target':'U01','ruling':None,'reasons':[]}
    result=allocate([first,second,cancel],{'NORTH':14})
    reversal=result['reversals'][0]
    # U01 的 14-15 仍被 U02 共用，先不退，只释放 16-19 共 4 页
    assert (reversal['restored'],reversal['shared_kept'])==(4,2)
    group=result['print_groups'][0]
    assert group['printed']==[[8,16]] and group['printed_pages']==8
    assert result['accounts']['2026/NORTH']['used']==8


def test_late_recorded_cancel_restores_historical_order(dirty):
    reversal=dirty['pages']['reversals'][0]
    # C01 获准 6 页；撤销时第 8 页仍被 C02 获准而留组，只退其余 5 页
    assert (reversal['restored'],reversal['shared_kept'])==(5,1)
    assert copy(dirty,'C03')['licensed']==5
    assert copy(dirty,'C01')['licensed']==6
    group=next(g for g in dirty['pages']['print_groups'] if g['group'].endswith('NORTH-2'))
    # C01 退出后，组并集为 C02 的 8-12 与 C03 的 14-18，共 10 页
    assert group['printed']==[[8,13],[14,19]] and group['printed_pages']==10
    assert dirty['pages']['accounts']['2026/NORTH']['used']==10


def test_cut_both_article_limits():
    assert split_limit([[1,24]],3,20,2)==([[3,5]],[[1,3],[21,24]],[[5,21]])


def test_duplicate_and_wrong_holder_do_not_credit(dirty):
    assert [r['reason'] for r in dirty['pages']['reversals'][1:]]==['WRONG_ORG','REPEATED_CANCEL','UNKNOWN_TARGET']


def test_cancel_cannot_cross_quota_year(dirty):
    rows=dirty['licenses']['verdicts']
    source=next(row for row in rows if row['entry']=='C01')
    cancel=next(row for row in rows if row['entry']=='R01')
    result=allocate([source,dict(cancel,received='2027-01-01')],load_register()['authority']['pools'])
    assert result['reversals'][0]['reason']=='BOUNDARY'
    assert result['accounts']['2026/NORTH']['used']==6
