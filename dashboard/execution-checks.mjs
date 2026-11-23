import assert from 'node:assert/strict';
import {executionView,executionPanel} from './dist/execution-view.js';
const now=Date.parse('2026-11-16T10:52:00+05:30'),timestamp='2026-11-16T10:50:00+05:30';
const snapshot={intraday:{latest_bar:timestamp,candidate:'bull_put_spread',condition:'rising',volatility:'rich',bars:[{timestamp,Close:25219,trigger_fast:25240,trigger_slow:25220}]},paper:{decisions:[{timestamp,action:'skip',reason:'waiting_for_5m_bullish_trigger',candidate:'bull_put_spread'}],orders:[],position:null}};
const auto={enabled:true,state:'watching',latest_bar:timestamp,candidate:'bull_put_spread',checked_at:'2026-11-16T10:51:30+05:30'};
let view=executionView(snapshot,auto,'local',now);
assert.equal(view.title,'Waiting for entry trigger');
assert.equal(view.candidate,'bull_put_spread');
assert.ok(view.detail.includes('EMA20'));
assert.equal(view.position,undefined);
assert.equal(view.orders.length,0);
assert.equal(view.trigger.passed,false);

const withPosition=structuredClone(snapshot);
withPosition.paper.position={strategy:'bear_put_spread',lots:2};
withPosition.paper.decisions=[{timestamp,action:'hold',reason:'position_open'}];
withPosition.paper.orders=[
 {filled_at:'2026-11-13T10:00:00+05:30',side:'BUY',order_id:'old'},
 {filled_at:timestamp,side:'BUY',order_id:'current-long'},
 {filled_at:timestamp,side:'SELL',order_id:'current-short'}
];
view=executionView(withPosition,auto,'local',now);
assert.equal(view.title,'Managing an open paper position');
assert.equal(view.position.strategy,'bear_put_spread'); // Do not relabel a held position as the new candidate.
assert.equal(view.candidate,'bull_put_spread');
assert.equal(view.orders.length,2);
assert.equal(view.buys,1);assert.equal(view.sells,1);
assert.equal(view.lastOrder.filled_at,timestamp);
assert.equal(executionView(snapshot,{...auto,candidate:null},'local',now).candidate,null);
assert.equal(executionView(snapshot,{...auto,enabled:false},'local',now).title,'New entries paused');
assert.equal(executionView(withPosition,{...auto,enabled:false,state:'stopped'},'local',now).title,'Engine stopped — position unmanaged');
assert.equal(executionView(snapshot,auto,'local-disconnected',now).title,'Paper engine disconnected');
assert.equal(executionView(snapshot,auto,'snapshot',now).title,'Saved snapshot');
assert.equal(executionView(snapshot,{...auto,state:'data_error',error:'feed unavailable'},'local',now).detail,'feed unavailable');
assert.equal(executionView(snapshot,{...auto,checked_at:'2026-11-16T10:40:00+05:30'},'local',now).title,'Engine heartbeat delayed');
assert.equal(executionView(snapshot,{...auto,checked_at:null},'local',now+11*60000).title,'Waiting for fresh market data');
assert.equal(executionView(withPosition,{...auto,checked_at:null},'local',now+11*60000).title,'Position open — waiting for fresh data');
const catchingUp=structuredClone(snapshot);catchingUp.paper.decisions[0].timestamp='2026-11-16T10:45:00+05:30';
assert.equal(executionView(catchingUp,auto,'local',now).title,'Waiting for the latest decision');
const closed=structuredClone(snapshot);closed.paper.decisions[0]={timestamp,action:'close',reason:'session_square_off'};
assert.equal(executionView(closed,auto,'local',now).title,'Paper position closed');
const helpers={e:x=>String(x??'').replaceAll('<','&lt;'),human:x=>String(x??''),num:x=>String(x),date:x=>String(x),icon:()=>''};
const html=executionPanel(snapshot,auto,'local',helpers);
for(const text of ['Selected strategy','Active position strategy','bull_put_spread','BUY 0','SELL 0','No paper fills recorded yet.','Decision log'])assert.ok(html.includes(text),text);
assert.ok(!html.includes('undefined'));
assert.equal(snapshot.paper.orders.length,0); // Rendering cannot manufacture fills.
console.log('Execution status passed candidate/position separation, real fill counts, trigger waiting, stale/error states and decision freshness checks.');

const weekend=executionView(snapshot,{...auto,state:'market_closed',checked_at:new Date(now+86400000).toISOString()},'cloud',now+86400000);
assert.equal(weekend.title,'Market closed — automatic paper standing by');assert.equal(weekend.trigger,null);
assert.equal(executionView(withPosition,{...auto,state:'market_closed',checked_at:null},'cloud',now+86400000).title,'Position open — waiting for fresh data');
assert.equal(executionView(snapshot,{...auto,state:'storage_guard'},'cloud',now).title,'Storage guard — no new entries');
