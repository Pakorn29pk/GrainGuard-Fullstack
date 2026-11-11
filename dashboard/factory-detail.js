/* Compact Node detail presentation. Uses the existing live adapters and commands. */
(function(root){
 'use strict';
 const words={
  th:{back:'กลับภาพรวม',identity:'ข้อมูลเครื่อง',signals:'สัญญาณปัจจุบัน',diagnostics:'ข้อมูลสำหรับช่าง',issues:'รายละเอียดปัญหาและวิธีตรวจ',care:'ดูแลตะแกรง',lastChange:'เปลี่ยนล่าสุด',careHistory:'ประวัติการดูแล',record:'บันทึกเปลี่ยนตะแกรง',unloaded:'ยังไม่ได้โหลดประวัติ',noCare:'ยังไม่มีบันทึกการเปลี่ยน',timeline:'เหตุการณ์ของเครื่องนี้',allEvents:'ประวัติเหตุการณ์',machineAlt:'เครื่องขัดขาวข้าว',range:'ช่วงเวลากราฟ',noNode:'ยังไม่มี Node',slotHistory:'ประวัติผูกกับช่องเครื่องนี้',missing:'ไม่มีข้อมูลปัจจุบัน'},
  en:{back:'Back to overview',identity:'Machine details',signals:'Current signals',diagnostics:'Technician details',issues:'Issue details & inspection',care:'Screen care',lastChange:'Last replacement',careHistory:'Care history',record:'Record replacement',unloaded:'History not loaded yet',noCare:'No replacement recorded',timeline:'Machine events',allEvents:'Event history',machineAlt:'Rice whitener',range:'Chart time range',noNode:'No Node assigned',slotHistory:'History belongs to this machine slot',missing:'No current data'}
 };
 function render(c){
  const {node:n,lang='th',t,esc,icon,btn,name,age,badge,assess,readings,chart,range='30m',commandPending=false,eventRows,events=[],life,when}=c;
  if(!n)return `<div class="empty">${esc(t('empty'))}</div>`;
  const l=words[lang]||words.th,id=Number(n.id),a=assess(n),issues=Array.isArray(a.issues)?a.issues:[];
  const attrs=`data-id="${id}"`,isAlarm=a.level==='alarm'&&Boolean(n.raw?.alarm_active)&&n.mode==='ALARM_ON';
  const ack=isAlarm?btn(t('ack'),'ack','primary','check',`${attrs} ${n.ack||commandPending?'disabled':''}`):'';
  // n.vin/n.tc are normalized current values. Never expose retained raw readings
  // as current values after a Node/Hub disconnect; numeric zero remains visible.
  const currentNumber=(v,suffix)=>typeof v==='number'&&Number.isFinite(v)?`${v.toFixed(1)} ${suffix}`:'—';
  const info=[['MAC',n.mac||l.noNode],[t('nodeState'),['offline','unknown','empty'].includes(n.status)?a.title:n.raw?.state||'—'],[t('mode'),n.mode||'—'],[t('supply'),currentNumber(n.vin,'V')],[t('boardTemp'),currentNumber(n.tc,'°C')],[t('firmware'),n.fw||n.raw?.fw||'—']];
  const diagnostics=`<details class="factory-detail-diagnostics"><summary>${icon('settings')}<span>${esc(l.diagnostics)}</span></summary><div class="factory-diagnostic-grid">${info.map(([key,value])=>`<div class="info-row"><span>${esc(key)}</span><strong>${esc(value)}</strong></div>`).join('')}</div></details>`;
  const issueDetails=issues.length?`<details class="factory-detail-issues"><summary>${icon('alert')}<span>${esc(l.issues)}</span><span class="badge">${issues.length}</span></summary><div>${issues.map(i=>`<div class="info-row"><div><strong>${esc(i.code)} · ${esc(i.title)}</strong><p>${esc(i.action||a.action)}</p></div></div>`).join('')}</div></details>`:'';
  const maintenance=root.GGMaintenanceView;
  const careModel=maintenance?.model?maintenance.model(life,n):null;
  const last=careModel?.latest;
  const lastText=last?(maintenance.dateLabel?maintenance.dateLabel(last.ts,last.date,lang):last.ts&&when?when(last.ts):last.date||'—'):careModel?.loaded?l.noCare:l.unloaded;
  const care=`<section class="panel factory-node-care"><div class="section-head"><h2>${esc(l.care)}</h2>${icon('screen')}</div><div class="info-row"><span>${esc(l.lastChange)}</span><strong>${esc(lastText)}</strong></div><small class="muted">${esc(l.slotHistory)}</small><div class="factory-node-actions">${btn(l.careHistory,'maintenance-select','','history',attrs)}${btn(l.record,'record','','plus',attrs)}</div></section>`;
  const machineEvents=(Array.isArray(events)?events:[]).filter(e=>Number(e.n)===id).slice().sort((x,y)=>(Number(y.ts)||0)-(Number(x.ts)||0)).slice(0,4);
  const timeline=`<section class="panel factory-node-timeline"><div class="section-head"><h2>${esc(l.timeline)}</h2>${btn(l.allEvents,'nav','quiet','history','data-page="history"')}</div>${eventRows(machineEvents)}</section>`;
  const ranges=['30m','1h','8h'].map(value=>`<button type="button" data-action="range" data-value="${value}" aria-pressed="${range===value}">${value==='30m'?(lang==='th'?'30 นาที':'30 min'):value==='1h'?(lang==='th'?'1 ชั่วโมง':'1 h'):(lang==='th'?'8 ชั่วโมง':'8 h')}</button>`).join('');
  return `<div class="factory-detail"><div class="factory-detail-back"><button type="button" class="text-button back" data-action="nav" data-page="overview">${icon('arrow')}${esc(l.back)}</button></div><section class="panel factory-detail-hero" data-level="${esc(a.level)}"><div class="factory-detail-identity"><p class="eyebrow">Node ${id}</p><h1>${esc(name(n))}</h1><div class="factory-detail-status">${badge(n)}<span class="factory-detail-fresh">${esc(t('fresh'))} ${esc(age(n))}</span></div><p class="factory-detail-status-copy">${esc(a.summary)}</p>${a.needsAttention?`<p class="factory-detail-action">${esc(a.action)}</p>`:''}<div class="factory-node-actions">${ack}${btn(t('machineSettings'),'machine-settings','','settings',attrs)}${btn(l.careHistory,'maintenance-select','quiet','screen',attrs)}</div></div><img class="factory-machine-art" src="assets/real-whitener.webp" alt="${esc(l.machineAlt)}"><div class="factory-detail-readings" aria-label="${esc(l.signals)}">${readings(n,'a')}${readings(n,'b')}</div></section><section class="panel factory-detail-chart"><div class="section-head"><h2>${esc(t('trend'))}</h2><div class="segmented" role="group" aria-label="${esc(l.range)}">${ranges}</div></div>${chart(n)}<p class="settings-copy">${esc(t('trendHint'))}</p></section><div class="factory-detail-columns">${care}${timeline}</div><section class="panel factory-detail-engineering">${issueDetails}${diagnostics}<p class="settings-copy">${esc(t('dataNote'))}</p></section></div>`;
 }
 const api={render};root.GGFactoryDetail=api;
 if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
