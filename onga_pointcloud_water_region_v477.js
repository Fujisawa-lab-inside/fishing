// v4.7.7 point-cloud water region and hotspot patch
(function(){
  'use strict';
  if(window.__ONGA_POINTCLOUD_WATER_V477__) return;
  window.__ONGA_POINTCLOUD_WATER_V477__ = true;
  const VERSION='onga-pointcloud-water-v4.7.7';
  const CELL_M=18;
  const SAMPLE_M=7;
  const toRad=d=>d*Math.PI/180;
  const clampLocal=typeof clamp==='function'?clamp:((v,a,b)=>Math.max(a,Math.min(b,v)));
  const gaussianLocal=typeof gaussian==='function'?gaussian:((x,mu,sigma)=>Math.exp(-0.5*Math.pow((x-mu)/sigma,2)));
  const ref={lat:33.892724,lng:130.674220};
  const cosRef=Math.cos(toRad(ref.lat));
  function xy(lat,lng){return{x:(lng-ref.lng)*111320*cosRef,y:(lat-ref.lat)*110540};}
  function ll(x,y){return{lat:ref.lat+y/110540,lng:ref.lng+x/(111320*cosRef)};}
  function hav(a,b,c,d){if(typeof haversine==='function')return haversine(a,b,c,d);const p1=toRad(a),p2=toRad(c),d1=toRad(c-a),d2=toRad(d-b),x=Math.sin(d1/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(d2/2)**2;return 12742000*Math.atan2(Math.sqrt(x),Math.sqrt(1-x));}
  function noStand(lat,lng){return !!(window.ONGA_SPATIAL_SAFETY&&window.ONGA_SPATIAL_SAFETY.noStandAt&&window.ONGA_SPATIAL_SAFETY.noStandAt(lat,lng));}
  function castBlocked(a,b,c,d){return !!(window.ONGA_SPATIAL_SAFETY&&window.ONGA_SPATIAL_SAFETY.castBlock&&window.ONGA_SPATIAL_SAFETY.castBlock(a,b,c,d));}
  function nearMapEdge(lat,lng){
    const b=(typeof GSI!=='undefined'&&GSI.bounds)||null;
    if(!b) return false;
    const mLat=.00022, mLng=.00032;
    return lat<b.south+mLat||lat>b.north-mLat||lng<b.west+mLng||lng>b.east-mLng;
  }
  function buildRegion(points){
    const pts=(points||[]).filter(p=>p&&Number.isFinite(p.lat)&&Number.isFinite(p.lng)&&Number.isFinite(p.score)&&p.score>.035);
    if(pts.length<30) return null;
    const m=pts.map(p=>({...p,...xy(p.lat,p.lng)}));
    let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
    for(const p of m){minX=Math.min(minX,p.x);minY=Math.min(minY,p.y);maxX=Math.max(maxX,p.x);maxY=Math.max(maxY,p.y);}
    const pad=CELL_M*3; minX-=pad; minY-=pad; maxX+=pad; maxY+=pad;
    const w=Math.ceil((maxX-minX)/CELL_M)+1,h=Math.ceil((maxY-minY)/CELL_M)+1;
    if(w<3||h<3||w*h>260000) return null;
    const occ=new Uint8Array(w*h);
    const idx=(x,y)=>y*w+x;
    for(const p of m){
      const ix=Math.floor((p.x-minX)/CELL_M),iy=Math.floor((p.y-minY)/CELL_M);
      for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){
        const x=ix+dx,y=iy+dy;
        if(x>=0&&y>=0&&x<w&&y<h) occ[idx(x,y)]=1;
      }
    }
    // Close very small holes/gaps so the contour follows the evaluated water body rather than individual dots.
    const closed=occ.slice();
    for(let y=1;y<h-1;y++)for(let x=1;x<w-1;x++){
      if(occ[idx(x,y)]) continue;
      let n=0;
      for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++) if(dx||dy) n+=occ[idx(x+dx,y+dy)];
      if(n>=5) closed[idx(x,y)]=1;
    }
    function occupied(x,y){return x>=0&&y>=0&&x<w&&y<h&&closed[idx(x,y)];}
    function v(ix,iy){return ll(minX+ix*CELL_M,minY+iy*CELL_M);}
    const segments=[];
    function add(a,b,open){segments.push({a,b,open});}
    for(let y=0;y<h;y++)for(let x=0;x<w;x++){
      if(!occupied(x,y)) continue;
      if(!occupied(x,y-1)) add(v(x,y),v(x+1,y),y===0);
      if(!occupied(x+1,y)) add(v(x+1,y),v(x+1,y+1),x===w-1);
      if(!occupied(x,y+1)) add(v(x+1,y+1),v(x,y+1),y===h-1);
      if(!occupied(x-1,y)) add(v(x,y+1),v(x,y),x===0);
    }
    const standSamples=[];
    for(const s of segments){
      const len=hav(s.a.lat,s.a.lng,s.b.lat,s.b.lng), steps=Math.max(1,Math.ceil(len/SAMPLE_M));
      for(let k=0;k<=steps;k++){
        const t=k/steps, lat=s.a.lat+(s.b.lat-s.a.lat)*t, lng=s.a.lng+(s.b.lng-s.a.lng)*t;
        if(s.open||nearMapEdge(lat,lng)||noStand(lat,lng)) continue;
        standSamples.push({lat,lng,segment:s});
      }
    }
    return {version:VERSION,cellM:CELL_M,segments,standSamples,count:pts.length,bounds:{minX,minY,maxX,maxY,w,h}};
  }
  function nearestStand(target,region){
    if(!target||!region) return null;
    const maxM=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.maxM)||100;
    let best=null;
    for(const s of region.standSamples||[]){
      const d=hav(s.lat,s.lng,target.lat,target.lng);
      if(d<2||d>maxM||castBlocked(s.lat,s.lng,target.lat,target.lng)) continue;
      const score=(target.score||0)*(.70+.30*gaussianLocal(d,34,30));
      if(!best||score>best.score) best={lat:s.lat,lng:s.lng,distanceM:d,bearing:0,landConfidence:1,bankQuality:1,score,onPointCloudEdge:true};
    }
    return best;
  }
  function computeHotspots(points,region,n=8,fallback=[]){
    if(!region) return fallback||[];
    const targets=[...(points||[])].filter(p=>p&&Number.isFinite(p.score)&&p.score>.35).sort((a,b)=>b.score-a.score);
    const raw=[];
    for(const t of targets.slice(0,1600)){
      const s=nearestStand(t,region); if(!s) continue;
      raw.push({...t,lat:s.lat,lng:s.lng,targetLat:t.lat,targetLng:t.lng,targetScore:t.score,castDistanceM:s.distanceM,landConfidence:1,bankQuality:1,onLand:true,onPointCloudEdge:true,score:clampLocal(s.score||t.score,0,1),structureName:`点群外縁釣り座：${t.structureName||t.hydroLabel||'水面標的'}`,reason:`評価点群の水面外縁 / ${Math.round(s.distanceM||0)}m先 / ${t.reason||''}`});
    }
    raw.sort((a,b)=>b.score-a.score);
    const chosen=[],bankSep=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.bankSepM)||85,targetSep=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.targetSepM)||90;
    for(const c of raw){
      let ok=true;
      for(const h of chosen){if(hav(c.lat,c.lng,h.lat,h.lng)<bankSep||hav(c.targetLat,c.targetLng,h.targetLat,h.targetLng)<targetSep){ok=false;break;}}
      if(ok) chosen.push(c);
      if(chosen.length>=n) break;
    }
    if(chosen.length<n){
      for(const h of fallback||[]){
        if(chosen.length>=n) break;
        if(!chosen.some(c=>hav(c.lat,c.lng,h.lat,h.lng)<bankSep)) chosen.push(h);
      }
    }
    return chosen.slice(0,n).map((h,i)=>({...h,rank:i+1,score100:Math.round((h.score||0)*100),targetScore100:Math.round((h.targetScore||h.score||0)*100)}));
  }
  function drawRegion(ctx,region){
    if(!ctx||!region||!region.segments?.length||typeof latLngToCanvas!=='function') return;
    ctx.save();
    ctx.strokeStyle='rgba(80,210,255,.95)';
    ctx.lineWidth=2.2;
    ctx.setLineDash([4,5]);
    ctx.beginPath();
    for(const s of region.segments){
      const a=latLngToCanvas(s.a.lat,s.a.lng), b=latLngToCanvas(s.b.lat,s.b.lng);
      if((a.x<-80&&b.x<-80)||(a.y<-80&&b.y<-80)||(a.x>state.width+80&&b.x>state.width+80)||(a.y>state.height+80&&b.y>state.height+80)) continue;
      ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y);
    }
    ctx.stroke();
    ctx.restore();
  }
  const prevBuild=typeof buildFishingModel==='function'?buildFishingModel:null;
  if(prevBuild) buildFishingModel=function(){
    const model=prevBuild.apply(this,arguments);
    try{
      const region=buildRegion(model?.points||[]);
      if(region){
        model.pointCloudWaterRegion=region;
        model.hotspots=computeHotspots(model.points,region,8,model.hotspots||[]);
        state.pointCloudWaterRegion=region;
        state.photoSampleStatus=(state.photoSampleStatus||'水面評価')+` / 評価点群外縁${region.segments.length}線分`;
        if(typeof updateWaterStatus==='function') updateWaterStatus();
      }
    }catch(e){console.warn('[pointcloud water] build failed',e);}
    return model;
  };
  const prevRender=typeof renderAll==='function'?renderAll:null;
  if(prevRender) renderAll=function(){const r=prevRender.apply(this,arguments);try{drawRegion(state.ctx,state.pointCloudWaterRegion);}catch(e){}return r;};
  window.ONGA_POINTCLOUD_WATER={version:VERSION,buildRegion,computeHotspots,drawRegion};
})();
