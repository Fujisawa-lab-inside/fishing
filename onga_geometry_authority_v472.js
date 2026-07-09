// v4.7.3 authoritative coordinate-geometry water and hotspot patch
(function(){
  'use strict';
  if(window.__ONGA_GEOMETRY_AUTHORITY_V473__) return;
  window.__ONGA_GEOMETRY_AUTHORITY_V473__ = true;
  const VERSION='onga-geometry-authority-v4.7.3';
  const toRad=d=>d*Math.PI/180;
  const clampLocal=typeof clamp==='function'?clamp:((v,a,b)=>Math.max(a,Math.min(b,v)));
  const gaussianLocal=typeof gaussian==='function'?gaussian:((x,mu,sigma)=>Math.exp(-0.5*Math.pow((x-mu)/sigma,2)));
  const ref={lat:33.892724,lng:130.674220};
  const cosRef=Math.cos(toRad(ref.lat));
  function xy(lat,lng){return{x:(lng-ref.lng)*111320*cosRef,y:(lat-ref.lat)*110540};}
  function hav(a,b,c,d){if(typeof haversine==='function')return haversine(a,b,c,d);const p1=toRad(a),p2=toRad(c),d1=toRad(c-a),d2=toRad(d-b),x=Math.sin(d1/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(d2/2)**2;return 12742000*Math.atan2(Math.sqrt(x),Math.sqrt(1-x));}
  function pointInRing(lat,lng,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const yi=ring[i][1],xi=ring[i][0],yj=ring[j][1],xj=ring[j][0];if(((yi>lat)!==(yj>lat))&&(lng<(xj-xi)*(lat-yi)/(yj-yi||1e-12)+xi))inside=!inside;}return inside;}
  function pointInPolygon(lat,lng,feature){const rings=feature.geometry?.coordinates||[];if(!rings.length||!pointInRing(lat,lng,rings[0]))return false;for(let i=1;i<rings.length;i++)if(pointInRing(lat,lng,rings[i]))return false;return true;}
  function bbox(feature,padDeg){let b={west:Infinity,east:-Infinity,south:Infinity,north:-Infinity};function add(c){b.west=Math.min(b.west,c[0]-padDeg);b.east=Math.max(b.east,c[0]+padDeg);b.south=Math.min(b.south,c[1]-padDeg);b.north=Math.max(b.north,c[1]+padDeg);}const g=feature.geometry||{};if(g.type==='Polygon')for(const ring of g.coordinates||[])for(const c of ring)add(c);else if(g.type==='LineString')for(const c of g.coordinates||[])add(c);return b;}
  function inBox(lat,lng,b){return lng>=b.west&&lng<=b.east&&lat>=b.south&&lat<=b.north;}
  function install(){
    const api=window.ONGA_GEOMETRY_ENGINE;
    if(!api||!api.engine||!api.engine.ready){setTimeout(install,120);return;}
    const E=api.engine;
    const oldWater=typeof calibratedWaterMaskValueAt==='function'?calibratedWaterMaskValueAt:null;
    const oldHydro=typeof nearestHydroCorridor==='function'?nearestHydroCorridor:null;
    const oldStand=typeof findLandCastPositionForWater==='function'?findLandCastPositionForWater:null;
    const oldHotspots=typeof makeShoreCastingHotspots==='function'?makeShoreCastingHotspots:null;
    const oldDrawPins=typeof drawPins==='function'?drawPins:null;
    const strictBoxes=E.waterPolygons.map(f=>bbox(f,0.00035));
    function explicitState(lat,lng){
      for(const f of E.landPolygons)if(pointInPolygon(lat,lng,f))return false;
      for(const f of E.waterPolygons)if(pointInPolygon(lat,lng,f))return true;
      for(const b of strictBoxes)if(inBox(lat,lng,b))return false;
      return null;
    }
    function water(lat,lng){const s=explicitState(lat,lng);if(s===true)return 1;if(s===false)return 0;return oldWater?oldWater(lat,lng):0;}
    function geoStand(target){
      const maxM=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.maxM)?CAST_MODEL.maxM:100;
      let best=null;
      for(const s of E.shorelineSamples||[]){
        if(api.noStandAt&&api.noStandAt(s.lat,s.lng))continue;
        const d=hav(s.lat,s.lng,target.lat,target.lng);
        if(d<2||d>maxM||(api.castBlocked&&api.castBlocked(s.lat,s.lng,target.lat,target.lng)))continue;
        const score=(target.score||0)*(.70+.30*gaussianLocal(d,34,30));
        if(!best||score>best.score)best={lat:s.lat,lng:s.lng,distanceM:d,bearing:0,landConfidence:1,bankQuality:1,score,onGeometryShoreline:true,shorelineId:s.feature?.properties?.id};
      }
      return best;
    }
    function standFor(target){
      if(!target||!Number.isFinite(target.lat)||!Number.isFinite(target.lng))return null;
      const s=explicitState(target.lat,target.lng);
      if(s===false)return null;
      if(s===true)return geoStand(target);
      return oldStand?oldStand(target):null;
    }
    function targetAllowed(p){return !!p&&Number.isFinite(p.lat)&&Number.isFinite(p.lng)&&explicitState(p.lat,p.lng)!==false;}
    calibratedWaterMaskValueAt=water;
    if(typeof isKnownWater==='function')isKnownWater=(lat,lng)=>water(lat,lng)>.5;
    if(typeof nearestHydroCorridor==='function')nearestHydroCorridor=function(lat,lng){if(water(lat,lng)<=0)return null;return (api.hydro&&api.hydro(lat,lng))||(oldHydro&&oldHydro(lat,lng));};
    if(typeof findLandCastPositionForWater==='function')findLandCastPositionForWater=standFor;
    if(typeof makeShoreCastingHotspots==='function')makeShoreCastingHotspots=function(cands,n=8){
      const sorted=[...(cands||[])].filter(p=>p&&Number.isFinite(p.score)&&p.score>.35&&targetAllowed(p)).sort((a,b)=>b.score-a.score);
      const raw=[];
      for(const t of sorted.slice(0,1300)){
        const s=standFor(t); if(!s)continue;
        raw.push({...t,lat:s.lat,lng:s.lng,targetLat:t.lat,targetLng:t.lng,targetScore:t.score,castDistanceM:s.distanceM,landConfidence:1,bankQuality:1,onLand:true,onGeometryShoreline:!!s.onGeometryShoreline,shorelineId:s.shorelineId,score:clampLocal(s.score||t.score,0,1),structureName:`釣り座：${t.structureName||t.hydroLabel||'水面標的'}`,reason:`${s.onGeometryShoreline?'座標GeoJSON':'既存水面'}ターゲット / ${Math.round(s.distanceM||0)}m先 / ${t.reason||''}`});
      }
      raw.sort((a,b)=>b.score-a.score);
      const chosen=[],bankSep=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.bankSepM)||85,targetSep=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.targetSepM)||90;
      for(const c of raw){let ok=true;for(const h of chosen){if(hav(c.lat,c.lng,h.lat,h.lng)<bankSep||hav(c.targetLat,c.targetLng,h.targetLat,h.targetLng)<targetSep){ok=false;break;}}if(ok)chosen.push(c);if(chosen.length>=n)break;}
      if(chosen.length<n&&oldHotspots){for(const h of oldHotspots(cands,n)){if(chosen.length>=n)break;if(!targetAllowed({lat:h.targetLat||h.lat,lng:h.targetLng||h.lng}))continue;if(!chosen.some(c=>hav(c.lat,c.lng,h.lat,h.lng)<bankSep))chosen.push(h);}}
      return chosen.slice(0,n).map((h,i)=>({...h,rank:i+1,score100:Math.round((h.score||0)*100),targetScore100:Math.round((h.targetScore||h.score||0)*100)}));
    };
    if(typeof drawPins==='function'&&typeof drawPin==='function')drawPins=function(ctx){
      const toggle=document.getElementById('togglePins'); if(toggle&&!toggle.checked)return;
      for(const h of state.hotspots||[]){const p=latLngToCanvas(h.lat,h.lng);if(p.x<-40||p.y<-40||p.x>state.width+40||p.y>state.height+40)continue;drawPin(ctx,p.x,p.y,h.rank,h.score100);}
    };
    window.ONGA_GEOMETRY_AUTHORITY={version:VERSION,explicitState,water,standFor,strictBoxes,oldDrawPins};
    try{state.waterSampleCache?.clear?.();state.fluidCache?.clear?.();state.fluidBaseCache?.clear?.();state.validationCache?.clear?.();if(state.timeline?.length&&typeof computeAndRender==='function')computeAndRender(true);else if(typeof renderAll==='function')renderAll();}catch(e){}
    console.info('[onga-geometry-authority]',VERSION);
  }
  install();
})();
