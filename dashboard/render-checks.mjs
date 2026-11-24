import {accountPanel} from './dist/account-panel.js';
import {accountPath} from './dist/terminal-api.js';
import {analyticsWorkspace,terminalSafetyBar,bindPanelDock,panelOrder} from './dist/terminal-analytics.js';
// Template/unit checks complement browser verification.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {terminal,ordersView} from './dist/terminal.js';
import {TerminalApi,isLocalHost} from './dist/terminal-api.js';
import {CloudApi,mobilePage,mobileNav,initialiseMobile} from './dist/mobile-app.js';
import {TradingTools} from './dist/trading-tools.js';
import {initializeTheme,currentTheme,toggleTheme} from './dist/theme.js';
const text=fs.readFileSync(new URL('./dist/app.js',import.meta.url),'utf8').split("$('#file-input').addEventListener")[0].replace(/^import .*;\n/gm,'');
const root={innerHTML:''};
const document={querySelector:()=>root,querySelectorAll:()=>[],activeElement:null};
const context=vm.createContext({location:{hash:''},Intl,Date,Set,Map,Number,Math,console,document,terminal,ordersView,TerminalApi,isLocalHost,CloudApi,mobilePage,mobileNav,initialiseMobile,TradingTools,initializeTheme,currentTheme,toggleTheme,accountPanel,accountPath,analyticsWorkspace,terminalSafetyBar,bindPanelDock,panelOrder});
vm.runInContext(text+`\nglobalThis.qa={setData(data){snapshot=data;resetReport(0);},screen(name){const pages={terminal:terminalPage,orders:ordersPage,overview,compare,market:marketPage,journal,paper,sources};return pages[name]();},shell(){render();},setMode(mode){sourceMode=mode;automation={state:'market_closed',enabled:true};}}`,context);
const data=JSON.parse(fs.readFileSync(new URL('./dist/data.json',import.meta.url)));
context.qa.setData(data);
for(const page of ['terminal','orders','overview','compare','market','journal','paper','sources']){
 const html=context.qa.screen(page);
 assert.ok(html.length>100,page+' should render content');
 assert.ok(!html.includes('NaN'),page+' must not show NaN');
 assert.ok(!html.includes('Invalid Date'),page+' must have valid dates');
 assert.ok(!html.includes('undefined'),page+' must not show undefined');
}
context.qa.shell();
assert.ok(root.innerHTML.includes('LAST OF<br>OUR LEAGUE'));
assert.ok(root.innerHTML.includes('Nifty 50 5m OHLC candlesticks'));
assert.ok(root.innerHTML.includes('Start auto paper'));
assert.ok(root.innerHTML.includes('hosted_snapshot')===false);
context.qa.setMode('local');
assert.ok(context.qa.screen('terminal').includes('Auto paper enabled'));
console.log('All eight dashboard views, candlesticks, dates and local/snapshot control states passed template checks.');
const fixture=structuredClone(data);
fixture.paper.orders=[
 {order_id:'PAPER-FIXTURE-OPEN-1',filled_at:'2026-11-16T10:00:00+05:30',side:'BUY',phase:'OPEN',strike:25000,option_type:'CE',expiry:'2026-11-17',lots:2,fill_price:123.45,strategy:'bull_call_spread'},
 {order_id:'PAPER-FIXTURE-CLOSE-1',filled_at:'2026-11-16T10:30:00+05:30',side:'SELL',phase:'CLOSE',strike:25000,option_type:'CE',expiry:'2026-11-17',lots:2,fill_price:130,strategy:'bull_call_spread'}
];
context.qa.setData(fixture);
const orderHtml=context.qa.screen('orders');
for(const label of ['BUY','SELL','Opening','Closing','₹123.45','Modelled fill','PAPER-FIXTURE-OPEN-1'])assert.ok(orderHtml.includes(label),'Orders must show '+label);
console.log('Populated order-book template passed BUY/SELL, open/close and stored-price checks; fixtures were not saved to the account.');
