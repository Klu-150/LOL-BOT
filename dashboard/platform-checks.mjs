import assert from 'node:assert/strict';
import fs from 'node:fs';
import {accountSummary,optionGreeks,modelStructure,researchDiagnostics,tradeKey,closedAnalytics} from './dist/platform-model.js';
import {template} from './dist/strategy-engine.js';
import {PlatformStore} from './dist/platform-store.js';
import {TradingTools} from './dist/trading-tools.js';
import {initializeTheme,currentTheme,toggleTheme} from './dist/theme.js';
const data=JSON.parse(fs.readFileSync(new URL('./dist/data.json',import.meta.url)));
const history=JSON.parse(fs.readFileSync(new URL('./dist/strategy-data.json',import.meta.url)));
const meta={config:history.config,expiry_switch:history.expiry_switch};
const memory=()=>{const m=new Map();return {getItem:k=>m.get(k)??null,setItem:(k,v)=>m.set(k,v)}};
const now=Date.parse('2026-11-20T10:05:00+05:30'),bar={timestamp:'2026-11-20T10:00:00+05:30',Close:25000,VIX:15};
const snapshot={paper:{started_at:'account-A',initial_capital_rs:500000,realised_equity_rs:495000,marked_equity_rs:494000,peak_equity:500000,session:'2026-11-20',session_equity:500000,daily_entries:1,trades:[{entry_date:bar.timestamp,exit_date:bar.timestamp,strategy:'bull_put_spread',status:'closed',exit:{net_pnl_rs:-5000}}]},settings:{RISK_PER_TRADE:.02,MAX_LOTS:5},intraday:{bars:[bar]}};
const automation={checked_at:new Date(now).toISOString(),enabled:true,state:'observing'};
const s=accountSummary(snapshot,automation,'cloud',now);
assert.equal(s.daily_loss_budget,15000);assert.equal(s.daily_remaining,10000);assert.equal(s.per_entry_budget,9900);assert.equal(s.today_net,-5000);assert.ok(Math.abs(s.drawdown_percent-1.2)<1e-8);assert.equal(s.fresh,true);
assert.equal(accountSummary(snapshot,automation,'snapshot',now).fresh,false);
assert.equal(accountSummary(snapshot,automation,'cloud',now+20*60000).fresh,false);
assert.equal(accountSummary({},automation,'snapshot',now).per_entry_budget,null);
const params={spot:25000,iv_percent:16,lots:1,width:100,strategy:'bull_put_spread',timestamp:bar.timestamp,expiry_day:'2026-11-24'};
for(const strategy of ['bull_put_spread','bear_call_spread','bull_call_spread','bear_put_spread','iron_condor']){
 const m=modelStructure({...params,strategy},meta);
 assert.ok(Number.isFinite(m.greeks.delta));assert.ok(m.max_loss>0);assert.ok(m.max_loss<100*65+1500);
 assert.equal(m.chain.length,11);assert.equal(m.scenarios.length,7);
 assert.ok(m.break_evens.length>=1);assert.ok(m.points.every(([,p])=>p>=-m.max_loss-1e-7&&p<=m.max_profit+1e-7));
 for(const be of m.break_evens){const legs=m.quote.legs;const intrinsic=legs.reduce((v,l)=>v+l.qty*Math.max(0,l.cp==='C'?be-l.K:l.K-be),0);assert.ok(Math.abs((intrinsic-m.quote.entry_net_pts)*65-m.entry_fees-m.closing_fees)<1e-6);}
 const twice=modelStructure({...params,strategy,lots:2},meta);assert.ok(Math.abs(twice.greeks.delta-2*m.greeks.delta)<1e-7);assert.ok(Math.abs(twice.max_loss-2*m.max_loss)<1e-7);
}
assert.throws(()=>modelStructure({...params,lots:6},meta));assert.throws(()=>modelStructure({...params,expiry_day:'2026-11-19'},meta));assert.throws(()=>modelStructure({...params,strategy:'naked_call'},meta));
const c={...meta.config,SKEW_SLOPE:0,SKEW_CURVE:0}; // Sensitivities remain finite for near-expiry and deep wings.
for(const T of [1/365,.1])for(const cp of ['C','P']){const g=optionGreeks(25000,25000,T,.16,cp,c);assert.ok(Object.values(g).every(Number.isFinite));assert.ok(g.vega>=0);assert.ok(g.gamma>=-1e-5);}
const store=new PlatformStore(memory());
const alert=store.addAlert({label:'Price level',type:'price_above',threshold:24900});
assert.equal(store.observe(snapshot,automation,'snapshot',now).length,0);
assert.equal(store.observe(snapshot,automation,'cloud',now).length,1);
assert.equal(store.observe(snapshot,automation,'cloud',now).length,0);
const below=structuredClone(snapshot);below.intraday.bars[0].Close=24000;
store.observe(below,automation,'cloud',now+20*60000);assert.equal(store.observe(snapshot,automation,'cloud',now).length,0,'stale prices must not rearm');
store.observe(below,automation,'cloud',now);assert.equal(store.observe(snapshot,automation,'cloud',now).length,1);
store.toggle(alert.id);assert.equal(store.observe(snapshot,automation,'cloud',now).length,0);
store.remove(alert.id);assert.equal(store.data.alerts.length,0);
assert.throws(()=>store.addAlert({label:'zero',type:'drawdown',threshold:0}));assert.throws(()=>store.addAlert({label:'bad',type:'x',threshold:4}));
store.addAlert({label:'Health',type:'engine',threshold:''});assert.equal(store.observe(snapshot,automation,'cloud-disconnected',now).length,1);
store.addAlert({label:'Drawdown',type:'drawdown',threshold:1});assert.equal(store.observe(snapshot,automation,'cloud',now).length,1);
store.addAlert({label:'Day loss',type:'daily_loss',threshold:1});assert.equal(store.observe(snapshot,automation,'cloud',now).length,1);
store.acknowledge();assert.equal(store.unread(),0);
const t=snapshot.paper.trades[0];store.saveNote(snapshot.paper,t,{text:'<script>alert(1)</script>',tags:'lesson'});
assert.equal(store.note(snapshot.paper,t).tags,'lesson');assert.notEqual(tradeKey(snapshot.paper,t),tradeKey({...snapshot.paper,started_at:'account-B'},t));
const exported=JSON.stringify(store.exportNotes()),copy=new PlatformStore(memory());copy.importNotes(exported);assert.equal(copy.note(snapshot.paper,t).tags,'lesson');
const notes=JSON.stringify(copy.data.notes);assert.throws(()=>copy.importNotes(JSON.stringify({schema_version:1,type:'trading_notes',notes:{'v1:bad':{text:42,tags:''}}})));assert.equal(JSON.stringify(copy.data.notes),notes);
const quota=new PlatformStore({getItem:()=>null,setItem:()=>{throw Error('Quota');}});assert.throws(()=>quota.saveNote(snapshot.paper,t,{text:'x',tags:''}));assert.deepEqual(quota.data.notes,{});
let paused=0;const ui=new TradingTools({storage:memory(),pause:()=>paused++});ui.setContext(data,{},'snapshot',false);ui.meta=meta;
for(const html of [ui.desk(),ui.options(),ui.review()]){assert.ok(!html.includes('NaN'));assert.ok(!html.includes('undefined'));assert.ok(!html.includes('Invalid Date'));}
await assert.rejects(ui.action('tools-pause'));assert.equal(paused,0);
ui.setContext(snapshot,automation,'cloud',false);ui.store=copy;ui.month='2026-11';assert.ok(ui.review().includes('&lt;script&gt;'));assert.ok(!ui.review().includes('<script>'));
const attrs=new Map(),storage=memory(),element={setAttribute:(k,v)=>attrs.set(k,v),getAttribute:k=>attrs.get(k)};const doc={documentElement:element,querySelector:()=>({setAttribute:()=>{}})};
assert.equal(initializeTheme(doc,storage),'light');toggleTheme(doc,storage);assert.equal(currentTheme(doc),'dark');assert.equal(initializeTheme(doc,storage),'dark');
const original=JSON.stringify(history.config),diag=researchDiagnostics(template(),history);assert.equal(JSON.stringify(history.config),original);assert.equal(diag.available,true);assert.ok(diag.training.sessions>diag.testing.sessions);assert.ok(diag.stress.trades>0);
assert.equal(closedAnalytics([]).win_rate,null);
const many=Array.from({length:200000},(_,i)=>({exit:{net_pnl_rs:i%2?1:-1}}));const large=closedAnalytics(many);assert.equal(large.count,200000);assert.equal(large.net,0);assert.equal(large.best,1);assert.equal(large.worst,-1);
console.log('Platform checks passed risk math, payoff extrema and break-evens, Greek aggregation, stale-data alerts, storage isolation, import validation, permissions, page escaping, theme persistence and chronological/stress diagnostics.');

ui.setContext(snapshot,automation,'cloud',false,{ready:false,version:'1.2.0',alerts:['disk_space_low'],backup:{state:'ok',at:'2026-11-22T10:00:00Z'},storage_free_bytes:500000000,execution_workers:1});
assert.ok(ui.desk().includes('Server health & recovery'));assert.ok(ui.desk().includes('Disk space low'));assert.ok(ui.desk().includes('1.2.0'));
ui.setContext(snapshot,automation,'snapshot',false,{version:'SHOULD-NOT-BE-LIVE'});assert.ok(!ui.desk().includes('SHOULD-NOT-BE-LIVE'));

ui.setContext(snapshot,automation,'cloud',false,{ready:true,version:'1.2.1',alerts:[],backup:{state:'ok'},offhost_backup:{state:'ok',off_host:true,last_success_at:'2026-11-23T12:00:00Z',restore_verified:true}});
assert.ok(ui.desk().includes('Off-server recovery'));
assert.ok(ui.desk().includes('download and isolated database-restore check'));
ui.setContext(snapshot,automation,'cloud',false,{ready:false,alerts:['offhost_backup_stale'],backup:{state:'ok'},offhost_backup:{state:'stale',off_host:false}});
assert.ok(ui.desk().includes('Off-server recovery is not currently confirmed'));
assert.ok(!ui.desk().includes('latest off-server copy passed'));
