// Stage 8C: authoritative heatmap-domain adapter only.
// Connected: drawHeatmap() source-point filtering and final raster clipping.
// Intentionally untouched: photo/corridor sample generation, fluid-grid construction,
// hotspot/stand generation, turbulence overlay, and river-direction fields.
(function installOngaUnifiedHeatmapStage8C(global){
  'use strict';

  const API_NAME='ONGA_UNIFIED_HEATMAP_STAGE8C';
  const water=global.ONGA_UNIFIED_WATER_DETECTION_STAGE8B;
  if(!water) throw new Error('[stage8c] missing Stage 8B water-detection API');
  if(!water.scope||water.scope.waterDetectionConnected!==true){
    throw new Error('[stage8c] Stage 8B water detection is not connected');
  }
  if(typeof global.drawHeatmap!=='function') throw new Error('[stage8c] drawHeatmap is unavailable');
  if(!Array.isArray(water.rows)||!Number.isInteger(water.width)||!Number.isInteger(water.height)){
    throw new Error('[stage8c] invalid authoritative water rows');
  }

  const previous={
    drawHeatmap:global.drawHeatmap,
    samplePhotoWaterCandidates:global.samplePhotoWaterCandidates,
    buildFluidBaseGrid:global.buildFluidBaseGrid,
    makeShoreCastingHotspots:global.makeShoreCastingHotspots,
    nearestHydroCorridor:global.nearestHydroCorridor,
    drawTurbulenceOverlay:global.drawTurbulenceOverlay
  };

  const domainRows=water.rows; // Same object: no second heatmap-domain definition.
  let domainCellCount=0;
  for(const row of domainRows){
    for(let i=0;i<row.length;i+=2) domainCellCount+=Number(row[i+1])-Number(row[i])+1;
  }

  let maskCache=null;
  let lastRender={
    sourcePoints:0,
    acceptedPoints:0,
    outsidePointsSuppressed:0,
    rendered:false,
    maskKey:'',
    domainCellCount
  };

  function finite(value,fallback=0){
    const number=Number(value);
    return Number.isFinite(number)?number:fallback;
  }

  function viewportKey(scale){
    const center=(typeof state==='object'&&state&&state.centerPx)||{x:0,y:0};
    return [
      Math.max(1,Math.round(finite(state?.width,1)*scale)),
      Math.max(1,Math.round(finite(state?.height,1)*scale)),
      finite(state?.zoom,0),
      finite(center.x,0).toFixed(3),
      finite(center.y,0).toFixed(3),
      scale.toFixed(3),
      String(water.specVersion||''),
    ].join('|');
  }

  function pointOutsideViewport(points,scale,padding=4){
    const width=finite(state?.width,1)*scale;
    const height=finite(state?.height,1)*scale;
    return points.every(point=>
      point.x<-padding||point.y<-padding||point.x>width+padding||point.y>height+padding
    );
  }

  function buildAuthoritativeMaskCanvas(scale=1){
    const key=viewportKey(scale);
    if(maskCache&&maskCache.key===key) return maskCache.canvas;

    const canvas=document.createElement('canvas');
    canvas.width=Math.max(1,Math.ceil(finite(state?.width,1)*scale));
    canvas.height=Math.max(1,Math.ceil(finite(state?.height,1)*scale));
    const ctx=canvas.getContext('2d');
    if(!ctx) throw new Error('[stage8c] 2D mask context is unavailable');
    ctx.fillStyle='rgba(255,255,255,1)';
    ctx.imageSmoothingEnabled=false;

    const sourceHeight=water.height;
    for(let y=0;y<sourceHeight;y++){
      const row=domainRows[y]||[];
      if(!row.length) continue;
      const y1=Math.min(sourceHeight,y+1);
      for(let i=0;i<row.length;i+=2){
        const x0=Number(row[i]);
        const x1=Number(row[i+1])+1;
        const ll0=water.imageXYToLatLng(x0,y);
        const ll1=water.imageXYToLatLng(x1,y);
        const ll2=water.imageXYToLatLng(x1,y1);
        const ll3=water.imageXYToLatLng(x0,y1);
        const p0=latLngToCanvas(ll0.lat,ll0.lng);
        const p1=latLngToCanvas(ll1.lat,ll1.lng);
        const p2=latLngToCanvas(ll2.lat,ll2.lng);
        const p3=latLngToCanvas(ll3.lat,ll3.lng);
        const points=[p0,p1,p2,p3].map(point=>({x:point.x*scale,y:point.y*scale}));
        if(pointOutsideViewport(points,scale,8)) continue;
        ctx.beginPath();
        ctx.moveTo(points[0].x,points[0].y);
        ctx.lineTo(points[1].x,points[1].y);
        ctx.lineTo(points[2].x,points[2].y);
        ctx.lineTo(points[3].x,points[3].y);
        ctx.closePath();
        ctx.fill();
      }
    }

    maskCache={key,canvas};
    return canvas;
  }

  function filterHeatPoints(points){
    const source=Array.isArray(points)?points:[];
    return source.filter(point=>
      point&&Number.isFinite(Number(point.lat))&&Number.isFinite(Number(point.lng))&&
      water.contains(Number(point.lat),Number(point.lng))
    );
  }

  function authoritativeDrawHeatmap(ctx){
    const toggle=(typeof document!=='undefined')?document.getElementById('toggleHeat'):null;
    if(toggle&&!toggle.checked) return;

    const source=Array.isArray(state?.heatPoints)?state.heatPoints:[];
    const points=filterHeatPoints(source);
    lastRender={
      sourcePoints:source.length,
      acceptedPoints:points.length,
      outsidePointsSuppressed:source.length-points.length,
      rendered:false,
      maskKey:'',
      domainCellCount
    };
    if(!ctx||!points.length) return;

    // Preserve the existing visual formula while drawing at reduced internal resolution.
    const scale=.58;
    const width=Math.max(1,Math.ceil(finite(state?.width,1)*scale));
    const height=Math.max(1,Math.ceil(finite(state?.height,1)*scale));
    const heat=document.createElement('canvas');
    heat.width=width;
    heat.height=height;
    const hctx=heat.getContext('2d');
    if(!hctx) return;

    const maxAlpha=clamp(finite(state?.baseOpacity,.15),0,.15);
    hctx.globalAlpha=1;
    for(const point of points){
      const score=clamp(Number.isFinite(Number(point.heatScore))?Number(point.heatScore):finite(point.score,0),0,1);
      if(score<=.05) continue;
      const projected=latLngToCanvas(Number(point.lat),Number(point.lng));
      if(projected.x<-80||projected.y<-80||projected.x>finite(state.width,1)+80||projected.y>finite(state.height,1)+80) continue;
      const cx=projected.x*scale;
      const cy=projected.y*scale;
      const radius=(22+11*(finite(state.zoom,16)-14))*(.70+score*.58)*scale;
      const colour=heatColor(score);
      const gradient=hctx.createRadialGradient(cx,cy,Math.max(.5,scale),cx,cy,Math.max(1,radius));
      gradient.addColorStop(0,`rgba(${colour[0]},${colour[1]},${colour[2]},${clamp(maxAlpha*(.45+.55*score),0,maxAlpha)})`);
      gradient.addColorStop(.42,`rgba(${colour[0]},${colour[1]},${colour[2]},${clamp(maxAlpha*.42*score,0,maxAlpha*.45)})`);
      gradient.addColorStop(1,`rgba(${colour[0]},${colour[1]},${colour[2]},0)`);
      hctx.fillStyle=gradient;
      hctx.beginPath();
      hctx.arc(cx,cy,Math.max(1,radius),0,Math.PI*2);
      hctx.fill();
    }

    // The authoritative Stage 8B water rows are the only heatmap clip domain.
    const mask=buildAuthoritativeMaskCanvas(scale);
    hctx.globalCompositeOperation='destination-in';
    hctx.drawImage(mask,0,0);
    hctx.globalCompositeOperation='source-over';

    ctx.save();
    ctx.drawImage(heat,0,0,finite(state.width,1),finite(state.height,1));
    ctx.restore();

    lastRender={
      sourcePoints:source.length,
      acceptedPoints:points.length,
      outsidePointsSuppressed:source.length-points.length,
      rendered:true,
      maskKey:maskCache?.key||'',
      domainCellCount
    };
  }

  function install(){
    global.drawHeatmap=authoritativeDrawHeatmap;
    try{
      if(typeof state==='object'&&state){
        state.unifiedHeatmapStage8C={
          version:'stage8c-heatmap-only',
          specVersion:String(water.specVersion||''),
          waterDetectionConnected:true,
          heatmapConnected:true,
          fluidConnected:false,
          standGenerationConnected:false,
          domainRowsShared:true,
          domainCellCount
        };
      }
    }catch(_){ }
  }

  function diagnostics(){
    return {
      version:'stage8c-heatmap-only',
      specVersion:String(water.specVersion||''),
      waterDetectionConnected:true,
      heatmapConnected:true,
      fluidConnected:false,
      standGenerationConnected:false,
      domainRowsShared:domainRows===water.rows,
      domainDifferenceCells:0,
      domainCellCount,
      lastRender:{...lastRender},
      overriddenFunctions:['drawHeatmap'],
      intentionallyUntouched:[
        'samplePhotoWaterCandidates','buildFluidBaseGrid','makeShoreCastingHotspots',
        'nearestHydroCorridor','drawTurbulenceOverlay'
      ],
      untouchedReferences:{
        samplePhotoWaterCandidates:global.samplePhotoWaterCandidates===previous.samplePhotoWaterCandidates,
        buildFluidBaseGrid:global.buildFluidBaseGrid===previous.buildFluidBaseGrid,
        makeShoreCastingHotspots:global.makeShoreCastingHotspots===previous.makeShoreCastingHotspots,
        nearestHydroCorridor:global.nearestHydroCorridor===previous.nearestHydroCorridor,
        drawTurbulenceOverlay:global.drawTurbulenceOverlay===previous.drawTurbulenceOverlay
      }
    };
  }

  const api={
    version:'stage8c-heatmap-only',
    waterApi:water,
    domainRows,
    domainCellCount,
    filterHeatPoints,
    buildAuthoritativeMaskCanvas,
    drawHeatmap:authoritativeDrawHeatmap,
    invalidateMaskCache(){maskCache=null;},
    install,
    diagnostics,
    previous,
    scope:{
      waterDetectionConnected:true,
      heatmapConnected:true,
      fluidConnected:false,
      standGenerationConnected:false
    }
  };

  global[API_NAME]=api;
  global.__ONGA_UNIFIED_HEATMAP_STAGE8C_INSTALLED__=true;
  install();
  if(typeof setTimeout==='function') [120,400,1000,2500].forEach(delay=>setTimeout(install,delay));
  if(typeof console!=='undefined'&&console.info) console.info('[onga-stage8c-heatmap]',diagnostics());
})(typeof window!=='undefined'?window:globalThis);
