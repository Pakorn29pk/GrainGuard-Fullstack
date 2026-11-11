/* Read-only presentation and filtering for the latest fetched Hub events. */
(function(root){
 'use strict';
 const CATEGORY_TYPES={alarm:['ALARM_ON','ALARM_OFF','ACK','SHADOW_ALARM','SHADOW_ALARM_END'],fault:['FAULT','FAULT_CLEAR','HEALTH'],connectivity:['NODE_OFFLINE','NODE_ONLINE','PLANT_POWER_OFF','HUB_BOOT','BOOT'],maintenance:['SCREEN_CHANGE'],admin:['CMD','ASSIGN','MODE','CAL','CAL_FORCED','RECORD']};
 const TITLES={ALARM_ON:'Alarm started',ALARM_OFF:'Alarm ended',ACK:'Acknowledged by Node',SHADOW_ALARM:'Shadow alarm observed',SHADOW_ALARM_END:'Shadow alarm ended',FAULT:'Node fault',FAULT_CLEAR:'Fault cleared',HEALTH:'Node health changed',NODE_OFFLINE:'Node offline',NODE_ONLINE:'Node online',PLANT_POWER_OFF:'Plant power unavailable',HUB_BOOT:'Hub started',BOOT:'Node restarted',SCREEN_CHANGE:'Screen replacement recorded',CMD:'Command sent',ASSIGN:'Machine assignment changed',MODE:'Node mode changed',CAL:'Baseline learning',CAL_FORCED:'Baseline learning command',RECORD:'Record mode'};
 const LABELS={
  en:{filters:'Filters',machine:'Machine / Node',allMachines:'All tracked machines + Hub',category:'Event category',all:'All events',alarm:'Process alarms & ACK',fault:'Sensor / equipment health',connectivity:'Connection & power',maintenance:'Screen maintenance',admin:'Settings & technician actions',other:'Other events',period:'Time window',allTime:'All fetched times',hour:'Last hour',day:'Last 24 hours',week:'Last 7 days',custom:'Custom range',from:'From (Bangkok, UTC+7)',to:'To (Bangkok, UTC+7)',search:'Search message, code or MAC',searchHint:'e.g. E102, Node MAC, screen',sort:'Order',newest:'Newest first',oldest:'Oldest first',reset:'Reset filters',time:'Time',event:'Event',action:'Action',view:'View Node',raw:'Original Hub message',none:'No fetched events match these filters.',scope:'Up to 100 recent Hub events, not the complete archive.',result:'events',loaded:'fetched',invalid:'Enter a valid date range; the end must be after the start.',noDate:'Time unavailable',hub:'Hub',type:'Type'},
  th:{filters:'ตัวกรอง',machine:'เครื่อง / Node',allMachines:'เครื่องที่ติดตามทั้งหมด + Hub',category:'ประเภทเหตุการณ์',all:'ทุกประเภท',alarm:'Alarm ของกระบวนการ / รับทราบ',fault:'สุขภาพเซ็นเซอร์ / อุปกรณ์',connectivity:'การเชื่อมต่อ / ไฟเลี้ยง',maintenance:'การดูแลตะแกรง',admin:'ตั้งค่า / คำสั่งช่าง',other:'เหตุการณ์อื่น',period:'ช่วงเวลา',allTime:'ทุกเวลาที่ดึงมา',hour:'1 ชั่วโมงล่าสุด',day:'24 ชั่วโมงล่าสุด',week:'7 วันล่าสุด',custom:'กำหนดช่วงเวลา',from:'ตั้งแต่ (เวลาไทย UTC+7)',to:'ถึง (เวลาไทย UTC+7)',search:'ค้นหาข้อความ รหัส หรือ MAC',searchHint:'เช่น E102, MAC ของ Node, ตะแกรง',sort:'เรียงลำดับ',newest:'ใหม่ไปเก่า',oldest:'เก่าไปใหม่',reset:'ล้างตัวกรอง',time:'เวลา',event:'เหตุการณ์',action:'ดำเนินการ',view:'ดู Node',raw:'ข้อความต้นฉบับจาก Hub',none:'ไม่พบเหตุการณ์ที่ตรงกับตัวกรองในข้อมูลที่ดึงมา',scope:'แสดงสูงสุด 100 เหตุการณ์ล่าสุดจาก Hub ไม่ใช่ประวัติทั้งหมด',result:'เหตุการณ์',loaded:'ดึงมา',invalid:'กรุณาระบุช่วงเวลาที่ถูกต้อง โดยเวลาสิ้นสุดต้องไม่น้อยกว่าเวลาเริ่มต้น',noDate:'ไม่ทราบเวลา',hub:'Hub',type:'ประเภท'}
 };
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const defaults=()=>({machine:'all',category:'all',period:'all',from:'',to:'',sort:'newest'});
 const classifyEvent=e=>Object.keys(CATEGORY_TYPES).find(k=>CATEGORY_TYPES[k].includes(String(e?.type||'').toUpperCase()))||'other';
 // datetime-local fields are explicitly Bangkok wall time, independent of browser timezone.
 function bangkokTimestamp(value){
  if(!value)return null;
  const m=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(String(value));
  if(!m)return NaN;
  const parts=m.slice(1).map(v=>v===undefined?0:Number(v)),[year,month,day,hour,minute,second]=parts;
  const check=new Date(Date.UTC(year,month-1,day,hour,minute,second));
  if(check.getUTCFullYear()!==year||check.getUTCMonth()!==month-1||check.getUTCDate()!==day||hour>23||minute>59||second>59)return NaN;
  return (check.getTime()-7*3600000)/1000;
 }
 function rangeValid(filters){
  const f={...defaults(),...filters};if(f.period!=='custom')return true;
  const from=bangkokTimestamp(f.from),to=bangkokTimestamp(f.to);
  return (from===null||Number.isFinite(from))&&(to===null||Number.isFinite(to))&&(from===null||to===null||to>=from);
 }
 function filterEvents(events,filters={},now=Date.now()/1000){
  const f={...defaults(),...filters};
  if(!rangeValid(f))return [];
  const duration={hour:3600,day:86400,week:604800}[f.period];
  const from=f.period==='custom'?bangkokTimestamp(f.from):duration?now-duration:null;
  const to=f.period==='custom'?bangkokTimestamp(f.to):duration?now:null;
  return (Array.isArray(events)?events:[]).filter(e=>{
   if(f.machine!=='all'&&(f.machine==='hub'?!!e.n:String(e.n)!==String(f.machine)))return false;
   if(f.category!=='all'&&classifyEvent(e)!==f.category)return false;
   const ts=Number(e.ts);
   if((from!==null||to!==null)&&(!Number.isFinite(ts)||e.ts==null))return false;
   if(from!==null&&ts<from||to!==null&&ts>to)return false;
   return true;
  }).sort((a,b)=>{
   const x=a.ts==null?NaN:Number(a.ts),y=b.ts==null?NaN:Number(b.ts);
   if(!Number.isFinite(x))return Number.isFinite(y)?1:0;if(!Number.isFinite(y))return -1;
   return f.sort==='oldest'?x-y:y-x;
  });
 }
 function render({events=[],nodes=[],lang='th',filters={},now=Date.now()/1000}={}){
  const l=LABELS[lang==='en'?'en':'th'],f={...defaults(),...filters},filtered=filterEvents(events,f,now);
  const option=(value,label,selected)=>`<option value="${esc(value)}"${String(selected)===String(value)?' selected':''}>${esc(label)}</option>`;
  const select=(key,label,options)=>`<label class="field history-field"><span>${esc(label)}</span><select data-history-filter="${key}" name="${key}">${options.map(([v,t])=>option(v,t,f[key])).join('')}</select></label>`;
  const machineOptions=[['all',l.allMachines],['hub',l.hub],...nodes.map(n=>[String(n.id??n.n),`Node ${n.id??n.n} · ${n.name||n.label||n.raw?.label||''}`])];
  const categories=[['all',l.all],...Object.keys(CATEGORY_TYPES).map(k=>[k,l[k]]),['other',l.other]];
  const dateField=(key,label)=>`<label class="field history-field"><span>${esc(label)}</span><input type="datetime-local" name="${key}" data-history-filter="${key}" value="${esc(f[key])}"${f.period==='custom'?'':' disabled'}></label>`;
  const formatTime=ts=>ts!=null&&Number.isFinite(Number(ts))?new Date(Number(ts)*1000).toLocaleString(lang==='en'?'en-GB':'th-TH',{timeZone:'Asia/Bangkok',hour12:false}):l.noDate;
  const nodeFor=e=>nodes.find(n=>Number(n.id??n.n)===Number(e.n));
  const machineName=e=>{if(!e.n)return l.hub;const n=nodeFor(e);return n&&(!e.mac||e.mac===n.mac)?`Node ${e.n} · ${n.name||n.label||n.raw?.label||''}`:`Node ${e.n} · ${e.label||e.mac||''}`;};
  const rows=filtered.map(e=>`<tr role="row"><td role="cell" class="history-time">${esc(formatTime(e.ts))}</td><td role="cell"><strong>${esc(machineName(e))}</strong>${e.mac?`<small class="history-mac">${esc(e.mac)}</small>`:''}</td><td role="cell"><span class="history-category" data-category="${classifyEvent(e)}">${esc(l[classifyEvent(e)])}</span><p>${esc(lang==='en'?(TITLES[e.type]||e.type):e.text||e.type)}</p>${lang==='en'&&e.text?`<details class="history-raw"><summary>${esc(l.raw)}</summary><p>${esc(e.text)}</p></details>`:''}${e.code?`<small class="muted">${esc(e.code)}</small>`:''}</td><td role="cell">${e.n&&nodeFor(e)?`<button type="button" class="button history-node-link" data-action="detail" data-id="${Number(e.n)}">${esc(l.view)}</button>`:'—'}</td></tr>`).join('');
  return `<section class="panel history-panel" aria-labelledby="history-filter-title"><form id="history-filter-form" class="history-filters"><div class="section-head"><h2 id="history-filter-title">${esc(l.filters)}</h2><button type="button" class="button" data-action="history-reset">${esc(l.reset)}</button></div><div class="history-filter-grid">${select('machine',l.machine,machineOptions)}${select('category',l.category,categories)}${select('period',l.period,[['all',l.allTime],['hour',l.hour],['day',l.day],['week',l.week],['custom',l.custom]])}${select('sort',l.sort,[['newest',l.newest],['oldest',l.oldest]])}${f.period==='custom'?dateField('from',l.from)+dateField('to',l.to):''}</div></form><p class="settings-copy history-scope">${esc(l.scope)}</p>${!rangeValid(f)?`<p role="alert" class="form-error">${esc(l.invalid)}</p>`:''}<div id="history-results" class="history-results"><p class="history-result-count" role="status" aria-live="polite"><strong>${filtered.length}</strong> ${esc(l.result)} · ${events.length} ${esc(l.loaded)}</p><div class="table-wrap"><table role="table"><thead role="rowgroup"><tr role="row"><th role="columnheader" scope="col">${esc(l.time)}</th><th role="columnheader" scope="col">${esc(l.machine)}</th><th role="columnheader" scope="col">${esc(l.event)}</th><th role="columnheader" scope="col">${esc(l.action)}</th></tr></thead><tbody role="rowgroup">${rows||`<tr role="row"><td role="cell" colspan="4"><div class="empty">${esc(l.none)}</div></td></tr>`}</tbody></table></div></div></section>`;
 }
 const api={defaults,classifyEvent,filterEvents,render,bangkokTimestamp,rangeValid};
 if(typeof module!=='undefined'&&module.exports)module.exports=api;
 root.GGHistoryView=api;
})(typeof globalThis!=='undefined'?globalThis:this);
