import {runResearch} from './platform-model.js';
self.onmessage=event=>{try{const {definition,dataset,range}=event.data;self.postMessage({result:runResearch(definition,dataset,range)});}catch(error){self.postMessage({error:error.message});}};
