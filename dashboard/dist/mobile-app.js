import {TerminalApi} from './terminal-api.js';
export function serverOrigin(value){
 let url;try{url=new URL(value)}catch{throw new Error('Enter your hosted engine HTTPS address.');}
 if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash||url.pathname!=='/')throw new Error('Use an HTTPS server origin without a path, password or query.');
 return url.origin;
}
export class CloudApi extends TerminalApi{
 constructor(origin,name,key,fetcher=(...args)=>fetch(...args)){
  const base=serverOrigin(origin);
  if(!/^[A-Za-z0-9_-]{1,40}$/.test(name)||!/^[A-Za-z0-9_-]{24,256}$/.test(key))throw new Error('Enter your username and the private access key supplied for the hosted engine.');
  const authorization=`Bearer ${name}.${key}`;
  super((path,options={})=>{
   if(!path.startsWith('/api/'))throw new Error('Unsupported hosted API path');
   return fetcher(base+path,{...options,credentials:'omit',redirect:'error',mode:'cors',headers:{...options.headers,Authorization:authorization}});
  },true);
  this.origin=base;
 }
}
export const defaultServer='https://last-of-our-league-dedf75.indiasouthcentral.cloudapp.azure.com';
export function rememberedServer(){try{return serverOrigin(localStorage.getItem('league_cloud_server')||defaultServer)}catch{return defaultServer}}
export function mobilePage({e,icon,sourceMode,cloudSession,api,installed,connecting}){
 const connected=sourceMode==='cloud',local=sourceMode==='local';
 return `<div class="page-heading"><div><p class="eyebrow">SHARED PAPER ACCOUNT</p><h1>Connect your devices</h1><p class="subheading">Use your laptop, your friend’s laptop or iPhone to view the same cloud paper account.</p></div></div>
 <div class="device-connect-grid"> <section class="panel setup-card cloud-setup"><h2 class="panel-title">Connect your paper engine</h2><p class="signal-note">Your Azure server address is filled in below. Enter your username and private access key to check its live status. You and your friend can use separate keys for the same virtual account.</p><form id="cloud-connect" class="cloud-connect"><label>Hosted engine address<input name="server" type="url" inputmode="url" autocomplete="url" value="${e(cloudSession?.origin||rememberedServer())}" required></label><label>Username<input name="username" autocomplete="username" autocapitalize="none" spellcheck="false" value="${e(cloudSession?.name||'madhan')}" required maxlength="40"></label><label>Private access key<input name="key" type="password" autocomplete="current-password" autocapitalize="none" spellcheck="false" required></label><button class="btn primary" type="submit" ${connecting?'disabled':''}>${icon('activity')}${connecting?'Connecting…':'Connect paper engine'}</button></form><p class="signal-note">The server address can be remembered. Your access key stays in app memory and is never included in report exports. Reopened app sessions may require signing in again. Signing out or closing the app does not pause the server.</p></section><aside class="panel device-guide"><div class="device-guide-mark">${icon('layers')}</div><p class="eyebrow">ONE SHARED WORKSPACE</p><h2>Your desk.<br>On every device.</h2><p>One cloud engine keeps your strategies, paper orders and positions together.</p><div class="device-guide-state"><i class="dot"></i><strong>${connected?'Cloud connected':local?'Local engine connected':'Sign in to view live activity'}</strong></div><ul><li>${icon('check')}Separate private sign-ins</li><li>${icon('check')}One shared virtual account</li><li>${icon('check')}Cloud processing when laptops close</li></ul><small>Trader permissions control entries. Viewer permissions allow account inspection.</small></aside></div>
 <section class="panel setup-card"><h2 class="panel-title">Two laptops, one trading engine</h2><p class="signal-note">Open this website on each laptop and connect below with your own username and private access key. Both clients see the same strategies, positions and paper orders. The designated trader can start or pause entries; viewers can inspect the account. Closing a browser or laptop does not stop the cloud engine. Do not launch a second local copy for this shared account.</p><p class="signal-note">Review notes, alerts and research drafts stay in each browser. They are not shared automatically.</p></section>
 <section class="panel phone-install"><img src="icons/icon-192.png" width="64" height="64" alt="Last of Our League app icon"><div><span class="tag">${installed?'APP WINDOW':'HOME SCREEN READY'}</span><h2>Last of Our League</h2><p>${installed?'You are using the standalone app window.':'Open this page in Safari on your iPhone to add it to your Home Screen.'}</p></div></section>
 <div class="mobile-setup-grid"><section class="panel setup-card"><h2 class="panel-title">Add the iPhone app</h2><ol class="install-steps"><li>Open this public link in <strong>Safari</strong>.</li><li>Tap <strong>Share</strong>, then <strong>Add to Home Screen</strong>.</li><li>Enable <strong>Open as Web App</strong> if shown, then tap <strong>Add</strong>.</li><li>Open <strong>Last of Our League</strong> from your Home Screen.</li></ol><p class="signal-note">No App Store download is needed. If you opened the link inside another app, choose Open in Safari first.</p></section>
 <section class="panel setup-card"><h2 class="panel-title">What is running?</h2><div class="phone-connection"><i class="dot"></i><strong>${connected?'Hosted engine connected':local?'Local computer connected':cloudSession?'Hosted engine disconnected':'Cloud engine not connected'}</strong></div><p class="signal-note">${connected?'The Python engine runs on your server. Closing the phone app does not stop that server.':local?'The engine runs on this computer. Turning it off stops processing.':'This app currently displays saved public records. An always-on server is required for independent trading.'}</p><p class="signal-note">Installing the app does not make iPhone background processing run the trading engine. Paper trades and exit management run on the connected server.</p>${cloudSession?`<div class="data-pair"><span>Server</span><strong>${e(cloudSession.origin)}</strong></div><div class="data-pair"><span>Signed in as</span><strong>${e(api.user?.name||cloudSession.name)} · ${e(api.user?.role||'unknown')}</strong></div><button class="btn" data-action="disconnect-cloud">Disconnect this app</button>`:''}</section></div>
`;
}
export function mobileNav(state,icon){
 return `<nav class="mobile-dock" aria-label="Mobile navigation">${[['terminal','activity','Terminal'],['orders','book','Orders'],['strategies','layers','Strategies'],['desk','shield','Tools'],['mobile','grid','Connect']].map(([view,ic,label])=>`<button data-action="${view==='activity'?'show-decisions':'nav'}" data-value="${view}" class="${view==='activity'?state.view==='terminal'&&state.bookTab==='activity'?'active':'':(view==='desk'?['desk','options','review'].includes(state.view):state.view===view&&(view!=='terminal'||state.bookTab!=='activity'))?'active':''}" aria-label="${label}">${icon(ic)}<span>${label}</span></button>`).join('')}</nav>`;
}
export function initialiseMobile(){
 if('serviceWorker' in navigator&&window.isSecureContext)navigator.serviceWorker.register('./sw.js',{updateViaCache:'none'}).catch(()=>{});
 return !!(window.matchMedia('(display-mode: standalone)').matches||navigator.standalone);
}
