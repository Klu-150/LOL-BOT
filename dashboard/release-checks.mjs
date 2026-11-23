import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {validateRelease} from './release-policy.mjs';
import * as originalEngine from './dist/strategy-engine.js';
import * as originalPrivacy from './dist/privacy-center.js';
import * as originalMobile from './dist/mobile-app.js';
const root=fileURLToPath(new URL('./build',import.meta.url));
const report=await validateRelease(root);
assert.equal(report.files.length,27);
const stage=await fs.mkdtemp(path.join(os.tmpdir(),'league-release-check-'));
try{
 await fs.cp(root,stage,{recursive:true});
 async function rejectedFile(name,content,pattern){
  const target=path.join(stage,name);await fs.mkdir(path.dirname(target),{recursive:true});await fs.writeFile(target,content);
  try{await assert.rejects(validateRelease(stage),pattern);}finally{await fs.rm(target);}
 }
 await rejectedFile('app.js','export const rawSource=true;',/unexpected file/);
 await rejectedFile('.env','NOT_A_REAL_KEY=x',/unexpected file/);
 await rejectedFile('paper/account.sqlite3','test fixture',/unexpected directory/);await fs.rm(path.join(stage,'paper'),{recursive:true});
 await rejectedFile('assets/extra.js.map','{}',/unexpected file/);
 const dataPath=path.join(stage,'data.json'),data=await fs.readFile(dataPath);
 for(const [suffix,pattern,secrets] of [
  ['\n//# sourceMappingURL=app.js.map',/source_map/,[]],
  ['\n-----BEGIN PRIVATE KEY-----',/private_key/,[]],
  ['\nunit-test-known-credential-123456789012345',/known credential/,['unit-test-known-credential-123456789012345']]
 ]){await fs.appendFile(dataPath,suffix);try{await assert.rejects(validateRelease(stage,{knownSecrets:secrets}),pattern);}finally{await fs.writeFile(dataPath,data);}}
 const asset=report.files.find(item=>item.file.endsWith('.js')&&item.file.startsWith('assets/')).file;
 const assetPath=path.join(stage,asset),source=await fs.readFile(assetPath);await fs.appendFile(assetPath,'\n// tamper');
 await assert.rejects(validateRelease(stage),/fingerprint mismatch/);await fs.writeFile(assetPath,source);
 await fs.symlink(dataPath,path.join(stage,'leak.json'));await assert.rejects(validateRelease(stage),/symbolic link/);await fs.unlink(path.join(stage,'leak.json'));
 await fs.rm(path.join(stage,'privacy.html'));await assert.rejects(validateRelease(stage),/missing privacy.html/);
}finally{await fs.rm(stage,{recursive:true,force:true});}
async function built(name){const file=report.files.find(item=>item.file.startsWith('assets/'+name+'-')&&item.file.endsWith('.js'));assert.ok(file);return import(pathToFileURL(path.join(root,file.file)).href);}
const engine=await built('strategy-engine');
const dataset=JSON.parse(await fs.readFile(path.join(root,'strategy-data.json'),'utf8'));
const expected=originalEngine.backtestStrategy(originalEngine.template(),dataset);
const actual=engine.backtestStrategy(engine.template(),dataset);
assert.deepEqual(actual,expected,'The shipped backtest must produce exactly the same trades, exits and accounting');
const privacy=await built('privacy-center');
assert.equal(privacy.privacyPage(),originalPrivacy.privacyPage());
const mobile=await built('mobile-app');
assert.equal(mobile.serverOrigin('https://engine.example'),originalMobile.serverOrigin('https://engine.example'));
for(const value of ['http://engine.example','https://user:secret@engine.example','https://engine.example/?key=bad'])assert.throws(()=>mobile.serverOrigin(value));
console.log(`Release gates passed credential/map/private-file/symlink/tamper rejection and emitted-module parity (${actual.trades.length} modelled research trades).`);
