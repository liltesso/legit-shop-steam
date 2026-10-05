"""Durable orders on Vercel via Upstash REST; SQLite for local development only."""
import json, os, sqlite3, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError
from core import Problem


def redis_ready():
    return bool(os.getenv('UPSTASH_REDIS_REST_URL') and os.getenv('UPSTASH_REDIS_REST_TOKEN'))

def redis(command):
    url = os.getenv('UPSTASH_REDIS_REST_URL', '').rstrip('/')
    token = os.getenv('UPSTASH_REDIS_REST_TOKEN', '')
    if not url.startswith('https://') or not token: raise Problem('order_storage', 503)
    try:
        req = Request(url, data=json.dumps(command).encode(), method='POST', headers={
            'Authorization':'Bearer '+token, 'Content-Type':'application/json', 'User-Agent':'LegitAssets/3.0'})
        with urlopen(req,timeout=6) as response: data=json.load(response)
        if 'error' in data or 'result' not in data: raise ValueError()
        return data['result']
    except (URLError, TimeoutError, ValueError, TypeError): raise Problem('order_storage',503)

def db_path():
    if os.getenv('VERCEL'): raise Problem('order_storage',503)
    path=Path(os.getenv('ORDER_DB',str(Path(__file__).parent/'data'/'orders-v3.sqlite3')))
    path.parent.mkdir(parents=True,exist_ok=True)
    return path

def local_db():
    db=sqlite3.connect(db_path())
    db.execute('CREATE TABLE IF NOT EXISTS orders_v3 (id TEXT PRIMARY KEY, record TEXT NOT NULL, expires INTEGER NOT NULL)')
    return db

def ensure_available():
    if not redis_ready() and os.getenv('VERCEL'): raise Problem('order_storage',503)

def get_record(order_id):
    ensure_available()
    if redis_ready(): value=redis(['GET','la:v3:order:'+order_id])
    else:
        with local_db() as db:
            row=db.execute('SELECT record FROM orders_v3 WHERE id=?',(order_id,)).fetchone()
            value=row[0] if row else None
    if not value: return None
    try: return json.loads(value)
    except (ValueError,TypeError): raise Problem('order_storage',503)

def put_record(order_id,record):
    """SET NX is atomic across Vercel instances. Return the winning record."""
    ensure_available()
    value=json.dumps(record,ensure_ascii=False)
    if redis_ready():
        if redis(['SET','la:v3:order:'+order_id,value,'NX','EX',86400])=='OK': return record
        existing=get_record(order_id)
    else:
        with local_db() as db:
            db.execute('DELETE FROM orders_v3 WHERE expires < ?',(int(time.time())-86400,))
            db.execute('INSERT OR IGNORE INTO orders_v3 VALUES (?,?,?)',(order_id,value,record['payload']['expiresAt']))
            row=db.execute('SELECT record FROM orders_v3 WHERE id=?',(order_id,)).fetchone()
            existing=json.loads(row[0])
    if not existing: raise Problem('order_storage',503)
    return existing
