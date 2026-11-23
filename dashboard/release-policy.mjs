// Fail-closed static release policy. No third-party code or telemetry.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
export const STATIC_FILES=Object.freeze(['index.html','privacy.html','offline.html','sw.js','manifest.webmanifest','data.json','strategy-data.json','platform-config.json','third-party-notices.txt']);
export const ICON_FILES=Object.freeze(['icon-192.png','icon-512.png','icon-maskable.png','apple-touch-icon.png']);
export const ASSET=/^[a-z-]+-[a-f0-9]{16}\.(js|css)$/;
const forbiddenText=[
 ['private_key',/-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----/],
 ['github_token',/\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b/],
 ['aws_access_key',/\b(?:AKIA|ASIA)[A-Z0-9]{16}\b/],
 ['credential_assignment',/(?:api[_-]?key|secret[_-]?key|access[_-]?token|client[_-]?secret|password)["']?\s*[:=]\s*["'][A-Za-z0-9_+\/-]{24,}["']/i],
 ['source_map',/sourceMappingURL\s*=|["']sourcesContent["']\s*:/],
 ['developer_home_path',/\/Users\/[A-Za-z0-9._-]+\//]
];
export function assertPublicText(text,label,knownSecrets=[]){
 for(const [kind,pattern] of forbiddenText)if(pattern.test(text))throw Error(`Release blocked: ${kind} in ${label}`);
 for(const secret of knownSecrets)if(typeof secret==='string'&&secret.length>=24&&text.includes(secret))throw Error(`Release blocked: known credential in ${label}`);
}
export async function validateRelease(root,{knownSecrets=[]}={}){
 const seen=[],inventory=[];let total=0;
 async function walk(relative=''){
  for(const item of await fs.readdir(path.join(root,relative),{withFileTypes:true})){
   const name=relative?relative+'/'+item.name:item.name;
   if(item.isSymbolicLink())throw Error('Release blocked: symbolic link '+name);
   if(item.isDirectory()){
    if(!['assets','icons'].includes(name))throw Error('Release blocked: unexpected directory '+name);
    await walk(name);continue;
   }
   if(!item.isFile())throw Error('Release blocked: non-regular file '+name);
   const allowed=STATIC_FILES.includes(name)||name.startsWith('assets/')&&ASSET.test(name.slice(7))||name.startsWith('icons/')&&ICON_FILES.includes(name.slice(6));
   if(!allowed)throw Error('Release blocked: unexpected file '+name);
   const data=await fs.readFile(path.join(root,name));total+=data.length;
   if(data.length>32*1024**2||total>64*1024**2)throw Error('Release blocked: artifact size limit');
   if(!name.endsWith('.png'))assertPublicText(data.toString('utf8'),name,knownSecrets);
   if(name.startsWith('assets/')){
    const hash=crypto.createHash('sha256').update(data).digest('hex').slice(0,16);
    if(!name.endsWith('-'+hash+path.extname(name)))throw Error('Release blocked: asset fingerprint mismatch '+name);
   }
   seen.push(name);inventory.push({file:name,bytes:data.length,sha256:crypto.createHash('sha256').update(data).digest('hex')});
  }
 }
 await walk();
 for(const required of [...STATIC_FILES,...ICON_FILES.map(name=>'icons/'+name)])if(!seen.includes(required))throw Error('Release blocked: missing '+required);
 // Every static import and worker URL must resolve to an emitted hashed module.
 for(const name of seen.filter(name=>name.startsWith('assets/')&&name.endsWith('.js'))){
  const source=await fs.readFile(path.join(root,name),'utf8');
  for(const match of source.matchAll(/(?:from\s*['"]\.\/|new URL\(['"]\.\/)([^'"]+)/g))if(!ASSET.test(match[1])||!seen.includes('assets/'+match[1]))throw Error('Release blocked: unresolved module '+name);
 }
 for(const name of ['index.html','privacy.html']){
  const html=await fs.readFile(path.join(root,name),'utf8');
  const modules=[...html.matchAll(/(?:src|href)="(assets\/[^"#?]+)"/g)].map(match=>match[1]);
  if(modules.length!==2||modules.some(asset=>!seen.includes(asset)))throw Error('Release blocked: invalid HTML entry '+name);
 }
 return {schema_version:1,files:inventory.sort((a,b)=>a.file.localeCompare(b.file)),total_bytes:total,
  checks:{allowlist:true,symlinks_rejected:true,asset_hashes:true,source_maps_absent:true,known_credential_values_checked:knownSecrets.length,credential_patterns:true,local_module_links:true},
  limitations:'Pattern scanning is not proof of absence of secrets. Browser code and research rules remain readable and copyable.'};
}
