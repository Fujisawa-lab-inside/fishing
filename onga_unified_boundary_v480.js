// v4.8.0 water/land boundary override derived from the approved authoritative water mask.
// This runs after onga_unified_water_domain_v480.js.
(function installOngaUnifiedBoundaryV480(){
  'use strict';
  const VERSION='onga-unified-boundary-v4.8.0';
  if(window.__ONGA_UNIFIED_BOUNDARY_V480__===VERSION)return;
  window.__ONGA_UNIFIED_BOUNDARY_V480__=VERSION;
  const domain=window.ONGA_UNIFIED_WATER_DOMAIN;
  if(!domain){console.warn('[unified-boundary] unified domain missing');return;}
  const source=domain.source,W=source.maskWidth,H=source.maskHeight,SX=source.cellScaleX||2,SY=source.cellScaleY||2;
  const clampLocal=(typeof clamp==='function')?clamp:((v,a,b)=>Math.max(a,Math.min(b,v)));
  function rowsToBits(rows){
    const bits=new Uint8Array(W*H);
    for(let y=0;y<H;y++){
      const row=rows[y]||[];
      for(let k=0;k<row.length;k+=2)for(let x=row[k];x<=row[k+1];x++)bits[y*W+x]=1;
    }
    return bits;
  }
  const water=rowsToBits(domain.waterRows||[]);
  function isOpenEdgeCell(x,y){
    const imageX=(x+.5)*SX,imageY=(y+.5)*SY;
    for(const b of domain.openBoundaries||[]){
      if(imageX<b.run[0]-6||imageX>b.run[1]+6)continue;
      if(b.edge==='top'&&imageY<=26)return true;
      if(b.edge==='bottom'&&imageY>=source.originalHeight-26)return true;
    }
    return false;
  }
  function isBoundaryCell(x,y){
    const k=y*W+x;if(!water[k]||isOpenEdgeCell(x,y))return false;
    if(x<=0||y<=0||x>=W-1||y>=H-1)return false;
    return !water[k-1]||!water[k+1]||!water[k-W]||!water[k+W];
  }
  function localMeters(lat,lng){
    const ref=domain.controlPoints[3],cos=Math.cos(ref.lat*Math.PI/180);
    return{x:(lng-ref.lng)*111320*cos,y:(lat-ref.lat)*110540};
  }
  let samples=null,bins=null;
  function buildSamples(){
    if(samples)return samples;
    const out=[];
    for(let y=1;y<H-1;y++)for(let x=1;x<W-1;x++){
      if(!isBoundaryCell(x,y))continue;
      const ll=domain.imageXYToLatLng((x+.5)*SX,(y+.5)*SY),m=localMeters(ll.lat,ll.lng);
      out.push({lat:ll.lat,lng:ll.lng,mx:m.x,my:m.y,ix:x,iy:y,onUnifiedBoundary:true});
    }
    samples=out;bins=null;return out;
  }
  function buildBins(){
    if(bins)return bins;
    const cell=70,map=new Map();
    for(const p of buildSamples()){
      const key=Math.floor(p.mx/cell)+','+Math.floor(p.my/cell);
      if(!map.has(key))map.set(key,[]);
      map.get(key).push(p);
    }
    bins={cell,map};return bins;
  }
  function nearestBoundaryStand(target){
    if(!target||!domain.contains(target.lat,target.lng))return null;
    const maxM=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.maxM)||100;
    const preferredM=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.preferredM)||45;
    const tm=localMeters(target.lat,target.lng),index=buildBins(),cell=index.cell;
    const bx=Math.floor(tm.x/cell),by=Math.floor(tm.y/cell),span=Math.ceil((maxM+cell)/cell);
    let best=null;
    for(let yy=by-span;yy<=by+span;yy++)for(let xx=bx-span;xx<=bx+span;xx++){
      const arr=index.map.get(xx+','+yy);if(!arr)continue;
      for(const s of arr){
        const d=Math.hypot(s.mx-tm.x,s.my-tm.y);
        if(d<1||d>maxM)continue;
        const safety=window.ONGA_SPATIAL_SAFETY;
        if(safety?.noStandAt?.(s.lat,s.lng))continue;
        if(safety?.castBlock?.(s.lat,s.lng,target.lat,target.lng))continue;
        const pref=Math.exp(-.5*Math.pow((d-preferredM)/32,2));
        const reach=clampLocal(1-d/maxM,0,1);
        const score=(target.score||0)*(.72+.20*pref+.08*reach);
        if(!best||score>best.score)best={lat:s.lat,lng:s.lng,distanceM:d,bearing:0,landConfidence:1,bankQuality:1,onUnifiedBoundary:true,score};
      }
    }
    return best;
  }
  function makeHotspots(candidates,n=8){
    const model=(typeof CAST_MODEL!=='undefined')?CAST_MODEL:{bankSepM:85,targetSepM:90};
    const sorted=[...(candidates||[])].filter(p=>p&&Number.isFinite(p.score)&&p.score>.35&&domain.contains(p.lat,p.lng)).sort((a,b)=>b.score-a.score),raw=[];
    for(const target of sorted.slice(0,1800)){
      const stand=nearestBoundaryStand(target);if(!stand)continue;
      raw.push({...target,lat:stand.lat,lng:stand.lng,targetLat:target.lat,targetLng:target.lng,targetScore:target.score,castDistanceM:stand.distanceM,landConfidence:1,bankQuality:1,onLand:true,onUnifiedBoundary:true,score:clampLocal(stand.score||target.score,0,1),structureName:'境界線釣り座：'+(target.structureName||target.hydroLabel||'水面標的'),reason:'統一水面・陸地境界 / '+Math.round(stand.distanceM||0)+'m先 / '+(target.reason||'')});
    }
    raw.sort((a,b)=>b.score-a.score);const chosen=[];
    for(const c of raw){
      let ok=true;
      for(const h of chosen){
        if(typeof haversine==='function'&&(haversine(c.lat,c.lng,h.lat,h.lng)<(model.bankSepM||85)||haversine(c.targetLat,c.targetLng,h.targetLat,h.targetLng)<(model.targetSepM||90))){ok=false;break;}
      }
      if(ok)chosen.push(c);if(chosen.length>=n)break;
    }
    return chosen.map((h,i)=>({...h,rank:i+1,score100:Math.round((h.score||0)*100),targetScore100:Math.round((h.targetScore||h.score||0)*100),unifiedBoundary:VERSION}));
  }
  domain.buildShoreSamples=buildSamples;
  domain.nearestBoundaryStand=nearestBoundaryStand;
  domain.boundaryDiagnostics=function(){return{version:VERSION,samples:buildSamples().length,openBoundarySamplesExcluded:true};};
  if(typeof findLandCastPositionForWater==='function')findLandCastPositionForWater=nearestBoundaryStand;
  if(typeof makeShoreCastingHotspots==='function')makeShoreCastingHotspots=makeHotspots;
  console.info('[unified-boundary]',VERSION,domain.boundaryDiagnostics());
})();
