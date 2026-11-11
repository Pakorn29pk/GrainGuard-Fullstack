/* Server-issued site identity; browser preferences never choose or grant a site. */
(function(root,factory){
  'use strict';
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.GGSiteContext=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  function context(session,language='th'){
    const site=session?.authenticated&&session.site&&typeof session.site==='object'?session.site:null;
    const name=site&&typeof site.name==='string'&&site.name.trim()?site.name.trim().slice(0,120):'GrainGuard';
    const mock=site?.mode==='mock';
    return {name,mock,id:site&&typeof site.id==='string'?site.id:null,
      modeLabel:mock?(language==='en'?'MOCK · Simulated data':'MOCK · ข้อมูลจำลอง'):'',
      sourceLabel:mock?(language==='en'?'Simulated machine data':'ข้อมูลเครื่องจำลอง'):(language==='en'?'Hub data':'ข้อมูลจาก Hub'),
      footerNote:mock?(language==='en'?'Simulated data · Not live machine readings':'ข้อมูลจำลอง · ไม่ใช่ข้อมูลเครื่องจริง'):(language==='en'?'Hub data · Check the last received time.':'ข้อมูลจาก Hub · ตรวจเวลาข้อมูลล่าสุดก่อนใช้งาน')};
  }
  function label(session,key,language='th'){
    if(!context(session,language).mock)return null;
    const words=language==='en'?{
      sampleLocal:'MOCK connected',liveLabel:'MOCK connected',sourceHub:'Simulated Hub status',generated:'Simulated machine data',simulated:'Simulated data',
      historyHint:'Simulated events for this mock mill.',trend:'Simulated signal trend',trendHint:'Simulated ratios for demonstration. Not measurements from a machine.',
      maintenanceIntro:'Maintenance records for this mock mill.',recordDesc:'This record is saved in the mock mill only.',recordTitle:'Record mock screen replacement',
      recordConfirm:'Save mock replacement record',preview:'MOCK DATA',sample:'Simulated data · Not live machine readings',lastPoll:'Last mock Hub response'
    }:{
      sampleLocal:'เชื่อมต่อ MOCK',liveLabel:'เชื่อมต่อ MOCK',sourceHub:'สถานะ Hub จำลอง',generated:'ข้อมูลเครื่องจำลอง',simulated:'ข้อมูลจำลอง',
      historyHint:'ประวัติเหตุการณ์จำลองของโรงสีนี้',trend:'กราฟสัญญาณจำลอง',trendHint:'อัตราส่วนจำลองสำหรับสาธิต ไม่ใช่ค่าที่วัดจากเครื่องจริง',
      maintenanceIntro:'ประวัติการดูแลของโรงสีจำลอง',recordDesc:'บันทึกนี้เก็บเฉพาะโรงสีจำลอง',recordTitle:'บันทึกเปลี่ยนตะแกรงจำลอง',
      recordConfirm:'บันทึกการเปลี่ยนตะแกรงจำลอง',preview:'ข้อมูล MOCK',sample:'ข้อมูลจำลอง · ไม่ใช่ข้อมูลเครื่องจริง',lastPoll:'รับข้อมูลจาก Hub จำลอง'
    };
    return words[key]??null;
  }
  return {context,label};
});
