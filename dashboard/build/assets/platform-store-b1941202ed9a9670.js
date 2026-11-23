import {accountSummary,tradeKey} from './platform-model-f1eba76098ddd6f0.js';
const KEY='league_tools_v1',types=['price_above','price_below','daily_loss','drawdown','engine'];
const own=(v)=>v!==null&&typeof v==='object'&&!Array.isArray(v);
export class PlatformStore{
 constructor(storage){try{this.storage=storage===undefined?globalThis.localStorage:storage;}catch{this.storage=null;}this.problem='';this.data={version:1,alerts:[],events:[],active:{},notes:{}};
  try{const raw=this.storage?.getItem(KEY);if(raw){const v=JSON.parse(raw);if(v.version!==1||!Array.isArray(v.alerts)||v.alerts.length>30||!Array.isArray(v.events)||v.events.length>100||!own(v.notes)||Object.keys(v.notes).length>500)throw Error();
   for(const a of v.alerts)this.validateAlert(a);
   this.data={version:1,alerts:v.alerts,events:v.events.filter(r=>own(r)&&typeof r.message==='string'&&r.message.length<500).slice(0,100),active:own(v.active)?v.active:{},notes:{}};
   for(const [k,n]of Object.entries(v.notes)){if(k.startsWith('v1:')&&k.length<300&&own(n)&&typeof n.text==='string'&&n.text.length<=2000&&typeof n.tags==='string'&&n.tags.length<=120)this.data.notes[k]={text:n.text,tags:n.tags,updated_at:String(n.updated_at||'')};}
  }}catch{this.problem='Saved alerts or notes could not be read. Existing device storage was left intact.';}
 }
 validateAlert(a){if(!own(a)||typeof a.id!=='string'||!/^[A-Za-z0-9-]{8,80}$/.test(a.id)||typeof a.label!=='string'||!a.label.trim()||a.label.length>80||!types.includes(a.type)||typeof a.enabled!=='boolean'||!Number.isFinite(a.threshold)||a.threshold<0||a.threshold>1e7||a.type!=='engine'&&a.threshold===0)throw Error('Use a supported alert, an 80-character label and a positive threshold (unused for engine alerts).');if(['drawdown','daily_loss'].includes(a.type)&&a.threshold>100)throw Error('Use percentages between 0 and 100.');}
 commit(next){if(!this.storage)throw Error('Device storage is unavailable. Notes and alerts cannot be saved.');this.storage.setItem(KEY,JSON.stringify(next));this.data=next;}
 addAlert({label,type,threshold}){if(this.data.alerts.length>=30)throw Error('Keep up to 30 device alerts.');const alert={id:crypto.randomUUID(),label:label.trim(),type,threshold:threshold===''?0:Number(threshold),enabled:true};this.validateAlert(alert);this.commit({...this.data,alerts:[...this.data.alerts,alert]});return alert;}
 toggle(id){this.commit({...this.data,alerts:this.data.alerts.map(a=>a.id===id?{...a,enabled:!a.enabled}:a),active:{...this.data.active,[id]:false}});}
 remove(id){const active={...this.data.active};delete active[id];this.commit({...this.data,alerts:this.data.alerts.filter(a=>a.id!==id),active});}
 rearm(id){this.commit({...this.data,active:{...this.data.active,[id]:false}});}
 acknowledge(){this.commit({...this.data,events:this.data.events.map(e=>({...e,read:true}))});}
 saveNote(paper,trade,{text,tags}){if(typeof text!=='string'||text.length>2000||typeof tags!=='string'||tags.length>120)throw Error('Use up to 2,000 characters for a note and 120 for tags.');const key=tradeKey(paper,trade);if(!Object.hasOwn(this.data.notes,key)&&Object.keys(this.data.notes).length>=500)throw Error('Export notes before adding more than 500 records.');this.commit({...this.data,notes:{...this.data.notes,[key]:{text,tags,updated_at:new Date().toISOString()}}});}
 note(paper,trade){return this.data.notes[tradeKey(paper,trade)]||{text:'',tags:''};}
 unread(){return this.data.events.filter(e=>!e.read).length;}
 observe(snapshot,automation,mode,now=Date.now()){
  if(!this.data.alerts.some(a=>a.enabled))return [];
  const s=accountSummary(snapshot,automation,mode,now),active={...this.data.active},added=[];
  for(const a of this.data.alerts){if(!a.enabled)continue;let met=false,value=null;
   if(a.type==='engine')met=mode.endsWith('disconnected')||s.connected&&(['error','data_error','stopped','square_off_waiting_for_data','storage_guard'].includes(automation.state)||!Number.isFinite(s.heartbeat_seconds)||s.heartbeat_seconds>180);
   else if(s.connected&&a.type==='daily_loss'){value=s.today_net;met=Number.isFinite(s.daily_loss_budget)&&s.today_net<=-(snapshot.paper?.session===s.day?snapshot.paper.session_equity:s.equity)*a.threshold/100;}
   else if(s.connected&&a.type==='drawdown'){value=s.drawdown_percent;met=Number.isFinite(value)&&value>=a.threshold;}
   else if(s.fresh&&Number.isFinite(s.bar?.Close)){value=s.bar.Close;met=a.type==='price_above'?value>=a.threshold:value<=a.threshold;}
   else if(a.type!=='engine')continue; // Stale data never rearms a price alert.
   if(met&&!active[a.id])added.push({id:crypto.randomUUID(),alert_id:a.id,label:a.label,message:a.type==='engine'?'Engine connection, heartbeat or data requires attention. Check the risk centre.':`${a.label}: observed ${Number(value).toFixed(2)}.`,at:new Date(now).toISOString(),source_bar:s.stamp||null,read:false});
   active[a.id]=met;
  }
  if(added.length||JSON.stringify(active)!==JSON.stringify(this.data.active))this.commit({...this.data,active,events:[...added,...this.data.events].slice(0,100)});
  return added;
 }
 exportNotes(){return {schema_version:1,type:'trading_notes',notes:this.data.notes};}
 importNotes(raw){if(raw.length>2*1024*1024)throw Error('Use notes exports smaller than 2 MB.');const parsed=JSON.parse(raw);if(parsed.schema_version!==1||parsed.type!=='trading_notes'||!own(parsed.notes))throw Error('Choose a trading-notes export.');const next={...this.data.notes};for(const [key,note]of Object.entries(parsed.notes)){if(!key.startsWith('v1:')||key.length>300||!own(note)||typeof note.text!=='string'||note.text.length>2000||typeof note.tags!=='string'||note.tags.length>120)throw Error('Invalid note record.');next[key]={text:note.text,tags:note.tags,updated_at:String(note.updated_at||'')};}if(Object.keys(next).length>500)throw Error('A device can keep up to 500 note records.');this.commit({...this.data,notes:next});}
}
