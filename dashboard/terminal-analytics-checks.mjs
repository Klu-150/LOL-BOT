import assert from 'node:assert/strict';
import fs from 'node:fs';
import {scenarioModel,portfolioGreeks,panelOrder,analyticsWorkspace,terminalSafetyBar} from './dist/terminal-analytics.js';
import {optionGreeks} from './dist/platform-model.js';
const meta=JSON.parse(fs.readFileSync(new URL('./dist/platform-config.json',import.meta.url)));
const snapshot={intraday:{latest_bar:'2026-11-16T10:00:00+05:30',candidate:'iron_condor',bars:[{timestamp:'2026-11-16T10:00:00+05:30',Close:25000,VIX:18}]},paper:{available:true,position:null,decisions:[]}};
const original=JSON.stringify(snapshot),base=scenarioModel(snapshot,meta);
assert.equal(base.chain.length,17);
assert.equal(base.chain.filter(r=>r.atm).length,1);
assert.ok(base.chain.every(r=>r.call.price>=0&&r.put.price>=0&&Number.isFinite(r.call.delta)));
const shifted=scenarioModel(snapshot,meta,{proIv:3,proMove:2,proDays:.25});
assert.deepEqual(shifted.model.points,base.model.points,'What-if sliders must preserve the original expiry payoff and entry basis');
assert.notDeepEqual(shifted.t0,base.t0);
assert.equal(shifted.scenarioSpot,25500);
assert.equal(JSON.stringify(snapshot),original,'Analytics must not mutate the paper account');
assert.throws(()=>scenarioModel(snapshot,meta,{proMove:4}));
assert.throws(()=>scenarioModel(snapshot,meta,{proIv:NaN}));
assert.equal(portfolioGreeks(snapshot,meta).flat,true);
assert.equal(portfolioGreeks({...snapshot,paper:{available:false}},meta),null);
assert.equal(portfolioGreeks({...snapshot,paper:{open_trades:1}},meta),null);
const position={expiry:base.model.expiry,lots:2,legs:base.model.quote.legs};
const aggregate=portfolioGreeks({...snapshot,paper:{position}},meta),T=(Date.parse(position.expiry)-Date.parse(snapshot.intraday.latest_bar))/(365*86400000);
for(const key of ['delta','gamma','theta','vega']){
 const expected=position.legs.reduce((n,l)=>n+l.qty*optionGreeks(25000,l.K,T,.18,l.cp,meta.config)[key]*2*meta.config.LOT_SIZE,0);
 assert.ok(Math.abs(aggregate[key]-expected)<1e-9);
}
assert.equal(portfolioGreeks({...snapshot,paper:{position:{...position,expiry:'2020-01-01'}}},meta),null);
assert.deepEqual(panelOrder('["log","chain","payoff","surface"]'),['log','chain','payoff','surface']);
assert.deepEqual(panelOrder('["log","log","payoff","surface"]'),['payoff','chain','surface','log']);
assert.deepEqual(panelOrder('<script>'),['payoff','chain','surface','log']);
const unsafe={...snapshot,paper:{...snapshot.paper,decisions:[{action:'<img onerror=x>',reason:'<script>bad</script>'}]}};
const html=analyticsWorkspace(unsafe,meta,{});
assert.ok(html.includes('&lt;script&gt;bad&lt;/script&gt;'));
assert.ok(!html.includes('<img onerror'));
assert.ok(html.includes('MODEL · NO LIVE QUOTES'));
assert.ok(html.includes('GAMMA EXPOSURE')&&html.includes('Unavailable'));
assert.ok(!html.includes('NaN'));
for(const [mode,allowed] of [['snapshot',true],['cloud-disconnected',true],['cloud',false]]){
 const bar=terminalSafetyBar(snapshot,meta,mode,{enabled:true},allowed);
 assert.match(bar,/data-action="auto-pause" disabled/);
}
assert.match(terminalSafetyBar(snapshot,meta,'cloud',{enabled:true},true),/data-action="auto-pause" >PAUSE ENTRIES/);
assert.match(terminalSafetyBar(snapshot,meta,'cloud',{},true),/class="pro-flatten" disabled/);
console.log('Terminal analytics passed: fixed-basis what-if pricing, actual-position Greeks, unavailable data, mode permissions, escaping and panel persistence validation.');
