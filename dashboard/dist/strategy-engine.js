// Research-only simulator. It has no network, broker, order or active-account API.
export const markets=['rising','falling','range'];
export const volatilities=['rich','cheap','mixed'];
export const structures=['bull_put_spread','bear_call_spread','bull_call_spread','bear_put_spread','iron_condor'];
export const defaults={adx_range:20,min_iv_rank:30,min_iv_rv_ratio:1.1,max_cheap_iv_rv_ratio:1,spread_width:100,risk_pct:2,max_lots:5,rsi_min:0,rsi_max:100,entry_start:'09:45',entry_end:'14:30'};
const bounds={adx_range:[10,40],min_iv_rank:[0,100],min_iv_rv_ratio:[.5,3],max_cheap_iv_rv_ratio:[.1,2],spread_width:[50,500],risk_pct:[.1,2],max_lots:[1,5],rsi_min:[0,100],rsi_max:[0,100]};
export function template(kind='adaptive'){
 const rules=[['rising','rich','bull_put_spread'],['rising','cheap','bull_call_spread'],['falling','rich','bear_call_spread'],['falling','cheap','bear_put_spread'],['range','rich','iron_condor']];
 return {schema_version:1,name:kind==='range'?'My range premium strategy':kind==='trend'?'My trend strategy':'My adaptive strategy',description:'Research draft. Test before considering any paper deployment.',parameters:{...defaults},rules:rules.filter(r=>kind==='range'?r[0]==='range':kind==='trend'?r[0]!=='range':true).map(([market,volatility,strategy])=>({market,volatility,strategy}))};
}
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
export function validateDefinition(value){
 if(!object(value)||Object.keys(value).some(k=>!['schema_version','name','description','parameters','rules'].includes(k))||value.schema_version!==1)throw Error('Import a version 1 strategy definition with rules, not executable code or a results report.');
 if(typeof value.name!=='string'||!value.name.trim()||value.name.trim().length>80||typeof(value.description??'')!=='string'||(value.description??'').length>600)throw Error('Use a name of 1–80 characters and a description up to 600.');
 if(value.parameters!==undefined&&!object(value.parameters))throw Error('Parameters must be an object.');
 const p={...defaults,...value.parameters};
 if(Object.keys(p).some(k=>!Object.hasOwn(defaults,k)))throw Error('Unknown strategy parameter.');
 for(const [key,[low,high]]of Object.entries(bounds))if(!Number.isFinite(p[key])||p[key]<low||p[key]>high)throw Error(`${key.replaceAll('_',' ')} must be between ${low} and ${high}.`);
 if(!Number.isInteger(p.max_lots)||p.spread_width%50)throw Error('Use whole lots and 50-point spread increments.');
 if(p.rsi_min>p.rsi_max||p.max_cheap_iv_rv_ratio>p.min_iv_rv_ratio)throw Error('Check RSI bounds and cheap/rich IV-to-RV thresholds.');
 for(const key of ['entry_start','entry_end'])if(typeof p[key]!=='string'||!/^\d\d:\d\d$/.test(p[key])||p[key]<'09:45'||p[key]>'14:30'||+p[key].slice(3)>=60||+p[key].slice(3)%5)throw Error('Choose 5-minute entry times between 09:45 and 14:30 IST.');
 if(p.entry_start>p.entry_end)throw Error('Entry start must precede entry end.');
 if(!Array.isArray(value.rules)||!value.rules.length||value.rules.length>9)throw Error('Enable at least one routing rule, up to nine.');
 const seen=new Set(),rules=[];
 for(const r of value.rules){
  if(!object(r)||Object.keys(r).sort().join(',')!=='market,strategy,volatility'||!markets.includes(r.market)||!volatilities.includes(r.volatility)||!structures.includes(r.strategy))throw Error('Use supported market conditions and defined-risk option spreads.');
  const key=r.market+':'+r.volatility;if(seen.has(key))throw Error('Each market and volatility pair can have only one rule.');seen.add(key);
  rules.push({market:r.market,volatility:r.volatility,strategy:r.strategy});
 }
 return {schema_version:1,name:value.name.trim(),description:value.description??'',parameters:p,rules};
}
const finite=Number.isFinite;
export function choose(definition,row,c){
 const p=definition.parameters;
 if(!finite(row.bias_age_minutes)||row.bias_age_minutes>20)return {strategy:null,reason:'missing_completed_15m_bias'};
 const close=finite(row.bias_close)?row.bias_close:row.Close;
 if(![close,row.VIX,row.ivr,row.adx,row.ema_fast,row.ema_slow,row.iv_rv_ratio,row.realized_vol].every(finite))return {strategy:null,reason:'insufficient_features'};
 if(close<=0||row.VIX<=0)return {strategy:null,reason:'invalid_market_data'};
 if(!row.vix_observed)return {strategy:null,reason:'missing_same_day_vix'};
 if(row.shock||row.VIX>=c.VIX_SHOCK)return {strategy:null,reason:'volatility_shock'};
 if(row.event)return {strategy:null,reason:'scheduled_event'};
 const market=row.adx<p.adx_range?'range':close>row.ema_fast&&row.ema_fast>row.ema_slow?'rising':close<row.ema_fast&&row.ema_fast<row.ema_slow?'falling':'unclear';
 const volatility=row.ivr>=p.min_iv_rank&&row.iv_rv_ratio>=p.min_iv_rv_ratio?'rich':row.ivr<p.min_iv_rank&&row.iv_rv_ratio<=p.max_cheap_iv_rv_ratio?'cheap':'mixed';
 if((p.rsi_min>0||p.rsi_max<100)&&(!finite(row.rsi)||row.rsi<p.rsi_min||row.rsi>p.rsi_max))return {strategy:null,market,volatility,reason:'rsi_filter'};
 const rule=definition.rules.find(r=>r.market===market&&r.volatility===volatility);
 return {strategy:rule?.strategy||null,market,volatility,reason:rule?'custom_rule':'no_custom_rule'};
}
function cdf(x){
 const a=Math.abs(x);if(a>9)return x>0?1:0;
 let term=a,sum=a;
 for(let n=1;n<500;n++){term*=a*a/(2*n+1);sum+=term;if(term<1e-16*Math.max(sum,1))break;}
 const v=Math.min(1,.5+Math.exp(-a*a/2)*sum/Math.sqrt(2*Math.PI));return x<0?1-v:v;
}
export function optionValue(S,K,T,iv,cp,c,delta=false){
 if(T<=0||iv<=0)return delta?(cp==='C'?(S>K?1:0):(S<K?-1:0)):Math.max(0,cp==='C'?S-K:K-S);
 let z=Math.max(-4,Math.min(4,Math.log(K/S)/(iv*Math.sqrt(T))));
 const sigma=Math.max(.5*iv,iv*(1-c.SKEW_SLOPE*z+c.SKEW_CURVE*z*z));
 const d1=(Math.log(S/K)+(c.RISK_FREE-c.DIV_YIELD+.5*sigma*sigma)*T)/(sigma*Math.sqrt(T)),d2=d1-sigma*Math.sqrt(T);
 if(delta)return cp==='C'?Math.exp(-c.DIV_YIELD*T)*cdf(d1):-Math.exp(-c.DIV_YIELD*T)*cdf(-d1);
 return cp==='C'?S*Math.exp(-c.DIV_YIELD*T)*cdf(d1)-K*Math.exp(-c.RISK_FREE*T)*cdf(d2):K*Math.exp(-c.RISK_FREE*T)*cdf(-d2)-S*Math.exp(-c.DIV_YIELD*T)*cdf(-d1);
}
function roundEven(x){const f=Math.floor(x);return x-f===.5?(f%2?f+1:f):Math.round(x);}
function shortStrike(S,T,iv,cp,target,c){
 const atm=roundEven(S/c.STRIKE_STEP)*c.STRIKE_STEP;let best=atm,error=9.9;
 for(let i=0;i<80;i++){const k=atm+(cp==='C'?1:-1)*i*c.STRIKE_STEP,d=Math.abs(optionValue(S,k,T,iv,cp,c,true)),e=Math.abs(d-target);if(e<error){best=k;error=e;}if(d<target-.05)break;}
 return best;
}
const slip=(v,c)=>c.SLIPPAGE_FIXED+c.SLIPPAGE_PCT*v;
function charges(fill,side,c){const turnover=fill*c.LOT_SIZE,txn=c.EXCHANGE_TXN*turnover,sebi=c.SEBI_FEE*turnover;return c.BROKERAGE_PER_ORDER+txn+sebi+c.GST*(c.BROKERAGE_PER_ORDER+txn+sebi)+(side==='sell'?c.STT_SELL_PREMIUM*turnover:c.STAMP_BUY*turnover);}
export function expiry(timestamp,switchDate){
 const day=timestamp.slice(0,10),date=new Date(day+'T00:00:00Z'),target=day<switchDate?4:2;
 date.setUTCDate(date.getUTCDate()+(target-date.getUTCDay()+7)%7);return date.toISOString().slice(0,10)+'T15:30:00+05:30';
}
const years=(end,start)=>Math.max((Date.parse(end)-Date.parse(start))/1000,60)/(365*86400);
export function quote(name,row,ts,p,c,switchDate,customExpiry=null){
 const expiryTime=customExpiry||expiry(ts,switchDate);
 const S=row.Close,T=years(expiryTime,ts),iv=row.VIX/100,w=p.spread_width,atm=roundEven(S/c.STRIKE_STEP)*c.STRIKE_STEP;
 let legs;
 const leg=(cp,K,qty)=>({cp,K,qty,expiry:'front'});
 if(name==='bull_call_spread')legs=[leg('C',atm,1),leg('C',atm+w,-1)];
 else if(name==='bear_put_spread')legs=[leg('P',atm,1),leg('P',atm-w,-1)];
 else if(name==='bull_put_spread'){const k=shortStrike(S,T,iv,'P',c.CREDIT_SHORT_DELTA,c);legs=[leg('P',k,-1),leg('P',k-w,1)];}
 else if(name==='bear_call_spread'){const k=shortStrike(S,T,iv,'C',c.CREDIT_SHORT_DELTA,c);legs=[leg('C',k,-1),leg('C',k+w,1)];}
 else {const kp=shortStrike(S,T,iv,'P',c.CONDOR_SHORT_DELTA,c),kc=shortStrike(S,T,iv,'C',c.CONDOR_SHORT_DELTA,c);legs=[leg('P',kp,-1),leg('P',kp-w,1),leg('C',kc,-1),leg('C',kc+w,1)];}
 let fees=0,reserve=0,net=0;const fills=[];
 for(const l of legs){const mid=optionValue(S,l.K,T,iv,l.cp,c),fill=l.qty>0?mid+slip(mid,c):Math.max(.05,mid-slip(mid,c));fills.push(fill);fees+=charges(fill,l.qty>0?'buy':'sell',c);reserve+=charges(mid,l.qty>0?'sell':'buy',c)+slip(mid,c)*c.LOT_SIZE;net+=l.qty*fill;}
 const debit=['bull_call_spread','bear_put_spread'].includes(name),loss=(debit?net:w+net)*c.LOT_SIZE,costReserve=fees+reserve+c.RISK_COST_BUFFER_RS;
 const risk=loss+costReserve;
 const valid=debit?net>0&&net<w&&((w-net)*c.LOT_SIZE-costReserve)/risk>=c.MIN_DEBIT_REWARD_RISK:-net>0&&-net<w&&-net/w>=c.MIN_CREDIT_WIDTH_RATIO;
 return {legs,fills,entry_net_pts:net,entry_charges_rs:fees,cost_reserve_rs:costReserve,payoff_max_loss_rs:loss,risk_estimate_rs:risk,valid,expiry:expiryTime};
}
function mark(pos,row,ts,c){
 if(!finite(row.VIX)||row.VIX<=0)throw Error('An open research position has no usable VIX observation. No exit was invented.');
 const T=years(pos.expiry,ts);let pnl=0,fees=0;const fills=[];
 pos.legs.forEach((l,i)=>{const mid=optionValue(row.Close,l.K,T,row.VIX/100,l.cp,c),fill=l.qty>0?Math.max(0,mid-slip(mid,c)):mid+slip(mid,c);fees+=charges(fill,l.qty>0?'sell':'buy',c);pnl+=l.qty*(fill-pos.fills[i]);fills.push(fill);});
 return {pnl_pts:pnl,gross_rs:pnl*c.LOT_SIZE*pos.lots,exit_charges_rs:fees*pos.lots,exit_fills:fills,net_pnl_rs:(pnl*c.LOT_SIZE-fees-pos.entry_charges_rs)*pos.lots};
}
export function backtestStrategy(input,dataset,{from='',to=''}={}){
 const definition=validateDefinition(input),p=definition.parameters,c=dataset.config;
 if(dataset.schema_version!==1||!Array.isArray(dataset.bars)||!dataset.bars.length||dataset.bars.length>30000)throw Error('A supported historical research dataset is required.');
 const days=new Map();let previous=-Infinity;
 for(const row of dataset.bars){const stamp=Date.parse(row.timestamp);if(!finite(stamp)||stamp<=previous)throw Error('Research bars must be chronological and unique.');previous=stamp;const day=row.timestamp.slice(0,10);if(from&&day<from||to&&day>to)continue;if(!days.has(day))days.set(day,[]);days.get(day).push(row);}
 let equity=500000,peak=equity,halted=false,lastExit=null,position=null,drawdown=0,sessions=0;const trades=[],events=[],curve=[],incomplete=[];
 for(const [day,bars]of days){
  if(bars[0].timestamp.slice(11,16)>p.entry_start||bars.at(-1).timestamp.slice(11,16)<c.INTRADAY_EXIT_TIME){incomplete.push(day);continue;}
  sessions++;const sessionEquity=equity;let entries=0;
  for(const row of bars){
   const ts=row.timestamp,time=ts.slice(11,16),pick=choose(definition,row,c);let reason=pick.reason,action='skip';
   if(position){
    const value=mark(position,row,ts,c),credit=-position.entry_net_pts,debit=position.entry_net_pts,isDebit=['bull_call_spread','bear_put_spread'].includes(position.strategy);
    reason=time>=c.INTRADAY_EXIT_TIME?'session_square_off':isDebit?(value.pnl_pts>=c.DEBIT_TAKE_PROFIT*(p.spread_width-debit)?'take_profit':value.pnl_pts<=-c.DEBIT_STOP*debit?'stop_loss':null):(value.pnl_pts>=c.CREDIT_TAKE_PROFIT*credit?'take_profit':value.pnl_pts<=-c.CREDIT_STOP_MULT*credit?'stop_loss':null);
    const b=finite(row.bias_close)?row.bias_close:row.Close,condition=row.adx<p.adx_range?'range':b>row.ema_fast&&row.ema_fast>row.ema_slow?'rising':b<row.ema_fast&&row.ema_fast<row.ema_slow?'falling':'unclear';
    if(!reason){if(row.VIX>=c.VIX_SHOCK)reason='volatility_shock';else if(position.strategy.startsWith('bull_')&&condition==='falling'||position.strategy.startsWith('bear_')&&condition==='rising')reason='regime_reversal';else if(position.strategy==='iron_condor'&&['rising','falling'].includes(condition)&&row.adx>=c.ADX_TREND)reason='range_breakout';}
    if(reason){equity+=value.gross_rs-value.exit_charges_rs;trades.push({...position,...value,exit:ts,exit_reason:reason,pnl_rs:value.net_pnl_rs/position.lots,charges_rs:value.exit_charges_rs/position.lots+position.entry_charges_rs});position=null;lastExit=ts;action='close';}
    else{reason='position_open';action='hold';}
   }else{
    if(time<p.entry_start||time>p.entry_end)reason='outside_entry_window';
    else if(halted)reason='drawdown_halt';
    else if(entries>=c.INTRADAY_MAX_TRADES)reason='daily_trade_limit';
    else if(lastExit&&(Date.parse(ts)-Date.parse(lastExit))/60000<c.INTRADAY_COOLDOWN_MINUTES)reason='cooldown';
    else if(pick.strategy?.startsWith('bull_')&&!(row.Close>row.trigger_fast&&row.trigger_fast>=row.trigger_slow))reason='waiting_for_5m_bullish_trigger';
    else if(pick.strategy?.startsWith('bear_')&&!(row.Close<row.trigger_fast&&row.trigger_fast<=row.trigger_slow))reason='waiting_for_5m_bearish_trigger';
    else if(pick.strategy){
     const q=quote(pick.strategy,row,ts,p,c,dataset.expiry_switch),remaining=sessionEquity*c.INTRADAY_DAILY_LOSS_LIMIT+equity-sessionEquity;
     const lots=Math.max(0,Math.min(p.max_lots,Math.floor(equity*p.risk_pct/100/q.risk_estimate_rs),Math.floor(remaining/q.risk_estimate_rs)));
     if(!q.valid)reason='entry_quote_filter';else if(!lots)reason='risk_budget';else{position={...q,strategy:pick.strategy,entry:ts,lots,condition:pick.market,volatility:pick.volatility,spot_entry:row.Close,vix_entry:row.VIX};delete position.valid;equity-=q.entry_charges_rs*lots;entries++;action='open';reason='custom_rule';}
    }
   }
   peak=Math.max(peak,equity);drawdown=Math.max(drawdown,peak-equity);halted=halted||equity<=peak*(1-c.MAX_ACCOUNT_DRAWDOWN);events.push({timestamp:ts,action,reason,equity_rs:equity});
  }
  if(position)throw Error('A session has an unresolved position. Restore its missing exit observations before testing.');
  curve.push([day,equity-500000]);
 }
 if(!sessions)throw Error('No complete sessions in this date range.');
 const wins=trades.filter(t=>t.net_pnl_rs>0).length,positive=trades.reduce((s,t)=>s+Math.max(0,t.net_pnl_rs),0),negative=trades.reduce((s,t)=>s+Math.min(0,t.net_pnl_rs),0);
 return {mode:'browser_research',definition,capital_rs:500000,equity_rs:equity,net_pnl_rs:equity-500000,trades,events,curve,sessions,incomplete,drawdown_rs:drawdown,win_rate:trades.length?100*wins/trades.length:null,profit_factor:negative?positive/-negative:null,halted,first_bar:dataset.first_bar,last_bar:dataset.last_bar,source:dataset.source};
}
