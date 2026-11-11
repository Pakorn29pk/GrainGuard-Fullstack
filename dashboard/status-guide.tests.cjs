const test = require('node:test');
const assert = require('node:assert/strict');
const alerts = require('./alerts.js');
const monitor = require('./monitor-view.js');

function fixture(lang, overrides = {}) {
  const nodes = [
    {id:1, mac:'020000000001', status:'warn', codes:['E104']},
    {id:2, mac:'020000000002', status:'warn', codes:['E101']},
    {id:3, mac:'020000000003', status:'alarm', mode:'ALARM_ON', codes:['E104']},
    {id:4, mac:'020000000004', status:'offline', codes:['E301']},
  ];
  const escape = value => String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  return {
    lang, nodes, connected:true, started:true, filter:'all', snapshot:{hub:{codes:['E501']}},
    assess:node => alerts.assessNode(node,[],lang), attentionItems:() => alerts.collect(nodes,[],lang),
    esc:escape, name:node => `Mill & Node ${node.id}`, icon:() => '', statusIcon:level => level,
    readings:() => '', age:() => '', btn:(label,action,_kind,_icon,attrs='') => `<button data-action="${action}" ${attrs}>${label}</button>`,
    pendingCards:() => '', offlineGroup:() => '', systemRows:() => '', ...overrides
  };
}

test('warning machines contribute to Equipment fault while process alarm remains separate', () => {
  const c = fixture('en');
  const original = c.assess(c.nodes[0]);
  const display = monitor.displayAssessment(original,'en');
  assert.equal(original.level,'warning');
  assert.equal(display.title,'Equipment fault');
  assert.equal(display.rank,original.rank);
  assert.deepEqual(display.issues,original.issues);
  assert.deepEqual(monitor.counts(c),{alarm:1,fault:2,offline:1,normal:0,rest:0,learning:0,unknown:0,empty:0});
  const markup = monitor.overview(c);
  assert.match(markup,/data-level="fault" data-node="1"/);
  assert.match(markup,/data-level="alarm" data-node="3"/);
  assert.match(markup,/Equipment fault<\/span><strong>2<\/strong>/);
  assert.doesNotMatch(markup,/Check required|data-level="warning"|class="eyebrow"/);
});

test('Operating guide keeps diagnostics accessible while defaulting to an action-first summary in both languages', () => {
  for(const lang of ['th','en']){
    const markup=monitor.guide(fixture(lang));
    assert.doesNotMatch(markup,/Check required|ควรตรวจสอบ|class="eyebrow"|data-level="warning"/);
    assert.match(markup,/data-guide-disclosure="node-1"/);
    assert.match(markup,/data-guide-disclosure="legend"/);
    assert.match(markup,/<code>E104<\/code>/);
    assert.match(markup,/Mill &amp; Node 1/);
    assert.match(markup,/data-action="detail" data-id="1"/);
    assert.match(markup,lang==='en'?/Inspection steps/:/ขั้นตอนตรวจเครื่อง/);
    const faultCard=markup.match(/<article class="guide-issue" data-level="fault">[\s\S]*?<\/article>/)?.[0];
    const [visible,disclosed]=faultCard.split('<details');
    assert.match(visible,lang==='en'?/Review codes and contact a technician/:/ดูรหัสปัญหาและแจ้งช่าง/);
    assert.doesNotMatch(visible,/E101|E104/);
    assert.match(disclosed,/<code>E101<\/code>/);
    assert.equal((markup.match(/<li>/g)||[]).length,7);
  }
});

test('guide hides unconfirmed diagnoses during Hub outage and shows one explicit retry state', () => {
  const markup=monitor.guide(fixture('en',{connected:false}));
  assert.match(markup,/Hub unreachable/);
  assert.match(markup,/data-action="retry"/);
  assert.doesNotMatch(markup,/<article|No reported issues|E104/);
});
