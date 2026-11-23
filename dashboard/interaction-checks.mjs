import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('./dist/app.js',import.meta.url),'utf8');
const script=source.slice(source.indexOf('function clearChartHover(){'),source.indexOf('\nasync function load('));
const events=()=>{const handlers=new Map();return {handlers,addEventListener(name,handler,options){const rows=handlers.get(name)||[];rows.push({handler,options});handlers.set(name,rows)},fire(name,event={}){for(const {handler}of handlers.get(name)||[])handler(event)}}};
const tip={style:{},innerHTML:''},line={attributes:{},setAttribute(k,v){this.attributes[k]=v}},wrap={querySelector:selector=>selector==='.chart-tooltip'?tip:null};
const svg={...events(),dataset:{chart:'fixture'},parentElement:wrap,querySelector:selector=>selector==='.crosshair'?line:null,getBoundingClientRect:()=>({left:0,top:0,right:600,bottom:250,width:600,height:250})};
const document={...events(),querySelectorAll:selector=>selector==='[data-chart]'?[svg]:selector==='.chart-tooltip'?[tip]:selector==='.crosshair'?[line]:[]},window=events();
const context=vm.createContext({document,window,charts:{fixture:{W:600,L:20,pw:560,dates:['2026-11-19','2026-11-20'],series:[{name:'Paper account',color:'#007f75',points:[['2026-11-19',100],['2026-11-20',200]]}],unit:'rupees'}},$: (selector,root)=>root.querySelector(selector),$$:selector=>document.querySelectorAll(selector),e:value=>String(value),date:value=>value,money:value=>'₹'+value,num:value=>String(value),Math});
vm.runInContext(script+'\ninstallChartHoverCleanup(document,window);bindCharts();',context);
const move=(extra={})=>svg.fire('pointermove',{clientX:300,clientY:100,pointerType:'mouse',buttons:0,...extra});
const visible=()=>{assert.equal(tip.style.display,'block');assert.equal(line.attributes.visibility,'visible');};
const hidden=()=>{assert.equal(tip.style.display,'none');assert.equal(line.attributes.visibility,'hidden');};
move();visible();assert.match(tip.innerHTML,/Paper account/);
for(const name of ['pointerleave','pointercancel','pointerdown','pointerup']){move();visible();svg.fire(name);hidden();}
for(const name of ['scroll','pointerdown','pointercancel','visibilitychange','focusin']){move();visible();document.fire(name);hidden();}
for(const name of ['blur','pagehide']){move();visible();window.fire(name);hidden();}
move();document.fire('keydown',{key:'Escape'});hidden();
move();document.fire('keydown',{key:'a'});visible();
for(const extra of [{pointerType:'touch'},{buttons:1},{clientX:-1},{clientY:300}]){move();visible();move(extra);hidden();}
assert.equal(document.handlers.get('scroll')[0].options,true,'nested scroll containers must clear hover through capture');
assert.equal(document.handlers.get('scroll').length,1);
const css=fs.readFileSync(new URL('./dist/styles.css',import.meta.url),'utf8');
const hovered=[...css.matchAll(/\.data-table tbody tr:hover td\{([^}]*)\}/g)];assert.ok(hovered.length);assert.ok(hovered.every(m=>m[1].includes('background:var(--soft)')),'higher-specificity legacy hover rules must be theme-aware');
assert.match(css,/\.data-table tbody tr\.selected:hover td\{background:var\(--green-light\)\}/);
for(const selector of ['.watch-row.active','.compare-chip.active','.router-tile.current']){const rules=[...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter(m=>m[1].trim()===selector);assert.ok(rules.at(-1)?.[2].includes('background:var(--green-light)'),selector+' must use theme colors');}
assert.ok(css.lastIndexOf('.panel-header .range-control{background:var(--soft)')>css.lastIndexOf('.panel-header .range-control{background:#'));
console.log('Interaction regression checks passed theme-aware row/selection colors and chart dismissal on leave, scroll, cancellation, touch, focus, Escape, backgrounding and window blur.');
