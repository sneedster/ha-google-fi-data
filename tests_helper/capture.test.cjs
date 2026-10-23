const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const core = require('../browser_helper/core.js');
const page = () => ({url:core.FI, member_id:'9007199254740993', token_present:true,
  user_agent:'Synthetic browser', session_index:'0'});
const cookie = () => ({name:'SID', value:'SYNTHETIC_NOT_A_CREDENTIAL', domain:'.google.com', secure:true, path:'/'});
function api(options={}) {
  let reads=0;
  return {tabs:{query:async()=>[{id:7,url:options.url||core.FI,cookieStoreId:'private'}]},
    scripting:{executeScript:async()=>[{result:reads++ && options.after ? options.after : page()}]},
    cookies:{getAllCookieStores:async()=>options.stores||[{id:'other',tabIds:[8]},{id:'private',tabIds:[7]}],
      getAll:async args=>{assert.deepEqual(args,{url:core.FI,storeId:'private'});return [cookie()];}}};
}

test('capture binds cookie reads to the active Fi tab store and contains no control context',async()=>{
  const result=JSON.parse(await core.capture(api()));
  assert.deepEqual(Object.keys(result).sort(),['cookies','user_agent']);
  assert.equal(result.cookies[0].value,cookie().value);
});
test('no cookie store fallback if the tab cannot be matched',async()=>{
  await assert.rejects(core.capture(api({stores:[{id:'other',tabIds:[8]}]})),/no_store/);
});
test('account or document changes during capture abort before copy',async()=>{
  for(const after of [{...page(),member_id:'456'}, {...page(),url:core.FI+'#account/2'}])
    await assert.rejects(core.capture(api({after})),/changed/);
});
test('non-Fi origins, HTTP, malformed URLs, and non-default Google accounts are rejected',()=>{
  for(const url of ['http://fi.google.com/account','https://fi.google.com.attacker.invalid/account',
    'https://fi.google.com/about','bad','https://fi.google.com/account?authuser=1'])
    assert.throws(()=>core.checkUrl(url));
});
test('missing tokens, malformed IDs and other session indices cannot be captured',()=>{
  for(const changes of [{member_id:'0'},{member_id:'18446744073709551616'},
    {token_present:false},{session_index:'1'},{user_agent:'secret\ninjection'}])
    assert.throws(()=>core.makeSession({...page(),...changes},[cookie()]));
});
test('only fixed auth-cookie names on exact Google/Fi domains and unpartitioned cookies survive',()=>{
  const values=[cookie(), {...cookie(),name:'analytics'}, {...cookie(),domain:'evilgoogle.com'},
    {...cookie(),domain:'.accounts.google.com'}, {...cookie(),partitionKey:{}},
    {...cookie(),firstPartyDomain:'other'},
    {...cookie(),name:'__Secure-1PSIDTS',expirationDate:2000000000}];
  const result=JSON.parse(core.makeSession(page(),values));
  assert.deepEqual(result.cookies.map(c=>c.name),['SID','__Secure-1PSIDTS']);
  assert.equal(result.cookies[1].expires,2000000000);
  assert.throws(()=>core.makeSession(page(),values.slice(1,-1)),/no_cookies/);
});
test('legacy login cookies need not have Secure set; exported cookies are always HTTPS-only',()=>{
  const values=['SID','HSID','APISID','SAPISID'].map(name=>({...cookie(),name,secure:false}));
  const result=JSON.parse(core.makeSession(page(),values));
  assert.deepEqual(result.cookies.map(c=>c.name),values.map(c=>c.name));
  assert.ok(result.cookies.every(c=>c.secure === true));
});
test('readFiPage reads DOM bootstrap without exposing CSRF token or executing page code',()=>{
  const result=vm.runInNewContext('('+core.readFiPage.toString()+')()',{
    document:{scripts:[{textContent:'window.WIZ_global_data={"EEqW7b":"9007199254740993","SNlM0e":"DO_NOT_RETURN"};window.SESSION_INDEX=0;'}]},
    location:{href:core.FI},navigator:{userAgent:'Synthetic browser'}});
  assert.equal(result.member_id,'9007199254740993');
  assert.equal(result.token_present,true);
  assert.equal(result.session_index,'0');
  assert.ok(!JSON.stringify(result).includes('DO_NOT_RETURN'));
});
test('helper manifest and implementation have no persistence, remote code, or network transport',()=>{
  const dir=path.join(__dirname,'../browser_helper');
  const manifest=JSON.parse(fs.readFileSync(path.join(dir,'manifest.json')));
  assert.deepEqual(manifest.permissions.sort(),['activeTab','clipboardWrite','cookies','scripting']);
  assert.ok(!manifest.background);
  assert.ok(!manifest.externally_connectable);
  assert.match(manifest.content_security_policy.extension_pages,/connect-src 'none'/);
  const source=['core.js','popup.js'].map(f=>fs.readFileSync(path.join(dir,f),'utf8')).join('\n');
  assert.doesNotMatch(source,/\bfetch\s*\(|XMLHttpRequest|sendBeacon|localStorage|\.storage\.|cookies\.(set|remove)\s*\(/);
});
