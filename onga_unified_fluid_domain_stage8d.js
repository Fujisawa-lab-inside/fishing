// Stage 8D: authoritative fluid-water domain adapter only.
// The existing hydraulic heads, boundary classification, depth/mobility model,
// solver iteration, velocity calculation and flow-direction logic are preserved.
// This patch changes only which finite-difference cells are eligible as water.
(function installOngaUnifiedFluidDomainStage8D(global){
  'use strict';

  const API_NAME='ONGA_UNIFIED_FLUID_DOMAIN_STAGE8D';
  const water=global.ONGA_UNIFIED_WATER_DETECTION_STAGE8B;
  const heatmap=global.ONGA_UNIFIED_HEATMAP_STAGE8C;
  if(!water||!water.scope||water.scope.waterDetectionConnected!==true){
    throw new Error('[stage8d] approved Stage 8B water API is unavailable');
  }
  if(!heatmap||!heatmap.scope||heatmap.scope.heatmapConnected!==true){
    throw new Error('[stage8d] approved Stage 8C heatmap API is unavailable');
  }
  if(typeof global.buildFluidGrid!=='function'){
    throw new Error('[stage8d] buildFluidGrid is unavailable');
  }
  if(typeof global.nearestHydroCorridor!=='function'){
    throw new Error('[stage8d] nearestHydroCorridor is unavailable');
  }

  const previous={
    buildFluidGrid:global.buildFluidGrid,
    nearestHydroCorridor:global.nearestHydroCorridor,
    calibratedWaterMaskValueAt:global.calibratedWaterMaskValueAt,
    isKnownWater:global.isKnownWater,
    drawHeatmap:global.drawHeatmap,
    samplePhotoWaterCandidates:global.samplePhotoWaterCandidates,
    makeShoreCastingHotspots:global.makeShoreCastingHotspots,
    drawTurbulenceOverlay:global.drawTurbulenceOverlay
  };

  let cachesCleared=false;
  let lastGridCheck={
    checked:false,
    nx:0,
    ny:0,
    authoritativeWaterCells:0,
    solverWaterCells:0,
    differenceCells:0,
    sourceWaterCells:Number(heatmap.domainCellCount||0),
    logicalDomainRowsShared:heatmap.domainRows===water.rows
  };

  function finite(value,fallback=0){
    const number=Number(value);
    return Number.isFinite(number)?number:fallback;
  }

  function syntheticHydroForAuthoritativeWater(lat,lng,hydro){
    if(hydro&&finite(hydro.corridor,0)>.01) return hydro;
    let main={s:.5,signedDistancePx:0,distancePx:0};
    try{
      if(typeof nearestRiverProgress==='function') main=nearestRiverProgress(lat,lng)||main;
    }catch(_){ }
    let widthPx=160;
    try{
      if(typeof modelWidthPixels==='function'&&typeof riverWidthAt==='function'){
        widthPx=modelWidthPixels(riverWidthAt(finite(main.s,.5)),lat);
      }
    }catch(_){ }
    return {
      ...(hydro||{}),
      kind:hydro?.kind||'main',
      label:hydro?.label||'統一青色水面',
      s:finite(hydro?.s,finite(main.s,.5)),
      tributaryProgress:finite(hydro?.tributaryProgress,finite(main.s,.5)),
      signedDistancePx:finite(hydro?.signedDistancePx,finite(main.signedDistancePx,0)),
      distancePx:finite(hydro?.distancePx,finite(main.distancePx,0)),
      widthPx:Math.max(1,finite(hydro?.widthPx,widthPx)),
      maxDistPx:Math.max(260,finite(hydro?.maxDistPx,widthPx*2.2)),
      corridor:1,
      seed:1,
      authoritativeFluidDomainAssist:true
    };
  }

  function authoritativeCorridor(lat,lng){
    let hydro=null;
    try{ hydro=previous.nearestHydroCorridor(lat,lng); }catch(_){ }
    if(!water.contains(lat,lng)) return hydro;
    return syntheticHydroForAuthoritativeWater(lat,lng,hydro);
  }

  function withAuthoritativeFluidEligibility(callback){
    const active=global.nearestHydroCorridor;
    global.nearestHydroCorridor=authoritativeCorridor;
    try{
      return callback();
    }finally{
      global.nearestHydroCorridor=active;
    }
  }

  function compareGridWater(grid){
    if(!grid||!grid.water||!Number.isInteger(grid.nx)||!Number.isInteger(grid.ny)){
      throw new Error('[stage8d] invalid fluid grid returned by previous solver');
    }
    const bounds=(typeof GSI!=='undefined'&&GSI&&GSI.bounds)?GSI.bounds:null;
    if(!bounds) throw new Error('[stage8d] GSI bounds are unavailable');
    const nx=grid.nx,ny=grid.ny;
    let expectedCount=0,actualCount=0,differenceCells=0;
    for(let j=0;j<ny;j++){
      const lat=Number(bounds.north)-(Number(bounds.north)-Number(bounds.south))*(j+.5)/ny;
      for(let i=0;i<nx;i++){
        const lng=Number(bounds.west)+(Number(bounds.east)-Number(bounds.west))*(i+.5)/nx;
        const index=j*nx+i;
        const expected=water.contains(lat,lng);
        const actual=Boolean(grid.water[index]);
        if(expected) expectedCount++;
        if(actual) actualCount++;
        if(expected!==actual) differenceCells++;
      }
    }
    return {
      checked:true,
      nx,ny,
      authoritativeWaterCells:expectedCount,
      solverWaterCells:actualCount,
      differenceCells,
      sourceWaterCells:Number(heatmap.domainCellCount||0),
      logicalDomainRowsShared:heatmap.domainRows===water.rows
    };
  }

  function authoritativeBuildFluidGrid(env){
    const grid=withAuthoritativeFluidEligibility(
      ()=>previous.buildFluidGrid.call(this,env)
    );
    const check=compareGridWater(grid);
    lastGridCheck=check;
    if(check.differenceCells!==0){
      throw new Error('[stage8d] fluid-water domain mismatch: '+check.differenceCells+' cells');
    }
    grid.authoritativeWaterDomain={
      version:String(water.specVersion||''),
      source:'Stage8B water.rows',
      logicalSourceCells:check.sourceWaterCells,
      solverWaterCells:check.solverWaterCells,
      differenceCells:0,
      classification:'cell_center_contains',
      boundaryConditionsUnchanged:true,
      velocityModelUnchanged:true
    };
    if(grid.stats){
      grid.stats.authoritativeWaterDomain=true;
      grid.stats.waterDomainDifferenceCells=0;
      grid.stats.logicalSourceCells=check.sourceWaterCells;
      grid.stats.solverWaterCells=check.solverWaterCells;
      grid.stats.fluidDomainStage='8D';
    }
    try{
      if(typeof state==='object'&&state){
        state.unifiedFluidDomainStage8D={
          version:'stage8d-fluid-water-cells-only',
          specVersion:String(water.specVersion||''),
          waterDetectionConnected:true,
          heatmapConnected:true,
          fluidConnected:true,
          standGenerationConnected:false,
          boundaryConditionsConnected:false,
          logicalDomainRowsShared:check.logicalDomainRowsShared,
          sourceWaterCells:check.sourceWaterCells,
          solverGrid:[check.nx,check.ny],
          solverWaterCells:check.solverWaterCells,
          differenceCells:0
        };
      }
    }catch(_){ }
    return grid;
  }

  function clearFluidCachesOnce(){
    if(cachesCleared) return;
    cachesCleared=true;
    try{ state?.fluidBaseCache?.clear?.(); }catch(_){ }
    try{ state?.fluidCache?.clear?.(); }catch(_){ }
    try{ state?.validationCache?.clear?.(); }catch(_){ }
  }

  function install(){
    clearFluidCachesOnce();
    global.buildFluidGrid=authoritativeBuildFluidGrid;
    try{
      if(typeof state==='object'&&state){
        state.unifiedFluidDomainStage8D={
          version:'stage8d-fluid-water-cells-only',
          specVersion:String(water.specVersion||''),
          waterDetectionConnected:true,
          heatmapConnected:true,
          fluidConnected:true,
          standGenerationConnected:false,
          boundaryConditionsConnected:false,
          logicalDomainRowsShared:heatmap.domainRows===water.rows,
          sourceWaterCells:Number(heatmap.domainCellCount||0),
          solverGrid:null,
          solverWaterCells:null,
          differenceCells:null
        };
      }
    }catch(_){ }
  }

  function diagnostics(){
    return {
      version:'stage8d-fluid-water-cells-only',
      specVersion:String(water.specVersion||''),
      waterDetectionConnected:true,
      heatmapConnected:true,
      fluidConnected:true,
      standGenerationConnected:false,
      boundaryConditionsConnected:false,
      logicalDomainRowsShared:heatmap.domainRows===water.rows,
      sourceWaterCells:Number(heatmap.domainCellCount||0),
      lastGridCheck:{...lastGridCheck},
      overriddenFunctions:['buildFluidGrid'],
      temporarilyWrappedDuringBaseBuild:['nearestHydroCorridor'],
      intentionallyUntouched:[
        'classifyFluidBoundary','hydrodynamicBoundaryFluxes','fluidDepthAndMobility',
        'samplePhotoWaterCandidates','drawHeatmap','makeShoreCastingHotspots',
        'drawTurbulenceOverlay','calibratedWaterMaskValueAt','isKnownWater'
      ],
      untouchedReferences:{
        calibratedWaterMaskValueAt:global.calibratedWaterMaskValueAt===previous.calibratedWaterMaskValueAt,
        isKnownWater:global.isKnownWater===previous.isKnownWater,
        drawHeatmap:global.drawHeatmap===previous.drawHeatmap,
        samplePhotoWaterCandidates:global.samplePhotoWaterCandidates===previous.samplePhotoWaterCandidates,
        makeShoreCastingHotspots:global.makeShoreCastingHotspots===previous.makeShoreCastingHotspots,
        drawTurbulenceOverlay:global.drawTurbulenceOverlay===previous.drawTurbulenceOverlay,
        nearestHydroCorridorRestored:global.nearestHydroCorridor===previous.nearestHydroCorridor
      }
    };
  }

  const api={
    version:'stage8d-fluid-water-cells-only',
    waterApi:water,
    heatmapApi:heatmap,
    buildFluidGrid:authoritativeBuildFluidGrid,
    compareGridWater,
    install,
    diagnostics,
    previous,
    get lastGridCheck(){return {...lastGridCheck};},
    scope:{
      waterDetectionConnected:true,
      heatmapConnected:true,
      fluidConnected:true,
      standGenerationConnected:false,
      boundaryConditionsConnected:false
    }
  };

  global[API_NAME]=api;
  global.__ONGA_UNIFIED_FLUID_DOMAIN_STAGE8D_INSTALLED__=true;
  install();
  if(typeof setTimeout==='function') [120,400,1000,2500].forEach(delay=>setTimeout(install,delay));
  if(typeof console!=='undefined'&&console.info) console.info('[onga-stage8d-fluid-domain]',diagnostics());
})(typeof window!=='undefined'?window:globalThis);
