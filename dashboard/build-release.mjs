// Build a separate deployable tree. Source and private account state are never copied.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {STATIC_FILES,ICON_FILES,ASSET,validateRelease} from './release-policy.mjs';
const project=fileURLToPath(new URL('./',import.meta.url));
execFileSync(process.execPath,[path.join(project,'prepare-assets.mjs')],{cwd:project,stdio:'inherit'});
const input=path.join(project,'dist'),output=path.join(project,'build');
const stage=await fs.mkdtemp(path.join(project,'.release-stage-'));
try{
 async function copy(relative){
  const src=path.join(input,relative),dest=path.join(stage,relative);
  if(!(await fs.lstat(src)).isFile())throw Error('Release input must be a regular file: '+relative);
  await fs.mkdir(path.dirname(dest),{recursive:true});await fs.copyFile(src,dest);
 }
 for(const name of STATIC_FILES)await copy(name);
 for(const name of ICON_FILES)await copy('icons/'+name);
 for(const name of await fs.readdir(path.join(input,'assets'))){if(!ASSET.test(name))throw Error('Unexpected generated asset name');await copy('assets/'+name);}
 // Compare literal existing access keys privately; no value is printed or included in reports.
 let knownSecrets=[];
 try{const data=JSON.parse(await fs.readFile(path.join(project,'../paper/cloud-access/private-access.json'),'utf8'));knownSecrets=Object.values(data).map(user=>user.key).filter(value=>typeof value==='string'&&value.length>=24);}
 catch(error){if(error.code!=='ENOENT')throw Error('Local credential exclusion check unavailable; inspect private access configuration without publishing it.');}
 const report=await validateRelease(stage,{knownSecrets});knownSecrets=[];
 // Syntax-check exactly the JavaScript that will be deployed, without executing it.
 for(const item of report.files.filter(item=>item.file.endsWith('.js')))execFileSync(process.execPath,['--check',path.join(stage,item.file)],{stdio:'pipe'});
 await fs.rm(output,{recursive:true,force:true});await fs.rename(stage,output);
 await fs.writeFile(path.join(project,'release-audit.json'),JSON.stringify(report,null,2)+'\n');
 console.log(`Release verified: ${report.files.length} allowlisted files, ${report.total_bytes} bytes. No duplicate source modules or source maps are shipped.`);
}finally{await fs.rm(stage,{recursive:true,force:true});}
