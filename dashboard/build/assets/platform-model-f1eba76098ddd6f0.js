import {optionValue,quote,expiry,backtestStrategy,template} from './strategy-engine-251c64dd6c468073.js';
const finite=Number.isFinite;
export function istDay(now=Date.now()){return new Date(now+330*60000).toISOString().slice(0,10);}
export function latestBar(snapshot){return snapshot.intraday?.bars?.at(-1)||null;}
export function tradePnl(trade){return trade.exit?.net_pnl_rs??trade.entry?.net_pnl_rs??null;}
export function tradeKey(paper,trade){return 'v1:'+String(paper.started_at||paper.start_date||'account')+'|'+String(trade.entry_date||trade.entry?.entry||'')+'|'+String(trade.strategy||'');}
export function accountSummary(s,automation={},mode='snapshot',now=Date.now()){
 const p=s.paper||{},settings=s.settings||{},day=istDay(now),equity=p.realised_equity_rs,marked=p.marked_equity_rs??equity,peak=p.peak_equity??p.initial_capital_rs;
 const closed=(p.trades||[]).filter(t=>t.status==='closed'&&finite(tradePnl(t))),today=closed.filter(t=>String(t.exit_date||t.entry?.exit||'').startsWith(day));
 const initial=p.initial_capital_rs,perEntry=finite(equity)?equity*(settings.RISK_PER_TRADE??.02):null;
 const sessionEquity=p.session===day&&finite(p.session_equity)?p.session_equity:equity;
 const dailyLimit=finite(sessionEquity)?sessionEquity*.03:null;
 const remaining=finite(dailyLimit)&&finite(equity)?Math.max(0,dailyLimit+equity-sessionEquity):null;
 const openRisk=p.position&&finite(p.position.risk_estimate_rs)?p.position.risk_estimate_rs*p.position.lots:0;
 const drawdown=finite(peak)&&peak>0&&finite(marked)?Math.max(0,100*(1-marked/peak)):null;
 const threshold=finite(peak)?peak*(1-(settings.MAX_ACCOUNT_DRAWDOWN??.15)):null;
 const connected=['cloud','local'].includes(mode),bar=latestBar(s),stamp=bar?.timestamp||s.intraday?.latest_bar;
 const age=stamp?(now-Date.parse(stamp))/60000:null,heartbeat=automation.checked_at?(now-Date.parse(automation.checked_at))/1000:null;
 const fresh=connected&&finite(age)&&age>=-1&&age<=10&&finite(heartbeat)&&heartbeat>=-5&&heartbeat<=180;
 return {paper:p,day,connected,bar,stamp,bar_age_minutes:age,heartbeat_seconds:heartbeat,fresh,equity,marked,initial,peak,per_entry_budget:perEntry,
  daily_loss_budget:dailyLimit,daily_remaining:remaining,open_risk:openRisk,drawdown_percent:drawdown,halt_equity:threshold,
  closed,today,today_net:today.reduce((n,t)=>n+tradePnl(t),0),unrealised:finite(marked)&&finite(equity)?marked-equity:null,
  daily_entries:p.session===day?(p.daily_entries||0):0,entry_limit:3,max_lots:settings.MAX_LOTS??5,
  total_closed:p.closed_trades??closed.length,total_pnl:p.net_closed_pnl_rs??null,
  history_truncated:!!p.history_window?.has_older_trades};
}
export function closedAnalytics(trades){
 const values=trades.map(tradePnl).filter(finite),wins=values.filter(v=>v>0),losses=values.filter(v=>v<0),sum=a=>a.reduce((s,v)=>s+v,0);
 return {count:values.length,net:sum(values),win_rate:values.length?100*wins.length/values.length:null,average:values.length?sum(values)/values.length:null,
  average_win:wins.length?sum(wins)/wins.length:null,average_loss:losses.length?sum(losses)/losses.length:null,
  profit_factor:losses.length?sum(wins)/-sum(losses):null,best:values.length?values.reduce((a,b)=>Math.max(a,b),-Infinity):null,worst:values.length?values.reduce((a,b)=>Math.min(a,b),Infinity):null};
}
export function dailyTrades(trades){
 const map=new Map();for(const t of trades){const day=String(t.exit_date||t.entry?.exit||'').slice(0,10),pnl=tradePnl(t);if(!/^\d{4}-\d{2}-\d{2}$/.test(day)||!finite(pnl))continue;if(!map.has(day))map.set(day,{day,pnl:0,trades:[]});const row=map.get(day);row.pnl+=pnl;row.trades.push(t);}
 return [...map.values()].sort((a,b)=>a.day.localeCompare(b.day));
}
export function optionGreeks(S,K,T,iv,cp,c){
 const h=Math.max(.01,S*.0001),v=.0001,base=optionValue(S,K,T,iv,cp,c),up=optionValue(S+h,K,T,iv,cp,c),down=optionValue(S-h,K,T,iv,cp,c);
 return {price:base,delta:(up-down)/(2*h),gamma:(up-2*base+down)/(h*h),
  theta:optionValue(S,K,Math.max(0,T-1/365),iv,cp,c)-base,
  vega:(optionValue(S,K,T,iv+v,cp,c)-optionValue(S,K,T,Math.max(.0001,iv-v),cp,c))/(2*v)*.01};
}
function modelCharges(fill,side,c){const turn=fill*c.LOT_SIZE,txn=c.EXCHANGE_TXN*turn,sebi=c.SEBI_FEE*turn;return c.BROKERAGE_PER_ORDER+txn+sebi+c.GST*(c.BROKERAGE_PER_ORDER+txn+sebi)+(side==='sell'?c.STT_SELL_PREMIUM*turn:c.STAMP_BUY*turn);}
export function modelStructure(input,meta){
 const c=meta.config,{spot,iv_percent,lots,width,strategy,timestamp}=input;
 if(!finite(spot)||spot<1000||spot>1e6||!finite(iv_percent)||iv_percent<1||iv_percent>100||!Number.isInteger(lots)||lots<1||lots>5||!finite(width)||width<50||width>500||width%50)throw Error('Use positive model inputs, 1–5 lots and 50–500 point wings in 50-point increments.');
 if(!['bull_call_spread','bear_put_spread','bull_put_spread','bear_call_spread','iron_condor'].includes(strategy))throw Error('Choose a supported defined-risk structure.');
 const baseTime=Date.parse(timestamp);if(!finite(baseTime))throw Error('A timestamped reference price is required.');
 const end=input.expiry_day?input.expiry_day+'T15:30:00+05:30':expiry(timestamp,meta.expiry_switch);
 const seconds=(Date.parse(end)-baseTime)/1000;
 if(!finite(seconds)||seconds<=0||seconds>366*86400)throw Error('Model expiry must be after the reference bar and within one year.');
 const p={spread_width:width},T=Math.max(seconds,60)/(365*86400),row={Close:spot,VIX:iv_percent};
 const q=quote(strategy,row,timestamp,p,c,meta.expiry_switch,end),units=c.LOT_SIZE*lots;
 const legGreeks=q.legs.map(l=>({...l,...optionGreeks(spot,l.K,T,iv_percent/100,l.cp,c)}));
 const greeks=Object.fromEntries(['delta','gamma','theta','vega'].map(k=>[k,legGreeks.reduce((n,l)=>n+l.qty*l[k]*units,0)]));
 const strikes=q.legs.map(l=>l.K),low=Math.max(1,Math.min(...strikes,spot*.97)-width),high=Math.max(...strikes,spot*1.03)+width;
 const closingFees=legGreeks.reduce((n,l)=>n+modelCharges(l.price,l.qty>0?'sell':'buy',c),0)*lots;
 const pnl=S=>{const value=q.legs.reduce((n,l)=>n+l.qty*Math.max(0,l.cp==='C'?S-l.K:l.K-S),0);return (value-q.entry_net_pts)*units-q.entry_charges_rs*lots-closingFees;};
 const points=Array.from({length:161},(_,i)=>[low+i*(high-low)/160,pnl(low+i*(high-low)/160)]),exact=[low,high,...strikes].map(S=>[S,pnl(S)]).sort((a,b)=>a[0]-b[0]);
 const breaks=[];for(let i=1;i<exact.length;i++){const [x0,y0]=exact[i-1],[x1,y1]=exact[i];if(y0===0)breaks.push(x0);if(y0*y1<0)breaks.push(x0+(x1-x0)*(-y0)/(y1-y0));}if(exact.at(-1)[1]===0)breaks.push(exact.at(-1)[0]);
 const atm=Math.round(spot/c.STRIKE_STEP)*c.STRIKE_STEP;
 const chain=Array.from({length:11},(_,i)=>{const K=atm+(i-5)*c.STRIKE_STEP;return {strike:K,call:optionGreeks(spot,K,T,iv_percent/100,'C',c),put:optionGreeks(spot,K,T,iv_percent/100,'P',c)};});
 const scenarios=[-3,-2,-1,0,1,2,3].map(move=>({move,spot:spot*(1+move/100),expiry_pnl:pnl(spot*(1+move/100))}));
 return {quote:q,expiry:end,greeks,legGreeks,points,break_evens:[...new Set(breaks)],max_profit:Math.max(...exact.map(p=>p[1])),max_loss:Math.max(0,-Math.min(...exact.map(p=>p[1]))),
  entry_cash:q.entry_net_pts*units,entry_fees:q.entry_charges_rs*lots,closing_fees:closingFees,risk_reserve:q.risk_estimate_rs*lots,scenarios,chain,lot_size:c.LOT_SIZE};
}
const diagnosticSummary=r=>({net_pnl_rs:r.net_pnl_rs,trades:r.trades.length,sessions:r.sessions,drawdown_rs:r.drawdown_rs,win_rate:r.win_rate});
export function researchDiagnostics(definition,dataset,range={}){
 const groups=new Map();for(const b of dataset.bars){const d=b.timestamp.slice(0,10);if(range.from&&d<range.from||range.to&&d>range.to)continue;if(!groups.has(d))groups.set(d,[]);groups.get(d).push(b);}
 const days=[...groups].filter(([,bars])=>bars[0].timestamp.slice(11,16)<=definition.parameters.entry_start&&bars.at(-1).timestamp.slice(11,16)>=dataset.config.INTRADAY_EXIT_TIME).map(([d])=>d).sort();
 const stressed={...dataset,config:{...dataset.config,SLIPPAGE_FIXED:dataset.config.SLIPPAGE_FIXED*2,SLIPPAGE_PCT:dataset.config.SLIPPAGE_PCT*2}};
 const stress=diagnosticSummary(backtestStrategy(definition,stressed,range));
 if(days.length<10)return {available:false,reason:'Use at least 10 complete sessions for the chronological split.',stress};
 const cut=Math.max(1,Math.min(days.length-1,Math.floor(days.length*.7)));
 return {available:true,split_date:days[cut],training:diagnosticSummary(backtestStrategy(definition,dataset,{from:days[0],to:days[cut-1]})),
  testing:diagnosticSummary(backtestStrategy(definition,dataset,{from:days[cut],to:days.at(-1)})),stress,
  note:'Chronological 70/30 diagnostic. Once inspected, this is not an untouched holdout. No parameter optimization or automatic activation.'};
}
export function runResearch(definition,dataset,range={}){
 const result=backtestStrategy(definition,dataset,range);
 result.baseline=backtestStrategy({...template(),name:'Adaptive baseline'},dataset,range);
 result.diagnostics=researchDiagnostics(result.definition,dataset,range);
 return result;
}
