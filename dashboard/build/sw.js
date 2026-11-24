// Static app shell only. Never cache API, account data, keys, or orders.
const CACHE='league-shell-f9c2c9fa745c19d9';
const SHELL=["/offline.html","/manifest.webmanifest","/icons/icon-192.png","/icons/icon-512.png","/icons/apple-touch-icon.png","/assets/execution-view-f1b717ac6ba642f9.js","/assets/terminal-eab2c8b04a05c0b2.js","/assets/terminal-api-17ffb68ac594d91f.js","/assets/mobile-app-0b38e282709b2b0e.js","/assets/strategy-engine-251c64dd6c468073.js","/assets/platform-model-f1eba76098ddd6f0.js","/assets/strategy-worker-184d5eb5c0df4cc5.js","/assets/strategy-workshop-a915f8bc092b8a2a.js","/assets/platform-store-b1941202ed9a9670.js","/assets/trading-tools-db7997962c63516c.js","/assets/theme-e2a65548f251d932.js","/assets/terminal-analytics-c88df3781ec9ac2a.js","/assets/account-panel-363d8aad362c6019.js","/assets/app-20a71021a62f78ed.js","/assets/privacy-center-ab4d906da15a44ed.js","/assets/styles-02bf667a187717cc.css"];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('league-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 if(request.method!=='GET'||url.origin!==self.location.origin||request.headers.has('Authorization')||url.pathname.startsWith('/api/')||url.pathname==='/data.json')return;
 if(request.mode==='navigate'){event.respondWith(fetch(request).catch(()=>caches.match('/offline.html')));return;}
 if(SHELL.includes(url.pathname))event.respondWith(caches.match(request).then(hit=>hit||fetch(request)));
});
