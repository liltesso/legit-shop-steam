import copy, hashlib, hmac, json, os, sys, tempfile, time, unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server, pricing, store
class MiniAppTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.env=patch.dict(os.environ,{'ORDER_DB':self.temp.name+'/orders.db','MARKUP_PERCENT':'20','VERCEL':'','UPSTASH_REDIS_REST_URL':'','UPSTASH_REDIS_REST_TOKEN':''});self.env.start()
  self.patches=[patch.object(server,'DEMO',False),patch.object(server,'TOKEN','test-token'),patch.object(server,'BOT','ExampleBot'),patch.object(server,'BOT_KEY','test-server-secret'),patch.object(server,'BOT_TOKEN','')]
  for p in self.patches:p.start()
  self.fx={'result':'success','base_code':'USD','rates':{'USD':1,'UAH':40,'RUB':100},'time_last_update_unix':int(time.time()),'time_next_update_unix':int(time.time())+86400}
  self.rates=patch.object(pricing,'snapshot',return_value=self.fx);self.rates.start()
  self.raw={'item_id':73001,'category_id':1,'item_state':'active','title':'CS2 Prime','price':1000,'price_currency':'rub','steam_level':5,'steam_csgo_prime':1,'login':'SECRET','password':'SECRET'}
  self.item=pricing.quote(server.normalize(self.raw,'cs2'),'UAH',self.fx,internal=True)
  self.body={'currency':'UAH','items':[{'id':'73001','priceMinor':48000,'currency':'UAH'}]}
 def tearDown(self):
  self.rates.stop()
  for p in reversed(self.patches):p.stop()
  self.env.stop();self.temp.cleanup()
 def checkout(self,body=None,key='request_1234567890'):
  with patch.object(server,'detail',return_value=self.item):return server.checkout(body or self.body,key)
 def test_twenty_percent_two_currencies(self):
  self.assertEqual(self.item['prices'],{'UAH':48000,'USD':1200});self.assertEqual(self.item['priceMinor'],48000)
  self.assertEqual(pricing.quote(server.normalize(self.raw),'USD',self.fx)['priceMinor'],1200)
 def test_margin_server_only(self):
  with patch.dict(os.environ,{'MARKUP_PERCENT':'35'}):self.assertEqual(pricing.quote(server.normalize(self.raw),'UAH',self.fx)['prices']['USD'],1350)
  self.assertEqual(self.checkout({**self.body,'markupPercent':0,'rates':{'UAH':1}})['totalMinor'],48000)
 def test_decimal_rounding(self):
  item={**server.normalize(self.raw),'priceMinor':101};self.assertEqual(pricing.quote(item,'UAH',self.fx)['prices'],{'UAH':48,'USD':1})
 def test_invalid_margin(self):
  for value in ['nan','-1','1001','Infinity']:
   with patch.dict(os.environ,{'MARKUP_PERCENT':value}):
    with self.assertRaises(server.Problem):pricing.quote(server.normalize(self.raw),'UAH',self.fx)
 def test_supplier_fields_private(self):
  public=pricing.public_item(self.item);self.assertNotIn('supplier',public);self.assertNotIn('SECRET',json.dumps(public));self.assertNotIn('supplier',self.checkout()['items'][0])
 def test_retail_filter_upstream_conversion(self):
  with patch.object(server,'upstream',return_value={'items':[self.raw],'hasNextPage':True}) as api:result=server.listing({'game':'cs2','currency':'UAH','pmin':'480','pmax':'480','page':'2'})
  params=api.call_args.args[1];self.assertEqual(params['game[]'],730);self.assertEqual(params['page'],2);self.assertLessEqual(Decimal(params['pmin']),1000);self.assertGreaterEqual(Decimal(params['pmax']),1000);self.assertEqual(result['items'][0]['priceMinor'],48000)
 def test_usd_filter_retail(self):
  with patch.object(server,'upstream',return_value={'items':[self.raw],'hasNextPage':False}):
   self.assertEqual(len(server.listing({'currency':'USD','pmax':'11'})['items']),0);self.assertEqual(len(server.listing({'currency':'USD','pmax':'12'})['items']),1)
 def test_fx_failure_no_supplier_fallback(self):
  with patch.object(pricing,'snapshot',side_effect=server.Problem('fx_unavailable',503)):
   with self.assertRaises(server.Problem):server.listing({})
 def test_bad_fx_feed(self):
  for changed in [{'time_last_update_unix':int(time.time())-172801},{'base_code':'EUR'},{'rates':{'USD':1,'UAH':0,'RUB':100}}]:
   with self.assertRaises(server.Problem):pricing.validate_snapshot({**self.fx,**changed})
 def test_price_tampering_reconfirmation(self):
  body=copy.deepcopy(self.body);body['items'][0]['priceMinor']=1
  with self.assertRaises(server.Problem) as cm:self.checkout(body)
  self.assertEqual(cm.exception.code,'cart_changed');self.assertEqual(cm.exception.data['conflicts'][0]['item']['priceMinor'],48000);self.assertNotIn('supplier',cm.exception.data['conflicts'][0]['item'])
 def test_sold(self):
  self.item['available']=False
  with self.assertRaises(server.Problem) as cm:self.checkout()
  self.assertEqual(cm.exception.code,'cart_changed')
 def test_missing_bot(self):
  with patch.object(server,'BOT',''):
   with self.assertRaises(server.Problem) as cm:self.checkout()
  self.assertEqual(cm.exception.code,'checkout_not_configured')
 def test_mixed_currency(self):
  body=copy.deepcopy(self.body);body['currency']='USD'
  with self.assertRaises(server.Problem) as cm:self.checkout(body)
  self.assertEqual(cm.exception.code,'mixed_currency')
 def test_duplicate(self):
  with self.assertRaises(server.Problem):self.checkout({**self.body,'items':self.body['items']*2})
 def test_idempotency_and_bot_audit(self):
  first=self.checkout();self.assertEqual(first['id'],self.checkout()['id']);self.assertEqual(first['totals'],{'UAH':48000,'USD':1200})
  item=store.get_record(first['id'])['payload']['items'][0];self.assertEqual(item['supplier']['currency'],'RUB');self.assertEqual(item['pricing']['markupPercent'],'20');self.assertLessEqual(len('order_'+first['id']),64)
 def test_idempotency_conflict(self):
  self.checkout();body=copy.deepcopy(self.body);body['items'][0]['priceMinor']=1
  with self.assertRaises(server.Problem) as cm:self.checkout(body)
  self.assertEqual(cm.exception.code,'idempotency_conflict')
 def test_vercel_no_sqlite(self):
  with patch.dict(os.environ,{'VERCEL':'1'}),patch.object(store,'local_db',side_effect=AssertionError('SQLite on Vercel')):
   with self.assertRaises(server.Problem) as cm:store.get_record('abc')
  self.assertEqual(cm.exception.code,'order_storage')
 def test_redis_atomic_cross_instance(self):
  memory={}
  def redis(command):
   if command[0]=='GET':return memory.get(command[1])
   self.assertIn('NX',command);self.assertIn('EX',command)
   if command[1] in memory:return None
   memory[command[1]]=command[2];return 'OK'
  with patch.dict(os.environ,{'VERCEL':'1'}),patch.object(store,'redis_ready',return_value=True),patch.object(store,'redis',side_effect=redis):
   first=store.put_record('x',{'payload':{'expiresAt':123},'fingerprint':'first'});second=store.put_record('x',{'payload':{'expiresAt':456},'fingerprint':'second'});self.assertEqual(first,second);self.assertEqual(store.get_record('x'),first)
 def test_gateway_route(self):
  from api.gateway import handler
  instance=object.__new__(handler);instance.path='/api/gateway?__route=listings&currency=USD&game=cs2';_,path,q=instance.route();self.assertEqual(path,'/api/listings');self.assertEqual(q['currency'],'USD')
 def test_telegram_validation(self):
  token='123:test';values={'auth_date':str(int(time.time())),'user':json.dumps({'id':4242}),'query_id':'abc'}
  message='\n'.join(f'{k}={v}' for k,v in sorted(values.items()));secret=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest();values['hash']=hmac.new(secret,message.encode(),hashlib.sha256).hexdigest()
  with patch.object(server,'BOT_TOKEN',token):
   self.assertEqual(server.telegram_user(urlencode(values)),4242);values['user']=json.dumps({'id':9999})
   with self.assertRaises(server.Problem):server.telegram_user(urlencode(values))
 def test_demo_not_buyable(self):
  with patch.object(server,'DEMO',True):
   with self.assertRaises(server.Problem) as cm:self.checkout()
  self.assertEqual(cm.exception.code,'demo_checkout')
if __name__=='__main__':unittest.main()
