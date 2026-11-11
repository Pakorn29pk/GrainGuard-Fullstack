const test=require('node:test');
const assert=require('node:assert/strict');
const A=require('./alerts.js');
const M=require('./model.js');
const catalog={codes:[
 {code:'E101',sev:'fault',th:'เซนเซอร์ไม่มีสัญญาณ'},
 {code:'E102',sev:'fault',th:'สัญญาณล้น'},
 {code:'E104',sev:'warn',th:'สัญญาณรบกวนสูงผิดปกติ'},
 {code:'E111',sev:'fault',th:'ช่อง B ไม่มีสัญญาณ'},
 {code:'E112',sev:'fault',th:'ช่อง B สัญญาณล้น'},
 {code:'E201',sev:'fault',th:'แรงดันไฟเลี้ยงต่ำ'},
 {code:'E203',sev:'warn',th:'อุณหภูมิบอร์ดสูง'},
 {code:'E303',sev:'info',th:'เฟิร์มแวร์ไม่ตรงเวอร์ชัน'},
]};
function node(extra={}){
 const raw={n:1,mac:'aabbccddeeff',label:'Machine 1',cls:'ok',state:'RUN',last_state:'RUN',mode:'ALARM_ON',ratio:0,ratio_b:0,fa:0,chb:true,b:{flt:0},last_seen_s:1,codes:[],errors:[],...extra};
 return M.normalizeSnapshot({nodes:[raw]},[raw.n])[0];
}

test('real zero readings are not a diagnosis or a reason to manufacture warnings',()=>{
 const n=node(),r=A.assessNode(n,catalog,'en');
 assert.equal(r.level,'normal');assert.equal(r.needsAttention,false);assert.equal(n.a,0);
 assert.deepEqual(r.channels,{a:'normal',b:'normal'});assert.deepEqual(r.issues,[]);
});
test('fault codes override a generic Hub warn presentation without changing classification',()=>{
 const n=node({cls:'warn',codes:['E102']}),r=A.assessNode(n,catalog,'th');
 assert.equal(r.level,'fault');assert.equal(n.status,'warn');assert.equal(r.channels.a,'fault');
 assert.equal(r.issues[0].title,'สัญญาณล้น');assert.equal(r.issues[0].channel,'a');
});
test('E104 is a warning, and English titles do not leak Thai catalog text',()=>{
 const r=A.assessNode(node({cls:'warn',codes:['E104']}),catalog,'en');
 assert.equal(r.level,'warning');assert.equal(r.channels.a,'warning');assert.equal(r.channels.b,'normal');
 assert.equal(r.issues[0].title,'High signal noise');assert.ok(!/[ก-๙]/.test(r.summary));
});
test('two reported channel faults receive independent sensor quality states',()=>{
 const r=A.assessNode(node({cls:'warn',codes:['E102','E112']}),catalog,'en');
 assert.equal(r.level,'fault');assert.deepEqual(r.channels,{a:'fault',b:'fault'});
 assert.deepEqual(r.issues.map(i=>i.code),['E102','E112']);
});
test('errors entries are accepted and duplicate codes are not repeated',()=>{
 const n=node({cls:'warn',codes:['E101'],errors:[{code:'E101',since:123},{code:'E112',since:124}]});
 const r=A.assessNode(n,catalog,'en');assert.equal(r.issues.length,2);
});
test('disabled Piezo does not create a fault from stale B codes or reported B flag',()=>{
 const r=A.assessNode(node({chb:false,codes:['E111','E112'],b:{flt:2}}),catalog,'en');
 assert.equal(r.level,'normal');assert.equal(r.channels.b,'unknown');assert.equal(r.issues.length,0);
});
test('Node power fault is visible without claiming both sensors are physically broken',()=>{
 const r=A.assessNode(node({cls:'warn',codes:['E201']}),catalog,'en');
 assert.equal(r.level,'fault');assert.equal(r.issues[0].channel,'power');
 assert.deepEqual(r.channels,{a:'unknown',b:'unknown'});
});
test('live raw FAULT without a code still gets a conspicuous equipment fault',()=>{
 const r=A.assessNode(node({cls:'warn',state:'FAULT',last_state:'FAULT'}),{},'en');
 assert.equal(r.level,'fault');assert.match(r.summary,/FAULT/);assert.equal(r.issues.length,0);
});
test('raw A/B fault flags are direct evidence without inventing matured E1xx codes',()=>{
 const n=node({fa:2,b:{flt:1}}),r=A.assessNode(n,{},'en');
 assert.equal(n.status,'run');assert.equal(r.level,'fault');
 assert.deepEqual(r.channels,{a:'fault',b:'fault'});
 assert.deepEqual(r.issues.map(i=>i.code).sort(),['b.flt=1','fa=2']);
 assert.ok(r.issues.every(i=>i.source==='node-flag'));
 assert.match(r.issues.find(i=>i.channel==='a').title,/saturation/);
 assert.match(r.issues.find(i=>i.channel==='b').title,/flatline/);
});
test('matching mature code suppresses duplicate flag issue on that channel',()=>{
 const r=A.assessNode(node({cls:'warn',fa:2,codes:['E102']}),catalog,'en');
 assert.equal(r.issues.length,1);assert.equal(r.issues[0].code,'E102');
});
test('offline remains visible and does not assert current sensor quality',()=>{
 const n=node({cls:'offline',state:'OFFLINE',fa:2,codes:['E301']}),r=A.assessNode(n,catalog,'en');
 assert.equal(r.level,'offline');assert.equal(r.needsAttention,true);assert.equal(n.mac,'aabbccddeeff');
 assert.deepEqual(r.channels,{a:'unknown',b:'unknown'});assert.ok(!r.issues.some(i=>i.source==='node-flag'));
});
test('lost Hub does not become a Node-offline or cached sensor-fault diagnosis',()=>{
 const n=node({cls:'warn',codes:['E102'],fa:2});n.status='unknown';n.reason='hub_lost';
 const r=A.assessNode(n,catalog,'en');assert.equal(r.level,'unknown');assert.equal(r.issues.length,0);
 assert.deepEqual(r.channels,{a:'unknown',b:'unknown'});assert.match(r.summary,/Hub is unreachable/);
});
test('acknowledgement cannot clear a real active alarm in the UI',()=>{
 const n=node({cls:'alarm',state:'ALARM',last_state:'ALARM',alarm_active:true,ack:1});
 const r=A.assessNode(n,catalog,'en');assert.equal(r.level,'alarm');assert.equal(r.rank,100);
 assert.equal(n.ack,true);assert.equal(n.status,'alarm');
});
test('SHADOW and RECORD observations are not promoted to physical production alarms',()=>{
 for(const mode of ['SHADOW','RECORD']){
  const n=node({cls:'shadow',mode,state:'ALARM',last_state:'ALARM',alarm_active:true,alarm_shadow:true});
  const r=A.assessNode(n,catalog,'en');assert.equal(r.level,'learning');assert.equal(r.needsAttention,false);
  assert.match(r.summary,/not a production alarm/);
 }
});
test('quiet mode does not suppress actual equipment fault codes',()=>{
 const r=A.assessNode(node({cls:'warn',mode:'SHADOW',codes:['E102']}),catalog,'en');
 assert.equal(r.level,'fault');assert.equal(r.needsAttention,true);
});
test('RUN in SHADOW mode remains a normal running machine',()=>{
 const r=A.assessNode(node({mode:'SHADOW',state:'RUN',last_state:'RUN'}),catalog,'en');
 assert.equal(r.level,'normal');assert.equal(r.title,'Running');assert.equal(r.needsAttention,false);
});
test('REST in SHADOW mode remains normal idle, not a shadow observation',()=>{
 const r=A.assessNode(node({mode:'SHADOW',state:'REST',last_state:'REST'}),catalog,'en');
 assert.equal(r.level,'normal');assert.equal(r.title,'Machine idle');assert.equal(r.needsAttention,false);
});
test('CAL in SHADOW mode explicitly shows baseline learning',()=>{
 const r=A.assessNode(node({cls:'cal',mode:'SHADOW',state:'CAL',last_state:'CAL'}),catalog,'en');
 assert.equal(r.level,'learning');assert.equal(r.title,'Learning baseline');
 assert.ok(!r.summary.includes('not a production alarm'));
});
test('unknown catalog code shows the code without inventing a diagnosis',()=>{
 const r=A.assessNode(node({cls:'warn',codes:['E777']}),{E777:{sev:'fault'}},'en');
 assert.equal(r.level,'fault');assert.equal(r.issues[0].title,'E777');assert.equal(r.issues[0].channel,null);
});
test('informational code alone does not turn running machine into a fault',()=>{
 const r=A.assessNode(node({codes:['E303']}),catalog,'en');assert.equal(r.level,'normal');
 assert.equal(r.issues[0].severity,'info');assert.equal(r.needsAttention,false);
});
test('overview sorts alerts by priority without mutating or reordering machine cards',()=>{
 const normal=node(),warn=node({n:2,cls:'warn',codes:['E104']}),fault=node({n:3,cls:'warn',codes:['E102']}),alarm=node({n:4,cls:'alarm',state:'ALARM',alarm_active:true});
 const nodes=[normal,warn,fault,alarm],before=[...nodes];const result=A.collect(nodes,catalog,'en');
 assert.deepEqual(result.map(a=>a.assessment.level),['alarm','fault','warning']);
 assert.deepEqual(nodes,before);assert.equal(result[0].node,alarm);assert.equal(result.length,3);
});
