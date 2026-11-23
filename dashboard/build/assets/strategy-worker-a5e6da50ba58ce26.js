import {runResearch} from './platform-model-f1eba76098ddd6f0.js';
self.onmessage=event=>{try{const {definition,dataset,range}=event.data;self.postMessage({result:runResearch(definition,dataset,range)});}catch(error){self.postMessage({error:error.message});}};
