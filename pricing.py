"""Server-owned FX and 20% markup. Browser never decides conversion or margin."""
import json, os, threading, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_FLOOR, ROUND_CEILING
from urllib.request import Request, urlopen
from urllib.error import URLError
from core import Problem
import store

SUPPORTED=('UAH','USD')
_lock=threading.RLock()
_snapshot=None

def decimal(value, low=Decimal('0.000001'), high=Decimal('100000000')):
    try:
        n=Decimal(str(value))
        if not n.is_finite() or not low<=n<=high: raise ValueError()
        return n
    except (ValueError,InvalidOperation,TypeError): raise Problem('pricing_config',503)

def markup():
    return decimal(os.getenv('MARKUP_PERCENT','20'),Decimal('0'),Decimal('1000'))

def validate_snapshot(data):
    if not isinstance(data,dict) or data.get('result')!='success' or data.get('base_code')!='USD': raise Problem('fx_unavailable',503)
    try:
        age=time.time()-int(data['time_last_update_unix'])
        if age< -300 or age>172800: raise ValueError()
        rates=data['rates']
        for currency in ('USD','UAH','RUB'): decimal(rates[currency])
        if decimal(rates['USD'])!=1: raise ValueError()
        int(data['time_next_update_unix'])
    except (KeyError,ValueError,TypeError,Problem): raise Problem('fx_unavailable',503)
    return data

def snapshot(demo=False):
    global _snapshot
    if demo:
        # Explicitly fictional fixtures; never used for live checkout.
        return {'result':'success','base_code':'USD','rates':{'USD':1,'UAH':40,'RUB':100},
                'time_last_update_unix':int(time.time()),'time_next_update_unix':int(time.time())+86400,'demo':True}
    with _lock:
        now=time.time()
        if _snapshot and _snapshot['time_next_update_unix']>now:
            return validate_snapshot(_snapshot)
        if store.redis_ready():
            try:
                cached=store.redis(['GET','la:v3:fx:USD'])
                candidate=validate_snapshot(json.loads(cached)) if cached else None
                if candidate and candidate['time_next_update_unix']>now:
                    _snapshot=candidate
                    return candidate
            except (Problem,ValueError,TypeError): pass
        try:
            req=Request('https://open.er-api.com/v6/latest/USD',headers={'Accept':'application/json','User-Agent':'LegitAssets/3.0'})
            with urlopen(req,timeout=8) as response: data=validate_snapshot(json.load(response))
        except (URLError,TimeoutError,ValueError,TypeError): raise Problem('fx_unavailable',503)
        # Respect provider update interval, capped to one day for cache freshness.
        data['time_next_update_unix']=min(max(int(data['time_next_update_unix']),int(now)+60),int(now)+86400)
        _snapshot=data
        if store.redis_ready():
            try: store.redis(['SET','la:v3:fx:USD',json.dumps(data),'EX',max(60,int(data['time_next_update_unix']-now))])
            except Problem: pass
        return data

def multiplier(source,target,rates,margin=None):
    if target not in SUPPORTED: raise Problem('invalid_request')
    try: factor=decimal(rates['rates'][target])/decimal(rates['rates'][source])
    except KeyError: raise Problem('market_currency',502)
    return factor*(1+(markup() if margin is None else margin)/100)

def quote(item,currency='UAH',rates=None,internal=False):
    if currency not in SUPPORTED: raise Problem('invalid_request')
    rates=rates or snapshot()
    margin=markup()
    prices={target:int((Decimal(item['priceMinor'])*multiplier(item['currency'],target,rates,margin)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) for target in SUPPORTED}
    if min(prices.values())<1 or max(prices.values())>100000000000: raise Problem('invalid_price',502)
    out={**item,'priceMinor':prices[currency],'currency':currency,'prices':prices,'rateUpdatedAt':rates['time_last_update_unix']}
    # Supplier price and applied pricing audit are server/bot-only fields.
    if internal:
        out['supplier']={'priceMinor':item['priceMinor'],'currency':item['currency']}
        out['pricing']={'markupPercent':str(margin),'usdRates':{c:str(rates['rates'][c]) for c in {item['currency'],'USD','UAH'}},'updatedAt':rates['time_last_update_unix']}
    return out

def source_bound(value,currency,rates,upper):
    # Expand by half a minor unit so rounded retail prices at either boundary are included.
    sale_minor=decimal(value)*100
    raw_minor=(sale_minor+(Decimal('.5') if upper else Decimal('-.5')))/multiplier('RUB',currency,rates)
    rounded=raw_minor.quantize(Decimal('1'),rounding=ROUND_CEILING if upper else ROUND_FLOOR)
    return str(max(Decimal('1'),rounded)/100)

def public_item(item):
    return {k:v for k,v in item.items() if k not in {'supplier','pricing'}}
