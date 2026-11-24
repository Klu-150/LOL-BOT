import {runResearch} from './platform-model-f1eba76098ddd6f0.js';
// This module must never install a Window message handler if imported outside
// its dedicated worker. Dedicated-worker channel messages normally use "" as
// origin; a non-empty origin must match the worker's own origin exactly.
if(typeof DedicatedWorkerGlobalScope!=='undefined'&&self instanceof DedicatedWorkerGlobalScope){
 self.onmessage=event=>{
  if(event.origin!==''&&event.origin!==self.location.origin)return;
  try{const {definition,dataset,range}=event.data;self.postMessage({result:runResearch(definition,dataset,range)});}
  catch(error){self.postMessage({error:error.message});}
 };
}
