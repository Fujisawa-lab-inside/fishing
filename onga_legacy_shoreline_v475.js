// v4.7.5 legacy annotated shoreline integration
(function(){
  'use strict';
  if(window.__ONGA_LEGACY_SHORELINE_V475__) return;
  window.__ONGA_LEGACY_SHORELINE_V475__ = true;
  const VERSION = 'onga-legacy-shoreline-v4.7.5';
  const SOURCE_URL = 'onga_green_boundary_stands_patch.js?v=legacy-green-source1';
  const toRad = d => d * Math.PI / 180;
  const clampLocal = typeof clamp === 'function' ? clamp : ((v,a,b)=>Math.max(a,Math.min(b,v)));
  const gaussianLocal = typeof gaussian === 'function' ? gaussian : ((x,mu,sigma)=>Math.exp(-0.5*Math.pow((x-mu)/sigma,2)));
  const ref = {lat:33.892724, lng:130.674220};
  const cosRef = Math.cos(toRad(ref.lat));
  function xy(lat,lng){return{x:(lng-ref.lng)*111320*cosRef,y:(lat-ref.lat)*110540};}
  function hav(a,b,c,d){if(typeof haversine==='function')return haversine(a,b,c,d);const p1=toRad(a),p2=toRad(c),d1=toRad(c-a),d2=toRad(d-b),x=Math.sin(d1/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(d2/2)**2;return 12742000*Math.atan2(Math.sqrt(x),Math.sqrt(1-x));}
  function pointInRing(lat,lng,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const yi=ring[i][1],xi=ring[i][0],yj=ring[j][1],xj=ring[j][0];if(((yi>lat)!==(yj>lat))&&(lng<(xj-xi)*(lat-yi)/(yj-yi||1e-12)+xi))inside=!inside;}return inside;}
  function pointInPolygon(lat,lng,feature){const rings=feature.geometry?.coordinates||[];if(!rings.length||!pointInRing(lat,lng,rings[0]))return false;for(let i=1;i<rings.length;i++)if(pointInRing(lat,lng,rings[i]))return false;return true;}
  function parseLegacySource(text){
    const key='const SHORELINES';
    const s=text.indexOf(key);
    if(s<0) throw new Error('SHORELINES not found');
    const a=text.indexOf('[',s);
    const e=text.indexOf('];',a);
    if(a<0||e<0) throw new Error('SHORELINES literal not closed');
    const literal=text.slice(a,e+1);
    const data=Function('"use strict";return ('+literal+');')();
    if(!Array.isArray(data)) throw new Error('SHORELINES is not an array');
    return data;
  }
  function featureFromLine(line,i){return{type:'Feature',properties:{kind:'legacy_shoreline',id:'legacy_green_'+String(i).padStart(2,'0'),name:'過去画像由来の補助境界 '+(i+1),source:'annotated_image_green_line',confidence:'medium',stand_candidate:true,legacy:true},geometry:{type:'LineString',coordinates:line.map(p=>[p[1],p[0]])}};}
  function sampleFeature(feature, spacingM=7){
    const out=[], line=feature.geometry?.coordinates||[];
    for(let i=0;i<line.length-1;i++){
      const a=line[i],b=line[i+1],d=hav(a[1],a[0],b[1],b[0]),steps=Math.max(1,Math.ceil(d/spacingM));
      for(let k=0;k<=steps;k++){const t=k/steps;out.push({lat:a[1]+(b[1]-a[1])*t,lng:a[0]+(b[0]-a[0])*t,feature});}
    }
    return out;
  }
  function nearSamples(lat,lng,samples,limitM){
    for(const s of samples||[]) if(hav(lat,lng,s.lat,s.lng)<=limitM) return true;
    return false;
  }
  function drawLine(ctx,feature,color,width=1.4,dash=[4,7]){
    const line=feature.geometry?.coordinates||[];
    if(!line.length||typeof latLngToCanvas!=='function') return;
    ctx.save(); ctx.strokeStyle=color; ctx.lineWidth=width; ctx.setLineDash(dash); ctx.beginPath();
    line.forEach((c,i)=>{const p=latLngToCanvas(c[1],c[0]); if(i)ctx.lineTo(p.x,p.y); else ctx.moveTo(p.x,p.y);});
    ctx.stroke(); ctx.restore();
  }
  function waitReady(fn){
    const api=window.ONGA_GEOMETRY_ENGINE;
    if(api&&api.engine&&api.engine.ready) return fn(api);
    setTimeout(()=>waitReady(fn),120);
  }
  function install(api, features){
    const E=api.engine;
    const highSamples=E.shorelineSamples||[];
    const legacySamples=[];
    for(const f of features){
      for(const s of sampleFeature(f)){
        if(nearSamples(s.lat,s.lng,highSamples,22)) continue;
        legacySamples.push(s);
      }
    }
    E.legacyShorelines=features;
    E.legacyShorelineSamples=legacySamples;
    window.ONGA_LEGACY_SHORELINES={version:VERSION,features,samples:legacySamples};
    const prevRender=typeof renderAll==='function'?renderAll:null;
    const prevFind=typeof findLandCastPositionForWater==='function'?findLandCastPositionForWater:null;
    const prevMake=typeof makeShoreCastingHotspots==='function'?makeShoreCastingHotspots:null;
    function explicitState(lat,lng){
      const auth=window.ONGA_GEOMETRY_AUTHORITY;
      if(auth&&typeof auth.explicitState==='function') return auth.explicitState(lat,lng);
      for(const f of E.landPolygons||[]) if(pointInPolygon(lat,lng,f)) return false;
      for(const f of E.waterPolygons||[]) if(pointInPolygon(lat,lng,f)) return true;
      return null;
    }
    function nearestFrom(samples,target,legacy){
      const maxM=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.maxM)||100;
      let best=null;
      for(const s of samples||[]){
        if(api.noStandAt&&api.noStandAt(s.lat,s.lng)) continue;
        const d=hav(s.lat,s.lng,target.lat,target.lng);
        if(d<2||d>maxM||(api.castBlocked&&api.castBlocked(s.lat,s.lng,target.lat,target.lng))) continue;
        const score=(target.score||0)*(.70+.30*gaussianLocal(d,34,30))*(legacy?.92:1);
        if(!best||score>best.score) best={lat:s.lat,lng:s.lng,distanceM:d,bearing:0,landConfidence:legacy?.78:1,bankQuality:legacy?.78:1,score,onGeometryShoreline:!legacy,onLegacyShoreline:!!legacy,shorelineId:s.feature?.properties?.id};
      }
      return best;
    }
    function standFor(target){
      if(!target||!Number.isFinite(target.lat)||!Number.isFinite(target.lng)) return null;
      const st=explicitState(target.lat,target.lng);
      if(st===false) return null;
      const high=nearestFrom(highSamples,target,false);
      if(high) return high;
      const legacy=nearestFrom(legacySamples,target,true);
      if(legacy) return legacy;
      return prevFind?prevFind(target):null;
    }
    if(typeof findLandCastPositionForWater==='function') findLandCastPositionForWater=standFor;
    if(typeof makeShoreCastingHotspots==='function') makeShoreCastingHotspots=function(cands,n=8){
      const sorted=[...(cands||[])].filter(p=>p&&Number.isFinite(p.score)&&p.score>.35&&explicitState(p.lat,p.lng)!==false).sort((a,b)=>b.score-a.score);
      const raw=[];
      for(const t of sorted.slice(0,1400)){
        const s=standFor(t); if(!s) continue;
        raw.push({...t,lat:s.lat,lng:s.lng,targetLat:t.lat,targetLng:t.lng,targetScore:t.score,castDistanceM:s.distanceM,landConfidence:s.landConfidence||1,bankQuality:s.bankQuality||1,onLand:true,onGeometryShoreline:!!s.onGeometryShoreline,onLegacyShoreline:!!s.onLegacyShoreline,shorelineId:s.shorelineId,score:clampLocal(s.score||t.score,0,1),structureName:`釣り座：${t.structureName||t.hydroLabel||'水面標的'}`,reason:`${s.onLegacyShoreline?'過去画像由来の補助境界':'座標GeoJSON境界'} / ${Math.round(s.distanceM||0)}m先 / ${t.reason||''}`});
      }
      raw.sort((a,b)=>b.score-a.score);
      const chosen=[],bankSep=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.bankSepM)||85,targetSep=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.targetSepM)||90;
      for(const c of raw){let ok=true;for(const h of chosen){if(hav(c.lat,c.lng,h.lat,h.lng)<bankSep||hav(c.targetLat,c.targetLng,h.targetLat,h.targetLng)<targetSep){ok=false;break;}}if(ok)chosen.push(c);if(chosen.length>=n)break;}
      if(chosen.length<n&&prevMake){for(const h of prevMake(cands,n)){if(chosen.length>=n)break;if(explicitState(h.targetLat||h.lat,h.targetLng||h.lng)===false)continue;if(!chosen.some(c=>hav(c.lat,c.lng,h.lat,h.lng)<bankSep))chosen.push(h);}}
      return chosen.slice(0,n).map((h,i)=>({...h,rank:i+1,score100:Math.round((h.score||0)*100),targetScore100:Math.round((h.targetScore||h.score||0)*100)}));
    };
    if(prevRender) renderAll=function(){const r=prevRender.apply(this,arguments);try{const ctx=state.ctx;for(const f of features) drawLine(ctx,f,'rgba(0,255,120,.34)',1.4,[4,7]);}catch(e){}return r;};
    try{state.waterSampleCache?.clear?.();state.fluidCache?.clear?.();state.fluidBaseCache?.clear?.();state.validationCache?.clear?.();if(state.timeline?.length&&typeof computeAndRender==='function')setTimeout(()=>computeAndRender(true),0);else if(typeof renderAll==='function')renderAll();}catch(e){}
    console.info('[onga-legacy-shoreline]',VERSION,features.length,legacySamples.length);
  }
  fetch(SOURCE_URL,{cache:'no-store'}).then(r=>r.text()).then(parseLegacySource).then(lines=>{
    const features=lines.map(featureFromLine).filter(f=>(f.geometry.coordinates||[]).length>1);
    waitReady(api=>install(api,features));
  }).catch(e=>console.warn('[onga-legacy-shoreline] failed',e));
})();
