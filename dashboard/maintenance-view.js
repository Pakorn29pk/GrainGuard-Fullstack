/* Screen-care views for machine-slot history. No estimated service life or hardware writes. */
(function (root) {
  'use strict';
  const array = value => Array.isArray(value) ? value : [];
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const words = {
    th: {title:'ดูแลตะแกรง',intro:'เลือก Node เพื่อดูและบันทึกการดูแลตะแกรงของเครื่องนั้น',choose:'เลือกเครื่อง / Node',node:'Node',machine:'เครื่องขัด',current:'ตะแกรงรอบปัจจุบัน',since:'วันที่เริ่มรอบ',none:'ยังไม่มีบันทึกวันที่เปลี่ยน',implicit:'Hub กำหนดจุดเริ่มต้นจากข้อมูลระบบ ยังไม่ใช่บันทึกการเปลี่ยนที่ยืนยัน',records:'ประวัติการเปลี่ยนตะแกรง',count:'รายการ',date:'วันที่เปลี่ยน',reason:'เหตุผล',note:'หมายเหตุ',record:'บันทึกเปลี่ยนตะแกรง',detail:'ดูข้อมูล Node',scope:'ประวัตินี้ผูกกับช่องเครื่อง การย้ายหรือเปลี่ยน Node ไม่ได้ย้ายประวัติไปกับ MAC',mac:'MAC ที่ผูกอยู่ปัจจุบัน',unassigned:'ยังไม่ได้ผูก Node',noEntries:'ยังไม่มีประวัติการเปลี่ยนตะแกรงของเครื่องนี้',unavailable:'ยังโหลดประวัติการดูแลไม่ได้',noMachines:'ยังไม่มีเครื่องที่ติดตาม',emptyNote:'เพิ่มเครื่องจากตั้งค่าเพื่อเริ่มดูประวัติ',noEstimate:'ไม่มีการคาดการณ์วันหมดอายุจากข้อมูลที่ยังไม่ยืนยัน',broke:'ตะแกรงชำรุด',scheduled:'เปลี่ยนตามแผน',other:'อื่น ๆ',last:'เปลี่ยนล่าสุด',all:'ดูประวัติการดูแล',load:'เปิดหน้าดูแลตะแกรงเพื่อโหลดประวัติ',currentNode:'Node ปัจจุบัน',notKnown:'ไม่มีข้อมูล'},
    en: {title:'Screen care',intro:'Choose a Node to view and record care for its machine.',choose:'Machine / Node',node:'Node',machine:'Whitener',current:'Current screen cycle',since:'Cycle start date',none:'No replacement date recorded',implicit:'Hub inferred this start from system data; it is not a confirmed replacement record.',records:'Screen replacement history',count:'records',date:'Replacement date',reason:'Reason',note:'Note',record:'Record replacement',detail:'View Node details',scope:'Records belong to the machine slot. Moving or replacing a Node does not transfer this history with its MAC.',mac:'Currently assigned MAC',unassigned:'No Node assigned',noEntries:'No screen replacements recorded for this machine.',unavailable:'Maintenance history could not be loaded.',noMachines:'No tracked machines',emptyNote:'Add a machine in Settings to view its records.',noEstimate:'No remaining-life estimate is shown without verified data.',broke:'Screen broke',scheduled:'Scheduled replacement',other:'Other',last:'Last replacement',all:'View screen-care history',load:'Open Screen care to load its records.',currentNode:'Current Node',notKnown:'No data'}
  };
  const idOf = node => Number(node && (node.id ?? node.n));
  const nameOf = (node,t) => node && (node.name || node.label) || `${t.machine} ${idOf(node)}`;
  function model(life, node) {
    const id = idOf(node);
    const machine = array(life && life.machines).find(item => Number(item.n) === id) || null;
    const entries = array(machine && machine.entries).slice().sort((a,b) => (Number(b.ts)||0)-(Number(a.ts)||0));
    return {id, machine, entries, latest:entries[0] || null, loaded:!!life};
  }
  function dateLabel(ts, fallback, lang) {
    if (typeof ts === 'number' && Number.isFinite(ts) && ts > 0) {
      return new Date(ts * 1000).toLocaleDateString(lang === 'th' ? 'th-TH' : 'en-GB', {year:'numeric',month:'short',day:'numeric',timeZone:'Asia/Bangkok'});
    }
    return typeof fallback === 'string' && fallback.trim() ? fallback : '—';
  }
  const button = (label,action,id,cls='') => `<button type="button" class="button ${cls}" data-action="${action}" data-id="${id}">${esc(label)}</button>`;
  function summary({life,node,lang='th'}) {
    if (!node) return '';
    const t=words[lang] || words.th, m=model(life,node);
    const last = m.latest ? dateLabel(m.latest.ts,m.latest.date,lang) : '—';
    return `<section class="panel node-maintenance-summary"><div class="section-head"><div><p class="eyebrow">${esc(t.currentNode)} ${m.id}</p><h2>${esc(t.title)}</h2></div>${button(t.all,'maintenance-select',m.id)}</div><div class="info-row"><span>${esc(t.last)}</span><strong>${esc(last)}</strong></div><p class="settings-copy">${esc(!m.loaded?t.load:m.entries.length?t.scope:t.noEntries)}</p><div class="toolbar">${button(t.record,'record',m.id)}</div></section>`;
  }
  function render({life,nodes=[],selectedId,lang='th',canManage=false}) {
    const t=words[lang] || words.th, available=array(nodes);
    if (!available.length) return `<section class="panel empty"><h2>${esc(t.noMachines)}</h2><p>${esc(t.emptyNote)}</p></section>`;
    const node=available.find(item=>idOf(item)===Number(selectedId)) || available[0];
    const m=model(life,node), machine=m.machine;
    const reasonOf = entry => t[entry.reason] || (lang==='th' && entry.reason_th) || entry.reason || t.other;
    const start = dateLabel(machine && machine.start_ts,machine && machine.start_date,lang);
    const last = m.latest ? dateLabel(m.latest.ts,m.latest.date,lang) : '—';
    return `<div class="maintenance-layout"><aside class="panel maintenance-node-list"><label class="field" for="maintenance-node"><span>${esc(t.choose)}</span><select id="maintenance-node">${available.map(item=>`<option value="${idOf(item)}" ${idOf(item)===m.id?'selected':''}>${esc(t.node)} ${idOf(item)} · ${esc(nameOf(item,t))}</option>`).join('')}</select></label><div class="maintenance-node-rail" aria-label="${esc(t.choose)}">${available.map(item=>{const itemModel=model(life,item);return `<button type="button" class="maintenance-node-option ${idOf(item)===m.id?'is-selected':''}" data-action="maintenance-select" data-id="${idOf(item)}" aria-pressed="${idOf(item)===m.id}"><span class="maintenance-node-number">${esc(t.node)} ${idOf(item)}</span><strong>${esc(nameOf(item,t))}</strong><small>${itemModel.entries.length} ${esc(t.count)}</small></button>`;}).join('')}</div></aside><div class="maintenance-content"><section class="panel maintenance-identity">
      <div class="section-head maintenance-primary"><div><h2>${esc(nameOf(node,t))}</h2><p>${esc(t.last)} <strong>${esc(!m.loaded?t.notKnown:m.latest?last:t.none)}</strong></p></div>${canManage?button(t.record,'record',m.id,'primary'):''}</div>
      ${!m.loaded?`<p class="callout">${esc(t.unavailable)}</p>`:''}
      ${machine?.implicit_start?`<p class="callout">${esc(t.implicit)}</p>`:''}
      <details class="maintenance-tech" data-machine="${m.id}">
       <summary>${lang==='en'?'Machine and cycle details':'ข้อมูลเครื่องและรอบตะแกรง'}</summary>
       <div class="info-row"><span>${esc(t.mac)}</span><strong class="mono">${esc(node.mac || t.unassigned)}</strong></div>
       ${m.loaded?`<div class="info-row"><span>${esc(t.since)}</span><strong>${esc(start==='—'?t.notKnown:start)}</strong></div>`:''}
       <p class="settings-copy">${esc(t.scope)}</p>
       ${button(t.detail,'detail',m.id)}
      </details>
     </section><section class="panel maintenance-records"><div class="section-head"><h2>${esc(t.records)}</h2><span class="badge">${m.entries.length} ${esc(t.count)}</span></div>${m.entries.length?`<div class="table-wrap"><table><thead><tr><th>${esc(t.date)}</th><th>${esc(t.reason)}</th><th>${esc(t.note)}</th></tr></thead><tbody>${m.entries.map(entry=>`<tr><td>${esc(dateLabel(entry.ts,entry.date,lang))}</td><td>${esc(reasonOf(entry))}</td><td>${esc(entry.note || '—')}</td></tr>`).join('')}</tbody></table></div>`:`<div class="empty maintenance-records-empty">${esc(m.loaded?t.noEntries:t.unavailable)}</div>`}</section></div></div>`;
  }
  const api={render,summary,model,dateLabel};
  root.GGMaintenanceView=api;
  if (typeof module==='object' && module.exports) module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
