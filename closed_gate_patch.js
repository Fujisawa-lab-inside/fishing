(function installV461ClosedGateMainZero(){
  'use strict';
  if(window.__ONGA_V461_CLOSED_GATE_MAIN_ZERO__) return;
  window.__ONGA_V461_CLOSED_GATE_MAIN_ZERO__ = true;
  const PATCH_VERSION = 'v4.6.1 closed-gate-main-zero 2026-07-06';
  const norm = v => Math.max(0, Math.min(1, Number(v) || 0));
  const safeClamp = (typeof clamp === 'function') ? clamp : ((v,a,b)=>Math.max(a,Math.min(b,v)));
  function currentDate(){
    try{ return state?.timeline?.[state.currentIndex]?.date || new Date(); }catch(_){ return new Date(); }
  }
  function observedGate(env){
    try{
      if(env?.gate?.observedGate) return env.gate.observedGate;
      if(typeof gateObservationForDate === 'function') return gateObservationForDate(env?.entry?.date || currentDate());
    }catch(_){ }
    return null;
  }
  function isClosedMainGate(env){
    const obs = observedGate(env);
    if(obs && obs.active && (obs.openNos||[]).length===0 && norm(obs.weight ?? 1) > 0) return true;
    if(env?.gate?.manualGateApplied && norm(env?.gate?.gateOpening ?? env?.gate?.risk) <= .001 && env?.gate?.observedGate && (env.gate.observedGate.openNos||[]).length===0) return true;
    return false;
  }
  function downstreamHead(env){
    const falling = norm(env?.falling), rising = norm(env?.rising), tideMove = norm(env?.tideMove);
    const gate = norm(env?.gate?.gateOpening ?? env?.gate?.risk);
    return .82*rising*tideMove - .58*falling*tideMove - .20*gate;
  }
  function fishwayValue(lat,lng,env){
    try{
      if(typeof fishwayInfluenceAtPoint === 'function') return norm(fishwayInfluenceAtPoint(lat,lng,env).score);
    }catch(_){ }
    return 0;
  }
  function closedWaterMass(base,lat,lng,env){
    const b = base || {};
    const fish = fishwayValue(lat,lng,env);
    const nishi = norm(b.nishi);
    const magari = norm(b.magari);
    const sea = norm(b.sea);
    const total = Math.max(.001, fish + nishi + magari + sea);
    const out = {
      ...b,
      onga:0,
      fishway:fish/total,
      nishi:nishi/total,
      magari:magari/total,
      sea:sea/total
    };
    const names = [['魚道',out.fishway],['西川',out.nishi],['曲川',out.magari],['潮汐/海側',out.sea]];
    names.sort((a,b)=>b[1]-a[1]);
    out.dominant = names[0][0];
    out.label = `${names[0][0]}${Math.round(names[0][1]*100)}% / ${names[1][0]}${Math.round(names[1][1]*100)}%`;
    out.front = safeClamp((1-Math.max(out.fishway,out.nishi,out.magari,out.sea))*1.35 + Math.min(out.sea,out.fishway+out.nishi+out.magari)*.30,0,1);
    out.mixing = safeClamp(1-Math.max(out.fishway,out.nishi,out.magari,out.sea),0,1);
    out.branchMix = safeClamp(Math.min(out.fishway+out.sea,out.nishi+out.magari)*1.20 + out.front*.20,0,1);
    return out;
  }

  if(typeof hydrodynamicBoundaryFluxes === 'function'){
    const prevFlux = hydrodynamicBoundaryFluxes;
    hydrodynamicBoundaryFluxes = function(env){
      const f = prevFlux(env);
      if(!isClosedMainGate(env)) return f;
      return {...f, riverDown:0, ongaUpQ:0, netMain:(f.tidalEbb||0)-(f.tidalFlood||0), closedOngaMain:true};
    };
  }

  if(typeof boundaryPhi === 'function'){
    const prevBoundaryPhi = boundaryPhi;
    boundaryPhi = function(type,env,flux){
      if(isClosedMainGate(env) && (type===2 || type===5)) return downstreamHead(env);
      return prevBoundaryPhi(type,env,flux);
    };
  }

  if(typeof classifyFluidBoundary === 'function'){
    const prevClassify = classifyFluidBoundary;
    classifyFluidBoundary = function(lat,lng,env){
      const r = prevClassify(lat,lng,env);
      if(isClosedMainGate(env) && r && (r.type==='onga_up' || r.type==='gate')){
        return {fixed:true, phi:downstreamHead(env), type:'closed_onga_main_zero'};
      }
      return r;
    };
  }

  if(typeof window.waterMassContributionAt === 'function'){
    const prevWM = window.waterMassContributionAt;
    window.waterMassContributionAt = function(lat,lng,env){
      const wm = prevWM(lat,lng,env);
      return isClosedMainGate(env) ? closedWaterMass(wm,lat,lng,env) : wm;
    };
  }

  if(typeof scoreFishingSample === 'function'){
    const prevScore = scoreFishingSample;
    scoreFishingSample = function(sample,env){
      const p = prevScore(sample,env);
      if(!isClosedMainGate(env)) return p;
      const lat = Number(p?.lat ?? sample?.lat), lng = Number(p?.lng ?? sample?.lng);
      if(!Number.isFinite(lat) || !Number.isFinite(lng)) return p;
      const wm0 = p.waterMass || (typeof window.waterMassContributionAt === 'function' ? window.waterMassContributionAt(lat,lng,env) : null);
      const wm = closedWaterMass(wm0,lat,lng,env);
      const fishBoost = safeClamp((wm.fishway||0)*.025,0,.025);
      const mainPenalty = safeClamp((p.onga||0)*.050 + (wm0?.onga||0)*.040,0,.085);
      const score = safeClamp((p.score||0) - mainPenalty + fishBoost,0,1);
      let structureName = p.structureName || '';
      if(wm.dominant === '魚道' && (wm.fishway||0) > .22) structureName = '魚道流れ出し/ヨレ';
      else if(/遠賀川本流/.test(structureName)) structureName = structureName.replace(/遠賀川本流/g,'全閉時支流・潮汐');
      let reason = p.reason || '';
      if(!reason.includes('本流ゲート0')) reason = reason ? `${reason} / 本流ゲート0` : '本流ゲート0';
      return {...p, score, heatScore:score, onga:0, fishway:wm.fishway, nishi:wm.nishi, magari:wm.magari, sea:wm.sea, waterMass:wm, waterMassLabel:wm.label, structureName, reason};
    };
  }

  if(typeof updateSidebar === 'function'){
    const prevUpdateSidebar = updateSidebar;
    updateSidebar = function(entry,w,m,gate,tide,model){
      const r = prevUpdateSidebar.apply(this,arguments);
      try{
        const env = {entry, gate, tide, falling:norm(tide?.falling), rising:norm(tide?.rising), tideMove:norm(tide?.tideMove)};
        if(isClosedMainGate(env)){
          const top = state.hotspots && state.hotspots[0];
          const wm = top?.waterMass;
          const tri = document.getElementById('tributaryIndex');
          if(tri && wm) tri.textContent = `全閉 本流0 / 魚道${Math.round((wm.fishway||0)*100)} / 西川${Math.round((wm.nishi||0)*100)} / 曲川${Math.round((wm.magari||0)*100)} / 潮汐${Math.round((wm.sea||0)*100)}`;
          const comment = document.getElementById('gateComment');
          if(comment) comment.textContent = '全閉入力中: 遠賀川本流ゲート流は0。魚道・西川・曲川・潮汐のみを流れ成分として計算。';
        }
      }catch(_){ }
      return r;
    };
  }

  try{ state.fluidCache && state.fluidCache.clear && state.fluidCache.clear(); }catch(_){ }
  try{ state.waterSampleCache && state.waterSampleCache.clear && state.waterSampleCache.clear(); }catch(_){ }
  try{ state.v33ValidationCache && state.v33ValidationCache.clear && state.v33ValidationCache.clear(); }catch(_){ }
  try{
    const sub = document.querySelector('.sub');
    if(sub && !sub.textContent.includes('全閉時本流ゼロ')) sub.textContent += ' 全閉時本流ゼロモデルを反映。';
  }catch(_){ }
  try{
    if(typeof computeAndRender === 'function' && state?.timeline?.length) computeAndRender(true);
    else if(typeof renderAll === 'function') renderAll();
  }catch(_){ }
  window.ONGA_CLOSED_GATE_FLOW_MODEL = {version:PATCH_VERSION, isClosedMainGate};
})();
