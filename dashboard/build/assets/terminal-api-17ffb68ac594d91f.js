// A restarted local server has a new session token. Reconnect before each action.
export const isLocalHost = hostname => ['localhost','127.0.0.1','::1','[::1]'].includes(hostname);
export function accountPath(path,profile){
 if(profile!=='adaptive25')return path;
 return ({'/api/dashboard':'/api/experiment/dashboard','/api/status':'/api/experiment/status',
  '/api/automation/start':'/api/experiment/start','/api/automation/pause':'/api/experiment/pause'})[path]||path;
}

export class TerminalApi {
 constructor(fetcher=(...args)=>fetch(...args),remote=false) { this.fetcher=fetcher; this.token=null;this.remote=remote;this.permissions={control:!remote};this.user=null;this.operations=null;this.supportsIdempotency=false;this.supportsExperiments=false; }
 async read(path, options={}) {
  let response;
  try { response=await this.fetcher(path,{cache:'no-store',signal:AbortSignal.timeout(8000),...options}); }
  catch { this.token=null; throw new Error(options.method==='POST'
   ? 'Could not confirm the action. Reconnect and check the engine status before trying again.'
   : this.remote?'The hosted paper engine is not responding. Check its address and hosting status.':'The local paper server is not responding. Open Launch Last of Our League.command, then reconnect.'); }
  let data;
  try { data=await response.json(); }
  catch { throw new Error('This page is not connected to the Python paper server. Launch the bot dashboard, then reconnect.'); }
  if(!response.ok) { const error=new Error(data.error||'The local operation failed.');error.status=response.status;throw error; }
  return data;
 }
 async connect() {
  this.token=null;
  const health=await this.read('/api/health');
  if(this.remote){
   if(health.status!=='ok'||health.mode!=='paper'||health.execution!=='cloud')throw new Error('This address is not a supported hosted paper engine.');
   this.permissions=health.permissions||{control:false};this.user=health.user||null;this.operations=health.operations||null;this.supportsIdempotency=health.capabilities?.idempotency===true;
   this.supportsExperiments=health.capabilities?.paper_experiments===true;
   return health.automation||{};
  }
  if(health.status!=='ok'||health.mode!=='paper'||typeof health.session_token!=='string'||!health.session_token)
   throw new Error('The local paper server did not return a valid session. Launch the bot dashboard, then reconnect.');
  this.token=health.session_token;
  return health.automation||{};
 }
 async action(path) {
  await this.connect();
  const actionKey=this.remote&&this.supportsIdempotency?globalThis.crypto.randomUUID():null;
  const post=()=>this.read(path,{method:'POST',headers:{...(this.remote?{}:{'X-Terminal-Token':this.token}),'Content-Type':'application/json',...(actionKey?{'Idempotency-Key':actionKey}:{})},body:'{}'});
  try { return await post(); }
  catch(error) {
   // Only a rejected session can safely be retried. Never replay an uncertain POST.
   if(this.remote||error.status!==403)throw error;
   await this.connect();
   return post();
  }
 }
}
