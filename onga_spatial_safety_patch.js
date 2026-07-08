// v4.6.2 Onga spatial safety override
(function(){'use strict';
const V='onga-spatial-safety-v4.6.2',REF=[33.892724,130.674220],RAD=Math.PI/180,C=Math.cos(33.892724*RAD);
const NS=[
{id:'onga_kakouzeki_barrage',name:'遠賀川河口堰',kind:'barrage',buf:24,line:[[33.8894929,130.6746400],[33.8897854,130.6781117]]},
{id:'onga_left_bridge',name:'左岸側の橋',kind:'bridge',buf:10,line:[[33.8951109,130.6669177],[33.8962809,130.6683850]]},
{id:'onga_right_channel_bridge',name:'右岸側水路の橋',kind:'bridge',buf:10,line:[[33.8919257,130.6784988],[33.8920960,130.6790658]]},
{id:'onga_fishway',name:'魚道',kind:'fishway',buf:8,point:[33.8894929,130.6745243]}
];
const NC=[
{id:'onga_kakouzeki_barrage',name:'遠賀川河口堰',kind:'barrage',buf:4,line:[[33.8894929,130.6746400],[33.8897854,130.6781117]]},
{id:'onga_left_bridge',name:'左岸側の橋',kind:'bridge',buf:4,line:[[33.8951109,130.6669177],[33.8962809,130.6683850]]},
{id:'onga_right_channel_bridge',name:'右岸側水路の橋',kind:'bridge',buf:4,line:[[33.8919257,130.6784988],[33.8920960,130.6790658]]}
];
const CL=typeof clamp==='function'?clamp:((v,a,b)=>Math.max(a,Math.min(b,v))),GA=typeof gaussian==='function'?gaussian:((x,m,s)=>Math.exp(-.5*((x-m)/s)**2));
function xy(lat,lng){return {x:(lng-REF[1])*111320*C,y:(lat-REF[0])*110540};}
function p(a){return {lat:a[0],lng:a[1]};}
function d2(a,b){const x=a.x-b.x,y=a.y-b.y;return x*x+y*y;}
function pd(pt,a,b){const P=xy(pt.lat,pt.lng),A=xy(a.lat,a.lng),B=xy(b.lat,b.lng),vx=B.x-A.x,vy=B.y-A.y,wx=P.x-A.x,wy=P.y-A.y,t=Math.max(0,Math.min(1,(wx*vx+wy*vy)/(vx*vx+vy*vy||1))),Q={x:A.x+vx*t,y:A.y+vy*t};return Math.sqrt(d2(P,Q));}
function o(a,b,c){return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);}
function on(a,b,c){return Math.min(a.x,b.x)-1e-9<=c.x&&c.x<=Math.max(a.x,b.x)+1e-9&&Math.min(a.y,b.y)-1e-9<=c.y&&c.y<=Math.max(a.y,b.y)+1e-9;}
function inter(a,b,c,d){a=xy(a.lat,a.lng);b=xy(b.lat,b.lng);c=xy(c.lat,c.lng);d=xy(d.lat,d.lng);const o1=o(a,b,c),o2=o(a,b,d),o3=o(c,d,a),o4=o(c,d,b);return ((o1>0&&o2<0||o1<0&&o2>0)&&(o3>0&&o4<0||o3<0&&o4>0))||(Math.abs(o1)<1e-9&&on(a,b,c))||(Math.abs(o2)<1e-9&&on(a,b,d))||(Math.abs(o3)<1e-9&&on(c,d,a))||(Math.abs(o4)<1e-9&&on(c,d,b));}
function sd(a,b,c,d){return inter(a,b,c,d)?0:Math.min(pd(a,c,d),pd(b,c,d),pd(c,a,b),pd(d,a,b));}
function hit(lat,lng,r){if(r.point){const A=xy(lat,lng),B=xy(r.point[0],r.point[1]);return Math.sqrt(d2(A,B))<=r.buf;}return pd({lat,lng},p(r.line[0]),p(r.line[1]))<=r.buf;}
function noStandAt(lat,lng){return NS.find(r=>hit(lat,lng,r))||null;}
function castBlock(lat1,lng1,lat2,lng2){const a={lat:lat1,lng:lng1},b={lat:lat2,lng:lng2};return NC.find(r=>sd(a,b,p(r.line[0]),p(r.line[1]))<=r.buf)||null;}
function okHotspot(h){return !!(h&&Number.isFinite(h.lat)&&Number.isFinite(h.lng)&&!noStandAt(h.lat,h.lng)&&(!Number.isFinite(h.targetLat)||!Number.isFinite(h.targetLng)||(!noStandAt(h.targetLat,h.targetLng)&&!castBlock(h.lat,h.lng,h.targetLat,h.targetLng))));}
function rerank(arr){return (arr||[]).filter(okHotspot).map((h,i)=>Object.assign({},h,{rank:i+1,score100:Math.round(((Number.isFinite(h.score)?h.score:(h.score100||0)/100)||0)*100),targetScore100:Math.round(((Number.isFinite(h.targetScore)?h.targetScore:(h.targetScore100||h.score100||0)/100)||0)*100)}));}
window.ONGA_SPATIAL_SAFETY={version:V,noStandAt,castBlock,hotspotAllowed:okHotspot,rules:{noStand:NS,noLureCrossing:NC}};
if(typeof landConfidenceAt==='function'){const prev=landConfidenceAt;landConfidenceAt=function(lat,lng){return noStandAt(lat,lng)?0:prev(lat,lng);};}
if(typeof findLandCastPositionForWater==='function'&&typeof destinationPointMeters==='function')findLandCastPositionForWater=function(wp){if(!wp||!Number.isFinite(wp.lat)||!Number.isFinite(wp.lng))return null;const M=typeof CAST_MODEL!=='undefined'?CAST_MODEL:{maxM:100,preferredM:45};let best=null,bs=[],ds=[8,12,16,20,26,32,40,50,62,74,86,98];for(let b=0;b<360;b+=15)bs.push(b);for(const d of ds)for(const b of bs){const q=destinationPointMeters(wp.lat,wp.lng,b,d);if(typeof isWithinBounds==='function'&&!isWithinBounds(q.lat,q.lng))continue;if(noStandAt(q.lat,q.lng)||castBlock(q.lat,q.lng,wp.lat,wp.lng))continue;const land=landConfidenceAt(q.lat,q.lng);if(land<.78)continue;const toward=(Math.atan2((wp.lng-q.lng)*111320*Math.cos(q.lat*RAD),(wp.lat-q.lat)*110540)*180/Math.PI+360)%360;let ev=0;for(const dd of [4,8,14,20,28]){const z=destinationPointMeters(q.lat,q.lng,toward,dd);if(typeof isKnownWater==='function'&&isKnownWater(z.lat,z.lng))ev++;}if(ev===0&&d>28)continue;const reach=CL(1-d/M.maxM,0,1),pref=GA(d,M.preferredM,32),bq=CL(.55*land+.30*pref+.15*reach,0,1),score=wp.score*(.72+.28*bq);if(!best||score>best.score)best={lat:q.lat,lng:q.lng,distanceM:d,bearing:b,landConfidence:land,bankQuality:bq,score};}return best;};
if(typeof makeShoreCastingHotspots==='function')makeShoreCastingHotspots=function(cands,n=8){const M=typeof CAST_MODEL!=='undefined'?CAST_MODEL:{bankSepM:85,targetSepM:90},sorted=[...(cands||[])].filter(x=>x&&Number.isFinite(x.score)&&x.score>.35).sort((a,b)=>b.score-a.score),raw=[];for(let i=0;i<Math.min(sorted.length,850);i++){const t=sorted[i],land=findLandCastPositionForWater(t);if(!land)continue;const h=Object.assign({},t,{lat:land.lat,lng:land.lng,targetLat:t.lat,targetLng:t.lng,targetScore:t.score,castDistanceM:land.distanceM,landConfidence:land.landConfidence,bankQuality:land.bankQuality,onLand:true,score:CL(land.score,0,1),spatialSafety:V,structureName:'岸上釣り座：'+t.structureName,reason:'空間安全マスク通過 / 100m射程内で水面標的へ届く / '+t.reason});if(okHotspot(h))raw.push(h);}raw.sort((a,b)=>b.score-a.score);const chosen=[];for(const c of raw){let ok=true;for(const h of chosen){if(haversine(c.lat,c.lng,h.lat,h.lng)<M.bankSepM||haversine(c.targetLat,c.targetLng,h.targetLat,h.targetLng)<M.targetSepM){ok=false;break;}}if(ok)chosen.push(c);if(chosen.length>=n)break;}return rerank(chosen);};
if(typeof renderHotspotList==='function'){const prev=renderHotspotList;renderHotspotList=function(){if(typeof state!=='undefined'&&Array.isArray(state.hotspots))state.hotspots=rerank(state.hotspots);prev();try{const root=document.getElementById('hotspotList');if(root&&!root.querySelector('.ongaSafetyNote')){const note=document.createElement('div');note.className='note ongaSafetyNote';note.style.marginTop='8px';note.textContent='v4.6.2: 河口堰・橋・魚道の釣り座除外と、河口堰/橋を跨ぐキャスト禁止を適用中。';root.appendChild(note);}}catch(e){}};}
if(typeof drawPins==='function'){const prev=drawPins;drawPins=function(ctx){if(typeof state!=='undefined'&&Array.isArray(state.hotspots))state.hotspots=rerank(state.hotspots);return prev(ctx);};}
if(typeof updateWaterStatus==='function'){const prev=updateWaterStatus;updateWaterStatus=function(){prev();const el=document.getElementById('waterStatus');if(el&&!el.textContent.includes('v4.6.2空間安全'))el.textContent+=' / v4.6.2空間安全: 河口堰・橋・魚道除外';};}
try{const s=document.querySelector('.sub');if(s&&!s.textContent.includes('v4.6.2'))s.innerHTML+='<br>v4.6.2: 遠賀川河口堰・橋・魚道の釣り座除外と、河口堰/橋を跨ぐキャスト禁止を適用。';if(typeof state!=='undefined'){state.waterSampleCache?.clear?.();state.fluidCache?.clear?.();if(state.timeline?.length&&typeof computeAndRender==='function')setTimeout(()=>computeAndRender(true),0);}}catch(e){console.warn('[onga-spatial-safety]',e);}
})();
