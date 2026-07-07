(function installPrimeFishingWindow(){
  'use strict';
  if(window.__ONGA_PRIME_WINDOW__) return;
  window.__ONGA_PRIME_WINDOW__ = true;
  const VERSION='v4.6.1 prime-window 2026-07-06';
  const R=Math.PI/180;
  const CFG={scanHours:24,stepMin:30,windowMin:90,updateMs:60000};
  const P={fishway:{lat:33.88913889,lng:130.67458333},nishi:{lat:33.8945411,lng:130.6705074},magari:{lat:33.8952535,lng:130.6721811},confluence:{lat:33.89482,lng:130.6715},ashiya:{lat:33.8960965,lng:130.66676435}};
  let card=null,lastRender=0;

  function clamp(v,a,b){return Math.max(a,Math.min(b,v))}
  function fmtTime(d){try{return d.toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit'})}catch(_){return '--:--'}}
  function fmtRange(s,e){return `${fmtTime(s)}〜${fmtTime(e)}`}
  function tide(d){let h=+d/36e5;return Math.sin((h%12.42)/12.42*2*Math.PI)}
  function tideSlope(d){return(tide(new Date(+d+36e5))-tide(new Date(+d-36e5)))/2}
  function nightScore(d){let h=d.getHours()+d.getMinutes()/60;return (h>=18||h<=5)?1:(h>=16.5&&h<18?0.45:(h>5&&h<=7?0.35:0))}
  function currentDate(){try{if(typeof state!=='undefined'&&state.timeline&&state.timeline[state.currentIndex])return new Date(state.timeline[state.currentIndex].date)}catch(_){ }let d=new Date();d.setMinutes(0,0,0);return d}
  function isClosedAt(d){try{if(window.ONGA_CLOSED_GATE_FLOW_MODEL&&typeof window.ONGA_CLOSED_GATE_FLOW_MODEL.isClosedMainGate==='function')return !!window.ONGA_CLOSED_GATE_FLOW_MODEL.isClosedMainGate({entry:{date:d}})}catch(_){ }try{if(typeof gateObservationForDate==='function'){let o=gateObservationForDate(d);return !!(o&&o.active&&(o.openNos||[]).length===0)}}catch(_){ }return false}
  function gateLabel(d){try{if(typeof gateObservationForDate==='function'){let o=gateObservationForDate(d);if(o&&o.active)return (o.openNos||[]).length?`開門 ${o.openNos.join(',')}`:'全閉'}}catch(_){ }return 'ゲート自動'}
  function nearTideTurn(d){let a=Math.abs(tideSlope(new Date(+d-90*60000))),b=Math.abs(tideSlope(d)),c=Math.abs(tideSlope(new Date(+d+90*60000)));return (b>.025&&(a<.030||c<.030))?1:0}
  function tideName(d){let s=tideSlope(d);if(Math.abs(s)<.015)return '潮止まり';return s>0?'上げ':'下げ'}
  function rank(score){return score>=80?'A':score>=65?'B':score>=50?'C':'D'}
  function timeline(){try{if(typeof state!=='undefined'&&Array.isArray(state.timeline)&&state.timeline.length)return state.timeline.map((e,i)=>({date:new Date(e.date),index:i,entry:e}))}catch(_){ }
    const start=new Date();start.setMinutes(Math.floor(start.getMinutes()/30)*30,0,0);let out=[];for(let i=0;i<=CFG.scanHours*2;i++)out.push({date:new Date(+start+i*30*60000),index:null,entry:null});return out;
  }
  function evalAt(d){
    const sl=tideSlope(d),move=clamp(Math.abs(sl)*2.35,0,1),night=nightScore(d),turn=nearTideTurn(d),closed=isClosedAt(d);
    const rising=sl>0,falling=sl<0;
    const fishway=closed?0.82:0.48;
    const tributary=closed?0.78:0.52;
    const tideFlow=clamp(.25+move*.75,0,1);
    const slackPenalty=Math.abs(sl)<.015?16:0;
    const daytimePenalty=night<.2?6:0;
    let score=34+move*18+night*16+turn*10+tideFlow*10+tributary*8+fishway*7-slackPenalty-daytimePenalty;
    if(closed)score+=6;
    if(falling&&night>.4)score+=5;
    if(rising&&closed)score+=3;
    score=clamp(score,0,100);
    let reasons=[];
    if(closed)reasons.push('全閉で魚道・支流筋');
    else reasons.push(gateLabel(d));
    if(Math.abs(sl)<.015)reasons.push('潮止まり注意'); else reasons.push((turn?'動き始めの':'')+tideName(d));
    if(night>.8)reasons.push('夜間'); else if(night>.3)reasons.push('まずめ');
    if(tideFlow>.65)reasons.push('潮汐流あり');
    return {date:d,score,rank:rank(score),closed,move,night,turn,reasons:dedupe(reasons).slice(0,3),tide:tideName(d)};
  }
  function dedupe(a){return [...new Set(a.filter(Boolean))]}
  function buildWindows(){
    const tl=timeline();const now=new Date();const end=new Date(+now+CFG.scanHours*3600000);let wins=[];
    for(const t of tl){let center=t.date;if(center<now||center>end)continue;let s=new Date(+center-CFG.windowMin*30000),e=new Date(+center+CFG.windowMin*30000);let samples=[new Date(+center-30*60000),center,new Date(+center+30*60000)].map(evalAt);let avg=samples.reduce((a,b)=>a+b.score,0)/samples.length;let best=samples.slice().sort((a,b)=>b.score-a.score)[0];let score=clamp(avg*.65+best.score*.35,0,100);wins.push({start:s,end:e,center,score,rank:rank(score),reasons:dedupe(best.reasons).slice(0,3),closed:best.closed,tide:best.tide,index:t.index});
    }
    wins.sort((a,b)=>b.score-a.score);
    const best=wins[0]||null;
    const second=wins.find(w=>best&&Math.abs(w.center-best.center)>90*60000)||wins[1]||null;
    const avoid=windowsAvoid(tl,now,end);
    return {best,second,avoid};
  }
  function windowsAvoid(tl,now,end){let arr=[];for(const t of tl){let d=t.date;if(d<now||d>end)continue;let e=evalAt(d);arr.push({...e,index:t.index,start:new Date(+d-45*60000),end:new Date(+d+45*60000)})}arr.sort((a,b)=>a.score-b.score);return arr[0]||null}
  function applyWindow(w){
    if(!w)return;try{if(typeof state!=='undefined'&&Array.isArray(state.timeline)){let best=0,bd=Infinity;state.timeline.forEach((e,i)=>{let d=Math.abs(+new Date(e.date)-+w.center);if(d<bd){bd=d;best=i}});state.currentIndex=best;let sl=document.getElementById('timeSlider');if(sl){sl.value=String(best);sl.dispatchEvent(new Event('input',{bubbles:true}));sl.dispatchEvent(new Event('change',{bubbles:true}))}if(typeof computeAndRender==='function')computeAndRender(true);else if(typeof renderAll==='function')renderAll();setTimeout(render,80);return}}catch(err){console.warn('prime window apply failed',err)}
    alert(`本命時間: ${fmtRange(w.start,w.end)}`);
  }
  function cardHtml(w,title,main){if(!w)return `<div class="prime-empty">${title}: 算出不可</div>`;return `<div class="prime-window ${main?'main':''}"><div class="prime-title"><span>${title}</span><b>${w.rank} ${Math.round(w.score)}点</b></div><div class="prime-time">${fmtRange(w.start,w.end)}</div><div class="prime-reason">${w.reasons.join(' + ')}</div>${main?'<button id="primeApplyBtn" class="primary prime-apply">この時間に合わせる</button>':''}</div>`}
  function avoidHtml(w){if(!w)return '';return `<div class="prime-avoid"><div class="prime-title"><span>避ける時間</span><b>${Math.round(w.score)}点</b></div><div>${fmtRange(w.start,w.end)}</div><small>${w.reasons.join(' + ')}</small></div>`}
  function install(){
    let aside=document.querySelector('aside');if(!aside)return false;
    if(!document.getElementById('prime-window-style')){let st=document.createElement('style');st.id='prime-window-style';st.textContent=`.prime-card{border-color:rgba(91,212,255,.38)!important;background:linear-gradient(180deg,rgba(91,212,255,.14),rgba(255,255,255,.05))!important}.prime-head{display:flex;justify-content:space-between;gap:8px;align-items:center}.prime-head h2{margin:0!important}.prime-version{font-size:11px;color:var(--muted,#a9bbce)}.prime-window{border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:10px;margin-top:9px;background:rgba(0,0,0,.14)}.prime-window.main{border-color:rgba(91,212,255,.48);background:rgba(91,212,255,.10)}.prime-title{display:flex;justify-content:space-between;gap:10px;align-items:center;font-size:12px;color:var(--muted,#a9bbce)}.prime-title b{font-size:16px;color:#fff}.prime-time{font-size:22px;font-weight:900;margin:4px 0;color:#fff;letter-spacing:.02em}.prime-reason{font-size:12px;color:var(--muted,#a9bbce);line-height:1.45}.prime-apply{margin-top:9px;width:100%;background:#5bd4ff!important;color:#04111d!important}.prime-avoid{font-size:12px;color:var(--muted,#a9bbce);border-top:1px solid rgba(255,255,255,.10);margin-top:10px;padding-top:8px}.mobile .prime-time{font-size:18px}`;document.head.appendChild(st)}
    card=document.getElementById('primeWindowCard');if(!card){card=document.createElement('div');card.id='primeWindowCard';card.className='card prime-card';aside.insertBefore(card,aside.firstElementChild)}return true;
  }
  function render(){
    if(!install())return;lastRender=Date.now();const res=buildWindows();card.innerHTML=`<div class="prime-head"><h2>今日の本命90分</h2><span class="prime-version">${VERSION}</span></div>${cardHtml(res.best,'本命',true)}${cardHtml(res.second,'次点',false)}${avoidHtml(res.avoid)}`;let btn=document.getElementById('primeApplyBtn');if(btn)btn.onclick=()=>applyWindow(res.best);
  }
  const prevUpdate=typeof updateSidebar==='function'?updateSidebar:null;
  if(prevUpdate){try{updateSidebar=function(){let r=prevUpdate.apply(this,arguments);setTimeout(render,0);return r}}catch(_){ }}
  function boot(){if(!install()){setTimeout(boot,250);return}render();setInterval(()=>{if(Date.now()-lastRender>CFG.updateMs-1000)render()},CFG.updateMs)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
  window.ONGA_PRIME_WINDOW={version:VERSION,render,buildWindows,applyWindow};
})();
