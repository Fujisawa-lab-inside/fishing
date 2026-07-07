(function installOngaLightweightCFD(){
  'use strict';
  if(window.__ONGA_LIGHTWEIGHT_CFD__) return;
  window.__ONGA_LIGHTWEIGHT_CFD__ = true;
  const VERSION='v4.6.3 lightweight-2d-cfd 2026-07-06';
  const R=Math.PI/180;
  const bounds={south:33.8877,west:130.6648,north:33.8972,east:130.6810};
  const P={fishway:{lat:33.88913889,lng:130.67458333},nishi:{lat:33.8945411,lng:130.6705074},magari:{lat:33.8952535,lng:130.6721811},confluence:{lat:33.89482,lng:130.6715},ashiya:{lat:33.8960965,lng:130.66676435},barrage:{lat:33.88945,lng:130.67955},port:{lat:33.8922,lng:130.6782}};
  const GATES=[[33.88886111,130.67497222],[33.88891667,130.67552778],[33.88897222,130.67608333],[33.88902778,130.67661111],[33.88908333,130.67713889],[33.88911111,130.67772222],[33.88916667,130.67825],[33.88922222,130.67875]].map(p=>({lat:p[0],lng:p[1]}));
  const WATER=[[33.8961715,130.6657907],[33.8959932,130.6657907],[33.8958683,130.6659627],[33.8955294,130.6658982],[33.8952261,130.6660486],[33.8944055,130.6672093],[33.8918724,130.6721958],[33.891908,130.6726686],[33.8906771,130.6726901],[33.8885185,130.6720668],[33.888233,130.6720668],[33.8880903,130.6722173],[33.8880903,130.6724322],[33.888233,130.6725827],[33.8896246,130.6728406],[33.8906771,130.673206],[33.8920507,130.6732275],[33.891908,130.6735499],[33.8916226,130.6737648],[33.8906057,130.6741087],[33.8903917,130.674646],[33.8899635,130.6745171],[33.8893213,130.674646],[33.8896067,130.6784289],[33.8897494,130.6786438],[33.8909447,130.6786868],[33.8914085,130.6789017],[33.8924432,130.6787513],[33.8931389,130.6782784],[33.894245,130.6769028],[33.8944769,130.6764515],[33.8948693,130.6749684],[33.8951726,130.6749899],[33.8954223,130.6753123],[33.8945661,130.6772682],[33.8935492,130.6785148],[33.8925503,130.6791811],[33.8913193,130.6795465],[33.8912123,130.679783],[33.891355,130.6800194],[33.8927465,130.6796325],[33.8938347,130.6789017],[33.894905,130.6775906],[33.8963678,130.6746245],[33.8963143,130.6735713],[33.8960288,130.6723247],[33.8954223,130.6704333],[33.8951904,130.6702399],[33.8955115,130.6693156],[33.8961715,130.6683699],[33.8965283,130.6672738],[33.8965105,130.6669944],[33.8962429,130.6665],[33.8962964,130.6659627]];
  const isMobile=matchMedia('(max-width:760px)').matches;
  const nx=isMobile?74:118, ny=isMobile?58:86;
  const n=nx*ny;
  const water=new Uint8Array(n),phi=new Float32Array(n),nextPhi=new Float32Array(n),src=new Float32Array(n),u=new Float32Array(n),v=new Float32Array(n);
  const dx=((bounds.east-bounds.west)*111320*Math.cos(((bounds.north+bounds.south)/2)*R))/(nx-1);
  const dy=((bounds.north-bounds.south)*111320)/(ny-1);
  let lastKey='',lastSolve=0,enabled=localStorage.getItem('ongaCFD')!=='off',panel=null,info=null,button=null;

  function idx(i,j){return j*nx+i}
  function clamp(x,a,b){return Math.max(a,Math.min(b,x))}
  function lat(j){return bounds.south+(bounds.north-bounds.south)*j/(ny-1)}
  function lng(i){return bounds.west+(bounds.east-bounds.west)*i/(nx-1)}
  function ijOf(ll){return {i:clamp(Math.round((ll.lng-bounds.west)/(bounds.east-bounds.west)*(nx-1)),0,nx-1),j:clamp(Math.round((ll.lat-bounds.south)/(bounds.north-bounds.south)*(ny-1)),0,ny-1)}}
  function meterDelta(a,b){let la=(a.lat+b.lat)*.5*R;return{x:(b.lng-a.lng)*111320*Math.cos(la),y:(b.lat-a.lat)*111320}}
  function inPoly(ll){let x=ll.lng,y=ll.lat,ok=false;for(let i=0,j=WATER.length-1;i<WATER.length;j=i++){let xi=WATER[i][1],yi=WATER[i][0],xj=WATER[j][1],yj=WATER[j][0];if((yi>y)!=(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)ok=!ok}return ok}
  function waterAt(ll){try{if(typeof window.isWaterPoint==='function')return !!window.isWaterPoint(ll.lat,ll.lng);}catch(_){ }try{if(typeof window.isWater==='function')return !!window.isWater(ll.lat,ll.lng);}catch(_){ }return inPoly(ll)}
  function currentDate(){try{if(typeof state!=='undefined'&&state.timeline&&state.timeline[state.currentIndex])return new Date(state.timeline[state.currentIndex].date);}catch(_){ }let d=new Date();d.setMinutes(0,0,0);return d}
  function tide(d=currentDate()){let h=+d/36e5;return Math.sin((h%12.42)/12.42*2*Math.PI)}
  function tideSlope(d=currentDate()){return(tide(new Date(+d+36e5))-tide(new Date(+d-36e5)))/2}
  function closedGate(){try{if(window.ONGA_CLOSED_GATE_FLOW_MODEL&&typeof window.ONGA_CLOSED_GATE_FLOW_MODEL.isClosedMainGate==='function')return !!window.ONGA_CLOSED_GATE_FLOW_MODEL.isClosedMainGate({entry:{date:currentDate()}});}catch(_){ }return false}
  function openGateIndices(){try{if(typeof gateObservationForDate==='function'){let o=gateObservationForDate(currentDate());if(o&&o.active)return (o.openNos||[]).map(x=>x-1).filter(x=>x>=0&&x<8);}}catch(_){ }return [0,1,2,3,4,5,6,7]}
  function addAt(ll,q,spread=1){let p=ijOf(ll);for(let dj=-spread;dj<=spread;dj++)for(let di=-spread;di<=spread;di++){let i=p.i+di,j=p.j+dj;if(i<0||i>=nx||j<0||j>=ny)continue;let k=idx(i,j);if(!water[k])continue;let w=1/(1+di*di+dj*dj);src[k]+=q*w}}
  function buildMask(){for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){let k=idx(i,j);water[k]=waterAt({lat:lat(j),lng:lng(i)})?1:0;phi[k]=nextPhi[k]=src[k]=u[k]=v[k]=0}}
  function buildSources(){src.fill(0);let sl=tideSlope(),closed=closedGate(),rain=.12;try{if(typeof state!=='undefined'&&Number.isFinite(state.rainIndex))rain=state.rainIndex}catch(_){ }
    addAt(P.fishway,.70+rain*.35,1);addAt(P.nishi,.50+rain*.85,2);addAt(P.magari,.45+rain*.75,2);
    if(!closed){let ids=openGateIndices();let q=(.85+rain*.70)/(ids.length||1);for(const gi of ids)addAt(GATES[gi]||GATES[0],q,1)}
    if(sl>=0){addAt(P.ashiya,.85+sl*1.2,3);addAt(P.barrage,-.34,2);addAt(P.confluence,-.22,2)}
    else{addAt(P.confluence,.50+Math.abs(sl)*.9,2);addAt(P.ashiya,-.95-Math.abs(sl)*1.2,3)}
    if(closed){for(const g of GATES)addAt(g,-.06,1)}
  }
  function solve(iter=enabled?70:20){buildSources();for(let t=0;t<iter;t++){for(let j=1;j<ny-1;j++)for(let i=1;i<nx-1;i++){let k=idx(i,j);if(!water[k]){nextPhi[k]=0;continue}let sum=0,c=0;let ks=[idx(i-1,j),idx(i+1,j),idx(i,j-1),idx(i,j+1)];for(const kk of ks){if(water[kk]){sum+=phi[kk];c++}}nextPhi[k]=c?sum/c+src[k]*0.045:phi[k]}phi.set(nextPhi)}
    for(let j=1;j<ny-1;j++)for(let i=1;i<nx-1;i++){let k=idx(i,j);if(!water[k]){u[k]=v[k]=0;continue}let e=water[idx(i+1,j)]?phi[idx(i+1,j)]:phi[k],w=water[idx(i-1,j)]?phi[idx(i-1,j)]:phi[k],nn=water[idx(i,j+1)]?phi[idx(i,j+1)]:phi[k],s=water[idx(i,j-1)]?phi[idx(i,j-1)]:phi[k];u[k]=clamp(-(e-w)/(2*dx)*110,-2,2);v[k]=clamp(-(nn-s)/(2*dy)*110,-2,2)}
    lastKey=stateKey();lastSolve=performance.now();}
  function stateKey(){return `${closedGate()?1:0}:${openGateIndices().join(',')}:${Math.round(tideSlope()*100)}`}
  function ensureFresh(){let k=stateKey(),now=performance.now();if(k!==lastKey||now-lastSolve>1800)solve(isMobile?48:70)}
  function bilinear(arr,ll){let x=(ll.lng-bounds.west)/(bounds.east-bounds.west)*(nx-1),y=(ll.lat-bounds.south)/(bounds.north-bounds.south)*(ny-1);if(x<0||y<0||x>nx-1||y>ny-1)return 0;let i=Math.floor(x),j=Math.floor(y),fx=x-i,fy=y-j;i=clamp(i,0,nx-2);j=clamp(j,0,ny-2);let a=arr[idx(i,j)],b=arr[idx(i+1,j)],c=arr[idx(i,j+1)],d=arr[idx(i+1,j+1)];return a*(1-fx)*(1-fy)+b*fx*(1-fy)+c*(1-fx)*fy+d*fx*fy}
  function velocityAt(ll){ensureFresh();let vv={x:bilinear(u,ll),y:bilinear(v,ll)};let m=Math.hypot(vv.x,vv.y);if(m>1.8){vv.x*=1.8/m;vv.y*=1.8/m}return vv}
  function scalarAt(ll){ensureFresh();return {phi:bilinear(phi,ll),speed:Math.hypot(bilinear(u,ll),bilinear(v,ll)),source:bilinear(src,ll),closedGate:closedGate()}}
  function installPanel(){let map=document.getElementById('mapCanvas')||document.querySelector('canvas.mapCanvas')||document.querySelector('canvas.map');if(!map)return false;let parent=map.parentElement||document.body;if(getComputedStyle(parent).position==='static')parent.style.position='relative';panel=document.createElement('div');panel.id='ongaCfdPanel';panel.style.cssText='position:absolute;right:12px;top:164px;z-index:11;background:rgba(4,14,24,.78);border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:8px 10px;color:#eef;font:12px -apple-system,BlinkMacSystemFont,sans-serif;backdrop-filter:blur(10px);max-width:250px';panel.innerHTML='<button id="ongaCfdToggle" style="border:0;border-radius:999px;padding:6px 10px;background:#8cff9b;color:#04111d;font-weight:700">CFD ON</button><div id="ongaCfdInfo" style="margin-top:6px;color:#a9bbce;line-height:1.35">軽量2D CFD</div>';parent.appendChild(panel);button=panel.querySelector('#ongaCfdToggle');info=panel.querySelector('#ongaCfdInfo');function sync(){button.textContent=enabled?'CFD ON':'CFD OFF';button.style.background=enabled?'#8cff9b':'#18304a';button.style.color=enabled?'#04111d':'#eef';localStorage.setItem('ongaCFD',enabled?'on':'off')}button.onclick=()=>{enabled=!enabled;sync();solve(enabled?80:20)};sync();return true}
  function tick(){ensureFresh();if(info)info.textContent=(closedGate()?'全閉: 本流ゲート流0 / ':'')+`CFD格子 ${nx}×${ny} / ${VERSION}`;setTimeout(tick,1000)}
  function init(){buildMask();solve(90);installPanel();tick();try{let sub=document.querySelector('.sub');if(sub&&!sub.textContent.includes('軽量CFD'))sub.textContent+=' 軽量2D CFD速度場を粒子流に適用。';}catch(_){ }}
  window.ONGA_CFD={version:VERSION,velocityAt,scalarAt,solve,isEnabled:()=>enabled,setEnabled:v=>{enabled=!!v;localStorage.setItem('ongaCFD',enabled?'on':'off');solve(enabled?80:20)},closedGate};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
