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
  window.ONGA_BARRAGE_ALIGNMENT = {version:VERSION, source:{west:SRC_W,east:SRC_E}, target:{west:TGT_W,east:TGT_E}, scale, angleDeg:angle*180/Math.PI, rawToAligned, alignedToRaw};
})();
