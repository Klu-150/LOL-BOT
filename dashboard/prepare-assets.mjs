// Fingerprint all browser modules together so deployments cannot mix old/new code.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
const dist=fileURLToPath(new URL('./dist/',import.meta.url));
const assets=path.join(dist,'assets');
const historical=JSON.parse(await fs.readFile(path.join(dist,'strategy-data.json'),'utf8'));
await fs.writeFile(path.join(dist,'platform-config.json'),JSON.stringify({schema_version:1,config:historical.config,expiry_switch:historical.expiry_switch,reference_history:{first_bar:historical.first_bar,last_bar:historical.last_bar}}));
await fs.mkdir(assets,{recursive:true});
const seen=new Map(),visiting=new Set();
const digest=text=>crypto.createHash('sha256').update(text).digest('hex').slice(0,16);
async function emit(name){
 if(seen.has(name))return seen.get(name);
 if(visiting.has(name))throw new Error('Circular browser module: '+name);
 if(!/^[a-z-]+\.js$/.test(name))throw new Error('Unexpected browser module: '+name);
 visiting.add(name);
 let source=await fs.readFile(path.join(dist,name),'utf8');
 for(const match of [...source.matchAll(/from (['"])\.\/([a-z-]+\.js)\1/g)]){
  const child=await emit(match[2]);
  source=source.replace(match[0],`from '${'./'+child}'`);
 }
 for(const match of [...source.matchAll(/new URL\((['"])\.\/([a-z-]+\.js)\1,\s*import\.meta\.url\)/g)]){
  const child=await emit(match[2]);
  source=source.replace(match[0],`new URL('./${child}',import.meta.url)`);
 }
 const out=name.replace('.js',`-${digest(source)}.js`);
 await fs.writeFile(path.join(assets,out),source);
 visiting.delete(name);seen.set(name,out);return out;
}
const app=await emit('app.js');
const privacy=await emit('privacy-center.js');
const css=(await Promise.all(['styles.css','workspace.css'].map(name=>fs.readFile(path.join(dist,name),'utf8')))).join('\n');
const cssName=`styles-${digest(css)}.css`;
await fs.writeFile(path.join(assets,cssName),css);
const indexPath=path.join(dist,'index.html');
let html=await fs.readFile(indexPath,'utf8');
html=html.replace(/src="(?:app\.js|assets\/app-[a-f0-9]+\.js)"/,`src="assets/${app}"`)
 .replace(/href="(?:styles\.css|assets\/styles-[a-f0-9]+\.css)"/,`href="assets/${cssName}"`);
if(!html.includes(`assets/${app}`)||!html.includes(`assets/${cssName}`))throw new Error('Missing application asset links');
await fs.writeFile(indexPath,html);
const privacyPath=path.join(dist,'privacy.html');
let privacyHtml=await fs.readFile(privacyPath,'utf8');
privacyHtml=privacyHtml.replace(/src="(?:privacy-center\.js|assets\/privacy-center-[a-f0-9]+\.js)"/,`src="assets/${privacy}"`)
 .replace(/href="(?:styles\.css|assets\/styles-[a-f0-9]+\.css)"/,`href="assets/${cssName}"`);
if(!privacyHtml.includes(`assets/${privacy}`)||!privacyHtml.includes(`assets/${cssName}`))throw new Error('Missing privacy page asset links');
await fs.writeFile(privacyPath,privacyHtml);
// Remove only this generator's obsolete outputs.
const keep=new Set([...seen.values(),cssName]);
for(const file of await fs.readdir(assets))if(/^[a-z-]+-[a-f0-9]{16}\.(js|css)$/.test(file)&&!keep.has(file))await fs.unlink(path.join(assets,file));
console.log(`Prepared ${seen.size} versioned modules and stylesheet.`);
const offline=await fs.readFile(path.join(dist,'offline.html'),'utf8');
const precache=['/offline.html','/manifest.webmanifest','/icons/icon-192.png','/icons/icon-512.png','/icons/apple-touch-icon.png',...keep].map(p=>p.startsWith('/')?p:'/assets/'+p);
const version=digest(precache.join('\n')+offline);
await fs.writeFile(path.join(dist,'sw.js'),`// Static app shell only. Never cache API, account data, keys, or orders.
const CACHE='league-shell-${version}';
const SHELL=${JSON.stringify(precache)};
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)));});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('league-shell-')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 if(request.method!=='GET'||url.origin!==self.location.origin||request.headers.has('Authorization')||url.pathname.startsWith('/api/')||url.pathname==='/data.json')return;
 if(request.mode==='navigate'){event.respondWith(fetch(request).catch(()=>caches.match('/offline.html')));return;}
 if(SHELL.includes(url.pathname))event.respondWith(caches.match(request).then(hit=>hit||fetch(request)));
});
`);
