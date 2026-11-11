/* Display-only interpretation of Hub diagnostics. Never diagnoses ratios,
 * changes Hub classification, or treats acknowledgement as fault clearance. */
(function (root) {
  'use strict';
  const arrays=value=>Array.isArray(value)?value:[];
  const hasNumber=value=>typeof value==='number'&&Number.isFinite(value);
  const severityRank={critical:4,fault:3,warn:2,info:1,unknown:0};
  const known={
    E101:['fault','a','Pickup has no signal','Pickup ไม่มีสัญญาณ'],
    E102:['fault','a','Pickup signal saturated','สัญญาณ Pickup ล้น'],
    E103:['warn','a','Pickup baseline drift','ค่าพื้นฐาน Pickup เปลี่ยนไป'],
    E104:['warn','a','High signal noise','สัญญาณรบกวนสูง'],
    E105:['warn','node','Baseline learning incomplete','เรียนรู้ค่าพื้นฐานไม่จบ'],
    E111:['fault','b','Piezo has no signal','Piezo ไม่มีสัญญาณ'],
    E112:['fault','b','Piezo signal saturated','สัญญาณ Piezo ล้น'],
    E199:['fault','node','Node reports an internal fault','Node รายงานความผิดพลาดภายใน'],
    E201:['fault','power','Node supply voltage low','แรงดันไฟเลี้ยง Node ต่ำ'],
    E202:['fault','power','Node supply voltage high','แรงดันไฟเลี้ยง Node สูง'],
    E203:['warn','board','Node board temperature high','อุณหภูมิบอร์ด Node สูง'],
    E204:['fault','board','Node repeatedly restarting','Node รีสตาร์ทซ้ำ'],
    E301:['fault','network','Node not responding','ไม่ได้รับข้อมูลจาก Node'],
    E302:['warn','network','High packet loss','ข้อมูลเครือข่ายขาดหายมาก'],
    E303:['info','node','Unexpected firmware version','เฟิร์มแวร์ไม่ตรงเวอร์ชันที่ตั้งไว้'],
    E401:['warn','ack','Acknowledgement input stuck','ปุ่มรับทราบค้าง'],
    E402:['warn','ack','Alarm awaiting acknowledgement','แจ้งเตือนยังไม่ได้รับทราบ'],
    E310:['info','network','Plant power unavailable','ไฟโรงสีไม่พร้อม'],
    E501:['warn','hub','Hub disk nearly full','พื้นที่เก็บข้อมูล Hub ใกล้เต็ม'],
    E502:['critical','hub','Hub database error','ฐานข้อมูล Hub ผิดพลาด'],
    E503:['warn','hub','Cloud connection unavailable','Hub ส่งข้อมูล Cloud ไม่ได้'],
    E504:['warn','hub','Cloud credentials rejected','Cloud ปฏิเสธข้อมูลยืนยันตัวตน'],
    E505:['warn','hub','Hub clock not synchronized','นาฬิกา Hub ยังไม่ตรง'],
    E506:['warn','hub','Hub internal service restarted','บริการภายใน Hub รีสตาร์ท'],
    E507:['warn','hub','Hub CPU temperature high','อุณหภูมิ CPU ของ Hub สูง'],
    E508:['fault','hub','Hub-to-switch connection unavailable','การเชื่อมต่อ Hub กับสวิตช์ไม่พร้อม'],
    E900:['critical','hub','Cloud reports Hub unreachable','Cloud รายงานว่า Hub ไม่ตอบสนอง']
  };
  const words={
    th:{alarm:'แจ้งเตือนการทำงาน',fault:'อุปกรณ์ขัดข้อง',warning:'ควรตรวจสอบ',offline:'ไม่ได้รับข้อมูลจาก Node',unknown:'ยังยืนยันสถานะไม่ได้',normal:'ไม่พบข้อผิดพลาดที่ Hub รายงาน',running:'กำลังทำงาน',rest:'เครื่องพัก',learning:'กำลังเรียนรู้ค่าพื้นฐาน',shadow:'เฝ้าดูแบบเงียบ',empty:'ยังไม่ได้ผูก Node',alarmSummary:'Hub รายงานเหตุแจ้งเตือน ตรวจเครื่องตามขั้นตอนของโรงสี',alarmAction:'ดูเหตุและตรวจเครื่อง',faultAction:'ดูรายละเอียดและให้ช่างตรวจ',warningAction:'ดูรายละเอียดการเตือน',offlineSummary:'ตรวจไฟและสายเครือข่ายของ Node ข้อมูลที่ขาดไม่ใช่การยืนยันว่าเครื่องพัก',offlineAction:'ตรวจไฟและการเชื่อมต่อ',unknownHub:'ติดต่อ Hub ไม่ได้ จึงยังยืนยันสถานะเครื่องและเซ็นเซอร์ไม่ได้',unknownData:'รอข้อมูลที่ยืนยันสถานะได้จาก Hub',unknownAction:'ตรวจ Hub และเครือข่าย',normalSummary:'ไม่พบเหตุผิดปกติที่ Hub รายงานในข้อมูลล่าสุด',normalAction:'ดูข้อมูลล่าสุด',learningSummary:'ระบบยังเรียนรู้ค่าพื้นฐาน ตรวจโหมดและสถานะก่อนใช้งาน',shadowSummary:'ระบบเก็บเหตุไว้ตรวจสอบในโหมดเงียบ ไม่ใช่ Alarm ที่สั่งเตือนจริง',learningAction:'ดูโหมดและประวัติ',emptySummary:'ให้ Admin กำหนด Node ที่ตรงกับเครื่องนี้',emptyAction:'ตั้งค่าเครื่อง',fallbackFault:'Node ส่งสถานะ FAULT แต่ยังไม่มีรายละเอียดรหัสปัญหา',fallbackWarning:'Hub รายงานสถานะเตือน กรุณาดูรายละเอียดและประวัติ',unknownCode:'Hub รายงานรหัสที่ยังไม่มีคำอธิบาย',aAction:'ตรวจ Pickup และวงจรรับสัญญาณตามขั้นตอนของโรงสี',bAction:'ตรวจ Piezo และวงจรช่อง B ตามขั้นตอนของโรงสี',powerAction:'ให้ช่างตรวจไฟเลี้ยง Node ตามขั้นตอนของโรงสี',boardAction:'ให้ช่างตรวจบอร์ดและสภาพติดตั้ง',networkAction:'ตรวจไฟและเครือข่ายของอุปกรณ์',ackAction:'ตรวจสถานะการรับทราบและปุ่ม ACK',hubAction:'ตรวจรายละเอียดสถานะ Hub',nodeAction:'ดูรหัสและประวัติของ Node',more:'รายการเพิ่มเติม'},
    en:{alarm:'Operational alarm',fault:'Equipment fault',warning:'Check required',offline:'No Node data',unknown:'State unconfirmed',normal:'No Hub-reported fault',running:'Running',rest:'Machine idle',learning:'Learning baseline',shadow:'Quiet monitoring',empty:'No Node assigned',alarmSummary:'The Hub reports an active alarm. Inspect the machine using mill procedures.',alarmAction:'Review alarm and inspect machine',faultAction:'Review details and ask a technician to inspect',warningAction:'Review warning details',offlineSummary:'Check Node power and network. Missing data does not confirm that the machine is idle.',offlineAction:'Check power and connection',unknownHub:'The Hub is unreachable. Machine and sensor states cannot be confirmed.',unknownData:'Waiting for Hub data that confirms the current state.',unknownAction:'Check Hub and network',normalSummary:'The latest Hub data contains no reported fault.',normalAction:'View latest readings',learningSummary:'Baseline learning is in progress. Check the mode and state before use.',shadowSummary:'The system records observations in quiet mode. This is not a production alarm.',learningAction:'Review mode and history',emptySummary:'An Admin must assign the correct Node to this machine.',emptyAction:'Machine settings',fallbackFault:'The Node reports FAULT without a diagnostic code.',fallbackWarning:'The Hub reports a warning. Review details and event history.',unknownCode:'Hub code without an available description',aAction:'Inspect Pickup and its signal circuit using mill procedures',bAction:'Inspect Piezo and channel B using mill procedures',powerAction:'Ask a technician to inspect Node power using mill procedures',boardAction:'Ask a technician to inspect the board and installation',networkAction:'Check device power and network',ackAction:'Review acknowledgement status and the ACK button',hubAction:'Review Hub diagnostics',nodeAction:'Review Node codes and event history',more:'more issues'}
  };
  function indexCatalog(catalog){
    if(!catalog||typeof catalog!=='object')return {};
    if(Array.isArray(catalog))return Object.fromEntries(catalog.filter(x=>x&&x.code).map(x=>[String(x.code).toUpperCase(),x]));
    if(catalog.codes)return indexCatalog(catalog.codes);
    return catalog;
  }
  function codeEntries(node){
    const raw=node.raw||{},map=new Map();
    for(const value of [...arrays(node.codes),...arrays(raw.codes)]){
      const code=typeof value==='string'?value.trim().toUpperCase():'';
      if(code)map.set(code,{code});
    }
    for(const entry of [...arrays(raw.errors),...arrays(node.errors)]){
      if(!entry||typeof entry.code!=='string'||entry.ts_clear!=null||entry.open===false)continue;
      const code=entry.code.trim().toUpperCase();
      if(code)map.set(code,{...map.get(code),...entry,code});
    }
    return [...map.values()];
  }
  function assessNode(node,catalog,lang='th'){
    node=node||{};const en=lang==='en',w=words[en?'en':'th'],raw=node.raw||{};
    const enabledB=Boolean(node.channelBEnabled??node.chb??raw.chb);
    const channelUnknown={a:'unknown',b:'unknown'};
    function result(level,rank,title,summary,action,issues=[],channels=channelUnknown){
      return {level,rank,title,summary,action,issues,channels:{...channels},needsAttention:['alarm','fault','warning','offline','unknown'].includes(level)};
    }
    // Suppress cached diagnoses when Hub connectivity cannot establish recency.
    if(node.reason==='hub_lost'||node.status==='unknown')return result('unknown',60,w.unknown,node.reason==='hub_lost'?w.unknownHub:w.unknownData,w.unknownAction);
    if(node.status==='empty'||(!node.mac&&!raw.mac))return result('empty',10,w.empty,w.emptySummary,w.emptyAction);
    const byCode=indexCatalog(catalog);
    const issues=codeEntries(node).filter(entry=>!(known[entry.code]?.[1]==='b'&&!enabledB)).map(entry=>{
      const code=entry.code,meta=byCode[code]||{},fallback=known[code];
      let channel=fallback?.[1]||null;
      if(code==='E199'&&['A','B'].includes(entry.detail?.ch))channel=entry.detail.ch.toLowerCase();
      if(channel==='b'&&!enabledB)channel='node';
      const severity=Object.hasOwn(severityRank,meta.sev)?meta.sev:fallback?.[0]||'unknown';
      const title=en?(meta.en||fallback?.[2]||code):(meta.th||fallback?.[3]||code);
      const action=en?(meta.action_en||w[(channel||'node')+'Action']||w.nodeAction):(meta.action_th||meta.where||w[(channel||'node')+'Action']||w.nodeAction);
      return {code,title,severity,action,channel};
    }).sort((a,b)=>(severityRank[b.severity]-severityRank[a.severity])||a.code.localeCompare(b.code));
    if(node.status==='offline'||raw.cls==='offline'||raw.state==='OFFLINE')return result('offline',80,w.offline,w.offlineSummary,w.offlineAction,issues);
    // Firmware fault flags are direct reported evidence, not new threshold
    // calculations. Do not manufacture mature Hub E1xx diagnostic codes.
    for(const [channel,value,label] of [['a',raw.fa,'fa'],['b',raw.b?.flt,'b.flt']]){
      if(channel==='b'&&!enabledB)continue;
      if(!Number.isInteger(value)||value<=0)continue;
      if(issues.some(issue=>issue.channel===channel&&['critical','fault'].includes(issue.severity)))continue;
      const sensor=channel==='a'?'Pickup':'Piezo';
      const kind=en?(value===1?'flatline':value===2?'signal saturation':'a fault flag'):(value===1?'ไม่มีสัญญาณ':value===2?'สัญญาณล้น':'แฟล็กความผิดพลาด');
      issues.push({code:`${label}=${value}`,title:en?`${sensor} reports ${kind}`:`${sensor} รายงาน${kind}`,severity:'fault',action:w[channel+'Action'],channel,source:'node-flag'});
    }
    issues.sort((a,b)=>(severityRank[b.severity]-severityRank[a.severity])||a.code.localeCompare(b.code));
    const channels={a:hasNumber(node.a)?'normal':'unknown',b:enabledB&&hasNumber(node.b)?'normal':'unknown'};
    for(const issue of issues){
      if(['power','board','node'].includes(issue.channel)&&['critical','fault'].includes(issue.severity)){
        channels.a='unknown';channels.b='unknown';
      }
    }
    for(const channel of ['a','b']){
      const direct=issues.filter(issue=>issue.channel===channel);
      if(direct.some(issue=>['critical','fault'].includes(issue.severity)))channels[channel]='fault';
      else if(direct.some(issue=>issue.severity==='warn'))channels[channel]='warning';
    }
    const mode=node.mode||raw.mode,quiet=['SHADOW','RECORD'].includes(mode);
    const actualState=raw.state||node.state||raw.last_state;
    const baselineLearning=actualState==='CAL'||['cal','learn'].includes(raw.cls);
    const shadowObservation=raw.alarm_shadow===true||(actualState==='ALARM'&&mode!=='ALARM_ON');
    const physicalAlarm=!quiet&&(node.status==='alarm'||(raw.alarm_active===true&&mode==='ALARM_ON'));
    if(physicalAlarm)return result('alarm',100,w.alarm,w.alarmSummary,w.alarmAction,issues,channels);
    const faults=issues.filter(issue=>['critical','fault'].includes(issue.severity));
    const actualFault=[node.state,raw.state,raw.last_state].includes('FAULT');
    if(faults.length||actualFault){
      const summary=faults.length?`${faults[0].code} · ${faults[0].title}${issues.length>1?` (+${issues.length-1} ${w.more})`:''}`:w.fallbackFault;
      if(actualFault&&!faults.length){channels.a='unknown';channels.b='unknown';}
      return result('fault',faults.some(issue=>issue.severity==='critical')?95:90,w.fault,summary,w.faultAction,issues,channels);
    }
    const warnings=issues.filter(issue=>issue.severity==='warn'||issue.severity==='unknown');
    if(warnings.length||node.status==='warn'||raw.cls==='warn'){
      const summary=warnings.length?`${warnings[0].code} · ${warnings[0].title}${issues.length>1?` (+${issues.length-1} ${w.more})`:''}`:w.fallbackWarning;
      return result('warning',70,w.warning,summary,w.warningAction,issues,channels);
    }
    if(baselineLearning){
      return result('learning',30,w.learning,w.learningSummary,w.learningAction,issues,channels);
    }
    if(shadowObservation){
      return result('learning',30,w.shadow,w.shadowSummary,w.learningAction,issues,channels);
    }
    if((node.status==='learn'||raw.cls==='shadow')&&!['RUN','REST'].includes(actualState)){
      return result('learning',30,w.learning,w.learningSummary,w.learningAction,issues,channels);
    }
    return result('normal',0,actualState==='REST'||node.status==='rest'?w.rest:actualState==='RUN'||node.status==='run'?w.running:w.normal,w.normalSummary,w.normalAction,issues,channels);
  }
  function collect(nodes,catalog,lang='th'){
    return arrays(nodes).map((node,index)=>({node,assessment:assessNode(node,catalog,lang),index}))
      .filter(entry=>entry.assessment.needsAttention)
      .sort((a,b)=>b.assessment.rank-a.assessment.rank||a.index-b.index)
      .map(({node,assessment})=>({node,assessment}));
  }
  root.GGAlerts={assessNode,collect};
  if(typeof module!=='undefined')module.exports=root.GGAlerts;
})(globalThis);
