import {accountPanel} from './dist/account-panel.js';
import {accountPath} from './dist/terminal-api.js';
import {analyticsWorkspace,terminalSafetyBar,bindPanelDock,panelOrder} from './dist/terminal-analytics.js';
// Pure data/format checks: no browser automation or external dependencies.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {TerminalApi,isLocalHost} from './dist/terminal-api.js';
import {CloudApi,mobilePage,mobileNav,initialiseMobile} from './dist/mobile-app.js';
import {TradingTools} from './dist/trading-tools.js';
import {initializeTheme,currentTheme,toggleTheme} from './dist/theme.js';
const source=fs.readFileSync(new URL('./dist/app.js',import.meta.url),'utf8').split("$('#file-input').addEventListener")[0].replace(/^import .*;\n/gm,'');
const context=vm.createContext({location:{hash:''},Intl,Date,Set,Map,Number,Math,console,TerminalApi,isLocalHost,CloudApi,mobilePage,mobileNav,initialiseMobile,TradingTools,initializeTheme,currentTheme,toggleTheme,accountPanel,accountPath,analyticsWorkspace,terminalSafetyBar,bindPanelDock,panelOrder});
vm.runInContext(source+`\nglobalThis.checks={series,stats,drawdown,selectedTrades,validateReport,escape,resetReport,state,setData(data){snapshot=data;}};`,context);
const {checks}=context;
const report={summary:[{strategy:'REGIME_BOT',total_rs:10,trades:4,'win_rate_%':50,max_drawdown_rs:-100}],
 equity:{REGIME_BOT:[['2026-01-01',-100],['2026-01-08',-50],['2026-01-15',-90],['2026-01-22',10]]},
 weekly_decisions:['01','08','15','22'].map(d=>({entry:'2026-01-'+d,pick:'bull_put_spread'})),
 trades:['01','08','15','22'].map((d,i)=>({entry:'2026-01-'+d,strategy:'bull_put_spread',pnl_rs:[-100,50,-40,100][i]}))};
checks.setData({reports:[report],market_as_of:'2026-01-22'});
assert.equal(checks.stats('REGIME_BOT').total_rs,10);
checks.state.start='2026-01-08'; checks.state.end='2026-01-15';
const filtered=checks.stats('REGIME_BOT');
assert.equal(filtered.total_rs,10);
assert.equal(filtered.trades,2);
assert.equal(filtered['win_rate_%'],50);
assert.equal(filtered.max_drawdown_rs,-40);
assert.equal(checks.selectedTrades('REGIME_BOT').length,2);
assert.equal(checks.series('REGIME_BOT')[0][1],50); // rebase to selected period, not historical cumulative value
assert.equal(checks.escape('<img onerror="x">'),'&lt;img onerror=&quot;x&quot;&gt;');
assert.throws(()=>checks.validateReport({summary:[],equity:{}}));
assert.throws(()=>checks.validateReport({summary:[{strategy:'x'}],equity:{x:[['bad date',2]]}}));
assert.throws(()=>checks.validateReport({summary:[{strategy:'x'}],equity:{x:[['2026-01-01',null]]}}));
assert.equal(checks.validateReport(report),report);
const summaryOnly={...report,trades:[],weekly_decisions:[]};
checks.setData({reports:[summaryOnly]});
assert.equal(checks.stats('REGIME_BOT').trades,null); // do not invent trade counts for imported summary-only reports
console.log('Dashboard checks passed: period P&L, rebasing, drawdown, policy matching, missing ledgers and import validation.');
