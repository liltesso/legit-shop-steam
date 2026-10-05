import { dictionaries } from './i18n.js';
const lang = document.documentElement.lang in dictionaries ? document.documentElement.lang : 'uk';
const t = key => dictionaries[lang][key] || dictionaries.en[key] || key;
const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icons = {
 cart:'<path d="M3 3h2l2.4 12h11l2-8H6"/><circle cx="9" cy="20" r="1"/><circle cx="18" cy="20" r="1"/>',
 arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
 search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
 refresh:'<path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/>',
 layers:'<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
 check:'<path d="m8 12 3 3 5-6M12 2l9 4v6c0 5-9 10-9 10S3 17 3 12V6l9-4Z"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.arrow}</svg>`;
document.querySelectorAll('[data-t]').forEach(el => el.textContent=t(el.dataset.t));
document.querySelectorAll('[data-placeholder]').forEach(el => {el.placeholder=t(el.dataset.placeholder);el.setAttribute('aria-label',el.placeholder)});
document.querySelectorAll('[data-label]').forEach(el => el.setAttribute('aria-label',t(el.dataset.label)));
document.querySelectorAll('[data-icon]').forEach(el => el.innerHTML=icon(el.dataset.icon));
document.querySelector('.skip-link').textContent=t('back');
$('filters').setAttribute('aria-label',t('filters'));
document.title=`${t('title')} — Legit Assets`;
const state={config:null,game:'cs2',items:[],page:1,hasNext:false,cart:[],loading:false,checking:false,controller:null,detailController:null,detail:null,order:null,filters:{},key:null,currency:'UAH'};
const storageKey=()=>`legit-steam-cart-v3-${state.config?.demo?'demo':'live'}`;
const validItem = x => x && /^\d+$/.test(x.id) && typeof x.title==='string' && Number.isSafeInteger(x.priceMinor) && x.priceMinor>0 && ['UAH','USD'].every(c=>Number.isSafeInteger(x.prices?.[c])&&x.prices[c]>0);
function loadCart(){try{const data=JSON.parse(localStorage.getItem(storageKey())||'[]');state.cart=Array.isArray(data)?[...new Map(data.filter(validItem).map(x=>[String(x.id),{...x,id:String(x.id)}])).values()].slice(0,10):[]}catch{state.cart=[]}}
let toastTimer;
function toast(text){$('toast').textContent=text;$('toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('visible'),3500)}
function saveCart(){state.order=null;state.key=null;try{localStorage.setItem(storageKey(),JSON.stringify(state.cart))}catch{toast(t('storage'))}renderCart();updateAdds()}
function price(value,currency=state.currency){try{return new Intl.NumberFormat(lang==='uk'?'uk-UA':lang==='ru'?'ru-RU':'en-US',{style:'currency',currency,currencyDisplay:'narrowSymbol',maximumFractionDigits:2}).format(value/100)}catch{return `${(value/100).toFixed(2)} ${currency}`}}
const alternate=()=>state.currency==='UAH'?'USD':'UAH';
const retail=(item,currency=state.currency)=>item.prices[currency];
function totals(currency=state.currency){return price(state.cart.reduce((sum,x)=>sum+retail(x,currency),0),currency)}
function pair(item){return `<span class="price-pair"><strong class="price">${escape(price(retail(item)))}</strong><small class="secondary-price">≈ ${escape(price(retail(item,alternate()),alternate()))}</small></span>`}
const gameKeys=['cs2','rust','gta5','pubg','cyberpunk','rdr2','witcher3','terraria'];
const assetKey=id=>gameKeys.includes(id)?id:'cs2';
const gameAsset=(id,kind='cover')=>`/assets/games/${assetKey(id)}-${kind}.png`;
const squareIcons=new Set(['cs2','rust','cyberpunk','rdr2','terraria']);
const emoji=id=>`<img class="game-icon-image ${squareIcons.has(id)?'square-icon':'logo-icon'}" src="${gameAsset(id,squareIcons.has(id)?'icon':'logo')}" width="40" height="40" alt="" decoding="async">`;
const coverImage=(game,extra='')=>`<img class="game-cover ${extra}" src="${gameAsset(game.id)}" alt="${escape(game.name)}" width="460" height="215" loading="lazy" decoding="async">`;
const tg=window.Telegram?.WebApp;
const insideTelegram=!!tg && tg.platform!=='unknown' && !!tg.platform;
function haptic(){try{if(insideTelegram)tg.HapticFeedback?.selectionChanged()}catch{}}
function syncBackButton(){try{if(insideTelegram){if(document.querySelector('dialog[open]'))tg.BackButton?.show();else tg.BackButton?.hide()}}catch{}}
function initTelegram(){if(!insideTelegram)return;try{tg.ready();tg.expand();tg.setHeaderColor?.('#080f1c');tg.setBackgroundColor?.('#080f1c');tg.BackButton?.onClick(()=>{const open=[...document.querySelectorAll('dialog[open]')].pop();open?.close()});syncBackButton()}catch{}}
function renderCurrency(){document.querySelectorAll('[data-currency]').forEach(el=>{el.setAttribute('aria-pressed',String(el.dataset.currency===state.currency));el.disabled=state.checking});$('filter-currency').textContent=state.currency==='UAH'?'₴':'$';document.querySelector('.currency-label').textContent=`${state.currency} / ${alternate()}`}
function selectCurrency(currency){if(!['UAH','USD'].includes(currency)||state.checking||currency===state.currency)return;
 state.currency=currency;state.order=null;state.key=null;try{localStorage.setItem('legit-currency',currency)}catch{}
 const hadPrice=!!($('min').value||$('max').value);$('min').value='';$('max').value='';delete state.filters.pmin;delete state.filters.pmax;
 renderCurrency();renderCart();if(state.items.length)renderProducts();loadListings();haptic();if(hadPrice)toast(t('currencyChanged'));
}
function gameInfo(id){return state.config?.games.find(g=>g.id===id)||state.config?.games.find(g=>g.id===state.game)||{id:'cs2',short:'STEAM',color:'#1a9fff',name:'Steam'}}
function color(game){return /^#[a-f\d]{6}$/i.test(game.color)?game.color:'#1a9fff'}
async function api(path,options={}){
 const controller = options.signal ? null : new AbortController();
 const timer = controller ? setTimeout(()=>controller.abort(),65000) : null;
 try{
  const response=await fetch(`/api/${path}`,{...options,signal:options.signal||controller.signal,headers:{'Accept':'application/json',...(options.headers||{})}});
  let data;try{data=await response.json()}catch{throw {error:'connection'}}
  if(!response.ok)throw data;
  return data;
 }catch(error){if(error.name==='AbortError')throw error;throw error.error?error:{error:'connection'}}finally{clearTimeout(timer)}
}
function errorText(error){return t(error?.error||'connection')}
function emptyState(title,hint,retry=false){return `<div class="empty-state"><div class="empty-icon">${icon('layers')}</div><h3>${escape(title)}</h3><p>${escape(hint)}</p>${retry?`<button class="button secondary" data-action="retry">${escape(t('retry'))}</button>`:''}</div>`}
function renderGames(){
 $('game-grid').innerHTML=state.config.games.map(g=>`<button class="game-tile ${g.id===state.game?'selected':''}" style="--game-color:${color(g)}" data-game="${escape(g.id)}" data-symbol="${escape(g.short)}" aria-pressed="${g.id===state.game}">${coverImage(g,'category-cover')}<span class="game-tile-shade"></span><span class="game-emoji" aria-hidden="true">${emoji(g.id)}</span><span class="game-short">${escape(g.short)}</span><span class="game-name">${escape(g.name)}</span>${g.id===state.game?'<span class="selected-dot">✓</span>':''}</button>`).join('');
 $('game-title').textContent=gameInfo(state.game).name;
}
function factValue(key,value){if(value==null || value==='')return t('unknown');if(['prime','vac'].includes(key)){if(['1','true','yes'].includes(String(value)))return t('yes');if(['0','false','no'].includes(String(value)))return t('no')}return value}
function facts(item,detailed=false){const keys=detailed?Object.keys(item.facts||{}):['level','games','country'];return `<div class="facts">${keys.map(k=>`<div class="fact"><small>${escape(t(k))}</small><strong>${escape(factValue(k,item.facts?.[k]))}</strong></div>`).join('')}</div>`}
function product(item){const g=gameInfo(item.game),added=state.cart.some(x=>x.id===item.id);return `<article class="product" style="--game-color:${color(g)}"><div class="product-banner">${coverImage(g)}<span class="banner-caption">${escape(g.short)}</span><span class="lot-id">#${escape(item.id)}</span></div><div class="product-body"><div class="product-status">${escape(t(state.config.demo?'preview':'available'))}</div><h3>${escape(item.title)}</h3>${facts(item)}<div class="product-bottom">${pair(item)}<button class="button add-button ${added?'is-added':''}" data-action="add" data-id="${item.id}" aria-pressed="${added}">${added?'✓ ':''}${escape(t(added?'added':'add'))}</button></div><button class="product-details" data-action="detail" data-id="${item.id}"><span>${escape(t('details'))}</span>${icon('arrow')}</button></div></article>`}
function renderProducts(){
 $('products').innerHTML=state.items.length?state.items.map(product).join(''):emptyState(t('empty'),t('emptyHint'));
 $('result-count').textContent=`${t('loaded')}: ${state.items.length} ${t('unit')}`;
 $('load-more').hidden=!state.hasNext;
}
function updateAdds(){document.querySelectorAll('[data-action="add"]').forEach(el=>{const added=state.cart.some(x=>x.id===el.dataset.id);el.classList.toggle('is-added',added);el.setAttribute('aria-pressed',String(added));el.textContent=(added?'✓ ':'')+t(added?'added':'add')})}
async function loadListings(append=false){
 state.controller?.abort();const controller=new AbortController();state.controller=controller;
 state.loading=true;$('products').setAttribute('aria-busy','true');$('notice').innerHTML='';$('load-more').disabled=true;$('refresh').disabled=true;
 const page=append?state.page+1:1;
 if(!append){state.items=[];$('result-count').textContent=t('loading');$('products').innerHTML=Array.from({length:6},()=>'<div class="skeleton" aria-hidden="true"></div>').join('');$('load-more').hidden=true}
 const query=new URLSearchParams({game:state.game,page,...state.filters,currency:state.currency});
 const timer=setTimeout(()=>controller.abort('timeout'),35000);
 try{
  const data=await api(`listings?${query}`,{signal:controller.signal});
  if(state.controller!==controller)return;
  state.items=[...new Map([...(append?state.items:[]),...data.items.filter(validItem)].map(x=>[x.id,x])).values()];
  state.page=page;state.hasNext=data.hasNext;renderProducts();
  $('updated').textContent=`· ${t('updated')} ${new Date(data.updatedAt*1000).toLocaleTimeString(lang,{hour:'2-digit',minute:'2-digit'})}`;
 }catch(error){
  if(state.controller!==controller)return;
  if(controller.signal.aborted && controller.signal.reason!=='timeout')return;
  const message=errorText(error);
  if(append){$('notice').innerHTML=`<div class="error-inline">${escape(message)}</div>`;$('load-more').hidden=false}
  else{$('products').innerHTML=emptyState(message,t(error.error==='not_configured'?'setupHint':'emptyHint'),true);$('result-count').textContent='—'}
 }finally{clearTimeout(timer);if(state.controller===controller){state.loading=false;$('products').setAttribute('aria-busy','false');$('load-more').disabled=false;$('refresh').disabled=false}}
}
function addItem(item){if(state.checking)return;if(state.cart.some(x=>x.id===item.id)){openCart();return}if(state.cart.length>=10){toast(t('maxCart'));return}state.cart.push({...item});saveCart();haptic();toast(t('addedToast'))}
function openCart(){renderCart();if(!$('cart-dialog').open)$('cart-dialog').showModal();syncBackButton()}
function renderCart(){
 $('cart-count').textContent=state.cart.length;$('mobile-count').textContent=state.cart.length;$('mobile-total').textContent=totals();$('cart-total').textContent=totals();$('mobile-secondary').textContent='≈ '+totals(alternate());$('cart-total-secondary').textContent='≈ '+totals(alternate());renderCurrency();
 $('cart-items').innerHTML=state.cart.length?state.cart.map(x=>{const g=gameInfo(x.game);return `<div class="cart-row"><div class="cart-thumb" style="--game-color:${color(g)}">${emoji(g.id)}</div><div><h3>${escape(x.title)}</h3><strong>${escape(price(retail(x)))}</strong><small class="secondary-price">≈ ${escape(price(retail(x,alternate()),alternate()))}</small>${x.available===false?`<small class="change-note">${escape(t('sold'))}</small>`:x.changed?`<small class="change-note">${escape(t('changedPrice'))}</small>`:''}</div><button class="icon-button" data-action="remove" data-id="${x.id}" aria-label="${escape(t('remove'))}" ${state.checking?'disabled':''}>×</button></div>`}).join(''):emptyState(t('cartEmpty'),t('cartHint'));
 $('checkout').disabled=!state.cart.length||state.checking||state.cart.some(x=>x.available===false);
 $('checkout').textContent=t(state.checking?'checking':'checkout');$('clear-cart').disabled=!state.cart.length||state.checking;
 if(!state.order)$('checkout-result').innerHTML='';
}
async function openDetail(id){
 state.detailController?.abort();const controller=new AbortController();state.detailController=controller;
 state.detail=null;$('detail-content').innerHTML=`<div class="detail-body"><h2 id="detail-title">${escape(t('loading'))}</h2><div class="skeleton"></div></div>`;
 if(!$('detail-dialog').open)$('detail-dialog').showModal();syncBackButton();
 const timer=setTimeout(()=>controller.abort(),35000);
 try{const data=await api(`items/${id}?currency=${state.currency}`,{signal:controller.signal});if(state.detailController!==controller)return;
 const listed=state.items.find(x=>x.id===id);state.detail={...data.item,game:listed?.game||data.item.game};const item=state.detail,g=gameInfo(item.game);
 $('detail-content').innerHTML=`<div class="product-banner detail-banner" style="--game-color:${color(g)}">${coverImage(g)}<span class="banner-caption">${escape(g.name)}</span></div><div class="detail-body"><div class="eyebrow">${escape(t('item'))} #${escape(item.id)}</div><h2 id="detail-title">${escape(item.title)}</h2><p class="muted">${escape(t(item.available?'available':'unavailable'))}${item.seller?' · '+escape(t('seller'))+': '+escape(item.seller):''}</p>${facts(item,true)}<h3 class="muted">${escape(t('description'))}</h3><div class="description">${escape(item.description==='DEMO'?t('demo'):item.description||t('missingDetails'))}</div><div class="detail-actions">${pair(item)}<button class="button add-button" data-action="add" data-id="${item.id}" ${item.available?'':'disabled'}>${escape(t('add'))}</button></div></div>`;updateAdds();
 }catch(error){if(state.detailController!==controller)return;$('detail-content').innerHTML=`<div class="detail-body"><h2 id="detail-title">${escape(errorText(error))}</h2><button class="button secondary full" data-action="detail" data-id="${id}">${escape(t('retry'))}</button></div>`}finally{clearTimeout(timer)}
}
function requestKey(){return crypto.randomUUID().replaceAll('-','')}
async function checkout(){
 if(state.checking||!state.cart.length)return;
 state.checking=true;state.order=null;state.key ||= requestKey();renderCart();
 try{
  const order=await api('checkout',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':state.key},body:JSON.stringify({currency:state.currency,initData:tg?.initData||'',items:state.cart.map(x=>({id:x.id,priceMinor:retail(x),currency:state.currency}))})});
  state.order=order;
  const botUrl=typeof order.botUrl==='string'&&/^https:\/\/t\.me\/[A-Za-z0-9_]+\?start=order_[A-Za-z0-9_-]+$/.test(order.botUrl)?order.botUrl:null;
  if(!botUrl)throw {error:'checkout_not_configured'};
  $('checkout-result').innerHTML=`<div class="checkout-summary"><h3>✓ ${escape(t('verified'))}</h3><p class="muted">${escape(t('verifiedNote'))}</p><strong class="price">${escape(price(order.totalMinor,order.currency))}</strong><p class="muted">${escape(t('botNote'))}</p><a class="button primary full" data-telegram-link href="${escape(botUrl)}" target="_blank" rel="noopener noreferrer"><img class="telegram-mark" src="/assets/decor/telegram.png" width="22" height="22" alt="">${escape(t('openBot'))} ↗</a></div>`;
  $('checkout-result').scrollIntoView({block:'nearest',behavior:'smooth'});
 }catch(error){
  if(error.error==='cart_changed'){
   for(const conflict of error.conflicts||[]){const item=state.cart.find(x=>x.id===conflict.id);if(!item)continue;if(conflict.reason==='unavailable')item.available=false;else if(validItem(conflict.item))Object.assign(item,conflict.item,{game:item.game,changed:true})}
   saveCart();
  }
  if(['cart_changed','idempotency_conflict','order_expired','invalid_request','mixed_currency','telegram_auth'].includes(error.error))state.key=null;state.order={error:true};$('checkout-result').innerHTML=`<div class="error-inline">${escape(error.error==='cart_changed'?t('changed'):errorText(error))}</div>`;
 }finally{state.checking=false;renderCart()}
}
$('game-grid').addEventListener('click',event=>{const el=event.target.closest('[data-game]');if(!el)return;state.game=el.dataset.game;history.replaceState(null,'',`#${state.game}`);renderGames();loadListings();$('listings').scrollIntoView({block:'start',behavior:'smooth'})});
$('filters').addEventListener('submit',event=>{event.preventDefault();if($('min').value&&$('max').value&&Number($('min').value)>Number($('max').value)){toast(t('invalid_request'));return}state.filters={q:$('search').value.trim(),pmin:$('min').value,pmax:$('max').value,sort:$('sort').value,noVac:$('no-vac').checked?'1':'0'};loadListings()});
$('reset').addEventListener('click',()=>{$('filters').reset();state.filters={};loadListings()});
$('refresh').addEventListener('click',()=>loadListings());$('load-more').addEventListener('click',()=>loadListings(true));
$('open-cart').addEventListener('click',openCart);$('mobile-cart').addEventListener('click',openCart);
$('clear-cart').addEventListener('click',()=>{if(state.checking)return;state.cart=[];saveCart()});
$('checkout').addEventListener('click',checkout);
document.addEventListener('click',event=>{
 const moneyButton=event.target.closest('[data-currency]');if(moneyButton){selectCurrency(moneyButton.dataset.currency);return}
 const botLink=event.target.closest('[data-telegram-link]');if(botLink&&insideTelegram){event.preventDefault();tg.openTelegramLink(botLink.href);return}
 const closer=event.target.closest('[data-close]');if(closer){$(closer.dataset.close).close();return}
 const button=event.target.closest('[data-action]');if(!button)return;const id=button.dataset.id;
 if(button.dataset.action==='retry'){if(state.config)loadListings();else boot()}
 if(button.dataset.action==='detail')openDetail(id);
 if(button.dataset.action==='add'){const item=state.detail?.id===id?state.detail:state.items.find(x=>x.id===id);if(item?.available){if($('detail-dialog').open && state.cart.some(x=>x.id===id))$('detail-dialog').close();addItem(item)}}
 if(button.dataset.action==='remove'&&!state.checking){state.cart=state.cart.filter(x=>x.id!==id);saveCart();toast(t('removedToast'))}
});
for(const dialog of document.querySelectorAll('dialog')){dialog.addEventListener('close',syncBackButton);dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close()}})}
$('detail-dialog').addEventListener('close',()=>{state.detailController?.abort();state.detailController=null});
window.addEventListener('storage',event=>{if(event.key===storageKey()&&!state.checking){loadCart();state.order=null;state.key=null;renderCart();updateAdds()}});
async function boot(){try{
 state.config=await api('config');if(!Array.isArray(state.config.games))throw {error:'connection'};
 const hash=location.hash.slice(1);if(state.config.games.some(g=>g.id===hash))state.game=hash;
 $('demo-banner').hidden=!state.config.demo;if(state.config.demo)$('source-label').textContent=t('preview');
 try{const saved=localStorage.getItem('legit-currency');if(['UAH','USD'].includes(saved))state.currency=saved}catch{}
 loadCart();renderCart();renderGames();renderCurrency();await loadListings();
 }catch(error){$('products').innerHTML=emptyState(t('connection'),t('setupHint'),true);renderCart()}}
document.addEventListener('error',event=>{if(event.target instanceof HTMLImageElement){event.target.hidden=true;event.target.closest('.product-banner,.game-tile')?.classList.add('image-unavailable')}},true);
initTelegram();
boot();
