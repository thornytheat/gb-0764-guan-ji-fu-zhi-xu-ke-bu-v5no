from hashlib import sha256
from app.vault.record import encode


def path(client):
    return '/api/volumes/'+client.post('/api/volumes',json={'sample':'dirty'}).json['run_id']


def test_unsigned_draft_blocked(client):
    response=client.get(path(client)+'/export')
    assert (response.status_code,response.json['error'])==(409,'DRAFT_ONLY')


def test_certificate_signature_matches_detached_document(client):
    address=path(client)
    signature=client.post(address+'/stamp').json['imprint']
    reply=client.get(address+'/export')
    assert reply.headers['Content-Disposition'].startswith('attachment;')
    assert reply.json['verified'] and sha256(encode(reply.json['document']).encode()).hexdigest()==signature


def test_stamp_is_immutable_on_repeat(client):
    address=path(client)+'/stamp'
    first=client.post(address).json
    assert client.post(address).json==dict(first,reused=True)


def test_unknown_archive(client):
    result=client.post('/api/volumes/unknown/stamp')
    assert (result.status_code,result.json['error'])==(404,'RUN_UNKNOWN')


def test_retry_stamp_never_charges_pages_twice(client):
    address=path(client)
    first=client.post(address+'/stamp').json
    second=client.post(address+'/stamp').json
    assert second==dict(first,reused=True)
    doc=client.get(address+'/export').json['document']
    # 凭证中的合印并集与额度占用在重试后保持不变，没有二次扣页
    assert sum(g['printed_pages'] for g in doc['print_groups'])==doc['accounting']['effective']
    assert {k:v['used'] for k,v in doc['accounting']['accounts'].items()}=={
        '2026/COLL':5,'2026/NET':8,'2026/NORTH':10,'2026/OPEN':3}


def test_evidence_contains_old_orders_and_reversals(client):
    address=path(client)
    client.post(address+'/stamp')
    doc=client.get(address+'/export').json['document']
    assert doc['requests'][0]['licensed']==6 and doc['revocations'][0]['restored']==5
    assert doc['revocations'][0]['shared_kept']==1
    assert len(doc['isolated'])==5


def test_reveals_tampered_certificate(client,desk):
    address=path(client)
    client.post(address+'/stamp')
    with desk.vault.session() as conn:
        conn.execute("UPDATE slips SET body='{}'")
    assert client.get(address+'/export').json['verified'] is False
