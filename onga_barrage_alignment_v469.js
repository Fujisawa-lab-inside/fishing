// v4.6.9 barrage alignment calibration patch
(function(){
  'use strict';
  if (window.__ONGA_BARRAGE_ALIGNMENT_V469__) return;
  window.__ONGA_BARRAGE_ALIGNMENT_V469__ = true;
  const VERSION = 'onga-barrage-alignment-v4.6.9';
  const SRC_W = {lat:33.8894929, lng:130.6746400};
  const SRC_E = {lat:33.8897854, lng:130.6781117};
  const TGT_W = {lat:33.88886111, lng:130.67497222};
  const TGT_E = {lat:33.88922222, lng:130.67875000};
  const REF = {lat:33.892724, lng:130.674220};
  const toRad = d => d * Math.PI / 180;
  const cosRef = Math.cos(toRad(REF.lat));
  const clampLocal = typeof clamp === 'function' ? clamp : ((v,a,b)=>Math.max(a,Math.min(b,v)));
  function xy(p){ return {x:(p.lng-REF.lng)*111320*cosRef, y:(p.lat-REF.lat)*110540}; }
  function ll(p){ return {lat:REF.lat+p.y/110540, lng:REF.lng+p.x/(111320*cosRef)}; }
  const s0=xy(SRC_W), s1=xy(SRC_E), t0=xy(TGT_W), t1=xy(TGT_E);
  const sv={x:s1.x-s0.x,y:s1.y-s0.y}, tv={x:t1.x-t0.x,y:t1.y-t0.y};
  const scale=(Math.hypot(tv.x,tv.y)||1)/(Math.hypot(sv.x,sv.y)||1);
  const angle=Math.atan2(tv.y,tv.x)-Math.atan2(sv.y,sv.x);
  const ca=Math.cos(angle), sa=Math.sin(angle);
  function rawToAligned(lat,lng){ const p=xy({lat,lng}), x=p.x-s0.x, y=p.y-s0.y; return ll({x:t0.x+scale*(ca*x-sa*y), y:t0.y+scale*(sa*x+ca*y)}); }
  function alignedToRaw(lat,lng){ const p=xy({lat,lng}), x=p.x-t0.x, y=p.y-t0.y; return ll({x:s0.x+(ca*x+sa*y)/scale, y:s0.y+(-sa*x+ca*y)/scale}); }
  const oldMask = typeof calibratedWaterMaskValueAt === 'function' ? calibratedWaterMaskValueAt : null;
  const oldHydro = typeof nearestHydroCorridor === 'function' ? nearestHydroCorridor : null;
  if (oldMask) calibratedWaterMaskValueAt = function(lat,lng){ const p=alignedToRaw(lat,lng); return oldMask(p.lat,p.lng); };
  if (typeof isKnownWater === 'function') isKnownWater = function(lat,lng){ return calibratedWaterMaskValueAt(lat,lng) > .5; };
  if (oldHydro) nearestHydroCorridor = function(lat,lng){ const p=alignedToRaw(lat,lng); const h=oldHydro(p.lat,p.lng); return h ? {...h, barrageAligned:VERSION} : h; };
  const rawGreen = (window.ONGA_APPROVED_GREEN_RECOGNITION && Array.isArray(window.ONGA_APPROVED_GREEN_RECOGNITION.greenStandPoints)) ? window.ONGA_APPROVED_GREEN_RECOGNITION.greenStandPoints : [];
  const green = rawGreen.map(q=>{ const p=rawToAligned(q[0],q[1]); return [p.lat,p.lng]; }).filter(q=>Number.isFinite(q[0])&&Number.isFinite(q[1]));
  function hav(a,b,c,d){ if(typeof haversine==='function')return haversine(a,b,c,d); const p1=toRad(a),p2=toRad(c),d1=toRad(c-a),d2=toRad(d-b),x=Math.sin(d1/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(d2/2)**2; return 12742000*Math.atan2(Math.sqrt(x),Math.sqrt(1-x)); }
  function unsafeStand(a,b){ return !!(window.ONGA_SPATIAL_SAFETY && window.ONGA_SPATIAL_SAFETY.noStandAt && window.ONGA_SPATIAL_SAFETY.noStandAt(a,b)); }
  function unsafeCast(a,b,c,d){ return !!(window.ONGA_SPATIAL_SAFETY && window.ONGA_SPATIAL_SAFETY.castBlock && window.ONGA_SPATIAL_SAFETY.castBlock(a,b,c,d)); }
  function nearestAlignedGreen(target){ if(!target||!Number.isFinite(target.lat)||!Number.isFinite(target.lng))return null; const max=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.maxM)||100; let best=null; for(const p of green){ if(unsafeStand(p[0],p[1]))continue; const d=hav(p[0],p[1],target.lat,target.lng); if(d<2||d>max||unsafeCast(p[0],p[1],target.lat,target.lng))continue; const score=(target.score||0)*(.7+.3*Math.exp(-.5*((d-35)/32)**2)); if(!best||score>best.score)best={lat:p[0],lng:p[1],distanceM:d,score,landConfidence:1,bankQuality:1,onBarrageAlignedBoundary:true}; } return best; }
  if(typeof findLandCastPositionForWater==='function') findLandCastPositionForWater = nearestAlignedGreen;
  if(typeof makeShoreCastingHotspots==='function') makeShoreCastingHotspots = function(cands,n=8){ const sorted=[...(cands||[])].filter(p=>p&&Number.isFinite(p.score)&&p.score>.35).sort((a,b)=>b.score-a.score), raw=[]; for(let i=0;i<Math.min(sorted.length,1200);i++){ const t=sorted[i], s=nearestAlignedGreen(t); if(!s)continue; raw.push({...t, lat:s.lat, lng:s.lng, targetLat:t.lat, targetLng:t.lng, targetScore:t.score, castDistanceM:s.distanceM, onLand:true, onGreenBoundary:true, onBarrageAlignedBoundary:true, score:clampLocal(s.score,0,1), structureName:`河口堰補正境界釣り座：${t.structureName||t.hydroLabel||'水面標的'}`, reason:`河口堰1-8補正後の境界上 / ${Math.round(s.distanceM)}m先 / ${t.reason||''}`}); } raw.sort((a,b)=>b.score-a.score); return raw.slice(0,n).map((h,i)=>({...h,rank:i+1,score100:Math.round((h.score||0)*100),targetScore100:Math.round((h.targetScore||h.score||0)*100)})); };
  window.ONGA_BARRAGE_ALIGNMENT = {version:VERSION, source:{west:SRC_W,east:SRC_E}, target:{west:TGT_W,east:TGT_E}, scale, angleDeg:angle*180/Math.PI, rawToAligned, alignedToRaw, green};
  try{ state.waterSampleCache?.clear?.(); state.fluidCache?.clear?.(); state.fluidBaseCache?.clear?.(); state.validationCache?.clear?.(); if(state.timeline?.length && typeof computeAndRender==='function') setTimeout(()=>computeAndRender(true),0); else if(typeof renderAll==='function') renderAll(); }catch(e){}
})();
