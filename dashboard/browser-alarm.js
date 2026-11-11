/* Optional speaker notification on this browser only. Never sends a Hub command. */
(function(root){
 'use strict';
 let on=false,active=false,ctx=null,timer=null;
 function eligible(nodes,connected,assess){return !!connected&&(nodes||[]).some(n=>assess(n).level==='alarm'&&n.mode==='ALARM_ON'&&n.raw?.alarm_active&&!n.ack);}
 function beep(){if(!on||!active||!ctx||ctx.state!=='running')return;const tone=ctx.createOscillator(),gain=ctx.createGain(),now=ctx.currentTime;tone.frequency.value=660;gain.gain.setValueAtTime(0,now);gain.gain.linearRampToValueAtTime(.035,now+.015);gain.gain.setValueAtTime(.035,now+.14);gain.gain.linearRampToValueAtTime(0,now+.18);tone.connect(gain);gain.connect(ctx.destination);tone.start(now);tone.stop(now+.2);}
 function stop(){if(timer!==null)clearInterval(timer);timer=null;}
 function sync(nodes,connected,assess){const next=eligible(nodes,connected,assess);active=next;if(!on||!active){stop();return;}if(timer===null){beep();timer=setInterval(beep,2000);}}
 async function toggle(){if(on){on=false;stop();return false;}const Audio=root.AudioContext||root.webkitAudioContext;if(!Audio)return false;try{ctx=ctx||new Audio();await ctx.resume();on=ctx.state==='running';if(on&&active&&timer===null){beep();timer=setInterval(beep,2000);}return on;}catch{on=false;return false;}}
 root.addEventListener?.('pagehide',()=>{on=false;active=false;stop();ctx?.close();ctx=null;});
 const api={eligible,sync,toggle,enabled:()=>on};root.GGBrowserAlarm=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
