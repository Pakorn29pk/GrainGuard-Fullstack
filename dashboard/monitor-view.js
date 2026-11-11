/* Presentation only. Hub/Node evidence and command authorization stay unchanged. */
(function(root){
 'use strict';
 const words={
  th:{overview:'ภาพรวมโรงสี',intro:'สถานะทุกเครื่อง ในจอเดียว',tracked:'เครื่องที่ติดตาม',all:'ทั้งหมด',attention:'ต้องตรวจ',offline:'ขาดข้อมูล',alarm:'Alarm การทำงาน',fault:'อุปกรณ์ขัดข้อง',faultAction:'ดูรหัสปัญหาและแจ้งช่าง',normal:'กำลังทำงาน',rest:'เครื่องพัก',learning:'เรียนรู้ / เฝ้าดู',unknown:'ยังยืนยันไม่ได้',empty:'ยังไม่ผูก Node',status:'สถานะโรงสี',system:'การเชื่อมต่อระบบ',issues:'จุดที่ต้องตรวจ',clear:'ไม่พบเหตุผิดปกติที่รายงาน',check:'ดูวิธีตรวจและรายละเอียด',guide:'คู่มือการใช้งาน',details:'รายละเอียด',care:'ดูแลตะแกรง',settings:'ตั้งค่าเครื่อง',signal:'สถานะสัญญาณ',add:'เพิ่มเครื่อง',fresh:'ข้อมูลล่าสุด',noMatch:'ไม่พบเครื่องตามตัวกรอง',noNodes:'ยังไม่มีเครื่องที่ติดตาม',addHint:'เพิ่มเครื่อง แล้วผูก Node ในตั้งค่าเครื่อง',discovered:'พบ Node ใหม่',manage:'จัดการ Node',loading:'กำลังรับข้อมูล',lost:'ติดต่อ Hub ไม่ได้',stale:'ข้อมูลจาก Hub ค้าง',retry:'ลองใหม่',lostHint:'ยังยืนยันสถานะเครื่องไม่ได้',sample:'ตัวอย่างในคอม · ไม่เชื่อมต่อ Pi',limit:'ตำแหน่งการ์ดคงที่ตาม Node',active:'ปัญหาที่ต้องตรวจสอบ',allMachines:'ทุกเครื่อง',noIssue:'ไม่พบปัญหาที่รายงานในเครื่องที่เลือก',steps:'ขั้นตอนตรวจเครื่อง',step1:'ตรวจชื่อเครื่องและหมายเลข Node',step2:'อ่านวิธีตรวจและรหัสปัญหา',step3:'ตรวจตามขั้นตอนของโรงสี',ack:'รับทราบ (ACK) คือยืนยันว่าเห็นเหตุแล้ว เหตุที่ยังเกิดอยู่จะยังแสดงต่อ',legend:'ความหมายของสถานะ',inspect:'ดูรายละเอียดเครื่อง',hub:'Hub ต้องตรวจ',hubHint:'ตรวจสถานะระบบและประวัติเหตุการณ์',legendAlarm:'ตรวจเครื่องตามขั้นตอนโรงสี',legendFault:'รวมข้อควรตรวจของระบบวัดและอุปกรณ์',legendOffline:'ตรวจไฟและเครือข่ายของ Node',legendLearning:'กำลังเรียนรู้หรือเฝ้าดูแบบเงียบ',legendRest:'เครื่องพัก แต่ Node ยังส่งข้อมูล',legendNormal:'เครื่องทำงานและ Node ส่งข้อมูล',showAll:'ดูทุกเครื่อง',codes:'รหัสที่รายงาน',quality:'ตัวเลขเป็นอัตราส่วน ไม่ใช่ dB หรือค่าการสั่นที่สอบเทียบ',history:'ประวัติเหตุการณ์',unknownCopy:'รอข้อมูลที่ยืนยันได้ก่อนประเมินสภาพเครื่อง'},
  en:{overview:'Mill overview',intro:'Every machine. One clear view.',tracked:'Tracked machines',all:'All',attention:'Needs attention',offline:'No data',alarm:'Operational alarm',fault:'Equipment fault',faultAction:'Review codes and contact a technician',normal:'Running',rest:'Idle',learning:'Learning / observing',unknown:'Unconfirmed',empty:'Unassigned',status:'Mill status',system:'System connection',issues:'Items to inspect',clear:'No reported abnormalities',check:'Open guidance and details',guide:'Operating guide',details:'Details',care:'Screen care',settings:'Machine settings',signal:'Signal status',add:'Add machine',fresh:'Last sample',noMatch:'No machines match this filter.',noNodes:'No tracked machines yet',addHint:'Add a machine, then assign its Node in settings.',discovered:'New Node discovered',manage:'Manage Nodes',loading:'Receiving data',lost:'Hub unreachable',stale:'Hub data is stale',retry:'Retry',lostHint:'Machine states cannot be confirmed.',sample:'Local sample · No Pi connection',limit:'Cards stay in Node order',active:'Issues to inspect',allMachines:'All machines',noIssue:'No reported issues for the selected machines.',steps:'Inspection steps',step1:'Match the machine and Node number.',step2:'Review the action and issue code.',step3:'Follow your mill’s inspection procedure.',ack:'Acknowledge (ACK) confirms you saw an event. An active event remains visible.',legend:'Status reference',inspect:'Open machine details',hub:'Hub needs inspection',hubHint:'Review system connection and event history.',legendAlarm:'Inspect the machine using mill procedures.',legendFault:'Includes equipment and sensor warnings.',legendOffline:'Check Node power and network.',legendLearning:'Baseline learning or quiet monitoring.',legendRest:'The machine is idle and the Node is online.',legendNormal:'The machine is running and the Node is online.',showAll:'Show all machines',codes:'Reported codes',quality:'Readings are ratios, not dB or calibrated vibration values.',history:'Event history',unknownCopy:'Wait for confirmed data before assessing the machine.'}
 };
 function context(c){const w={...words[c.lang==='en'?'en':'th']};if(c.mock)w.sample=c.lang==='en'?'MOCK · Simulated data, not live machine readings':'MOCK · ข้อมูลจำลอง ไม่ใช่ข้อมูลเครื่องจริง';return {...c,w};}
 // Regroup warnings in the UI without mutating the diagnostic evidence or its rank.
 function displayAssessment(assessment,lang){
  if(assessment.level!=='warning')return assessment;
  return {...assessment,level:'fault',title:words[lang==='en'?'en':'th'].fault};
 }
 function level(n,a){return a.level==='normal'&&n.status==='rest'?'rest':a.level;}
 function title(n,a,w){return a.level==='normal'&&n.status==='run'?w.normal:a.level==='normal'&&n.status==='rest'?w.rest:a.title;}
 function counts(c){
  const out={alarm:0,fault:0,offline:0,normal:0,rest:0,learning:0,unknown:0,empty:0};
  for(const n of c.nodes)out[level(n,displayAssessment(c.assess(n),c.lang))]++;
  return out;
 }
 function card(n,c){
  const {w,esc:e,icon,btn}=c,a=displayAssessment(c.assess(n),c.lang),l=level(n,a),label=title(n,a,w);
  return `<article class="machine-card monitor-card" data-level="${l}" data-node="${n.id}" data-ack="${!!n.ack}" aria-label="Node ${n.id} · ${e(c.name(n))} · ${e(label)}">
   <header class="monitor-card-head"><button class="node-heading" data-action="detail" data-id="${n.id}"><span class="node-number"><small>NODE</small><strong>${String(n.id).padStart(2,'0')}</strong></span><span class="node-name">${e(c.name(n))}</span></button><span class="monitor-status" data-level="${l}">${icon(c.statusIcon(l))}<span>${e(label)}</span></span></header>
   <div class="monitor-identity"><span title="MAC">${e(n.mac||w.empty)}</span><span>${e(n.mode||'—')}</span></div>
   <div class="monitor-readings">${c.readings(n,'a')}${c.readings(n,'b')}</div>
   <div class="monitor-condition">${a.needsAttention?`<button class="condition-link" data-action="inspect" data-id="${n.id}" title="${e(a.summary)}">${icon(l==='offline'?'unlink':'alert')}<span>${e(n.codes.length?n.codes.join(' · '):a.title)}</span>${icon('chevron')}</button>`:`<span>${icon(l==='learning'?'clock':'check')}${e(label)}</span>`}<small>${e(c.age(n))}</small></div>
   <footer class="monitor-card-actions">${btn(w.details,'detail','','chevron',`data-id="${n.id}"`)}${btn(w.care,'node-maintenance','','screen',`data-id="${n.id}"`)}${btn(w.settings,'machine-settings','monitor-settings','settings',`data-id="${n.id}" title="${e(w.settings)}"`)}</footer>
  </article>`;
 }
 function cards(input){const c=context(input);let nodes=[...c.nodes].sort((a,b)=>a.id-b.id);if(c.filter==='attention')nodes=nodes.filter(n=>c.assess(n).needsAttention);if(c.filter==='offline')nodes=nodes.filter(n=>['offline','unknown'].includes(n.status));if(c.filter==='all'&&c.offlinePolicy==='group')nodes=nodes.filter(n=>n.status!=='offline');return nodes.map(n=>card(n,c)).join('')||`<div class="empty monitor-empty">${c.icon('grid')}<h2>${c.nodes.length?c.w.noMatch:c.w.noNodes}</h2>${!c.nodes.length?`<p>${c.w.addHint}</p>${c.btn(c.w.add,'add-machine','primary','plus')}`:''}</div>`;}
 function overview(input){
  const c=context(input),{w,esc:e,icon,btn}=c,tot=counts(c),nodeIssues=c.nodes.filter(n=>c.assess(n).needsAttention).length,hubCodes=c.connected?(c.snapshot?.hub?.codes||[]):[],issues=nodeIssues+(hubCodes.length?1:0);
  const railLevel=!c.connected?'unknown':tot.alarm?'alarm':tot.fault||hubCodes.length?'fault':tot.offline?'offline':issues?'unknown':'normal';
  return `<div class="monitor-heading"><div><h1>${w.overview}</h1></div><div class="monitor-heading-actions">${btn(w.add,'add-machine','','plus')}</div></div>
   <div class="monitor-layout"><section class="monitor-machines" aria-label="${w.tracked}"><div class="monitor-grid-toolbar"><div><strong>${w.tracked}</strong><span class="count">${c.nodes.length}</span></div><div class="segmented" role="group" aria-label="${w.tracked}">${[['all','all'],['attention','attention'],['offline','offline']].map(([v,k])=>`<button data-action="filter" data-value="${v}" aria-pressed="${c.filter===v}">${w[k]}</button>`).join('')}</div></div><div id="machine-cards" class="monitor-grid" data-count="${c.nodes.length}">${cards(c)}</div><div id="offline-group">${c.offlineGroup()}</div></section>
   <aside class="monitor-rail" aria-label="${w.status}"><section class="rail-clock"><span>${c.lang==='en'?'LOCAL TIME':'เวลาโรงสี'}</span><strong id="header-clock">${c.clock?c.clock():'—'}</strong><small class="rail-clock-date">${c.date?e(c.date()):''}</small></section><section class="rail-status"><div class="rail-heading"><h2>${w.status}</h2><span>${c.nodes.length} ${c.lang==='en'?'Nodes':'เครื่อง'}</span></div><button class="rail-attention" data-level="${railLevel}" data-action="view-attention"><strong>${issues}</strong><span>${!c.connected?w.unknown:issues?w.issues:w.clear}${icon('chevron')}</span></button>${hubCodes.length?`<button class="rail-hub-issue" data-action="view-attention" data-level="fault">${icon('alert')}<span>${w.hub}<small>${hubCodes.map(e).join(' · ')}</small></span></button>`:''}<div class="rail-counts">${['alarm','fault','offline','normal','rest','learning','unknown','empty'].filter(k=>!c.connected?k==='unknown':!['unknown','empty'].includes(k)||tot[k]).map(k=>`<div data-level="${k}"><span class="status-dot"></span><span>${w[k]}</span><strong>${tot[k]}</strong></div>`).join('')}</div></section>
   <section class="rail-system"><div class="rail-heading"><h2>${w.system}</h2>${icon(c.connected?'link':'unlink')}</div>${c.fixture?`<p class="fixture-note">${w.sample}</p>`:''}${!c.connected?`<div class="rail-disconnected" role="status"><strong>${w[c.connectionState==='stale'?'stale':c.started?'lost':'loading']}</strong><p>${w.lostHint}</p>${btn(w.retry,'retry','','link')}</div>`:''}<div class="rail-system-rows">${c.connected?c.systemRows():''}</div></section>
   ${c.soundButton?c.soundButton():''}<button class="rail-guide" data-action="nav" data-page="guide">${icon('help')}<span>${w.guide}<small>${w.check}</small></span>${icon('chevron')}</button>${c.pendingCards()?`<details class="rail-discovery"><summary>${w.discovered} (${c.pendingCount})</summary><div>${c.pendingCards()}</div></details>`:''}${c.pendingCount?`<button class="rail-pending" data-action="nav" data-page="settings">${icon('plus')}${w.discovered} (${c.pendingCount})</button>`:''}</aside></div>`;
 }
 function guideIssue(c,node,assessment){
  const {w,esc:e,icon,btn}=c;
  const a=displayAssessment(assessment,c.lang);
  const action=a.level==='fault'?(a.issues.length?w.faultAction:a.action):a.action;
  const diagnosis=a.level==='fault'&&a.issues.length?'':a.summary;
  return `<article class="guide-issue" data-level="${a.level}">
    <header class="guide-issue-head">
      <div class="guide-identity"><span class="guide-node">Node ${node.id}</span><h3>${e(c.name(node))}</h3></div>
      <span class="monitor-status" data-level="${a.level}">${icon(c.statusIcon(a.level))}${e(a.title)}</span>
    </header>
    <div class="guide-next"><p>${e(action)}</p>${btn(w.details,'detail','','chevron',`data-id="${node.id}"`)}</div>
    <details class="guide-disclosure" data-guide-disclosure="node-${node.id}">
      <summary>${w.diagnostics}${a.issues.length?` <span class="guide-code-count">${a.issues.length}</span>`:''}</summary>
      <div class="guide-disclosure-body">
        ${node.mac?`<p class="guide-mac">MAC ${e(node.mac)}</p>`:''}
        ${diagnosis?`<p>${e(diagnosis)}</p>`:''}
        ${a.issues.length?`<ul class="guide-codes">${a.issues.map(i=>`<li><code>${e(i.code)}</code><div><strong>${e(i.title)}</strong>${i.action&&i.action!==action?`<p>${e(i.action)}</p>`:''}</div></li>`).join('')}</ul>`:''}
        ${btn(w.settings,'machine-settings','','settings',`data-id="${node.id}"`)}
      </div>
    </details>
   </article>`;
 }
 function guideReference(c){
  const {w,icon}=c;
  const legend=[['alarm','legendAlarm'],['fault','legendFault'],['offline','legendOffline'],['learning','legendLearning'],['rest','legendRest'],['normal','legendNormal']];
  return `<aside class="guide-reference" aria-label="${w.legend}">
    <section class="panel guide-quick-steps"><h2>${w.steps}</h2><ol class="guide-steps"><li>${w.step1}</li><li>${w.step2}</li><li>${w.step3}</li></ol></section>
    <details class="panel guide-disclosure guide-status-reference" data-guide-disclosure="legend">
      <summary>${w.legend}</summary>
      <div class="guide-disclosure-body">
        <dl class="guide-legend">${legend.map(([level,key])=>`<div><dt><span class="monitor-status" data-level="${level}">${icon(c.statusIcon(level))}${w[level]}</span></dt><dd>${w[key]}</dd></div>`).join('')}</dl>
        <p>${w.ack}</p><p>${w.quality}</p>
      </div>
    </details>
  </aside>`;
 }
 function guide(input){
  const c=context(input),{w,esc:e,icon,btn}=c;
  w.diagnostics=c.lang==='en'?'Diagnostics':'รหัสและรายละเอียด';
  const items=c.attentionItems().filter(({node})=>!c.selected||node.id===c.selected);
  const hubCodes=c.connected?(c.snapshot?.hub?.codes||[]):[];
  const visibleIssues=c.connected?items.length+(hubCodes.length?1:0):0;
  let issueContent;
  if(!c.connected){
   const connectionLabel=w[c.connectionState==='stale'?'stale':c.started?'lost':'loading'];
   issueContent=`<div class="panel guide-empty" role="status">${icon('unlink')}<p><strong>${connectionLabel}</strong></p>${c.started?btn(w.retry,'retry','','link'):''}</div>`;
  }else if(!visibleIssues){
   issueContent=`<div class="panel guide-empty">${icon('check')}<p>${w.noIssue}</p></div>`;
  }else{
   issueContent=items.map(({node,assessment})=>guideIssue(c,node,assessment)).join('');
   if(hubCodes.length)issueContent+=`<article class="guide-issue" data-level="fault">
    <header class="guide-issue-head"><div class="guide-identity"><h3>${w.hub}</h3></div><span class="monitor-status" data-level="fault">${icon(c.statusIcon('fault'))}${w.fault}</span></header>
    <div class="guide-next"><p>${hubCodes.map(e).join(' · ')}</p>${btn(w.history,'nav','','history','data-page="history"')}</div>
   </article>`;
  }
  return `<div class="page-head"><h1>${w.guide}</h1>${c.selected?btn(w.showAll,'guide-all','','grid'):''}</div>
   <div class="guide-layout guide-compact">
    <section class="guide-active" aria-labelledby="guide-active-heading"><div class="section-head"><h2 id="guide-active-heading">${w.active}</h2>${visibleIssues?`<span class="count">${visibleIssues}</span>`:''}</div>${issueContent}</section>
    ${guideReference(c)}
   </div>`;
 }
 const api={overview,cards,guide,counts,displayAssessment};root.GGMonitorView=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
