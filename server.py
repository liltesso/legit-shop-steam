"""Legit Assets: same-origin catalogue proxy and verified checkout, Python 3.11+."""
import hashlib, hmac, json, mimetypes, os, re, threading, time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
# .env is read only on the server. Environment variables take precedence.
if (ROOT / '.env').exists():
    for line in (ROOT / '.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('\"').strip("'"))
TOKEN = os.getenv('LZT_TOKEN', '')
BOT = os.getenv('TELEGRAM_BOT_USERNAME', '').lstrip('@')
BOT_KEY = os.getenv('BOT_API_SECRET', '')
ORIGIN = os.getenv('PUBLIC_ORIGIN', '').rstrip('/')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
from core import Problem
import pricing, store
DEMO = os.getenv('DEMO_MODE', '0') == '1'
GAMES = [
    {'id':'cs2','appId':730,'name':'Counter-Strike 2','short':'CS2','color':'#e9af55'},
    {'id':'rust','appId':252490,'name':'Rust','short':'RUST','color':'#e27660'},
    {'id':'gta5','appId':271590,'name':'Grand Theft Auto V','short':'GTA V','color':'#80bd90'},
    {'id':'pubg','appId':578080,'name':'PUBG: BATTLEGROUNDS','short':'PUBG','color':'#ddbd73'},
    {'id':'cyberpunk','appId':1091500,'name':'Cyberpunk 2077','short':'2077','color':'#e5dd60'},
    {'id':'rdr2','appId':1174180,'name':'Red Dead Redemption 2','short':'RDR 2','color':'#de6c72'},
    {'id':'witcher3','appId':292030,'name':'The Witcher 3','short':'WITCHER','color':'#b4bed6'},
    {'id':'terraria','appId':105600,'name':'Terraria','short':'TERRARIA','color':'#77c6ac'}]
GAME_MAP = {g['id']: g for g in GAMES}
BLOCKED_ORIGINS = {'brute','phishing','stealer','retrieve_via_support'}
CACHE, RATE = OrderedDict(), OrderedDict()
LOCK = threading.RLock()

def money(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number <= 0 or number > 100000000:
            raise ValueError()
        return int((number * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        raise Problem('invalid_price', 502)

def integer(value, low=1, high=1000000000000):
    if isinstance(value, bool) or not re.fullmatch(r'\d+', str(value)):
        raise Problem('invalid_request')
    n = int(value)
    if not low <= n <= high: raise Problem('invalid_request')
    return n

def upstream(path, params=None, cached=False):
    if not TOKEN: raise Problem('not_configured', 503)
    url = 'https://api.lzt.market/' + path + ('?' + urlencode(params, doseq=True) if params else '')
    with LOCK:
        found = CACHE.get(url)
        if cached and found and found[0] > time.time(): return found[1]
    try:
        req = Request(url, headers={'Authorization': 'Bearer ' + TOKEN, 'Accept':'application/json', 'User-Agent':'LegitAssets/2.0'})
        with urlopen(req, timeout=15) as response:
            data = json.load(response)
        if not isinstance(data, dict) or data.get('errors'): raise Problem('market_error', 502)
    except HTTPError as e:
        mapping = {401:('market_auth',503),403:('market_auth',503),404:('unavailable',404),429:('rate_limit',429)}
        code, status = mapping.get(e.code, ('market_error',502))
        raise Problem(code,status)
    except (URLError, TimeoutError, ValueError): raise Problem('market_unreachable',502)
    if cached:
        with LOCK:
            CACHE[url] = (time.time()+20,data)
            while len(CACHE)>150: CACHE.popitem(last=False)
    return data

def normalize(item, game=None, fallback_currency=None):
    if not isinstance(item, dict): raise Problem('market_schema',502)
    if str(item.get('category_id',1)) != '1': raise Problem('unavailable',404)
    if item.get('item_origin') in BLOCKED_ORIGINS: raise Problem('unavailable',404)
    item_id = integer(item.get('item_id'))
    currency = str(item.get('price_currency') or item.get('currency') or fallback_currency or '').upper()
    if currency not in {'RUB','UAH','USD','EUR','KZT','BYN','GBP','TRY','BRL','CNY','PLN'}:
        raise Problem('market_currency',502)
    state = item.get('item_state')
    facts = {}
    fields = {'level':['steam_level'], 'country':['steam_country'], 'games':['steam_game_count'],
              'prime':['steam_csgo_prime','steam_cs2_prime'], 'rating':['steam_cs2_premier_elo'],
              'rank':['steam_cs2_profile_rank'], 'hours':['steam_hours_played'], 'vac':['steam_vac']}
    for name, candidates in fields.items():
        for field in candidates:
            value = item.get(field)
            if value is not None and isinstance(value,(str,int,float,bool)):
                facts[name] = str(value)[:100]
                break
    seller = item.get('seller') or {}
    return {'id':str(item_id), 'title':str(item.get('title') or 'Steam account')[:240],
            'priceMinor':money(item.get('price')), 'currency':currency,
            'available':state == 'active', 'game':game,
            'facts':facts, 'seller':str(seller.get('username',''))[:80] if isinstance(seller,dict) else '',
            'description':str(item.get('description') or '')[:4000],
            'url':f'https://lzt.market/{item_id}/'}

def demo_items(game):
    g = GAME_MAP[game]
    return [{'id':str(g['appId']*100+i),'title':f'{g["name"]} · Demo account {i+1:02}',
             'priceMinor':(450+i*187)*100, 'currency':'RUB','available':True,'game':game,
             'facts':{'level':str(4+i*3),'games':str(8+i*7),'country':['UA','PL','DE'][i%3],
                      **({'prime':'1','rating':str(6200+i*1340)} if game=='cs2' else {})},
             'seller':'Demo seller','description':'DEMO','url':None} for i in range(12)]

def listing(query):
    game = query.get('game','cs2')
    if game not in GAME_MAP: raise Problem('invalid_request')
    currency=query.get('currency','UAH')
    if currency not in pricing.SUPPORTED: raise Problem('invalid_request')
    if not TOKEN and not DEMO: raise Problem('not_configured',503)
    rates=pricing.snapshot(DEMO)
    page = integer(query.get('page','1'),1,500)
    order = query.get('sort','pdate_to_down')
    if order not in {'pdate_to_down','price_to_up','price_to_down'}: raise Problem('invalid_request')
    params = {'game[]':GAME_MAP[game]['appId'],'page':page,'order_by':order,'currency':'rub',
              'not_origin[]':sorted(BLOCKED_ORIGINS)}
    minimum=money(query['pmin']) if query.get('pmin') else 0
    maximum=money(query['pmax']) if query.get('pmax') else 100000000000
    if minimum>maximum: raise Problem('invalid_request')
    for key in ('pmin','pmax'):
        if query.get(key): params[key]=pricing.source_bound(query[key],currency,rates,key=='pmax')
    if query.get('q'): params['title'] = query['q'][:100]
    if query.get('noVac') == '1': params['no_vac'] = 1
    if DEMO:
        source=demo_items(game)
        if query.get('q'): source=[x for x in source if query['q'].lower() in x['title'].lower()]
        if page>1: source=[]
        has_next=False
    else:
        data=upstream('steam',params,cached=True)
        raw=data.get('items')
        if isinstance(raw,dict): raw=list(raw.values())
        if not isinstance(raw,list): raise Problem('market_schema',502)
        source=[]; malformed=0
        for row in raw:
            try: item=normalize(row,game,data.get('currency') or 'RUB')
            except Problem as error:
                if error.code!='unavailable': malformed+=1
                continue
            if item['available']: source.append(item)
        if raw and malformed==len(raw): raise Problem('market_schema',502)
        has_next=data.get('hasNextPage',data.get('has_next_page',len(raw)>0)) in (True,1,'1')
    items=[pricing.quote(item,currency,rates) for item in source]
    items=[item for item in items if minimum<=item['priceMinor']<=maximum]
    if DEMO and order.startswith('price'): items.sort(key=lambda x:x['priceMinor'],reverse=order=='price_to_down')
    return {'items':items,'hasNext':has_next,'page':page,'demo':DEMO,'currency':currency,
            'updatedAt':int(time.time()),'rateUpdatedAt':rates['time_last_update_unix']}

def detail(item_id,currency='UAH',rates=None,internal=False):
    item_id=integer(item_id)
    if currency not in pricing.SUPPORTED: raise Problem('invalid_request')
    if not TOKEN and not DEMO: raise Problem('not_configured',503)
    rates=rates or pricing.snapshot(DEMO)
    if DEMO:
        for game in GAME_MAP:
            for item in demo_items(game):
                if item['id']==str(item_id): return pricing.quote(item,currency,rates,internal)
        raise Problem('unavailable',404)
    data=upstream(str(item_id))
    return pricing.quote(normalize(data.get('item'),fallback_currency=data.get('currency')),currency,rates,internal)

def telegram_user(init_data):
    if not BOT_TOKEN:
        # No identity is inferred from unverified initData. Bot must bind the order on /start.
        return None
    if not isinstance(init_data,str) or len(init_data)>12000: raise Problem('telegram_auth',401)
    from urllib.parse import parse_qsl
    pairs=parse_qsl(init_data,keep_blank_values=True)
    if len({k for k,v in pairs})!=len(pairs): raise Problem('telegram_auth',401)
    values=dict(pairs)
    digest=values.pop('hash','')
    checked='\n'.join(f'{key}={value}' for key,value in sorted(values.items()))
    secret=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest()
    expected=hmac.new(secret,checked.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,digest): raise Problem('telegram_auth',401)
    try:
        age=time.time()-int(values['auth_date'])
        if not -30<=age<=3600: raise ValueError()
        user=json.loads(values['user'])
        return integer(user['id'])
    except (ValueError,KeyError,TypeError,Problem): raise Problem('telegram_auth',401)

def validate_record(record,fingerprint):
    if record['fingerprint']!=fingerprint: raise Problem('idempotency_conflict',409)
    if record['payload']['expiresAt']<time.time(): raise Problem('order_expired',410)
    return record['payload']

def public_order(order):
    return {**order,'items':[pricing.public_item(item) for item in order['items']]}

def checkout(body,key):
    if DEMO: raise Problem('demo_checkout',409)
    if not BOT or not BOT_KEY or not re.fullmatch(r'[A-Za-z0-9_]{5,32}',BOT): raise Problem('checkout_not_configured',503)
    store.ensure_available()
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',key): raise Problem('invalid_request')
    currency=body.get('currency','UAH')
    if currency not in pricing.SUPPORTED: raise Problem('invalid_request')
    rows=body.get('items')
    if not isinstance(rows,list) or not 1<=len(rows)<=10: raise Problem('invalid_request')
    ids=[]
    for row in rows:
        if not isinstance(row,dict): raise Problem('invalid_request')
        ids.append(str(integer(row.get('id'))))
        if type(row.get('priceMinor')) is not int: raise Problem('invalid_request')
        integer(row.get('priceMinor'),1,100000000000)
        if row.get('currency')!=currency: raise Problem('mixed_currency',409)
    if len(ids)!=len(set(ids)): raise Problem('duplicate_items')
    user_id=telegram_user(body.get('initData',''))
    fingerprint=hashlib.sha256(json.dumps({'items':rows,'currency':currency,'user':user_id},sort_keys=True).encode()).hexdigest()
    # Stable for retries, opaque without the random 128-bit client request key.
    order_id=hashlib.sha256(('legit-v3:'+key).encode()).hexdigest()[:40]
    existing=store.get_record(order_id)
    if existing: return public_order(validate_record(existing,fingerprint))
    rates=pricing.snapshot()
    def inspect(row):
        try: return detail(row['id'],currency,rates,internal=True)
        except Problem as error:
            if error.code=='unavailable': return None
            raise
    with ThreadPoolExecutor(max_workers=5) as pool: current=list(pool.map(inspect,rows))
    conflicts=[]
    for row,item in zip(rows,current):
        if not item or not item['available']:
            conflicts.append({'id':str(row['id']),'reason':'unavailable'})
        elif item['priceMinor']!=row['priceMinor']:
            conflicts.append({'id':item['id'],'reason':'price_changed','item':pricing.public_item(item)})
    if conflicts: raise Problem('cart_changed',409,conflicts=conflicts)
    payload={'id':order_id,'status':'awaiting_bot_checkout','items':current,
             'totalMinor':sum(x['priceMinor'] for x in current),'currency':currency,
             'totals':{c:sum(x['prices'][c] for x in current) for c in pricing.SUPPORTED},
             'telegramUserId':user_id,'createdAt':int(time.time()),'expiresAt':int(time.time())+900,
             'botUrl':f'https://t.me/{BOT}?start=order_{order_id}'}
    winner=store.put_record(order_id,{'fingerprint':fingerprint,'payload':payload})
    return public_order(validate_record(winner,fingerprint))

class Handler(BaseHTTPRequestHandler):
    def route(self):
        parsed=urlsplit(self.path)
        query={k:v[-1] for k,v in parse_qs(parsed.query).items()}
        path=parsed.path
        if path in ('/api/gateway','/api/gateway.py') and '__route' in query:
            path='/api/'+query.pop('__route').lstrip('/')
        return parsed,path,query
    def log_message(self, fmt, *args):
        # Do not log request URLs: order IDs are bearer references.
        pass
    def response(self,status,data):
        payload=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers(); self.wfile.write(payload)
    def rate_limit(self):
        # Only Vercel is trusted to set forwarding headers. Local requests use the socket address.
        ip=(self.headers.get('X-Forwarded-For','').split(',')[0].strip() if os.getenv('VERCEL') else '') or self.client_address[0]
        now=time.time()
        with LOCK:
            times=[t for t in RATE.pop(ip,[]) if now-t<60]
            RATE[ip]=times
            while len(RATE)>5000: RATE.popitem(last=False)
            if len(times)>=90: raise Problem('rate_limit',429)
            times.append(now)
    def do_GET(self):
        try:
            parsed,path,query=self.route()
            if path.startswith('/api/'):
                self.rate_limit()
                if path=='/api/config': data={'games':GAMES,'demo':DEMO,'configured':bool(TOKEN) or DEMO,'botEnabled':bool(BOT and BOT_KEY),'currency':'UAH','currencies':['UAH','USD']}
                elif path=='/api/listings': data=listing(query)
                elif re.fullmatch(r'/api/items/\d+',path): data={'item':detail(path.split('/')[-1],query.get('currency','UAH'))}
                elif re.fullmatch(r'/api/bot/orders/[A-Za-z0-9_-]+',path):
                    if not BOT_KEY or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+BOT_KEY): raise Problem('unauthorized',401)
                    record=store.get_record(path.split('/')[-1])
                    if not record: raise Problem('unavailable',404)
                    data=record['payload']
                    if data['expiresAt']<time.time(): raise Problem('order_expired',410)
                else: raise Problem('not_found',404)
                self.response(200,data); return
            public={'/':'index.html','/index.html':'index.html','/style.css':'style.css',
                    '/app.js':'app.js','/i18n.js':'i18n.js'}
            for lang in ('uk','ru','en'):
                public[f'/{lang}/']=f'{lang}/index.html'
                public[f'/{lang}/index.html']=f'{lang}/index.html'
            if path in ('/uk','/ru','/en'):
                self.send_response(302); self.send_header('Location',path+'/'); self.end_headers(); return
            if path.startswith('/assets/'):
                from urllib.parse import unquote
                file=(ROOT/'public'/unquote(path).lstrip('/')).resolve()
                if not file.is_relative_to((ROOT/'public'/'assets').resolve()) or file.suffix!='.png' or not file.is_file(): raise Problem('not_found',404)
            else:
                if path not in public: raise Problem('not_found',404)
                file=ROOT/'public'/public[path]
            content=file.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type','image/png' if file.suffix=='.png' else (mimetypes.guess_type(file)[0] or 'text/plain')+'; charset=utf-8')
            self.send_header('Content-Length',str(len(content)))
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Cache-Control','no-cache')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; object-src 'none'")
            self.end_headers(); self.wfile.write(content)
        except Problem as e: self.response(e.status,{'error':e.code,**e.data})
        except Exception: self.response(500,{'error':'server_error'})
    def do_POST(self):
        try:
            _,path,_=self.route()
            if path!='/api/checkout': raise Problem('not_found',404)
            self.rate_limit()
            origin=self.headers.get('Origin')
            allowed=ORIGIN or ('https://' if os.getenv('VERCEL') else 'http://')+self.headers.get('Host','')
            if origin and origin!=allowed: raise Problem('forbidden',403)
            if self.headers.get('Sec-Fetch-Site')=='cross-site': raise Problem('forbidden',403)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise Problem('invalid_request',415)
            length=integer(self.headers.get('Content-Length','0'),1,24000)
            try: body=json.loads(self.rfile.read(length))
            except (ValueError,UnicodeError): raise Problem('invalid_request')
            if not isinstance(body,dict): raise Problem('invalid_request')
            self.response(200,checkout(body,self.headers.get('Idempotency-Key','')))
        except Problem as e: self.response(e.status,{'error':e.code,**e.data})
        except Exception: self.response(500,{'error':'server_error'})

if __name__=='__main__':
    if BOT and not re.fullmatch(r'[A-Za-z0-9_]{5,32}',BOT): raise SystemExit('Invalid TELEGRAM_BOT_USERNAME')
    port=int(os.getenv('PORT','8080'))
    print(f'Legit Assets: http://localhost:{port}/uk/ | demo={DEMO}',flush=True)
    ThreadingHTTPServer((os.getenv('HOST','127.0.0.1'),port),Handler).serve_forever()
