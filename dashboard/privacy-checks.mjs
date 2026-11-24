import assert from 'node:assert/strict';
import fs from 'node:fs';
import {DEVICE_KEYS,deviceInventory,exportDeviceData,clearDeviceCategory,privacyPage} from './dist/privacy-center.js';
import {initializeTheme,toggleTheme} from './dist/theme.js';
const memory=new Map([
 ['league_tools_v1',JSON.stringify({notes:{test:{text:'Private தமிழ் note'}}})],
 ['league_strategy_library_v1','{"version":1,"items":[]}'],
 ['league_theme_v2','dark'],['league_cloud_server','https://example.com'],
 ['league_terminal_panels_v1','["log","chain","payoff","surface"]'],
 ['unrelated_host_cookie','preserve'],['private_access_key','NEVER_EXPORT']
]);
const storage={getItem:key=>memory.has(key)?memory.get(key):null,removeItem:key=>memory.delete(key),setItem:(key,value)=>memory.set(key,value)};
const inventory=deviceInventory(storage);
assert.equal(inventory.length,5);
assert.equal(inventory[0].key,DEVICE_KEYS.strategies[0]);
assert.equal(inventory.find(row=>row.key==='league_tools_v1').bytes,new TextEncoder().encode(memory.get('league_tools_v1')).length);
const output=exportDeviceData(storage);
assert.ok(output.values.league_tools_v1.includes('தமிழ்'));
assert.ok(output.values.league_terminal_panels_v1.includes('log'));
assert.ok(!JSON.stringify(output).includes('NEVER_EXPORT'));
assert.ok(!Object.hasOwn(output.values,'unrelated_host_cookie'));
assert.throws(()=>clearDeviceCategory(storage,'__proto__'));
assert.throws(()=>clearDeviceCategory(storage,'private_access_key'));
clearDeviceCategory(storage,'notes');
assert.equal(storage.getItem('league_tools_v1'),null);
assert.ok(storage.getItem('league_strategy_library_v1'));
assert.equal(storage.getItem('league_theme_v2'),'dark');
clearDeviceCategory(storage,'all');
assert.equal(storage.getItem('league_terminal_panels_v1'),null);
assert.ok(deviceInventory(storage).every(row=>!row.present));
assert.equal(storage.getItem('unrelated_host_cookie'),'preserve');
assert.equal(storage.getItem('private_access_key'),'NEVER_EXPORT');
const html=privacyPage([{key:'<img onerror=alert(1)>',present:true,bytes:1}],'<script>bad</script>');
assert.ok(!html.includes('<img onerror='));assert.ok(!html.includes('<script>bad'));
for(const label of ['Privacy notice','Usage rules','Manage this browser','Providers, cookies & licences','Venkata Madhan Kanakala','seven-day','20,000','no automatic age-based deletion','no checkout'])assert.ok(html.includes(label),label);
const source=fs.readFileSync(new URL('./dist/privacy-center.js',import.meta.url),'utf8');
assert.ok(!/\bfetch\s*\(/.test(source),'Device actions must not call the engine');
assert.ok(source.includes('globalThis.confirm('),'Irreversible device deletion requires explicit confirmation');
assert.ok(!source.includes('localStorage.clear('),'Never erase unowned origin data');
let theme='light',writes=0;
const doc={documentElement:{setAttribute:(_,value)=>theme=value,getAttribute:()=>theme},querySelector:()=>null};
const themeStorage={getItem:()=>null,setItem:()=>writes++};
initializeTheme(doc,themeStorage);assert.equal(writes,0,'Opening a page must not persist a default theme');
toggleTheme(doc,themeStorage);assert.equal(writes,1,'An explicitly requested theme choice may be remembered');
assert.ok(fs.readFileSync(new URL('./dist/app.js',import.meta.url),'utf8').includes('href="privacy.html"'));
assert.ok(fs.statSync(new URL('./dist/third-party-notices.txt',import.meta.url)).size>1000);
console.log('Privacy controls passed scoped export/deletion, unknown-key preservation, UTF-8 sizes, XSS, cloud isolation, notices and default-theme minimization checks.');

assert.ok(html.includes("kvenkatamadhan734@gmail.com") && html.includes("India"));
assert.ok(!html.includes("Operator identity and public privacy contact are awaiting confirmation"));
