import assert from 'node:assert/strict';
import fs from 'node:fs';
import {template,validateDefinition,backtestStrategy,choose} from './dist/strategy-engine.js';
import {StrategyWorkshop,resultReport} from './dist/strategy-workshop.js';
const data=JSON.parse(fs.readFileSync(new URL('./dist/strategy-data.json',import.meta.url)));
const fakeStorage=()=>{const map=new Map();return {getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,v)}};
const storage=fakeStorage(),messages=[];
let renders=0;const studio=new StrategyWorkshop({storage,render:()=>renders++,toast:m=>messages.push(m)});
assert.equal(studio.items.length,0);studio.save();assert.equal(studio.items.length,1);
const id=studio.id;const reloaded=new StrategyWorkshop({storage});assert.equal(reloaded.items[0].id,id);
studio.duplicate(id);studio.draft.name='Second strategy';studio.save();assert.equal(studio.items.length,2);
studio.edit(id);assert.equal(studio.definition().name,'My adaptive strategy');
const before=JSON.stringify(studio.items);
assert.throws(()=>studio.importText(JSON.stringify([template('range'),{...template(),code:'execute()'}])));
assert.equal(JSON.stringify(studio.items),before,'batch import must be atomic');
studio.importText(JSON.stringify(template('trend')));assert.equal(studio.items.length,3);
const invalid=[{...template(),schema_version:2},{...template(),rules:[]},{...template(),parameters:{risk_pct:20}},
 {...template(),parameters:{max_lots:2.5}},{...template(),parameters:{spread_width:125}},
 {...template(),parameters:{rsi_min:90,rsi_max:20}},{...template(),parameters:{entry_start:'08:00'}},
 {...template(),rules:[...template().rules,template().rules[0]]},JSON.parse('{"schema_version":1,"name":"x","__proto__":{}}')];
for(const def of invalid)assert.throws(()=>validateDefinition(def));
const html=studio.html();assert.ok(html.includes('Strategy Workshop'));assert.ok(html.includes('Run backtest'));assert.ok(html.includes('No trade'));
studio.draft.name='<img src=x onerror=alert(1)>';assert.ok(!studio.html().includes('<img src=x'));
const accountPath=new URL('../paper/intraday_500k.sqlite3',import.meta.url);const savedRoot=fs.existsSync(accountPath)?fs.readFileSync(accountPath):null;
const adaptive=backtestStrategy(template(),data);assert.ok(adaptive.sessions>40);assert.ok(adaptive.trades.length>0);
for(const t of adaptive.trades){assert.equal(t.entry.slice(0,10),t.exit.slice(0,10));assert.ok(t.lots>=1&&t.lots<=5);}
const perDay=new Map();for(const t of adaptive.trades)perDay.set(t.entry.slice(0,10),(perDay.get(t.entry.slice(0,10))||0)+1);assert.ok([...perDay.values()].every(n=>n<=3));
const rejecting=template();rejecting.parameters.rsi_min=100;rejecting.parameters.rsi_max=100;
assert.equal(backtestStrategy(rejecting,data).trades.length,0);
const closed=template();closed.rules=[{market:'range',volatility:'mixed',strategy:'iron_condor'}];
assert.equal(choose(closed,{...data.bars.at(-1),event:true},data.config).strategy,null);
const truncated=structuredClone(data);truncated.bars=truncated.bars.slice(-1);assert.throws(()=>backtestStrategy(template(),truncated),/complete sessions/);
adaptive.baseline=backtestStrategy({...template('trend'),name:'Adaptive baseline'},data);
const report=resultReport(adaptive);assert.equal(report.summary.length,2);assert.ok(report.equity.ADAPTIVE_BASELINE.length>0);
assert.ok(report.trades.every(t=>typeof t.legs==='string'));
if(savedRoot)assert.deepEqual(fs.readFileSync(accountPath),savedRoot,'Research must never write the active account');else assert.ok(!fs.existsSync(accountPath));
const emitter=fs.readFileSync(new URL('./dist/assets/'+fs.readdirSync(new URL('./dist/assets',import.meta.url)).find(n=>n.startsWith('strategy-workshop-')),import.meta.url),'utf8');
assert.match(emitter,/strategy-worker-[a-f0-9]{16}\.js/,'Worker must be versioned with its dependencies');
console.log('Strategy workshop passed durable saves, edits, atomic imports, escaping, validation, model replay, bounded risk, same-day exits, baseline report and active-account isolation checks.');

// Automatic routing is the default. Manual definitions remain an explicit research path.
const autoStore=fakeStorage(),automaticStudio=new StrategyWorkshop({storage:autoStore,fetcher:()=>{throw Error('Routing must not send account requests');}});
assert.equal(automaticStudio.selectionMode,'automatic');
assert.ok(automaticStudio.html().includes('Automatic strategy selection'));
assert.ok(!automaticStudio.html().includes('<select name="rule_'));
assert.ok(!automaticStudio.html().includes('id="studio-template"'));
const form={elements:{name:{value:'Automatic paper research'},description:{value:'Baseline'},...Object.fromEntries(Object.entries(template().parameters).map(([key,v])=>[key,{value:String(v)}]))}};
automaticStudio.capture(form);assert.deepEqual(automaticStudio.definition().rules,template().rules);
const expected={rising:{rich:'bull_put_spread',cheap:'bull_call_spread',mixed:null},falling:{rich:'bear_call_spread',cheap:'bear_put_spread',mixed:null},range:{rich:'iron_condor',cheap:null,mixed:null}};
for(const [market,cases]of Object.entries(expected))for(const [volatility,strategy]of Object.entries(cases)){
 const row={bias_age_minutes:5,bias_close:25000,Close:25000,VIX:15,adx:market==='range'?15:25,ema_fast:market==='falling'?25100:24900,ema_slow:market==='falling'?25200:24800,ivr:volatility==='cheap'?20:40,iv_rv_ratio:volatility==='rich'?1.2:volatility==='cheap'?.9:1.05,realized_vol:.15,vix_observed:true,shock:false,event:false};
 const def=automaticStudio.definition();assert.equal(choose(def,row,data.config).strategy,strategy,market+' / '+volatility);
 assert.equal(choose(def,{...row,event:true},data.config).strategy,null);
 assert.equal(choose(def,{...row,shock:true},data.config).strategy,null);
 assert.equal(choose(def,{...row,vix_observed:false},data.config).strategy,null);
}
automaticStudio.save();const autoId=automaticStudio.id;automaticStudio.edit(autoId);assert.equal(automaticStudio.selectionMode,'automatic');
automaticStudio.action('studio-custom');assert.equal(automaticStudio.selectionMode,'custom');assert.ok(automaticStudio.html().includes('<select name="rule_'));
automaticStudio.draft=template('range');automaticStudio.id=null;automaticStudio.save();const customId=automaticStudio.id;
const restored=new StrategyWorkshop({storage:autoStore});restored.edit(customId);assert.equal(restored.selectionMode,'custom');assert.deepEqual(restored.definition().rules,template('range').rules);
restored.action('studio-auto');assert.deepEqual(restored.definition().rules,template().rules);assert.equal(restored.selectionMode,'automatic');
restored.setContext(JSON.parse(fs.readFileSync(new URL('./dist/data.json',import.meta.url))),{},'snapshot');const status=restored.html();assert.ok(status.includes('SAVED SNAPSHOT'));assert.ok(status.includes('Selected strategy'));assert.ok(status.includes('Active position strategy'));
console.log('Automatic strategy routing passed all nine market/volatility pairs, event/shock/data vetoes, read-only default UI, automatic saves, custom-library compatibility and engine/snapshot visibility.');
