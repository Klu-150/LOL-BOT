// Read-only presentation of persisted decisions and fills; never creates orders.
const explanations={
 waiting_for_5m_bullish_trigger:'Waiting for the 5-minute close to be above EMA20, with EMA20 at or above EMA50.',
 waiting_for_5m_bearish_trigger:'Waiting for the 5-minute close to be below EMA20, with EMA20 at or below EMA50.',
 missed_or_stale_bar_no_entry:'This bar was historical, stale, or processed while entries were disabled. No entry was created.',
 outside_entry_window:'New paper entries are allowed only from 09:45 to 14:30 IST.',
 daily_trade_limit:'The maximum number of paper trades for this session has been reached.',
 daily_risk_budget:'There is not enough daily risk budget for another position.',
 drawdown_halt:'The account drawdown limit has halted new entries.',
 cooldown:'Waiting for the cooldown after the previous exit.',
 position_open:'Holding the paper position and checking exit rules on completed bars.',
 session_square_off:'The paper position was closed at the session square-off observation.',
 no_clear_setup:'The market does not match a qualifying strategy setup.',
 mixed_volatility:'The volatility filters do not match a qualifying setup.'
};
export const decisionExplanation=reason=>explanations[reason]||String(reason||'Waiting for the next completed-bar decision.').replaceAll('_',' ');
const latest=rows=>rows.reduce((last,row)=>String(row.timestamp||row.filled_at||'')>String(last?.timestamp||last?.filled_at||'')?row:last,null);

export function executionView(snapshot,automation={},sourceMode='snapshot',now=Date.now()){
 const paper=snapshot.paper||{},data=snapshot.intraday||{};
 const local=['local','cloud'].includes(sourceMode),offline=sourceMode.endsWith('disconnected');
 const recorded=latest(paper.decisions||[]);
 const sourceBar=(local?automation.latest_bar:null)||data.latest_bar||null;
 const matches=!!recorded&&recorded.timestamp===sourceBar;
 const candidate=local&&Object.hasOwn(automation,'candidate')?automation.candidate:data.candidate;
 const position=paper.position||(paper.trades||[]).find(t=>t.status==='open');
 const day=local||offline?new Date(now+330*60000).toISOString().slice(0,10):String(sourceBar||'').slice(0,10);
 const orders=(paper.orders||[]).filter(o=>String(o.filled_at||'').slice(0,10)===day);
 const lastOrder=latest(paper.orders||[]);
 const bar=data.bars?.findLast(b=>b.timestamp===sourceBar);
 const age=sourceBar?(now-Date.parse(sourceBar))/60000:null;
 let title='Waiting for a completed-bar decision',detail=decisionExplanation(recorded?.reason),tone='waiting';
 if(!local){title=offline?'Paper engine disconnected':'Saved snapshot';detail=offline?'Reconnect to the paper server. This app cannot confirm that the engine is running.':'Sign in to the hosted paper engine from Connect devices to view current automatic selections, orders and status. These are saved records.';tone='muted';}
 else if(['error','data_error'].includes(automation.state)){title='Engine error — no new entries';detail=automation.error||'The latest data check failed.';tone='blocked';}
 else if(automation.state==='storage_guard'){title='Storage guard — no new entries';detail=automation.message||'Low server disk space blocks new entries; existing exits remain managed.';tone='blocked';}
 else if(paper.halted){title='Risk halt — no new entries';detail=decisionExplanation('drawdown_halt');tone='blocked';}
 else if(automation.enabled&&automation.checked_at&&now-Date.parse(automation.checked_at)>Math.max(180,3*(automation.poll_seconds||60))*1000){title='Engine heartbeat delayed';detail='The engine has not reported a recent check. Check the engine connection before relying on automation.';tone='blocked';}
 else if(automation.state==='square_off_waiting_for_data'){title='Square-off waiting for data';detail='An open position needs a fresh completed bar to record its exit.';tone='blocked';}
 else if(automation.state==='stopped'){title=position?'Engine stopped — position unmanaged':'Paper engine stopped';detail='Start the paper engine to process market bars and manage positions.';tone=position?'blocked':'muted';}
 else if(position&&(!Number.isFinite(age)||age==null||age>10)){title='Position open — waiting for fresh data';detail='An open paper position is recorded, but a current mark or exit cannot be confirmed without fresh data.';tone='blocked';}
 else if(position){title='Managing an open paper position';detail=decisionExplanation(matches?recorded.reason:'position_open');tone='active';}
 else if(!automation.enabled){title=automation.state==='stopped'?'Paper engine stopped':'New entries paused';detail='Click Start auto paper to enable new entries. Reconnection alone does not enable them.';tone='muted';}
 else if(automation.state==='market_closed'){title='Market closed — automatic paper standing by';detail='The engine is enabled and waiting for the next eligible session. The displayed strategy is from the last observed bar; it will be reassessed with fresh data.';tone='waiting';}
 else if(age==null||!Number.isFinite(age)||age>10){title='Waiting for fresh market data';detail='The latest source bar is missing or more than 10 minutes old. New entries are blocked.';tone='blocked';}
 else if(!matches){title='Waiting for the latest decision';detail='The account view has not yet caught up with the latest source bar. No new fill is confirmed by this view.';}
 else if(recorded.action==='close'){title='Paper position closed';tone='active';}
 else if(recorded.reason==='outside_entry_window'){title='Outside entry hours';}
 else if(recorded.reason?.startsWith('waiting_for_5m_')){title='Waiting for entry trigger';}
 else if(!candidate){title='No qualifying strategy';}
 else{title='No paper entry on the last evaluated bar';}
 let trigger=null;
 if(local&&automation.state!=='market_closed'&&Number.isFinite(age)&&age<=10&&age>=-1&&candidate&&bar&&[bar.Close,bar.trigger_fast,bar.trigger_slow].every(Number.isFinite)){
  if(candidate.startsWith('bull_'))trigger={passed:bar.Close>bar.trigger_fast&&bar.trigger_fast>=bar.trigger_slow,rule:'Close > EMA20 ≥ EMA50',values:[bar.Close,bar.trigger_fast,bar.trigger_slow]};
  if(candidate.startsWith('bear_'))trigger={passed:bar.Close<bar.trigger_fast&&bar.trigger_fast<=bar.trigger_slow,rule:'Close < EMA20 ≤ EMA50',values:[bar.Close,bar.trigger_fast,bar.trigger_slow]};
 }
 return {title,detail,tone,candidate,position,recorded,sourceBar,matches,trigger,day,orders,lastOrder,
  buys:orders.filter(o=>o.side==='BUY').length,sells:orders.filter(o=>o.side==='SELL').length,
  condition:(local?automation.market_condition:null)||data.condition,
  volatility:(local?automation.volatility_condition:null)||data.volatility};
}

export function executionPanel(s,automation,sourceMode,{e,human,num,date,icon}){
 const v=executionView(s,automation,sourceMode);
 const heartbeat=['local','cloud'].includes(sourceMode)&&automation.checked_at?`${automation.checked_at.slice(11,19)} IST`:'Not confirmed';
 return `<section class="execution-panel panel" aria-label="Strategy and paper execution status">
  <div class="execution-heading"><div><span class="eyebrow">STRATEGY & EXECUTION</span><h2>${e(v.title)}</h2></div><span class="tag ${v.tone==='blocked'?'red':v.tone==='active'?'':'gray'}">${['local','cloud'].includes(sourceMode)&&automation.enabled?'AUTO PAPER ENABLED':sourceMode.endsWith('disconnected')?'DISCONNECTED':['local','cloud'].includes(sourceMode)?'ENTRIES DISABLED':'SAVED SNAPSHOT'}</span></div>
  <div class="execution-cards"><div><span>Selected strategy</span><strong>${e(v.candidate?human(v.candidate):'Stand aside')}</strong><small>${e(human(v.condition||'unknown'))} market · ${e(human(v.volatility||'unknown'))} volatility</small></div><div><span>Active position strategy</span><strong>${e(v.position?human(v.position.strategy):'None')}</strong><small>${v.position?`${num(v.position.lots)} lots · checking exit rules`:'A selected strategy waits until all entry rules pass.'}</small></div><div><span>Paper fills · ${e(v.day||'unknown date')}</span><strong>${num(v.orders.length)} <small>leg fills</small></strong><small>BUY ${num(v.buys)} · SELL ${num(v.sells)}</small></div></div>
  <div class="execution-decision"><strong>${v.position?'Position management':'Latest entry / exit decision'}</strong><p>${e(v.detail)}</p>${v.trigger?`<div class="trigger-check"><span class="tag ${v.trigger.passed?'':'amber'}">5m trigger: ${v.trigger.passed?'Passed':'Waiting'}</span><span>${e(v.trigger.rule)}</span><small>Close ${num(v.trigger.values[0],2)} · EMA20 ${num(v.trigger.values[1],2)} · EMA50 ${num(v.trigger.values[2],2)}</small></div>`:''}</div>
  <div class="execution-footer"><div><span>Engine check: <b>${e(heartbeat)}</b></span><span>Last recorded decision: <b>${e(v.recorded?date(v.recorded.timestamp):'None yet')}</b>${v.recorded?` · ${e(human(v.recorded.action))}`:''}</span><span>${v.lastOrder?`Last paper fill: ${e(v.lastOrder.side)} · ${e(date(v.lastOrder.filled_at))}`:'No paper fills recorded yet.'} No broker connected.</span></div><div class="execution-links"><button class="btn" data-action="nav" data-value="orders">${icon('book')}View orders</button><button class="panel-link" data-action="show-decisions">Decision log</button></div></div>
 </section>`;
}
