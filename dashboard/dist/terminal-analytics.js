// League terminal analytics. Pure model calculations; no order or account API.
import {modelStructure,optionGreeks} from './platform-model.js';
import {optionValue,expiry} from './strategy-engine.js';
const finite=Number.isFinite;
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=(v,d=2)=>finite(v)?new Intl.NumberFormat('en-IN',{maximumFractionDigits:d,minimumFractionDigits:d}).format(v):'—';
const rupees=v=>finite(v)?(v<0?'−':'')+'₹'+number(Math.abs(v),0):'—';
export const panelIds=['payoff','chain','surface','log'];
export function panelOrder(raw){
 try{const value=JSON.parse(raw);if(Array.isArray(value)&&value.length===panelIds.length&&new Set(value).size===panelIds.length&&value.every(k=>panelIds.includes(k)))return value;}catch{}
 return [...panelIds];
}
export function portfolioGreeks(snapshot,meta){
 const position=snapshot.paper?.position;
 if(snapshot.paper?.available===false||!position&&snapshot.paper?.open_trades>0)return null;
 if(!position)return {delta:0,gamma:0,theta:0,vega:0,flat:true};
 const bar=snapshot.intraday?.bars?.at(-1),c=meta?.config;
 if(!bar||!c||![bar.Close,bar.VIX,position.lots].every(finite)||bar.Close<=0||bar.VIX<=0||position.lots<=0||!Array.isArray(position.legs)||!position.legs.length)return null;
 const T=(Date.parse(position.expiry)-Date.parse(bar.timestamp))/(365*86400000);
 if(!finite(T)||T<=0)return null;
 const result={delta:0,gamma:0,theta:0,vega:0,flat:false};
 for(const leg of position.legs){
  if(![leg.K,leg.qty].every(finite)||!['C','P'].includes(leg.cp))return null;
  const values=optionGreeks(bar.Close,leg.K,T,bar.VIX/100,leg.cp,c);
  for(const key of ['delta','gamma','theta','vega'])result[key]+=values[key]*leg.qty*position.lots*c.LOT_SIZE;
 }
 return Object.values(result).filter(v=>typeof v==='number').every(finite)?result:null;
}
export function scenarioModel(snapshot,meta,state={}){
 const bar=snapshot.intraday?.bars?.at(-1);
 if(!bar||!meta?.config)return null;
 const shift=Number(state.proIv??0),elapsed=Number(state.proDays??0),move=Number(state.proMove??0);
 if(![shift,elapsed,move].every(finite)||shift < -10||shift>10||elapsed<0||elapsed>7||move < -3||move>3)throw Error('Invalid what-if scenario');
 const input={spot:bar.Close,iv_percent:bar.VIX,lots:1,width:100,strategy:state.proStructure||snapshot.intraday?.candidate||'iron_condor',timestamp:bar.timestamp};
 const model=modelStructure(input,meta),T=(Date.parse(model.expiry)-Date.parse(bar.timestamp))/(365*86400000);
 const remaining=Math.max(0,T-elapsed/365),iv=Math.max(.01,bar.VIX/100+shift/100),c=meta.config;
 const atSpot=S=>{
  const value=model.quote.legs.reduce((n,l)=>n+l.qty*optionValue(S,l.K,remaining,iv,l.cp,c),0);
  return (value-model.quote.entry_net_pts)*c.LOT_SIZE-model.entry_fees-model.closing_fees;
 };
 const t0=model.points.map(([S])=>[S,atSpot(S)]),atm=Math.round(bar.Close/c.STRIKE_STEP)*c.STRIKE_STEP;
 const chain=Array.from({length:17},(_,i)=>{
  const strike=atm+(i-8)*c.STRIKE_STEP;
  return {strike,atm:strike===atm,call:optionGreeks(bar.Close,strike,T,bar.VIX/100,'C',c),put:optionGreeks(bar.Close,strike,T,bar.VIX/100,'P',c)};
 });
 const surface=[1,3,7,14,30].map(days=>({days,points:Array.from({length:13},(_,i)=>{
  const strike=atm+(i-6)*c.STRIKE_STEP,base=bar.VIX/100,z=Math.max(-4,Math.min(4,Math.log(strike/bar.Close)/(base*Math.sqrt(days/365))));
  return {strike,iv:100*Math.max(.5*base,base*(1-c.SKEW_SLOPE*z+c.SKEW_CURVE*z*z))};
 })}));
 return {bar,input,model,t0,chain,surface,move,shift,elapsed,scenarioSpot:bar.Close*(1+move/100),scenarioPnl:atSpot(bar.Close*(1+move/100))};
}
export function payoffSvg(a){
 const W=680,H=240,L=55,R=15,T=18,B=32,points=[...a.model.points,...a.t0],minX=points[0][0],maxX=a.model.points.at(-1)[0];
 const lo=Math.min(0,...points.map(p=>p[1])),hi=Math.max(0,...points.map(p=>p[1])),pad=(hi-lo||1)*.12;
 const x=v=>L+(v-minX)/(maxX-minX)*(W-L-R),y=v=>T+(hi+pad-v)/(hi-lo+2*pad)*(H-T-B);
 const line=ps=>ps.map(([xx,yy],i)=>`${i?'L':'M'}${x(xx).toFixed(2)},${y(yy).toFixed(2)}`).join(' ');
 const grid=Array.from({length:5},(_,i)=>{const v=lo+(hi-lo)*i/4;return `<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" class="pro-gridline"/><text x="${L-8}" y="${y(v)+4}" text-anchor="end">${number(v,0)}</text>`;}).join('');
 return `<svg viewBox="0 0 ${W} ${H}" class="pro-payoff" role="img" aria-label="Model scenario and expiry payoff in rupees per lot"><title>Modelled payoff, one lot. Amber: expiry; blue: scenario mark. Fees are reference estimates.</title>${grid}<line x1="${L}" x2="${W-R}" y1="${y(0)}" y2="${y(0)}" class="pro-zero"/><path d="${line(a.model.points)}" class="pro-expiry-line"/><path d="${line(a.t0)}" class="pro-today-line"/><line x1="${x(a.input.spot)}" x2="${x(a.input.spot)}" y1="${T}" y2="${H-B}" class="pro-reference"/><circle cx="${x(a.scenarioSpot)}" cy="${y(a.scenarioPnl)}" r="4" fill="#65b5ff"/>${[minX,a.input.spot,maxX].map(v=>`<text x="${x(v)}" y="${H-10}" text-anchor="middle">${number(v,0)}</text>`).join('')}</svg>`;
}
function surfaceSvg(a){
 const values=a.surface.flatMap(r=>r.points.map(p=>p.iv)),lo=Math.min(...values),span=Math.max(...values)-lo||1;
 const project=(i,j,iv)=>[60+i*29+j*20,205-j*24-(iv-lo)/span*95];
 const cells=[];
 for(let j=3;j>=0;j--)for(let i=0;i<12;i++){
  const coords=[[i,j],[i+1,j],[i+1,j+1],[i,j+1]].map(([ii,jj])=>project(ii,jj,a.surface[jj].points[ii].iv).join(','));
  const value=a.surface[j].points[i].iv;
  cells.push(`<polygon points="${coords.join(' ')}" fill="hsl(${180+(value-lo)/span*50} 68% ${24+(value-lo)/span*18}%)" stroke="#101a20" stroke-width=".8"><title>${a.surface[j].days} days · ${a.surface[j].points[i].strike} strike · ${number(value)}% model IV</title></polygon>`);
 }
 return `<svg class="pro-surface" viewBox="0 0 520 250" role="img" aria-label="Synthetic model implied-volatility surface, not observed market data"><title>Assumed skew across strike and maturity. No option-chain calibration.</title>${cells.join('')}<text x="35" y="40">IV %</text><text x="190" y="242">STRIKE</text><text x="425" y="96">DAYS</text><text x="58" y="228">${a.surface[0].points[0].strike}</text><text x="392" y="228">${a.surface[0].points.at(-1).strike}</text></svg>`;
}
function panel(id,title,badge,body){return `<section class="panel pro-panel" data-pro-panel="${id}"><div class="pro-panel-head"><button class="pro-drag" draggable="true" data-pro-drag="${id}" aria-label="Drag ${title} panel">⠿</button><h2>${title}</h2><span class="pro-badge">${badge}</span><button data-action="pro-move" data-value="${id}:-1" aria-label="Move ${title} panel earlier">‹</button><button data-action="pro-move" data-value="${id}:1" aria-label="Move ${title} panel later">›</button></div>${body}</section>`;}
export function analyticsWorkspace(snapshot,meta,state={}){
 let a,error='';try{a=scenarioModel(snapshot,meta,state);}catch(err){error=err.message;}
 const decisions=[...(snapshot.paper?.decisions||[])].reverse().slice(0,30);
 const log=panel('log','EXECUTION STREAM','STORED DECISIONS',`<div class="pro-log">${decisions.length?decisions.map(d=>`<div><time>${escape((d.timestamp||d.day||'').slice(0,19).replace('T',' '))}</time><b class="${d.action==='open'?'positive':d.action==='close'?'negative':''}">${escape(String(d.action||'observe').toUpperCase())}</b><span>${escape(d.candidate||'NO TRADE')}</span><small>${escape(d.reason||'No recorded reason')}</small></div>`).join(''):'<p>No recorded decisions in this snapshot. Connect your engine to receive its activity.</p>'}</div><div class="pro-panel-foot">Recorded engine events only · refresh follows the connected paper API</div>`);
 if(!a)return `<div class="pro-dock-grid">${panel('payoff','OPTIONS ANALYTICS','MODEL',`<p class="pro-empty">${escape(error||state.proMetaError||'Loading model parameters…')}</p>${state.proMetaError?'<button class="btn" data-action="tools-retry-model">Retry analytics</button>':''}`)}${log}</div>`;
 const structures=['iron_condor','bull_call_spread','bear_put_spread','bull_put_spread','bear_call_spread'];
 const sliders=[['proMove','Spot move',-3,3,.1,state.proMove??0,'%'],['proIv','IV shift',-10,10,.5,state.proIv??0,'pp'],['proDays','Days elapsed',0,7,.25,state.proDays??0,'d']];
 const payoff=panel('payoff','PAYOFF & SCENARIOS','1 LOT · MODEL',`<div class="pro-model-select"><label>Study structure<select id="pro-structure">${structures.map(s=>`<option value="${s}" ${s===a.input.strategy?'selected':''}>${s.replaceAll('_',' ')}</option>`).join('')}</select></label><span>Nominal expiry ${escape(a.model.expiry.slice(0,10))}</span></div>${payoffSvg(a)}<div class="pro-chart-key"><span class="amber">━ Expiry</span><span class="blue">━ ${a.elapsed?'Scenario mark':'T+0 model'}</span><span>Scenario P&L <b class="${a.scenarioPnl<0?'negative':'positive'}">${rupees(a.scenarioPnl)}</b></span></div><div class="pro-scenarios">${sliders.map(([key,label,min,max,step,value,unit])=>`<label>${label}<output>${number(Number(value),key==='proDays'?2:1)}${unit}</output><input type="range" data-pro-slider="${key}" aria-label="${label}" min="${min}" max="${max}" step="${step}" value="${value}"></label>`).join('')}</div><div class="pro-model-stats"><span>MAX PROFIT <b>${rupees(a.model.max_profit)}</b></span><span>MAX LOSS <b>${rupees(a.model.max_loss)}</b></span><button data-action="pro-reset">Reset scenario</button></div><div class="pro-panel-foot">Research study only · model premiums & fixed fee estimates · never changes orders or risk limits</div>`);
 const chain=panel('chain','NIFTY OPTION CHAIN','MODEL · NO LIVE QUOTES',`<div class="pro-chain-context"><span>CALLS</span><b>STRIKE</b><span>PUTS</span></div><div class="pro-chain-scroll"><table class="pro-chain"><thead><tr><th>OI</th><th>Δ</th><th>Model ₹</th><th>STRIKE</th><th>Model ₹</th><th>Δ</th><th>OI</th></tr></thead><tbody>${a.chain.map(r=>`<tr class="${r.atm?'pro-atm':''}"><td>—</td><td>${number(r.call.delta,2)}</td><td class="blue">${number(r.call.price)}</td><th>${number(r.strike,0)}${r.atm?' <small>ATM</small>':''}</th><td class="amber">${number(r.put.price)}</td><td>${number(r.put.delta,2)}</td><td>—</td></tr>`).join('')}</tbody></table></div><div class="pro-panel-foot">VIX pricing proxy ${number(a.bar.VIX)}% · OI, bid/ask and traded IV require a data provider</div>`);
 const surface=panel('surface','VOLATILITY SURFACE','SYNTHETIC SKEW',`${surfaceSvg(a)}<div class="pro-vol-range"><span>Low ${number(Math.min(...a.surface.flatMap(r=>r.points.map(p=>p.iv))))}%</span><i></i><span>High ${number(Math.max(...a.surface.flatMap(r=>r.points.map(p=>p.iv))))}%</span></div><div class="pro-gex"><strong>GAMMA EXPOSURE</strong><span>Unavailable</span><p>Market GEX needs observed open interest and a stated positioning convention. No synthetic GEX is shown.</p></div><div class="pro-panel-foot">1 / 3 / 7 / 14 / 30 days · model assumptions, not observed expiries or an arbitrage-free surface</div>`);
 const blocks={payoff,chain,surface,log};
 return `<div class="pro-workspace-heading"><div><span class="pro-kicker">ANALYTICS WORKSPACE</span><h2>One market. Every angle.</h2></div><button class="btn" data-action="pro-layout-reset">Reset panels</button></div><div class="pro-dock-grid">${panelOrder(JSON.stringify(state.proOrder)).map(id=>blocks[id]).join('')}</div>`;
}
export function terminalSafetyBar(snapshot,meta,sourceMode,automation,controlAllowed,pending=false){
 const connected=['local','cloud'].includes(sourceMode),g=portfolioGreeks(snapshot,meta),asof=snapshot.intraday?.latest_bar;
 return `<div class="pro-safety"><div class="pro-terminal-id"><span class="pro-logo">LL</span><strong>LAST OF OUR LEAGUE<small>OPTIONS ALGO TERMINAL</small></strong></div><div class="pro-mode" aria-label="Execution mode"><span class="active">PAPER</span><button disabled title="Broker execution is not connected">LIVE</button></div><div class="pro-net-greeks" aria-label="Net portfolio Greeks"><span>NET GREEKS <small>${g?.flat?'FLAT':`MODEL · ${escape(asof?.slice(11,16)||'NO MARK')} IST`}</small></span>${[['Δ','delta',2],['Γ','gamma',4],['Θ','theta',1],['V','vega',1]].map(([label,key,d])=>`<span title="${key}: aggregate model sensitivity across the paper position">${label} <b>${number(g?.[key],d)}</b></span>`).join('')}</div><button class="pro-halt" data-action="auto-pause" ${connected&&controlAllowed&&!pending?'':'disabled'}>${automation.enabled?'PAUSE ENTRIES':'ENTRIES PAUSED'}</button><button class="pro-flatten" disabled title="Immediate flatten is not supported by the connected engine. Pause entries keeps existing exit management active.">FLATTEN UNAVAILABLE</button></div>`;
}
export function bindPanelDock(root=document,save=()=>{}){
 let dragged=null;
 for(const handle of root.querySelectorAll('[data-pro-drag]')){
  handle.addEventListener('dragstart',ev=>{dragged=handle.dataset.proDrag;ev.dataTransfer?.setData('text/plain',dragged);if(ev.dataTransfer)ev.dataTransfer.effectAllowed='move';});
  handle.addEventListener('dragend',()=>{dragged=null;for(const p of root.querySelectorAll('[data-pro-panel]'))p.classList.remove('pro-drop-target');});
 }
 for(const panel of root.querySelectorAll('[data-pro-panel]')){
  panel.addEventListener('dragover',ev=>{if(dragged){ev.preventDefault();panel.classList.add('pro-drop-target');}});
  panel.addEventListener('dragleave',()=>panel.classList.remove('pro-drop-target'));
  panel.addEventListener('drop',ev=>{ev.preventDefault();panel.classList.remove('pro-drop-target');if(!dragged||dragged===panel.dataset.proPanel)return;const grid=panel.parentElement,source=[...grid.children].find(p=>p.dataset.proPanel===dragged);if(source){grid.insertBefore(source,panel);save([...grid.children].map(p=>p.dataset.proPanel));}dragged=null;});
 }
}
