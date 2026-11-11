/* Real Hub machine settings. All writes are delegated to the authenticated request supplied by the host app. */
(function(root){
 'use strict';
 const copy={
  th:{title:'ตั้งค่าเครื่อง',assign:'กำหนด Node ให้เครื่องขัด',close:'ปิด',node:'Node (ตัวส่งสัญญาณ)',current:'Node ปัจจุบัน',discovered:'Node ที่พบใหม่',manual:'หรือกรอก MAC ด้วยตนเอง',manualHint:'เลขฐานสิบหก 12 ตัว เช่น a4cf12ab34cd (ใส่ : หรือ - คั่นได้)',noNodes:'ยังไม่พบ Node ใหม่ ตรวจไฟและสายเครือข่ายของ Node แล้วรอรับข้อมูล หรือกรอก MAC ด้านล่าง',slot:'ใช้กับเครื่องขัดหมายเลข',empty:'ยังไม่ผูก Node',occupied:'มี Node อยู่แล้ว',label:'ชื่อเครื่องบนหน้าจอ',save:'บันทึก',cancel:'ยกเลิก',tools:'เครื่องมือช่าง',lamps:'ทดสอบไฟสัญญาณ',horn:'ทดสอบแตร',reset:'รีเซ็ตค่าฐานใน Hub',cal:'เรียนรู้ค่าพื้นฐานใหม่ (CAL)',remove:'ถอด Node ออกจากเครื่องนี้',resetHint:'ใช้หลังเปลี่ยนตะแกรงหรือปรับเครื่อง เพื่อให้ Hub เริ่มเทียบค่าพื้นฐาน 7 วันใหม่ แยกจากคำสั่ง CAL ที่ส่งไปยัง Node',calHint:'ทำตอนเครื่องหยุดและตะแกรง/ท่อปกติเท่านั้น Node จะเรียนรู้ค่าพื้นฐานใหม่ประมาณ 2 นาที หากเครื่องผิดปกติระหว่างเรียนรู้ ระบบอาจจำสภาวะผิดปกติเป็นค่าปกติ ห้ามสั่งขณะ Alarm ค้าง และ Hub จะบันทึกชื่อผู้สั่ง เวลา และเหตุผล',operator:'ชื่อผู้สั่ง (อย่างน้อย 2 ตัวอักษร)',reason:'เหตุผล (ไม่บังคับ)',calConfirm:'ยืนยันส่งคำสั่ง CAL',removeConfirm:'ยืนยันถอด Node',confirm:'ยืนยันดำเนินการ',confirmTitle:'ตรวจสอบก่อนดำเนินการ',lampsConfirm:'คำสั่งนี้จะสั่งไฟสัญญาณที่ Node จริง กรุณายืนยันเครื่องและตำแหน่งก่อนส่ง',hornConfirm:'คำสั่งนี้จะทำให้แตรที่ Node จริงส่งเสียง กรุณายืนยันเครื่องและแจ้งผู้ที่อยู่บริเวณนั้นก่อนส่ง',resetConfirm:'ยืนยันรีเซ็ตค่าฐานเปรียบเทียบใน Hub ของเครื่องนี้ การดำเนินการนี้ไม่ได้สั่งให้ Node ทำ CAL',removeHint:'ยืนยันยกเลิกการผูก Node กับเครื่องนี้ ประวัติใน Hub จะยังคงอยู่ Node ที่ยังส่งข้อมูลอาจกลับไปอยู่ในรายการ Node ใหม่',replaceHint:'เครื่องปลายทางมี Node อีกตัวอยู่ การบันทึกจะแทนที่ Node เดิม กรุณาตรวจเครื่องและหมายเลข MAC',replaceConfirm:'ยืนยันแทนที่ Node และบันทึก',invalidMac:'กรุณาเลือก Node หรือกรอก MAC เลขฐานสิบหก 12 ตัวให้ถูกต้อง',invalidLabel:'กรุณากรอกชื่อเครื่อง 1–40 ตัวอักษร',invalidOperator:'กรุณากรอกชื่อผู้สั่งอย่างน้อย 2 ตัวอักษร',noSnapshot:'ยังไม่ได้รับข้อมูลจาก Hub กรุณารอการเชื่อมต่อ',offline:'Node ไม่ได้เชื่อมต่อ จึงยังส่งคำสั่งไป Node ไม่ได้',alarmBlocked:'เครื่องนี้มี Alarm ค้างอยู่ จึงสั่ง CAL ไม่ได้',sent:'Hub รับและส่งคำสั่งแล้ว รอตรวจผลจาก Node จริง',saved:'Hub บันทึกการผูก Node และชื่อเครื่องแล้ว',resetDone:'Hub รีเซ็ตค่าฐานเปรียบเทียบแล้ว',removed:'Hub ยกเลิกการผูก Node แล้ว',failed:'ดำเนินการไม่สำเร็จ',working:'กำลังส่งคำขอ…',fw:'เฟิร์มแวร์',mode:'โหมด Node',state:'สถานะ Node',last:'ได้รับข้อมูลล่าสุด',seconds:'วินาทีที่แล้ว',unknown:'ไม่มีข้อมูล',codes:'รหัสปัญหาจาก Hub',noCodes:'ไม่มีรหัสปัญหาที่รายงาน',auth:'การบันทึกและเครื่องมือช่างใช้รหัสผู้ดูแลของ Hub จริง',macUsed:'MAC นี้ถูกผูกกับเครื่องอื่นอยู่ กรุณาตรวจและถอดจากเครื่องเดิมก่อนย้าย',configFirst:'บันทึกการผูก Node ก่อนใช้เครื่องมือช่าง'},
  en:{title:'Machine settings',assign:'Assign a Node to a whitener',close:'Close',node:'Node (signal transmitter)',current:'Current Node',discovered:'Newly discovered Node',manual:'Or enter a MAC address',manualHint:'12 hexadecimal characters, e.g. a4cf12ab34cd (: or - separators allowed)',noNodes:'No new Nodes found. Check Node power and Ethernet, wait for data, or enter the MAC below.',slot:'Assign to machine slot',empty:'No Node assigned',occupied:'Node already assigned',label:'Machine display name',save:'Save',cancel:'Cancel',tools:'Technician tools',lamps:'Test signal lamps',horn:'Test horn',reset:'Reset Hub comparison baseline',cal:'Learn a new baseline (CAL)',remove:'Unassign Node from this machine',resetHint:'Use after a screen replacement or machine adjustment to restart the Hub’s seven-day comparison baseline. This is separate from Node CAL.',calHint:'Use only while the machine is stopped and the screen/pipe is in normal condition. The Node learns a new baseline for about two minutes. An abnormal condition may be learned as normal. CAL is blocked while an alarm remains active. The Hub audits the operator, time and reason.',operator:'Operator name (at least 2 characters)',reason:'Reason (optional)',calConfirm:'Confirm sending CAL',removeConfirm:'Confirm unassignment',confirm:'Confirm action',confirmTitle:'Review before proceeding',lampsConfirm:'This command operates the lamps on a real Node. Confirm the machine and location before sending.',hornConfirm:'This command sounds the horn on a real Node. Confirm the machine and notify people nearby before sending.',resetConfirm:'Confirm resetting this machine’s comparison baseline in the Hub. This does not start Node CAL.',removeHint:'Confirm removing the Node-to-machine assignment. Existing Hub history is retained. A Node still sending data may reappear as newly discovered.',replaceHint:'The destination machine already has a different Node. Saving replaces that assignment. Check the machine and MAC addresses.',replaceConfirm:'Confirm replacement and save',invalidMac:'Select a Node or enter a valid 12-character hexadecimal MAC.',invalidLabel:'Enter a machine name of 1–40 characters.',invalidOperator:'Enter an operator name of at least 2 characters.',noSnapshot:'No Hub data received yet. Wait for the connection.',offline:'The Node is offline. Node commands are unavailable.',alarmBlocked:'This machine has an active alarm. CAL is unavailable.',sent:'The Hub accepted and sent the command. Verify the result on the real Node.',saved:'The Hub saved the Node assignment and machine name.',resetDone:'The Hub reset the comparison baseline.',removed:'The Hub removed the Node assignment.',failed:'The action failed.',working:'Sending request…',fw:'Firmware',mode:'Node mode',state:'Node state',last:'Last received',seconds:'seconds ago',unknown:'No data',codes:'Hub diagnostic codes',noCodes:'No diagnostic codes reported',auth:'Saving and technician tools require the real Hub administrator token.',macUsed:'This MAC is assigned to another machine. Check and unassign it there before moving it.',configFirst:'Save the Node assignment before using technician tools'}
 };
 Object.assign(copy.th,{assigned:'Node ที่ผูกกับเครื่องอื่น',source:'ผูกอยู่กับ',destination:'ย้ายไปเครื่อง',moveHint:'ยืนยันย้ายตัวรับสัญญาณนี้จากเครื่องต้นทางไปยังเครื่องปลายทาง การผูกกับเครื่องต้นทางจะถูกยกเลิก',moveConfirm:'ยืนยันย้าย Node และบันทึก',replaces:'Node เดิมที่ปลายทางจะถูกแทนที่',moveAssignment:'กำลังเลือกย้าย Node กรุณาบันทึกก่อนใช้เครื่องมือช่างกับปลายทาง',savedRefreshFailure:'Hub รับคำขอแล้ว แต่รีเฟรชหน้าจอไม่สำเร็จ กรุณาปิดหน้าต่างและเชื่อมต่อใหม่ก่อนดำเนินการซ้ำ'});
 Object.assign(copy.en,{assigned:'Node assigned to another machine',source:'Currently assigned to',destination:'Move to machine',moveHint:'Confirm moving this receiver from the source machine to the destination machine. Its source assignment will be removed.',moveConfirm:'Confirm move and save',replaces:'The destination’s existing Node will be replaced',moveAssignment:'A Node move is selected. Save the assignment before using destination technician tools.',savedRefreshFailure:'The Hub accepted the request, but the dashboard refresh failed. Close this dialog and reconnect before repeating the action.'});
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const norm=s=>String(s||'').trim().toLowerCase().replace(/[:-]/g,'');
 function candidatesFor(snapshot,slot){
  const seen=new Set(),assigned=(snapshot.nodes||[]).filter(n=>n.mac).sort((a,b)=>(Number(a.n)===Number(slot)?-1:0)-(Number(b.n)===Number(slot)?-1:0));
  return [...assigned.map(n=>({...n,sourceSlot:Number(n.n),sourceLabel:n.label||''})),...(snapshot.new||[]).map(n=>({...n,sourceSlot:null,sourceLabel:''}))].filter(n=>{const mac=norm(n.mac);if(!/^[0-9a-f]{12}$/.test(mac)||seen.has(mac))return false;seen.add(mac);return true;});
 }
 function assignmentPlan(snapshot,slot,mac,label){
  const address=norm(mac),target=Number(slot),nodes=snapshot.nodes||[];
  const source=nodes.find(n=>n.mac&&norm(n.mac)===address)||null,destination=nodes.find(n=>Number(n.n)===target)||null;
  return {body:{mac:address,label:String(label||'').trim(),expected_source_machine:source?Number(source.n):null,expected_target_mac:destination?.mac?norm(destination.mac):null},source,destination,move:!!source&&Number(source.n)!==target,replace:!!destination?.mac&&norm(destination.mac)!==address};
 }
 function selectedCandidate(candidates,destinationMac,preferredMac){const preferred=norm(preferredMac);return candidates.some(c=>norm(c.mac)===preferred)?preferred:destinationMac?norm(destinationMac):norm((candidates.find(c=>c.sourceSlot==null)||candidates[0])?.mac);}
 let active=null;
 function styles(){if(document.querySelector('#gg-machine-settings-style'))return;const style=document.createElement('style');style.id='gg-machine-settings-style';style.textContent=`#gg-machine-settings{width:min(680px,calc(100% - 28px))}#gg-machine-settings .ms-candidates{display:grid;gap:8px;margin:8px 0 17px}#gg-machine-settings .ms-choice{display:flex;align-items:flex-start;gap:10px;background:var(--soft);border:1px solid var(--line);border-radius:9px;padding:10px;font-size:12px;cursor:pointer;overflow-wrap:anywhere}#gg-machine-settings .ms-choice input{flex:none;margin-top:4px}#gg-machine-settings .ms-tools{border-top:1px solid var(--line);padding-top:15px;margin-top:20px}#gg-machine-settings .ms-tools summary{cursor:pointer;font-size:14px;font-weight:650;padding:7px 0;min-height:38px}#gg-machine-settings .ms-tools .toolbar{margin-top:12px}#gg-machine-settings .ms-info{display:grid;grid-template-columns:1fr 1fr;gap:8px 20px;margin:0 0 18px;font-size:12px}#gg-machine-settings .ms-info dt{color:var(--muted)}#gg-machine-settings .ms-info dd{margin:0;overflow-wrap:anywhere}#gg-machine-settings .ms-info>div{display:grid;gap:3px}#gg-machine-settings .ms-error{color:var(--red);background:var(--red-bg);padding:10px 12px;border-radius:8px;font-size:12px;margin-top:12px;white-space:pre-wrap}#gg-machine-settings .ms-status{color:var(--green);font-size:12px;padding:10px 0}#gg-machine-settings .ms-confirm{border:1px solid var(--line);border-left:3px solid var(--amber);background:var(--soft);padding:15px;border-radius:10px;margin-top:15px}#gg-machine-settings .ms-confirm h3{font-size:15px;margin-bottom:9px}#gg-machine-settings .ms-confirm p{font-size:12px;margin-bottom:12px}#gg-machine-settings .ms-identity{display:block;font-family:Consolas,monospace;font-size:12px;margin-bottom:12px;overflow-wrap:anywhere}#gg-machine-settings [hidden]{display:none!important}@media(max-width:550px){#gg-machine-settings .ms-info{grid-template-columns:1fr}#gg-machine-settings .dialog-actions{flex-wrap:wrap}}`;document.head.append(style);}
 function open(options){
  if(!options||typeof options.request!=='function')throw new TypeError('request(path, body) is required');
  if(active)active.close();styles();
  const o=options,lang=o.lang==='en'?'en':'th',t=k=>copy[lang][k]||k;
  const snapshot=()=>typeof o.getSnapshot==='function'?o.getSnapshot():o.snapshot;
  if(!snapshot()||!Array.isArray(snapshot().nodes))throw Error(t('noSnapshot'));
  const nodes=()=>snapshot().nodes,find=n=>nodes().find(x=>Number(x.n)===Number(n));
  const first=Number(o.slot)||Number(nodes().find(n=>!n.mac)?.n)||Number(nodes()[0]?.n);
  const dialog=document.createElement('dialog');dialog.id='gg-machine-settings';dialog.setAttribute('aria-labelledby','gg-ms-title');
  let busy=false,armed=null,slot=first,refreshRequired=false;
  const initial=find(slot),title=initial?.mac?`${t('title')} · ${initial.label||slot}`:t('assign');
  const button=(label,action,extra='')=>`<button class="button" type="button" data-ms-action="${action}" ${extra}>${esc(label)}</button>`;
  dialog.innerHTML=`<div class="dialog-head"><h2 id="gg-ms-title">${esc(title)}</h2><button class="icon-button" type="button" data-ms-action="close" aria-label="${t('close')}">×</button></div><p>${t('auth')}</p><form id="gg-ms-form"><label class="field"><span>${t('slot')}</span><select name="slot">${nodes().map(n=>`<option value="${Number(n.n)}" ${Number(n.n)===slot?'selected':''}>#${Number(n.n)} · ${esc(n.label||n.n)} · ${t(n.mac?'occupied':'empty')}</option>`).join('')}</select></label><div><strong style="font-size:13px">${t('node')}</strong><div class="ms-candidates" role="radiogroup" aria-label="${t('node')}"></div></div><label class="field"><span>${t('manual')}</span><input name="manual" maxlength="17" autocomplete="off" autocapitalize="off" spellcheck="false"><small>${t('manualHint')}</small></label><label class="field"><span>${t('label')}</span><input name="label" maxlength="40" autocomplete="off" required></label><dl class="ms-info"></dl><div class="ms-status" role="status" aria-live="polite"></div><div class="ms-error" role="alert" hidden></div><div class="ms-confirm" hidden></div><details class="ms-tools"><summary>${t('tools')}</summary><div class="toolbar">${button(t('lamps'),'lamps')}${button(t('horn'),'horn')}${button(t('reset'),'reset')}${button(t('cal'),'cal')}${button(t('remove'),'remove','style="color:var(--red)"')}</div><p class="settings-copy">${t('resetHint')}</p><p class="settings-copy ms-tool-note"></p></details><div class="dialog-actions">${button(t('cancel'),'close')}<button class="button primary" type="submit">${t('save')}</button></div></form>`;
  document.body.append(dialog);
  const q=s=>dialog.querySelector(s),form=q('form');
  const current=()=>find(slot);
  function error(message){q('.ms-error').hidden=!message;q('.ms-error').textContent=message||'';q('.ms-status').textContent='';}
  function clearConfirm(){armed=null;q('.ms-confirm').hidden=true;q('.ms-confirm').innerHTML='';}
  q('.ms-info').insertAdjacentHTML('afterend','<p class="settings-copy ms-selection-note" hidden></p>');
  const selectedMac=()=>norm(q('[name=manual]').value.trim()||q('[name=mac]:checked')?.value||'');
  function updateSelection(){
   clearConfirm();error('');const n=current(),address=selectedMac(),device=candidatesFor(snapshot(),slot).find(c=>norm(c.mac)===address);
   q('.ms-info').innerHTML=device?[[t('source'),device.sourceSlot==null?t('discovered'):`#${device.sourceSlot} · ${device.sourceLabel||device.sourceSlot}`],[t('fw'),device.fw||'—'],[t('mode'),device.mode||'—'],[t('state'),device.state||device.cls||'—'],[t('codes'),device.codes?.join(', ')||t('noCodes')]].map(([a,b])=>`<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join(''):'';
   const pendingAssignment=!!address&&(!n?.mac||address!==norm(n.mac));q('.ms-selection-note').hidden=!pendingAssignment;q('.ms-selection-note').textContent=pendingAssignment?t('moveAssignment'):'';
   q('.ms-tools').hidden=!n?.mac||pendingAssignment;q('.ms-tools').open=false;
   const offline=!n?.mac||n.cls==='offline'||n.last_seen_s==null;
   for(const a of ['lamps','horn','cal'])q(`[data-ms-action=${a}]`).disabled=offline||(a==='cal'&&(n.alarm_active||n.state==='ALARM'));
   q('.ms-tool-note').textContent=offline?t('offline'):(n.alarm_active||n.state==='ALARM')?t('alarmBlocked'):'';
  }
  function chooseSlot(preferredMac='',manual=''){
   const n=current();clearConfirm();error('');q('[name=label]').value=n?.label||`${lang==='th'?'ขัด':'Whitener'} ${slot}`;q('[name=manual]').value=manual;
   q('#gg-ms-title').textContent=`${t('title')} · #${slot} · ${n?.label||slot}`;
   const candidates=candidatesFor(snapshot(),slot),selection=selectedCandidate(candidates,n?.mac,preferredMac);
   q('.ms-candidates').innerHTML=candidates.length?candidates.map(c=>`<label class="ms-choice"><input type="radio" name="mac" value="${esc(c.mac)}" ${norm(c.mac)===selection?'checked':''}><span><strong>${t(c.sourceSlot==null?'discovered':c.sourceSlot===slot?'current':'assigned')}</strong> · ${esc(c.mac)}${c.sourceSlot!=null?`<br>${t('source')} #${c.sourceSlot} · ${esc(c.sourceLabel||c.sourceSlot)}`:''}${c.last_seen_s!=null?`<br>${t('last')} ${Math.floor(c.last_seen_s)} ${t('seconds')}`:''}${c.fw?` · ${t('fw')} ${esc(c.fw)}`:''}</span></label>`).join(''):`<p class="muted">${t('noNodes')}</p>`;
   updateSelection();
  }
  function allowNodeCommand(){const n=current();if(!n?.mac||n.cls==='offline'||n.last_seen_s==null){error(t('offline'));return false;}return true;}
  function identity(){const n=current();return `${n?.label||slot} · #${slot} · ${n?.mac||'—'}`;}
  function confirm(kind,body=''){
   error('');armed={kind};if(kind==='remove')armed.body={unassign:true,expected_source_machine:slot,expected_target_mac:current()?.mac?norm(current().mac):null};const texts={lamps:'lampsConfirm',horn:'hornConfirm',reset:'resetConfirm',cal:'calHint',remove:'removeHint',replace:'replaceHint',move:'moveHint'};
   q('.ms-confirm').hidden=false;q('.ms-confirm').innerHTML=`<h3>${t('confirmTitle')}</h3><strong class="ms-identity">${esc(identity())}</strong><p>${t(texts[kind])}</p>${body}<div class="toolbar">${button(t('cancel'),'cancel-confirm')}<button class="button primary" type="button" data-ms-action="confirm">${t(kind==='cal'?'calConfirm':kind==='remove'?'removeConfirm':kind==='replace'?'replaceConfirm':kind==='move'?'moveConfirm':'confirm')}</button></div>`;
   q('.ms-confirm').scrollIntoView({block:'nearest'});
  }
  function setBusy(value){busy=value;dialog.setAttribute('aria-busy',String(value));for(const b of dialog.querySelectorAll('button,input,select'))b.disabled=value||refreshRequired;if(!value){if(refreshRequired){for(const b of dialog.querySelectorAll('[data-ms-action=close]'))b.disabled=false;return;}const n=current(),offline=!n?.mac||n.cls==='offline'||n.last_seen_s==null;for(const a of ['lamps','horn','cal'])q(`[data-ms-action=${a}]`).disabled=offline||(a==='cal'&&(n.alarm_active||n.state==='ALARM'));}}
  async function saved(result){if(!o.onSaved)return true;try{await o.onSaved(slot,result);return true;}catch{return false;}}
  async function run(path,body,message,closeAfter=false){
   if(busy)return;error('');setBusy(true);q('.ms-status').textContent=t('working');
   try{const result=await o.request(path,body);clearConfirm();q('.ms-status').textContent=t(message);if(!await saved(result)){refreshRequired=true;q('.ms-status').textContent=t('savedRefreshFailure');}else if(closeAfter){setBusy(false);handle.close();}}
   catch(e){error(e?.message||t('failed'));}
   finally{if(dialog.isConnected)setBusy(false);}
  }
  function assignment(){
   const n=current(),manual=q('[name=manual]').value.trim();const mac=norm(manual||q('[name=mac]:checked')?.value||n?.mac||'');const label=q('[name=label]').value.trim();
   if(!/^[0-9a-f]{12}$/.test(mac)){error(t('invalidMac'));return null;}if(!label||label.length>40){error(t('invalidLabel'));return null;}
   return {mac,label};
  }
  form.addEventListener('submit',e=>{e.preventDefault();if(busy)return;const input=assignment();if(!input)return;const plan=assignmentPlan(snapshot(),slot,input.mac,input.label),body=plan.body;if(plan.move){const source=plan.source,destination=plan.destination;confirm('move',`<p><strong>${t('source')}: #${Number(source.n)} · ${esc(source.label||source.n)}<br>↓<br>${t('destination')}: #${slot} · ${esc(body.label)}</strong><br>MAC ${esc(body.mac)}</p>${plan.replace?`<p><strong>${t('replaces')}: ${esc(destination.mac)}</strong></p>`:''}`);armed.body=body;return;}if(plan.replace){confirm('replace',`<p><strong>${esc(plan.destination.mac)} → ${esc(body.mac)}</strong></p>`);armed.body=body;return;}run(`/api/node/${slot}/assign`,body,'saved',true);});
  q('[name=slot]').addEventListener('change',()=>{const previousSelection=selectedMac(),manual=q('[name=manual]').value;slot=Number(q('[name=slot]').value);chooseSlot(previousSelection,manual);});
  q('.ms-candidates').addEventListener('change',()=>{q('[name=manual]').value='';updateSelection();});
  q('[name=manual]').addEventListener('input',updateSelection);
  q('[name=label]').addEventListener('input',clearConfirm);
  dialog.addEventListener('click',e=>{
   const b=e.target.closest('[data-ms-action]');if(!b||busy||b.disabled)return;const action=b.dataset.msAction;
   if(action==='close'){handle.close();return;}if(action==='cancel-confirm'){clearConfirm();return;}
   if(['lamps','horn','cal'].includes(action)&&!allowNodeCommand())return;
   if(action==='cal'){const n=current();if(n.alarm_active||n.state==='ALARM'){error(t('alarmBlocked'));return;}confirm('cal',`<label class="field"><span>${t('operator')}</span><input name="cal-operator" minlength="2" maxlength="40" autocomplete="off"></label><label class="field"><span>${t('reason')}</span><input name="cal-reason" maxlength="120" autocomplete="off"></label>`);q('[name=cal-operator]').focus();return;}
   if(['lamps','horn','reset','remove'].includes(action)){confirm(action);return;}
   if(action!=='confirm'||!armed)return;
   const kind=armed.kind;
   if(['lamps','horn','cal'].includes(kind)&&!allowNodeCommand())return;
   if(kind==='lamps'||kind==='horn'){run(`/api/node/${slot}/cmd`,{cmd:'test',what:kind==='lamps'?'lamps':'horn'},'sent');return;}
   if(kind==='reset'){run(`/api/node/${slot}/reset_baseline`,{},'resetDone');return;}
   if(kind==='remove'){run(`/api/node/${slot}/assign`,armed.body,'removed',true);return;}
   if(kind==='replace'||kind==='move'){run(`/api/node/${slot}/assign`,armed.body,'saved',true);return;}
   if(kind==='cal'){
    const n=current();if(n.alarm_active||n.state==='ALARM'){error(t('alarmBlocked'));return;}
    const operator=q('[name=cal-operator]').value.trim(),reason=q('[name=cal-reason]').value.trim();
    if(operator.length<2){error(t('invalidOperator'));q('[name=cal-operator]').focus();return;}
    run(`/api/node/${slot}/cal`,{operator,reason},'sent');
   }
  });
  const handle={dialog,close(){if(busy)return;dialog.close();},get slot(){return slot;}};
  dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});
  dialog.addEventListener('close',()=>{dialog.remove();if(active===handle)active=null;if(o.onClose)o.onClose();});
  chooseSlot(o.preferredMac);active=handle;dialog.showModal();return handle;
 }
 root.GGMachineSettings={open,candidatesFor,assignmentPlan,selectedCandidate};
 if(typeof module!=='undefined')module.exports=root.GGMachineSettings;
})(globalThis);
