import {accountPanel} from './dist/account-panel.js';
import {accountPath} from './dist/terminal-api.js';
import {analyticsWorkspace,terminalSafetyBar,bindPanelDock,panelOrder} from './dist/terminal-analytics.js';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {TerminalApi,isLocalHost} from './dist/terminal-api.js';
import {CloudApi,mobilePage,mobileNav,initialiseMobile} from './dist/mobile-app.js';
import {TradingTools} from './dist/trading-tools.js';
import {initializeTheme,currentTheme,toggleTheme} from './dist/theme.js';
import {terminal,ordersView} from './dist/terminal.js';
const ok=data=>({ok:true,json:async()=>data});
const health=token=>ok({status:'ok',mode:'paper',session_token:token,automation:{enabled:false,state:'stopped'}});

// An old tab gets the restarted server's current token before submitting Start.
let calls=[];
const api=new TerminalApi(async(path,options)=>{
 calls.push([path,options]);
 return path==='/api/health'?health('new-session'):ok({enabled:true,state:'starting'});
});
api.token='old-session';
assert.equal((await api.action('/api/automation/start')).enabled,true);
assert.equal(calls[1][1].headers['X-Terminal-Token'],'new-session');

// Restart between health and POST: retry only the rejected, unexecuted request.
let posts=0,connections=0;
const restarted=new TerminalApi(async(path,options)=>{
 if(path==='/api/health')return health(`session-${++connections}`);
 posts++;
 if(posts===1)return {ok:false,status:403,json:async()=>({error:'session rejected'})};
 assert.equal(options.headers['X-Terminal-Token'],'session-2');
 return ok({enabled:true});
});
await restarted.action('/api/automation/start');
assert.equal(posts,2);

// An uncertain POST must never be replayed automatically.
posts=0;
const uncertain=new TerminalApi(async path=>{
 if(path==='/api/health')return health('valid');
 posts++;throw new Error('connection lost after submission');
});
await assert.rejects(uncertain.action('/api/automation/start'),/Could not confirm/);
assert.equal(posts,1);
const staticServer=new TerminalApi(async()=>({ok:true,json:async()=>{throw new Error('HTML response')}}));
await assert.rejects(staticServer.action('/api/automation/start'),/not connected to the Python paper server/);
assert.equal(staticServer.token,null);

// Exercise the actual page's load/poll functions through disconnect and recovery.
const root={innerHTML:''};
const document={querySelector:()=>root,querySelectorAll:()=>[]};
const data=JSON.parse(fs.readFileSync(new URL('./dist/data.json',import.meta.url)));
let online=false,readCount=0;
const fetcher=async path=>{
 if(path==='data.json')return ok(structuredClone(data));
 if(!online)throw new Error('server stopped');
 if(path==='/api/health')return health('restored');
 if(path==='/api/dashboard'){readCount++;return ok(structuredClone(data));}
 if(path==='/api/status')return ok({automation:{enabled:false,state:'stopped'}});
 throw new Error('unexpected '+path);
};
const source=fs.readFileSync(new URL('./dist/app.js',import.meta.url),'utf8').split("$('#file-input').addEventListener")[0].replace(/^import .*;\n/gm,'');
const context=vm.createContext({location:{hash:'',hostname:'127.0.0.1'},Intl,Date,Set,Map,Number,Math,console,document,terminal,ordersView,TerminalApi,isLocalHost,CloudApi,mobilePage,mobileNav,initialiseMobile,TradingTools,initializeTheme,currentTheme,toggleTheme,accountPanel,accountPath,analyticsWorkspace,terminalSafetyBar,bindPanelDock,panelOrder,fetch:fetcher,setInterval:()=>1});
vm.runInContext(source+`\nglobalThis.qa={load,pollStatus,mode:()=>sourceMode,equity:()=>snapshot.paper.realised_equity_rs};`,context);
await context.qa.load();
assert.equal(context.qa.mode(),'local-disconnected');
assert.ok(root.innerHTML.includes('Paper engine disconnected'));
assert.ok(root.innerHTML.includes('Reconnect paper engine'));
const equity=context.qa.equity();
online=true;
await context.qa.pollStatus();
assert.equal(context.qa.mode(),'local');
assert.ok(root.innerHTML.includes('Start auto paper'));
assert.ok(!root.innerHTML.includes('Paper engine disconnected'));
assert.equal(context.qa.equity(),equity);
assert.equal(readCount,1);
online=false;
await context.qa.pollStatus();
assert.equal(context.qa.mode(),'local-disconnected');
assert.ok(root.innerHTML.includes('Paper engine disconnected'));
console.log('Paper controls passed server restart, session renewal, safe retry, static-server rejection, disconnect warning and automatic recovery checks.');

// A slow response from an account previously selected cannot replace the new account.
vm.runInContext(`globalThis.profileQA={select:v=>{state.paperProfile=v},api:v=>{localApi=v},snapshot:()=>snapshot,act:localAction};`,context);
const originalSnapshot=context.profileQA.snapshot();
let releaseDashboard;
const slowDashboard=new Promise(resolve=>{releaseDashboard=resolve});
const separateApi={remote:true,supportsExperiments:true,connect:async()=>({state:'original-state'}),
 read:async path=>path==='/api/dashboard'?slowDashboard:{automation:{state:'experimental-state'}}};
context.profileQA.api(separateApi);
const pendingLoad=context.qa.load();
await new Promise(resolve=>setImmediate(resolve));
context.profileQA.select('adaptive25');
releaseDashboard({...data,paper:{...data.paper,realised_equity_rs:123}});
await pendingLoad;
assert.equal(context.profileQA.snapshot(),originalSnapshot,'Old response must not overwrite selected account');
await assert.rejects(context.profileQA.act('/api/automation/start'),/selected account/);
console.log('Account controls reject mismatched data and discard responses after an account switch.');
