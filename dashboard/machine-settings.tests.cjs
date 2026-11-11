const test=require('node:test');
const assert=require('node:assert/strict');
const {candidatesFor,assignmentPlan,selectedCandidate}=require('./machine-settings.js');
function fixture(){return {nodes:[
 {n:1,mac:'aabbcc000001',label:'North',node_id:99},
 {n:2,mac:null,label:'Whitener 2'},
 {n:3,mac:'aabbcc000003',label:'South',node_id:1}
],new:[{mac:'AA:BB:CC:00:00:03',n:77},{mac:'aabbcc000004',n:100}]};}
test('assigned receiver can move directly into an empty destination',()=>{
 const p=assignmentPlan(fixture(),2,'AA:BB:CC:00:00:01','  Whitener 2  ');
 assert.equal(p.move,true);assert.equal(p.replace,false);
 assert.equal(p.source.n,1);assert.equal(p.destination.n,2);
 assert.deepEqual(p.body,{mac:'aabbcc000001',label:'Whitener 2',expected_source_machine:1,expected_target_mac:null});
});
test('moving into occupied destination explicitly reports replacement',()=>{
 const p=assignmentPlan(fixture(),3,'aabbcc000001','South');
 assert.equal(p.move,true);assert.equal(p.replace,true);
 assert.equal(p.source.n,1);assert.equal(p.destination.mac,'aabbcc000003');
 assert.equal(p.body.expected_source_machine,1);assert.equal(p.body.expected_target_mac,'aabbcc000003');
});
test('rename of the current receiver is neither move nor replacement',()=>{
 const p=assignmentPlan(fixture(),1,'aabbcc000001','Updated north');
 assert.equal(p.move,false);assert.equal(p.replace,false);
});
test('choices include assigned devices, deduplicate MAC and use Hub assignment slot',()=>{
 const c=candidatesFor(fixture(),3);assert.equal(c.length,3);
 assert.equal(c[0].mac,'aabbcc000003');assert.equal(c[0].sourceSlot,3);
 assert.equal(c.find(n=>n.mac==='aabbcc000001').sourceSlot,1);
 assert.equal(c.find(n=>n.mac==='aabbcc000004').sourceSlot,null);
 assert.equal(c.filter(n=>n.mac.toLowerCase().replaceAll(':','')==='aabbcc000003').length,1);
});
test('changing destination preserves the explicitly selected receiver',()=>{
 const snap=fixture(),c=candidatesFor(snap,3);
 assert.equal(selectedCandidate(c,snap.nodes[2].mac,'AA:BB:CC:00:00:01'),'aabbcc000001');
 assert.equal(selectedCandidate(candidatesFor(snap,2),null,''),'aabbcc000004');
});
