import {accountPanel} from './dist/account-panel.js';
import {accountPath} from './dist/terminal-api.js';
import {analyticsWorkspace,terminalSafetyBar,bindPanelDock,panelOrder} from './dist/terminal-analytics.js';
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {TerminalApi,isLocalHost} from './dist/terminal-api.js';
import {CloudApi,mobilePage,mobileNav,initialiseMobile} from './dist/mobile-app.js';
import {TradingTools} from './dist/trading-tools.js';
import {initializeTheme,currentTheme,toggleTheme} from './dist/theme.js';
import {terminal,ordersView} from './dist/terminal.js';
const source=fs.readFileSync(new URL('./dist/app.js',import.meta.url),'utf8').split("$('#file-input').addEventListener")[0].replace(/^import .*;\n/gm,'');
const fixture=JSON.parse(fs.readFileSync(new URL('./dist/data.json',import.meta.url)));
fixture.paper.decisions=[{timestamp:'2026-11-16T10:55:00+05:30',action:'skip',condition:'rising',candidate:'bull_put_spread',reason:'waiting_for_5m_bullish_trigger',equity_rs:500000}];
for(const hash of ['#terminal/activity','#activity']){
 const root={innerHTML:''},calls=[];
 const context=vm.createContext({location:{hash,hostname:'nifty-research-terminal.nearbydrape.chatgpt.site'},Intl,Date,Set,Map,Number,Math,console,TerminalApi,isLocalHost,CloudApi,mobilePage,mobileNav,initialiseMobile,TradingTools,initializeTheme,currentTheme,toggleTheme,accountPanel,accountPath,analyticsWorkspace,terminalSafetyBar,bindPanelDock,panelOrder,terminal,ordersView,document:{querySelector:()=>root,querySelectorAll:()=>[]},fetch:async path=>{
  calls.push(path);assert.equal(path,'data.json','Public pages must not call a loopback API');
  return {ok:true,json:async()=>structuredClone(fixture)};
 }});
 vm.runInContext(source+'\nglobalThis.qa={load,routeFromHash,state};',context);
 await context.qa.load();
 assert.equal(context.qa.state.view,'terminal');
 assert.equal(context.qa.state.bookTab,'activity');
 assert.ok(root.innerHTML.includes('Public saved snapshot'));
 assert.ok(root.innerHTML.includes('Saved engine decisions through'));
 assert.ok(root.innerHTML.includes('Bull put spread'));
 assert.ok(root.innerHTML.includes('Waiting for the 5-minute close to be above EMA20'));
 assert.ok(root.innerHTML.includes('Sign in to the hosted paper engine'));
 assert.ok(root.innerHTML.includes('href="#mobile"'));
 assert.ok(root.innerHTML.includes('data-action="auto-start" disabled'));
 assert.equal(calls.length,1);
 assert.equal(context.qa.routeFromHash('#terminal/orders').bookTab,'orders');
 assert.equal(context.qa.routeFromHash('#terminal/history').bookTab,'history');
 assert.equal(context.qa.routeFromHash('#orders').view,'orders');
 assert.equal(context.qa.routeFromHash('#terminal/unknown'),null);
 assert.equal(context.qa.routeFromHash('#orders/activity'),null);
}
console.log('Public snapshot passed direct activity links, reload routing, saved decision rendering, disabled execution and API isolation checks.');
