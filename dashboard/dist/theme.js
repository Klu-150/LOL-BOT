const KEY='league_theme_v2';
export function applyTheme(value,doc=globalThis.document,storage,persist=true){const theme=value==='dark'?'dark':'light';if(persist)try{(storage===undefined?globalThis.localStorage:storage)?.setItem(KEY,theme);}catch{}doc?.documentElement?.setAttribute('data-theme',theme);const meta=doc?.querySelector?.('meta[name="theme-color"]');if(meta)meta.setAttribute('content',theme==='dark'?'#07090c':'#f3f5f7');return theme;}
export function initializeTheme(doc=globalThis.document,storage){let value='dark';try{value=(storage===undefined?globalThis.localStorage:storage)?.getItem(KEY)||'dark';}catch{}return applyTheme(value,doc,storage,false);}
export function currentTheme(doc=globalThis.document){return doc?.documentElement?.getAttribute('data-theme')||'light';}
export function toggleTheme(doc=globalThis.document,storage){return applyTheme(currentTheme(doc)==='dark'?'light':'dark',doc,storage);}
