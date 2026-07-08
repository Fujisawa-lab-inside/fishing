// v4.6.3 Onga green-boundary water model override
(function(){
  'use strict';
  if(window.__ONGA_GREEN_BOUNDARY_WATER_V463__) return;
  window.__ONGA_GREEN_BOUNDARY_WATER_V463__ = true;

  const VERSION = 'onga-green-boundary-water-v4.6.3';
  const SOURCE_URL = 'https://maps.gsi.go.jp/#16/33.892724/130.674220/&base=std&ls=std%7Cseamlessphoto&blend=0&disp=11&vs=c1g1j0h0k0l0u0t0z0r0s0m0f1';
  const VIEW_BOUNDS = { south: 33.8822857, west: 130.6510672, north: 33.9042296, east: 130.6950125 };

  const DOWNSTREAM_PATH = [
    [33.8931871, 130.6740269],
    [33.8946120, 130.6710228],
    [33.8964822, 130.6673750],
    [33.8969274, 130.6639418],
    [33.8984413, 130.6602940],
    [33.9010238, 130.6577191],
    [33.9034281, 130.6538567]
  ];

  const GREEN_INFLOW_CHANNELS = [
    {
      id: 'nishi', name: '西川', side: 'west', mainS: 0.040, weight: 0.88,
      widthM: 150, seedWidthM: 230, influenceWidthM: 300,
      mouth: { lat: 33.8931871, lng: 130.6740269 },
      path: [
        [33.8832120, 130.6703791],
        [33.8855278, 130.6699499],
        [33.8874872, 130.6701645],
        [33.8890903, 130.6703791],
        [33.8906934, 130.6709155],
        [33.8917622, 130.6714520],
        [33.8926528, 130.6727394],
        [33.8931871, 130.6740269]
      ]
    },
    {
      id: 'onga_up', name: '遠賀川本流', side: 'center', mainS: 0.052, weight: 0.98,
      widthM: 235, seedWidthM: 340, influenceWidthM: 380,
      mouth: { lat: 33.8931871, lng: 130.6740269 },
      path: [
        [33.8832120, 130.6734904],
        [33.8853497, 130.6734904],
        [33.8872200, 130.6740269],
        [33.8890013, 130.6750998],
        [33.8905153, 130.6749925],
        [33.8916731, 130.6745633],
        [33.8926528, 130.6742415],
        [33.8931871, 130.6740269]
      ]
    },
    {
      id: 'magari', name: '曲川', side: 'east', mainS: 0.065, weight: 0.84,
      widthM: 180, seedWidthM: 280, influenceWidthM: 330,
      mouth: { lat: 33.8966603, lng: 130.6763872 },
      path: [
        [33.8838355, 130.6914076],
        [33.8858841, 130.6892618],
        [33.8881997, 130.6873306],
        [33.8905153, 130.6853994],
        [33.8926528, 130.6841120],
        [33.8944339, 130.6817516],
        [33.8960369, 130.6785330],
        [33.8966603, 130.6763872]
      ]
    }
  ];

  const WATER_AXES = [
    { id: 'downstream', name: '合流後の遠賀川下流', kind: 'main', path: DOWNSTREAM_PATH, widthM: 420, seedWidthM: 520 },
    ...GREEN_INFLOW_CHANNELS.map(c => ({ id: c.id, name: c.name, kind: c.id, path: c.path, widthM: c.widthM, seedWidthM: c.seedWidthM, mainS: c.mainS }))
  ];

  const refLat = 33.892724;
  const refLng = 130.674220;
  const toRadLocal = d => d * Math.PI / 180;
  const clampLocal = typeof clamp === 'function' ? clamp : ((v,min,max)=>Math.max(min,Math.min(max,v)));
  const gaussianLocal = typeof gaussian === 'function' ? gaussian : ((x,mu,sigma)=>Math.exp(-0.5*Math.pow((x-mu)/sigma,2)));

  function localXY(lat,lng){
    return { x: (lng - refLng) * 111320 * Math.cos(toRadLocal(refLat)), y: (lat - refLat) * 110540 };
  }
  function metersPerModelPixel(lat){
    if(typeof metersPerPixelAt === 'function' && typeof MODEL_ZOOM !== 'undefined') return metersPerPixelAt(lat, MODEL_ZOOM);
    return 156543.03392804097 * Math.cos(toRadLocal(lat)) / Math.pow(2, 18);
  }
  function axisWidth(axis, progress){
    if(axis.id === 'downstream') return clampLocal(250 + 260*gaussianLocal(progress, 0.05, 0.24) + 120*gaussianLocal(progress, 0.36, 0.30), 230, 560);
    if(axis.id === 'onga_up') return clampLocal(210 + 90*gaussianLocal(progress, 0.18, 0.25) + 55*gaussianLocal(progress, 0.72, 0.30), 190, 330);
    if(axis.id === 'magari') return clampLocal(170 + 40*gaussianLocal(progress, 0.50, 0.35), 155, 230);
    if(axis.id === 'nishi') return clampLocal(145 + 35*gaussianLocal(progress, 0.55, 0.35), 130, 205);
    return axis.widthM || 160;
  }
  function nearestOnAxisMeters(lat,lng,axis){
    const p=localXY(lat,lng), pts=axis.path.map(ll=>({lat:ll[0],lng:ll[1],...localXY(ll[0],ll[1])}));
    let total=0, segs=[];
    for(let i=0;i<pts.length-1;i++){ const dx=pts[i+1].x-pts[i].x, dy=pts[i+1].y-pts[i].y, len=Math.hypot(dx,dy)||1; segs.push({i,start:total,len,dx,dy}); total+=len; }
    let best=null;
    for(const seg of segs){
      const a=pts[seg.i], u=clampLocal(((p.x-a.x)*seg.dx+(p.y-a.y)*seg.dy)/(seg.len*seg.len||1),0,1);
      const cx=a.x+seg.dx*u, cy=a.y+seg.dy*u, vx=p.x-cx, vy=p.y-cy;
      const dist=Math.hypot(vx,vy), nx=-seg.dy/seg.len, ny=seg.dx/seg.len, signed=vx*nx+vy*ny;
      const progress=(seg.start+u*seg.len)/Math.max(1,total);
      if(!best || dist<best.distanceM) best={axis, progress, distanceM:dist, signedM:signed, x:cx, y:cy, tx:seg.dx/seg.len, ty:seg.dy/seg.len, nx, ny, segIndex:seg.i, totalM:total};
    }
    return best || {axis, progress:0, distanceM:Infinity, signedM:Infinity};
  }
  function nearestGreenAxis(lat,lng){
    let best=null;
    for(const axis of WATER_AXES){ const n=nearestOnAxisMeters(lat,lng,axis); n.widthM=axisWidth(axis,n.progress); n.seedWidthM=axis.seedWidthM || n.widthM*1.35; n.normalized=n.distanceM/Math.max(1,n.seedWidthM*0.5); if(!best || n.normalized < best.normalized) best=n; }
    return best;
  }
  function greenBoundaryWaterMaskValueAt(lat,lng){
    if(!Number.isFinite(lat) || !Number.isFinite(lng)) return 0;
    if(lat < VIEW_BOUNDS.south || lat > VIEW_BOUNDS.north || lng < VIEW_BOUNDS.west || lng > VIEW_BOUNDS.east) return 0;
    const n=nearestGreenAxis(lat,lng); if(!n || !Number.isFinite(n.distanceM)) return 0;
    const half=n.widthM*0.5, soft=12;
    return n.distanceM <= half ? 1 : (n.distanceM <= half + soft ? 0.65 : 0);
  }
  function greenHydroCorridor(lat,lng){
    const n=nearestGreenAxis(lat,lng); if(!n) return null;
    const mpp=metersPerModelPixel(lat), widthPx=n.widthM/mpp, seedPx=n.seedWidthM/mpp, distPx=n.distanceM/mpp, signedPx=n.signedM/mpp;
    const corridor=clampLocal(1 - n.distanceM/Math.max(1,n.seedWidthM*0.56),0,1), seed=clampLocal(1 - n.distanceM/Math.max(1,n.widthM*0.30),0,1);
    const s=n.axis.id === 'downstream' ? n.progress : (n.axis.mainS ?? 0.05);
    return { kind: n.axis.id === 'downstream' ? 'main' : n.axis.id, label: n.axis.name, s, tributaryProgress: n.progress, signedDistancePx: signedPx, distancePx: distPx, widthPx, maxDistPx: seedPx*0.56, corridor, seed, tx: n.tx, ty: n.ty, nx: n.nx, ny: n.ny, greenBoundary: VERSION };
  }

  function applyGeometry(){
    if(typeof GSI !== 'undefined'){
      GSI.sourceUrl = SOURCE_URL; GSI.center = {lat:33.892724,lng:130.674220}; GSI.zoom = 16; GSI.minZoom = 16; GSI.maxZoom = 18; GSI.bounds = {...VIEW_BOUNDS};
    }
    if(typeof ONGA !== 'undefined'){
      ONGA.center = {lat:33.892724,lng:130.674220}; ONGA.confluence = {lat:33.8931871,lng:130.6740269,name:'3河道合流域'}; ONGA.ashiya = {lat:33.8984413,lng:130.6602940,name:'芦屋橋'};
      ONGA.path = DOWNSTREAM_PATH.map(p=>p.slice());
      ONGA.inflowChannels = GREEN_INFLOW_CHANNELS.map(c=>({...c,path:c.path.map(p=>p.slice()),mouth:{...c.mouth}}));
      ONGA.tributaries = ONGA.inflowChannels.filter(c=>c.id==='nishi'||c.id==='magari');
      ONGA.landmarks = [ ...(ONGA.landmarks||[]).filter(l=>!['nishi','onga_up','magari','bridge','confluence'].includes(l.kind)), {lat:ONGA.confluence.lat,lng:ONGA.confluence.lng,label:'3河道合流域',kind:'confluence'}, {lat:33.8926528,lng:130.6727394,label:'西川上流筋',kind:'nishi'}, {lat:33.8905153,lng:130.6749925,label:'遠賀川本流上流筋',kind:'onga_up'}, {lat:33.8905153,lng:130.6853994,label:'曲川上流筋',kind:'magari'}, {lat:ONGA.ashiya.lat,lng:ONGA.ashiya.lng,label:'芦屋橋',kind:'bridge'} ];
    }
    try{ if(typeof pathMetrics !== 'undefined' && typeof buildPathMetricsFromLatLngs === 'function'){ const m=buildPathMetricsFromLatLngs(ONGA.path); pathMetrics.pts=m.pts; pathMetrics.segs=m.segs; pathMetrics.total=m.total; } }catch(e){ console.warn('[green-water] pathMetrics update failed',e); }
    try{
      if(typeof inflowMetrics !== 'undefined' && typeof buildPathMetricsFromLatLngs === 'function'){ const next=ONGA.inflowChannels.map(t=>({...t,metrics:buildPathMetricsFromLatLngs(t.path)})); inflowMetrics.splice(0,inflowMetrics.length,...next); }
      if(typeof tributaryMetrics !== 'undefined' && typeof buildPathMetricsFromLatLngs === 'function'){ const next=ONGA.inflowChannels.filter(t=>t.id==='nishi'||t.id==='magari').map(t=>({...t,metrics:buildPathMetricsFromLatLngs(t.path)})); tributaryMetrics.splice(0,tributaryMetrics.length,...next); }
    }catch(e){ console.warn('[green-water] inflow metrics update failed',e); }
  }

  applyGeometry();

  if(typeof calibratedWaterMaskValueAt === 'function') calibratedWaterMaskValueAt = function(lat,lng){ return greenBoundaryWaterMaskValueAt(lat,lng); };
  if(typeof nearestHydroCorridor === 'function') nearestHydroCorridor = function(lat,lng){ return greenHydroCorridor(lat,lng); };
  if(typeof riverWidthAt === 'function') riverWidthAt = function(s){ return clampLocal(260 + 270*gaussianLocal(s,0.05,0.25) + 95*gaussianLocal(s,0.36,0.30), 220, 560); };
  if(typeof updateWaterStatus === 'function'){
    const prevUpdateWaterStatus = updateWaterStatus;
    updateWaterStatus = function(){ const r=prevUpdateWaterStatus.apply(this,arguments); const el=document.getElementById('waterStatus'); if(el && !el.textContent.includes('緑線境界')) el.textContent += ' / v4.6.3: 緑線境界水面・西川/本流/曲川上流域込み'; return r; };
  }
  if(typeof bindUI === 'function'){
    const prevBindUI = bindUI;
    bindUI = function(){ const r=prevBindUI.apply(this,arguments); const h1=document.querySelector('h1'); if(h1) h1.textContent = h1.textContent.replace(/v4\.6|v4\.5|v4\.4|v4\.3|v4\.2|v4\.1|v4\.0/g,'v4.6.3'); const sub=document.querySelector('.sub'); if(sub) sub.textContent = '提供画像の緑線を水面/陸上境界として採用し、西川・遠賀川本流・曲川の上流（南側）領域も水面計算に含めます。'; return r; };
  }
  window.ONGA_GREEN_BOUNDARY_WATER = {version:VERSION, sourceUrl:SOURCE_URL, bounds:VIEW_BOUNDS, axes:WATER_AXES, waterMaskValueAt:greenBoundaryWaterMaskValueAt, nearestAxis:nearestGreenAxis};

  try{
    if(typeof state !== 'undefined'){
      state.waterSampleCache?.clear?.(); state.fluidCache?.clear?.(); state.fluidBaseCache?.clear?.(); state.validationCache?.clear?.();
      if(typeof GSI !== 'undefined' && typeof project === 'function' && (!state.center || Math.abs(state.center.lat-33.892724)>0.0005 || Math.abs(state.center.lng-130.674220)>0.0005)){ state.zoom = GSI.zoom; state.center = {...GSI.center}; state.centerPx = project(state.center.lat,state.center.lng,state.zoom); }
      if(state.timeline?.length && typeof computeAndRender === 'function') setTimeout(()=>computeAndRender(true),0);
    }
  }catch(e){ console.warn('[green-water] refresh failed',e); }
})();
