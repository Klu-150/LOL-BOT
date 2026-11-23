// Static app shell only. Never cache API, account data, keys, or orders.
const CACHE='league-shell-bbd831a2112067e5';
const SHELL=["/offline.html","/manifest.webmanifest","/icons/icon-192.png","/icons/icon-512.png","/icons/apple-touch-icon.png","/assets/execution-view-f1b717ac6ba642f9.js","/assets/terminal-41fdf28093f9a999.js","/assets/terminal-api-954788358d3cf4e2.js","/assets/mobile-app-ff46d89149c30098.js","/assets/strategy-engine-251c64dd6c468073.js","/assets/platform-model-f1eba76098ddd6f0.js","/assets/strategy-worker-a5e6da50ba58ce26.js","/assets/strategy-workshop-8378ca6fa22333db.js","/assets/platform-store-b1941202ed9a9670.js","/assets/trading-tools-c832e834da67bbeb.js","/assets/theme-132cccc706771f04.js","/assets/app-dc64357f60e3c041.js","/assets/privacy-center-ef740234da1be8ac.js","/assets/styles-50e6b4a4eb2c1a65.css"];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('league-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 if(request.method!=='GET'||url.origin!==self.location.origin||request.headers.has('Authorization')||url.pathname.startsWith('/api/')||url.pathname==='/data.json')return;
 if(request.mode==='navigate'){event.respondWith(fetch(request).catch(()=>caches.match('/offline.html')));return;}
 if(SHELL.includes(url.pathname))event.respondWith(caches.match(request).then(hit=>hit||fetch(request)));
});
