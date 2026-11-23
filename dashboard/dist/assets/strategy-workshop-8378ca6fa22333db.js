import {defaults,markets,volatilities,structures,template,validateDefinition,backtestStrategy} from './strategy-engine-251c64dd6c468073.js';
import {runResearch} from './platform-model-f1eba76098ddd6f0.js';
import {executionPanel} from './execution-view-f1b717ac6ba642f9.js';
const KEY='league_strategy_library_v1';
const e=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const human=v=>String(v).replaceAll('_',' ').replace(/^./,s=>s.toUpperCase());
const money=v=>Number.isFinite(v)?new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(v):'—';
const number=v=>Number.isFinite(v)?new Intl.NumberFormat('en-IN',{maximumFractionDigits:1}).format(v):'—';
const uid=()=>globalThis.crypto.randomUUID();
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export function resultReport(result){
 const sid='CUSTOM_RESEARCH',days=new Map(result.curve.map(([d])=>[d,0]));let wins=0,perLot=0,peak=0,dd=0;
 for(const t of result.trades){days.set(t.exit.slice(0,10),(days.get(t.exit.slice(0,10))||0)+t.pnl_rs);perLot+=t.pnl_rs;wins+=t.pnl_rs>0?1:0;}
 let cumulative=0;const equity=[...days].map(([d,pnl])=>{cumulative+=pnl;peak=Math.max(peak,cumulative);dd=Math.min(dd,cumulative-peak);return [d,cumulative];});
 const report={label:result.definition.name,algorithm:'custom_research',timeframe:'intraday',lot_size:65,weeks:result.sessions,period:result.curve[0][0]+' to '+result.curve.at(-1)[0],
  summary:[{strategy:sid,trades:result.trades.length,total_rs:perLot,'win_rate_%':result.trades.length?100*wins/result.trades.length:null,max_drawdown_rs:dd,avg_per_trade_rs:result.trades.length?perLot/result.trades.length:null}],equity:{[sid]:equity},
  trades:result.trades.map(t=>({...t,strategy:sid,structure:t.strategy,legs:t.legs.map(l=>`${l.qty>0?'+':'-'}${l.K}${l.cp}`).join('; ')})),
  account:{initial_capital_rs:500000,ending_equity_rs:result.equity_rs},research_definition:result.definition,research_diagnostics:result.diagnostics||null,
  assumptions:['Browser research simulation; historical underlying bars and modelled options fills.','Same-bar model fills are optimistic; no actual option-chain quotes or broker margin.','Equity comparison is per lot; the separate research account starts at ₹5,00,000.','Adding this report does not activate the strategy or change the cloud paper account.']};
 if(result.baseline){const base=resultReport(result.baseline),key='ADAPTIVE_BASELINE';report.summary.push({...base.summary[0],strategy:key});report.equity[key]=base.equity.CUSTOM_RESEARCH;report.trades.push(...base.trades.map(t=>({...t,strategy:key})));}
 return report;
}
export class StrategyWorkshop{
 constructor({render=()=>{},toast=()=>{},download=()=>{},compare=()=>{},storage,fetcher=(...a)=>fetch(...a)}={}){
  this.render=render;this.toast=toast;this.download=download;this.compare=compare;this.fetcher=fetcher;
  try{this.storage=storage===undefined?globalThis.localStorage:storage;}catch{this.storage=null;}
  this.selectionMode='automatic';this.liveContext=null;this.items=[];this.issue='';this.draft=template();this.id=null;this.result=null;this.results=[];this.running=false;this.range={from:'',to:''};this.dataset=null;
  try{const raw=this.storage?.getItem(KEY);if(raw){const parsed=JSON.parse(raw);if(parsed.version!==1||!Array.isArray(parsed.items)||parsed.items.length>50)throw Error();this.items=parsed.items.map(r=>{if(typeof r.id!=='string'||!/^[a-zA-Z0-9-]{8,80}$/.test(r.id))throw Error();return {id:r.id,revision:Number.isInteger(r.revision)?r.revision:1,definition:validateDefinition(r.definition),updated_at:String(r.updated_at||''),last_test:r.last_test||null};});}}
  catch{this.issue='Saved strategy data could not be read. Existing storage was left intact; export any drafts before clearing browser data.';}
 }
 persist(items){if(!this.storage)throw Error('Device storage is unavailable. Export the strategy JSON to keep it.');this.storage.setItem(KEY,JSON.stringify({version:1,items}));this.items=items;}
 setContext(snapshot,automation,sourceMode){this.liveContext={snapshot,automation,sourceMode};}
 automatic(){this.selectionMode='automatic';this.draft={...this.draft,rules:template().rules};this.result=null;this.render();}
 definition(){return validateDefinition(this.selectionMode==='automatic'?{...this.draft,rules:template().rules}:this.draft);}
 capture(form){
  const p={...this.draft.parameters};for(const key of Object.keys(defaults)){const value=form.elements[key].value;p[key]=key.startsWith('entry_')?value:value===''?'':Number(value);}
  const rules=this.selectionMode==='automatic'?template().rules:[];if(this.selectionMode!=='automatic')for(const market of markets)for(const volatility of volatilities){const strategy=form.elements['rule_'+market+'_'+volatility].value;if(strategy)rules.push({market,volatility,strategy});}
  this.draft={schema_version:1,name:form.elements.name.value,description:form.elements.description.value,parameters:p,rules};
 }
 save(){
  const definition=this.definition(),old=this.items.find(r=>r.id===this.id);if(!old&&this.items.length>=50)throw Error('Keep at most 50 strategies on this device. Export and remove an older draft first.');
  const record={id:old?.id||uid(),revision:old?old.revision+(equal(old.definition,definition)?0:1):1,definition,updated_at:new Date().toISOString(),last_test:old?.last_test||null};
  if(this.result&&equal(this.result.definition,definition))record.last_test={definition,net_pnl_rs:this.result.net_pnl_rs,trades:this.result.trades.length,sessions:this.result.sessions,last_bar:this.result.last_bar};
  const next=old?this.items.map(r=>r.id===old.id?record:r):[record,...this.items];this.persist(next);this.id=record.id;this.draft=definition;this.toast('Strategy saved on this device. Cloud trading is unchanged.');this.render();
 }
 edit(id){const item=this.items.find(r=>r.id===id);if(!item)return;this.selectionMode=equal(item.definition.rules,template().rules)?'automatic':'custom';this.id=id;this.draft=structuredClone(item.definition);this.result=null;this.render();}
 fresh(kind='adaptive'){this.selectionMode=kind==='adaptive'?'automatic':'custom';this.id=null;this.draft=template(kind);this.result=null;this.render();}
 duplicate(id){const item=this.items.find(r=>r.id===id);if(!item)return;this.selectionMode=equal(item.definition.rules,template().rules)?'automatic':'custom';this.id=null;this.draft={...structuredClone(item.definition),name:(item.definition.name+' copy').slice(0,80)};this.result=null;this.render();}
 remove(id){this.persist(this.items.filter(r=>r.id!==id));if(this.id===id){this.selectionMode='automatic';this.id=null;this.result=null;this.draft=template();}this.render();this.toast('Draft removed from this device.');}
 importText(text){
  if(text.length>128*1024)throw Error('Use strategy JSON files smaller than 128 KB.');
  const parsed=JSON.parse(text),definitions=Array.isArray(parsed)?parsed:[parsed];
  if(!definitions.length||definitions.length+this.items.length>50)throw Error('The device library supports up to 50 strategies.');
  const incoming=definitions.map(v=>({id:uid(),revision:1,definition:validateDefinition(v),updated_at:new Date().toISOString(),last_test:null}));
  this.persist([...incoming,...this.items]);this.edit(incoming[0].id);this.toast(`Added ${incoming.length} strategy definition${incoming.length===1?'':'s'}. Nothing was activated.`);
 }
 async loadData(){if(!this.dataset){const response=await this.fetcher('strategy-data.json',{cache:'no-store'});if(!response.ok)throw Error('Historical research data could not be loaded. Reconnect and try again.');this.dataset=await response.json();}return this.dataset;}
 async run(){
  if(this.running)return;const definition=this.definition();if(this.range.from&&this.range.to&&this.range.from>this.range.to)throw Error('Start date must precede end date.');
  this.running=true;this.render();
  try{
   const dataset=await this.loadData(),range={...this.range};
   const result=await new Promise((resolve,reject)=>{
    if(typeof Worker==='undefined'){try{resolve(runResearch(definition,dataset,range));}catch(error){reject(error);}return;}
    const worker=new Worker(new URL('./strategy-worker-a5e6da50ba58ce26.js',import.meta.url),{type:'module'});
    const timer=setTimeout(()=>{worker.terminate();reject(Error('This research test exceeded 45 seconds. Try a shorter date range.'));},45000);
    worker.onmessage=event=>{clearTimeout(timer);worker.terminate();event.data.error?reject(Error(event.data.error)):resolve(event.data.result);};
    worker.onerror=()=>{clearTimeout(timer);worker.terminate();reject(Error('The research worker could not run. Refresh the page and try again.'));};
    worker.postMessage({definition,dataset,range});
   });
   this.result=result;this.results=[result,...this.results].slice(0,5);
   if(this.id&&equal(this.draft,definition))this.save();
   this.toast(`Historical test completed: ${result.trades.length} modelled trades. No live or forward paper orders were placed.`);
  }finally{this.running=false;this.render();}
 }
 exportDefinition(){const definition=this.definition();this.download('strategy-definition.json',JSON.stringify(definition,null,2));}
 action(action,value){
  if(action==='studio-auto')this.automatic();
  if(action==='studio-custom'){this.selectionMode='custom';this.render();}
  if(action==='studio-new')this.fresh();
  if(action==='studio-edit')this.edit(value);
  if(action==='studio-duplicate')this.duplicate(value);
  if(action==='studio-delete'&&globalThis.confirm('Remove this saved draft from this device? Cloud trading is unchanged.'))this.remove(value);
  if(action==='studio-save')this.save();
  if(action==='studio-export')this.exportDefinition();
  if(action==='studio-import')document.querySelector('#workshop-import').click();
  if(action==='studio-backtest')return this.run();
  if(action==='studio-report'&&this.result)this.download('strategy-research-report.json',JSON.stringify(resultReport(this.result),null,2));
  if(action==='studio-compare'&&this.result)this.compare(resultReport(this.result));
 }
 html(){
  const automatic=this.selectionMode==='automatic',d=automatic?{...this.draft,rules:template().rules}:this.draft,p=d.parameters,dirty=this.result&&!equal(this.result.definition,d),option=(v,label,selected)=>`<option value="${e(v)}" ${v===selected?'selected':''}>${e(label)}</option>`;
  const field=(key,label,min,max,step=1)=>`<label>${label}<input name="${key}" type="number" min="${min}" max="${max}" step="${step}" value="${e(p[key])}" required></label>`;
  const curve=this.result?.curve||[];let plot='';if(curve.length){const vals=curve.map(p=>p[1]),lo=Math.min(0,...vals),hi=Math.max(0,...vals),span=hi-lo||1;const points=curve.map((p,i)=>`${20+i/(curve.length-1||1)*660},${145-(p[1]-lo)/span*125}`).join(' ');plot=`<svg class="studio-curve" viewBox="0 0 700 165" role="img" aria-label="Historical research account cumulative profit and loss"><line x1="20" x2="680" y1="${145-(0-lo)/span*125}" y2="${145-(0-lo)/span*125}" stroke="#667b92" stroke-dasharray="4 4"/><polyline points="${points}" fill="none" stroke="#d7b17e" stroke-width="3"/></svg>`;}
  const engine=this.liveContext?executionPanel(this.liveContext.snapshot,this.liveContext.automation,this.liveContext.sourceMode,{e,human,num:number,date:v=>String(v||'Unavailable').replace('T',' ').slice(0,19)+' IST',icon:()=>''}):'';
  return `<div class="strategy-studio"><div class="page-heading"><div><p class="eyebrow">RESEARCH LAB</p><h1>Automatic strategy selection</h1><p class="subheading">The adaptive rules choose a structure from the market condition. No per-trade strategy selection is needed.</p></div><div class="studio-top-actions"><button class="btn" data-action="studio-import">Import strategy</button><button class="btn primary" data-action="studio-new">New strategy</button></div></div>
  <section class="panel studio-auto-intro"><div><span class="eyebrow">CONDITION-BASED ROUTING</span><h2>The bot selects the strategy for each condition.</h2><p>Rising or falling markets use directional spreads; a qualifying range can use an iron condor. Unclear, mixed, event or shock conditions select no trade. Entry, data and risk checks still apply. Existing positions continue through their exit rules; a changed selection does not immediately replace an open position.</p></div><div class="studio-top-actions"><button class="btn primary" data-action="nav" data-value="terminal">Open auto paper terminal</button></div></section>${engine}<div class="studio-notice"><strong>Strategy Workshop · research and device library</strong><p>Definitions are saved in this browser. Export JSON to share or back up a strategy. Saving or testing never changes the active cloud bot.</p></div>${this.issue?`<p class="studio-error" role="alert">${e(this.issue)}</p>`:''}
  <input id="workshop-import" type="file" accept=".json,application/json" hidden>
  <div class="studio-layout"><aside class="panel studio-library"><div class="studio-panel-head"><h2>Your strategies</h2><span class="tag gray">${this.items.length} / 50</span></div>${this.items.length?this.items.map(item=>{const tested=item.last_test&&equal(item.definition,item.last_test.definition);return `<article class="studio-library-card ${this.id===item.id?'chosen':''}"><span class="tag ${tested?'':'gray'}">${tested?'Backtested draft':item.last_test?'Changed since test':'Draft'}</span><h3>${e(item.definition.name)}</h3><p>${item.definition.rules.length} rules · revision ${item.revision}</p>${tested?`<p>${money(item.last_test.net_pnl_rs)} · ${item.last_test.trades} modelled trades</p>`:''}<div class="studio-card-actions"><button class="btn" data-action="studio-edit" data-value="${e(item.id)}">Edit</button><button class="btn" data-action="studio-duplicate" data-value="${e(item.id)}">Copy</button><button class="btn" data-action="studio-delete" data-value="${e(item.id)}" aria-label="Remove ${e(item.definition.name)}">Remove</button></div></article>`;}).join(''):`<div class="studio-empty"><h3>A place for your next idea</h3><p>Automatic routing is ready. Save a research copy or open the terminal to inspect the paper engine.</p></div>`}<p class="studio-muted">Clearing browser data removes this library. Export strategies before changing devices.</p></aside>
  <section class="panel studio-editor"><div class="studio-panel-head"><h2>${automatic?'Automatic research strategy':this.id?'Edit custom research strategy':'Develop a custom research strategy'}</h2>${automatic?'<span class="tag">AUTOMATIC ROUTING</span><button class="btn" type="button" data-action="studio-custom">Advanced: custom rules</button>':`<button class="btn primary" type="button" data-action="studio-auto">Use automatic routing</button><label class="studio-template">Research template<select id="studio-template">${option('','Choose a template','')}${option('adaptive','Adaptive spreads','')}${option('trend','Directional spreads','')}${option('range','Range premium','')}</select></label>`}</div>
  <form id="strategy-builder"><div class="studio-fields"><label>Strategy name<input name="name" maxlength="80" value="${e(d.name)}" required autocomplete="off"></label><label class="studio-wide">Notes<textarea name="description" maxlength="600" rows="2">${e(d.description)}</textarea></label></div>
  <h3>${automatic?'Automatic condition-to-strategy rules':'Custom market conditions and option structures'}</h3>${automatic?'<p class="studio-muted">These rules are applied automatically at each historical bar in research. The engine status above reports the running account separately. Saving this definition does not enable entries or replace the running policy.</p>':''}<p class="studio-muted">Bias uses completed 15-minute observations; entries also require the 5-minute trigger. Unclear bias, scheduled events and volatility shocks remain no-trade conditions.</p>
  <div class="table-scroll"><table class="studio-rule-table"><thead><tr><th>Market</th><th>Volatility</th><th>${automatic?'Automatically selected structure':'Use this strategy'}</th></tr></thead><tbody>${markets.flatMap(market=>volatilities.map(volatility=>{const selected=d.rules.find(r=>r.market===market&&r.volatility===volatility)?.strategy||'';return `<tr><td>${human(market)}</td><td>${human(volatility)}</td><td>${automatic?`<strong>${selected?human(selected):'No trade'}</strong><small class="studio-auto-rule">Selected by condition</small>`:`<select name="rule_${market}_${volatility}" aria-label="Strategy for ${market} market and ${volatility} volatility">${option('','No trade',selected)}${structures.map(s=>option(s,human(s),selected)).join('')}</select>`}</td></tr>`;})).join('')}</tbody></table></div>
  <details class="studio-settings" ${automatic?'':'open'}><summary>${automatic?'Optional research parameters':'Setup and risk parameters'}</summary><div class="studio-fields">${field('adx_range','Range ADX threshold',10,40)}${field('min_iv_rank','Rich IV rank threshold (%)',0,100)}${field('min_iv_rv_ratio','Minimum rich IV / realised volatility',.5,3,.05)}${field('max_cheap_iv_rv_ratio','Maximum cheap IV / realised volatility',.1,2,.05)}${field('rsi_min','Minimum 5-minute RSI',0,100)}${field('rsi_max','Maximum 5-minute RSI',0,100)}${field('spread_width','Spread width (points)',50,500,50)}${field('risk_pct','Research risk per entry (%)',.1,2,.1)}${field('max_lots','Maximum research lots',1,5)}<label>Entry start (IST)<input name="entry_start" type="time" min="09:45" max="14:30" step="300" value="${e(p.entry_start)}" required></label><label>Entry cutoff (IST)<input name="entry_end" type="time" min="09:45" max="14:30" step="300" value="${e(p.entry_end)}" required></label></div><p class="studio-muted">Separate ₹5,00,000 research account · one position · maximum three entries/day · 3% daily risk budget · same-day square-off target 15:15 IST. Credit exits: 50% of premium profit / 2× premium loss. Debit exits: 50% of maximum profit / 50% of debit loss. Quotes, fees and slippage use the published research model.</p></details>
  <div class="studio-editor-actions"><button class="btn primary" type="submit">Save strategy</button><button class="btn" type="button" data-action="studio-export">Export strategy</button></div></form>
  <div class="studio-test-controls"><div><h3>Historical backtest</h3><p class="studio-muted">Runs on this device using observed underlying bars and modelled option fills. It does not place orders. Same-bar fills are optimistic; this is not evidence of a profitable edge.</p></div><div class="studio-date-range"><label>From<input id="studio-from" type="date" value="${e(this.range.from)}"></label><label>To<input id="studio-to" type="date" value="${e(this.range.to)}"></label><button class="btn primary" data-action="studio-backtest" ${this.running?'disabled':''}>${this.running?'Running research…':'Run backtest'}</button></div>${this.dataset?`<p class="studio-muted">Dataset: ${e(this.dataset.first_bar.slice(0,10))} to ${e(this.dataset.last_bar.slice(0,10))} · ${this.dataset.bars.length} completed 5-minute bars. Features include prior warm-up history; this is historical data, not a live option chain.</p>`:'<p class="studio-muted">Historical data loads when you run your first test. Its coverage dates will be shown here.</p>'}</div>
  </section></div>
  ${this.result?`<section class="panel studio-results" aria-live="polite"><div class="studio-panel-head"><div><p class="eyebrow">MODELLED RESEARCH RESULTS</p><h2>${e(this.result.definition.name)}</h2></div><span class="tag ${dirty?'red':''}">${dirty?'Draft changed · rerun to retest':'Completed backtest'}</span></div><div class="studio-metrics">${[['Net P&L',money(this.result.net_pnl_rs)],['Trades',number(this.result.trades.length)],['Win rate',this.result.win_rate==null?'—':number(this.result.win_rate)+'%'],['Maximum drawdown',money(this.result.drawdown_rs)],['Ending equity',money(this.result.equity_rs)],['Complete sessions',number(this.result.sessions)]].map(([k,v])=>`<div><span>${k}</span><strong>${v}</strong></div>`).join('')}</div>${plot}<p class="studio-muted">${this.result.incomplete.length} incomplete sessions excluded. Results describe the tested definition, even if the editor has changed. No active-account fills were created.</p><div class="studio-top-actions"><button class="btn" data-action="studio-compare">Compare this result</button><button class="btn" data-action="studio-report">Export research report</button></div></section>`:''}
  ${this.result?.diagnostics?`<section class="panel studio-results"><div class="studio-panel-head"><h2>Research validation</h2><span class="tag gray">DIAGNOSTIC</span></div><p class="studio-muted">Same rules, separate ₹5,00,000 research accounts. Chronological split and a 2× slippage stress run; no optimization or automatic activation. Once inspected, the later segment is not an untouched holdout.</p>${this.result.diagnostics.available?`<p class="studio-muted">Later segment begins ${e(this.result.diagnostics.split_date)}.</p>`:`<p class="studio-muted">${e(this.result.diagnostics.reason)}</p>`}<div class="table-scroll"><table class="data-table"><thead><tr><th>Segment / scenario</th><th>Sessions</th><th>Trades</th><th>Net account P&L</th><th>Drawdown</th></tr></thead><tbody>${[['Earlier 70%',this.result.diagnostics.training],['Later 30%',this.result.diagnostics.testing],['2× slippage',this.result.diagnostics.stress]].filter(([,r])=>r).map(([label,r])=>`<tr><td>${label}</td><td>${r.sessions}</td><td>${r.trades}</td><td>${money(r.net_pnl_rs)}</td><td>${money(r.drawdown_rs)}</td></tr>`).join('')}</tbody></table></div><p class="studio-muted">Slippage can change which entries pass filters, so trade counts may differ. This does not model real option-chain liquidity or guarantee future performance.</p></section>`:''}
  ${this.results.length>1?`<section class="panel studio-results"><div class="studio-panel-head"><h2>Recent experiments</h2><span class="studio-muted">Last five · this session</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>Tested strategy</th><th>Trades</th><th>Net account P&L</th><th>Drawdown</th></tr></thead><tbody>${this.results.map(r=>`<tr><td>${e(r.definition.name)}</td><td>${r.trades.length}</td><td>${money(r.net_pnl_rs)}</td><td>${money(r.drawdown_rs)}</td></tr>`).join('')}</tbody></table></div></section>`:''}</div>`;
 }
}
