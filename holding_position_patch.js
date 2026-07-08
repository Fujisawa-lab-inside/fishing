(function installOngaHoldingPositionPatch(){
  'use strict';
  if(window.__ONGA_HOLDING_POSITION_PATCH__) return;
  window.__ONGA_HOLDING_POSITION_PATCH__ = true;
  const VERSION='v4.7 flow-holding 2026-07-08';
  const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,Number(v)||0));
  const fmt=v=>Math.round(clamp(v)*100);
  const tideOf=d=>Math.sin(((+d/36e5)%12.42)/12.42*2*Math.PI);
  const slopeOf=d=>(tideOf(new Date(+d+36e5))-tideOf(new Date(+d-36e5)))/2;
  function currentDate(){try{if(state?.timeline?.[state.currentIndex])return new Date(state.timeline[state.currentIndex].date)}catch(_){ }return new Date();}
  function night(d){const h=d.getHours()+d.getMinutes()/60;return h>=18||h<=5?1:(h>=16.5&&h<18?0.45:(h>5&&h<=7?0.35:0));}
  function closedGate(d){try{if(window.ONGA_CLOSED_GATE_FLOW_MODEL?.isClosedMainGate)return !!window.ONGA_CLOSED_GATE_FLOW_MODEL.isClosedMainGate({entry:{date:d}})}catch(_){ }try{if(typeof gateObservationForDate==='function'){const o=gateObservationForDate(d);return !!(o&&o.active&&(o.openNos||[]).length===0)}}catch(_){ }return false;}
  function evalFlow(d){
    const sl=slopeOf(d),move=clamp(Math.abs(sl)*2.4),closed=closedGate(d),n=night(d),fall=sl<0,rise=sl>0;
    const main=closed?0:clamp(.22+move*.65);
    const fish=closed?clamp(.72+n*.14+move*.10):clamp(.34+move*.22+(rise?.12:0));
    const nishi=closed?clamp(.55+move*.14):clamp(.28+move*.25);
    const magari=closed?clamp(.36+move*.10):clamp(.18+Math.max(0,-tideOf(d))*.25);
    const shear=clamp(.30*main+.22*fish+.24*nishi+.15*magari+.20*move);
    const eddy=clamp(.28*fish+.25*nishi+.18*magari+.18*(1-main)+.12*move);
    const hold=clamp(.34*shear+.28*eddy+.20*n+.18*(fish+nishi+magari)/2.4);
    let mode=closed?'全閉・魚道/支川支配':fall?'下げ主導・本流脇':rise?'上げ主導・魚道出口':'潮止まり';
    const candidates=[];
    candidates.push({name:'魚道出口の本流合流縁',score:clamp(.42*fish+.28*shear+.20*n+.10*eddy),why:'緩流から本流へ出る流速差'});
    candidates.push({name:'西川合流縁',score:clamp(.40*nishi+.25*shear+.20*eddy+.15*n),why:'淡水・濁り・本流の境界'});
    candidates.push({name:'本流流芯脇の低流速帯',score:clamp(.38*main+.30*shear+.17*eddy+.15*n),why:'強流に隣接した待機帯'});
    candidates.push({name:'曲川・放水路の雨後筋',score:clamp(.42*magari+.22*shear+.18*eddy+.18*n),why:'雨後の濁り筋とヨレ'});
    candidates.sort((a,b)=>b.score-a.score);
    return {date:d,main,fish,nishi,magari,shear,eddy,hold,mode,candidates};
  }
  function ensureStyle(){if(document.getElementById('holding-position-style'))return;const st=document.createElement('style');st.id='holding-position-style';st.textContent=`.holding-card{border-color:rgba(255,209,102,.38)!important;background:linear-gradient(180deg,rgba(255,209,102,.13),rgba(255,255,255,.045))!important}.holding-head{display:flex;justify-content:space-between;gap:8px;align-items:center}.holding-head h2{margin:0!important}.holding-version{font-size:10px;color:var(--muted,#a9bbce)}.holding-mode{font-size:12px;color:#ffe6a5;margin:6px 0 8px}.holding-bars{display:grid;gap:6px;margin:8px 0}.holding-bar{display:grid;grid-template-columns:54px 1fr 34px;gap:8px;align-items:center;font-size:11px;color:var(--muted,#a9bbce)}.holding-track{height:7px;border-radius:999px;background:rgba(255,255,255,.10);overflow:hidden}.holding-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,#52d6ff,#ffd166)}.holding-list{display:grid;gap:7px;margin-top:9px}.holding-item{border:1px solid rgba(255,255,255,.10);border-radius:12px;padding:8px;background:rgba(0,0,0,.13)}.holding-title{display:flex;justify-content:space-between;gap:8px;font-weight:800;font-size:12px}.holding-why{font-size:11px;line-height:1.4;color:var(--muted,#a9bbce);margin-top:3px}.holding-link{display:block;text-align:center;margin-top:10px;border-radius:12px;padding:10px;text-decoration:none!important;font-weight:900;background:#ffd166;color:#08111d!important}.holding-note{font-size:11px;color:var(--muted,#a9bbce);line-height:1.45;margin-top:8px}`;document.head.appendChild(st);}
  function bar(label,v){return `<div class="holding-bar"><span>${label}</span><div class="holding-track"><div class="holding-fill" style="width:${fmt(v)}%"></div></div><b>${fmt(v)}</b></div>`;}
  function render(){
    ensureStyle();const aside=document.querySelector('aside');if(!aside)return false;let card=document.getElementById('holdingPositionCard');if(!card){card=document.createElement('div');card.id='holdingPositionCard';card.className='card holding-card';const anchor=document.getElementById('primeWindowCard')?.nextSibling||aside.firstElementChild;aside.insertBefore(card,anchor);}const r=evalFlow(currentDate());
    card.innerHTML=`<div class="holding-head"><h2>定位予測</h2><span class="holding-version">${VERSION}</span></div><div class="holding-mode">${r.mode}</div><div class="holding-bars">${bar('本流',r.main)}${bar('魚道',r.fish)}${bar('西川',r.nishi)}${bar('曲川',r.magari)}${bar('境界',r.shear)}${bar('渦',r.eddy)}</div><div class="holding-list">${r.candidates.slice(0,4).map((c,i)=>`<div class="holding-item"><div class="holding-title"><span>${i+1}. ${c.name}</span><b>${fmt(c.score)}</b></div><div class="holding-why">${c.why}．点ではなく境界線を横切らせる．</div></div>`).join('')}</div><a class="holding-link" href="./flow_holding_view.html">流れ場ビューアを開く</a><div class="holding-note">ロッド判断は表示しない．本流・魚道・西川・曲川の流れ場から定位点だけを推定する．</div>`;
    return true;
  }
  const prev=typeof updateSidebar==='function'?updateSidebar:null;
  if(prev){try{updateSidebar=function(){const out=prev.apply(this,arguments);setTimeout(render,0);return out;};}catch(_){ }}
  function boot(){if(!render())setTimeout(boot,250);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
  setInterval(render,60000);
  window.ONGA_HOLDING_POSITION={version:VERSION,evalFlow,render};
})();
