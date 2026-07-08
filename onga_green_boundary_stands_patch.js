// v4.6.4 green shoreline stand placement patch
(function(){
  'use strict';
  if(window.__ONGA_GREEN_SHORELINE_STANDS_V464__) return;
  window.__ONGA_GREEN_SHORELINE_STANDS_V464__ = true;
  const VERSION='onga-green-shoreline-stands-v4.6.4';
  // User-supplied green water/land boundary extracted from the annotated GSI screenshot.
  // Coordinates are [lat,lng]. These are stand candidate lines, not water polygons.
  const SHORELINES = [[[33.8984859,130.6661251],[33.8984146,130.6662646],[33.8982543,130.6663826],[33.8977556,130.6669512],[33.8973193,130.6671872],[33.8971501,130.6673482],[33.8970877,130.667434],[33.8971145,130.6676057],[33.8969898,130.6677988],[33.8966069,130.668067],[33.8963486,130.668346],[33.8963041,130.6684425],[33.896215,130.6684854],[33.8958766,130.6688288],[33.8957965,130.6690326],[33.8956451,130.6692901],[33.8956183,130.669569],[33.8955293,130.669848],[33.895084,130.6704059],[33.8949682,130.6706848],[33.8949415,130.6708672],[33.8949593,130.670996],[33.8952176,130.6715002],[33.8954135,130.6716934],[33.895556,130.6720796],[33.8955916,130.67238],[33.8955026,130.672498],[33.8955026,130.672616],[33.8956272,130.6728735],[33.895743,130.6733027],[33.8958232,130.6734636],[33.8958321,130.6736567],[33.8958944,130.6739142],[33.8959033,130.6743112],[33.8958588,130.6745365],[33.8956985,130.6749764],[33.8955204,130.6753304],[33.8955115,130.6754055],[33.8953334,130.6756738],[33.8951553,130.6758025],[33.8950039,130.6759849],[33.8948525,130.6762746],[33.8947278,130.6767252],[33.8946565,130.676811],[33.8946298,130.6769076],[33.8944339,130.6772187],[33.8941667,130.6775406],[33.8941133,130.67768],[33.893855,130.6780556],[33.8934276,130.6784096],[33.8933029,130.6785813],[33.8931604,130.6786886],[33.8926884,130.6789246],[33.8925548,130.6789353],[33.8923143,130.6790533],[33.8921807,130.6790748]],[[33.88779,130.683023],[33.8879147,130.6829908],[33.8882621,130.6826153],[33.8883511,130.6825831],[33.8884135,130.6824973],[33.8885114,130.6824329],[33.8886628,130.6822398],[33.8887163,130.6820789],[33.8888321,130.6819179],[33.88893,130.6815746],[33.8890013,130.681403],[33.8891082,130.6812528],[33.8892685,130.6810704],[33.8894288,130.6809738],[33.8896871,130.6806412],[33.8900255,130.6803301],[33.8901591,130.6801584],[33.8904619,130.6799438],[33.8908716,130.6795469],[33.8911209,130.6793752],[33.8912545,130.679343],[33.8914505,130.6792143],[33.8918779,130.6791499],[33.8919581,130.6790748],[33.8920472,130.679107],[33.8921273,130.679107],[33.8921629,130.6790748]],[[33.8981475,130.6629494],[33.8981386,130.662885],[33.8979694,130.6627133]],[[33.8981564,130.6629601],[33.89829,130.6632283],[33.8982811,130.6633034],[33.8979427,130.6635609],[33.8978358,130.6635716],[33.8977378,130.6634],[33.8976488,130.6633141],[33.8974796,130.6633892]],[[33.8875317,130.6724444],[33.8875496,130.6723693],[33.8876386,130.6722942],[33.8879058,130.6721762],[33.8879949,130.6721547],[33.8881285,130.6721869],[33.8883333,130.6721011],[33.8884936,130.6720903],[33.8885916,130.6720474],[33.8889478,130.6720367],[33.8896069,130.6722298],[33.8900967,130.6724444],[33.8907736,130.6725839],[33.8908894,130.6726697],[33.8911655,130.6727126],[33.8914416,130.6726697],[33.8918245,130.6722727],[33.8918512,130.6721869],[33.8920026,130.6719616],[33.8920561,130.6717685],[33.8921986,130.6715539],[33.8922876,130.6713071],[33.8924123,130.6711033],[33.8924568,130.6709316],[33.8926171,130.6706205],[33.8926973,130.6702879],[33.893009,130.669612],[33.8933741,130.6691506],[33.8934365,130.6690112],[33.893668,130.6687],[33.8937125,130.6685498],[33.8938639,130.6683889],[33.894051,130.6680992],[33.8941133,130.6679275],[33.8942647,130.6677666],[33.8943448,130.6675949]],[[33.8974796,130.6633892],[33.8974885,130.6635716],[33.8976043,130.6638613],[33.8976043,130.6639364],[33.8975152,130.6641081],[33.8974885,130.6642583],[33.8971234,130.6647411],[33.8970165,130.6648376],[33.8969096,130.6648805]],[[33.8951642,130.6668117],[33.8955738,130.6663397],[33.8956629,130.666286],[33.8960992,130.6657603],[33.8961883,130.6657174],[33.8964555,130.6654814],[33.8966781,130.6651488],[33.896874,130.6650093],[33.8969096,130.6648805]],[[33.8943538,130.6675842],[33.8944428,130.6675413],[33.8947723,130.6672302],[33.8948347,130.6671229],[33.8950306,130.6669619],[33.895084,130.6668547],[33.8951553,130.6668225]],[[33.8918245,130.678474],[33.8915395,130.678592],[33.8909339,130.67871],[33.8907736,130.6787851],[33.8903817,130.679107],[33.8899988,130.6795683],[33.8897405,130.6797829],[33.8894555,130.680094],[33.8893041,130.6801477],[33.8889033,130.6804588],[33.8888143,130.680491],[33.8886183,130.6807592],[33.8885471,130.6807914],[33.8881463,130.6811455],[33.8878257,130.68136],[33.8877277,130.6814673],[33.8875674,130.6815424],[33.8875317,130.6816068]],[[33.8875317,130.6786564],[33.8875496,130.6787315],[33.8876297,130.6787851],[33.8878969,130.6787851],[33.8879949,130.67871],[33.8880127,130.6785384],[33.8880572,130.678474],[33.8886807,130.6784633],[33.8891171,130.6783345],[33.8895267,130.6783131],[33.8900611,130.6782272],[33.8906489,130.6782379],[33.8910052,130.678195],[33.8910319,130.6783023],[33.8911477,130.6783774],[33.8916286,130.6783989],[33.8917711,130.678356]],[[33.8920026,130.678356],[33.8923589,130.6782165],[33.892724,130.6780019],[33.8932049,130.6776157],[33.8933207,130.6774655],[33.8934187,130.6774226],[33.8936502,130.6771865],[33.8938016,130.6769505],[33.8940331,130.6764891],[33.8941667,130.6763282],[33.8944606,130.6757167],[33.8945051,130.6754377],[33.8945586,130.675309],[33.8945497,130.6751802]],[[33.8918423,130.67341],[33.8913347,130.6736245],[33.8908805,130.6737533]],[[33.8908716,130.6737426],[33.8900433,130.6736031],[33.8895,130.6733563],[33.8890547,130.6731954],[33.8887964,130.6730559],[33.8885203,130.6730774],[33.8877366,130.6734958],[33.8875852,130.6736138],[33.8875317,130.6736031]],[[33.8904619,130.6742254],[33.8903194,130.6741395],[33.8903283,130.674043],[33.8908181,130.6738499],[33.8908716,130.6737533]],[[33.8875585,130.674794],[33.8879593,130.6747082],[33.8880661,130.6746545],[33.8888588,130.6746545],[33.8890993,130.6745687],[33.8892328,130.6744185],[33.889313,130.6743756],[33.8895891,130.6743648],[33.8898117,130.6742683],[33.89007,130.6742683],[33.8903639,130.6743327],[33.8904174,130.6743219],[33.8904619,130.6742468]]];

  const clampLocal = typeof clamp === 'function' ? clamp : ((v,min,max)=>Math.max(min,Math.min(max,v)));
  const gaussianLocal = typeof gaussian === 'function' ? gaussian : ((x,mu,sigma)=>Math.exp(-0.5*Math.pow((x-mu)/sigma,2)));
  const toRadLocal = d => d * Math.PI / 180;
  function havM(aLat,aLng,bLat,bLng){
    if(typeof haversine === 'function') return haversine(aLat,aLng,bLat,bLng);
    const R=6371000,p1=toRadLocal(aLat),p2=toRadLocal(bLat),d1=toRadLocal(bLat-aLat),d2=toRadLocal(bLng-aLng);
    const a=Math.sin(d1/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(d2/2)**2;
    return 2*R*Math.atan2(Math.sqrt(a),Math.sqrt(1-a));
  }
  function lerpLocal(a,b,t){ return a+(b-a)*t; }
  function noStand(lat,lng){
    return !!(window.ONGA_SPATIAL_SAFETY && typeof window.ONGA_SPATIAL_SAFETY.noStandAt === 'function' && window.ONGA_SPATIAL_SAFETY.noStandAt(lat,lng));
  }
  function castBlocked(aLat,aLng,bLat,bLng){
    return !!(window.ONGA_SPATIAL_SAFETY && typeof window.ONGA_SPATIAL_SAFETY.castBlock === 'function' && window.ONGA_SPATIAL_SAFETY.castBlock(aLat,aLng,bLat,bLng));
  }
  let boundaryCache=null;
  function buildBoundarySamples(){
    if(boundaryCache) return boundaryCache;
    const out=[];
    for(let li=0; li<SHORELINES.length; li++){
      const line=SHORELINES[li];
      for(let i=0; i<line.length-1; i++){
        const a=line[i], b=line[i+1];
        const d=havM(a[0],a[1],b[0],b[1]);
        const steps=Math.max(1,Math.ceil(d/6));
        for(let k=0;k<=steps;k++){
          const t=k/steps, lat=lerpLocal(a[0],b[0],t), lng=lerpLocal(a[1],b[1],t);
          if(!Number.isFinite(lat)||!Number.isFinite(lng)||noStand(lat,lng)) continue;
          out.push({lat,lng,line:li,seg:i});
        }
      }
    }
    boundaryCache=out;
    return out;
  }
  function nearestGreenBoundaryForTarget(target){
    if(!target || !Number.isFinite(target.lat) || !Number.isFinite(target.lng)) return null;
    const maxM=(typeof CAST_MODEL !== 'undefined' && CAST_MODEL.maxM) ? CAST_MODEL.maxM : 100;
    let best=null;
    for(const s of buildBoundarySamples()){
      const d=havM(s.lat,s.lng,target.lat,target.lng);
      if(d<1.5 || d>maxM) continue;
      if(castBlocked(s.lat,s.lng,target.lat,target.lng)) continue;
      const preferred=gaussianLocal(d,34,30);
      const score=(target.score||0) * (.66 + .34*preferred) * (d<5 ? .55 : 1);
      if(!best || score>best.score) best={lat:s.lat,lng:s.lng,distanceM:d,bearing:0,landConfidence:1,bankQuality:1,score,onGreenBoundary:true,line:s.line,seg:s.seg};
    }
    return best;
  }
  if(typeof findLandCastPositionForWater === 'function'){
    findLandCastPositionForWater = function(waterPoint){ return nearestGreenBoundaryForTarget(waterPoint); };
  }
  if(typeof makeShoreCastingHotspots === 'function'){
    makeShoreCastingHotspots = function(scoredWaterCandidates,n=8){
      const sorted=[...(scoredWaterCandidates||[])]
        .filter(p=>p && Number.isFinite(p.score) && p.score>.35)
        .sort((a,b)=>b.score-a.score);
      const raw=[];
      for(let i=0;i<Math.min(sorted.length,1100);i++){
        const target=sorted[i];
        const boundary=nearestGreenBoundaryForTarget(target);
        if(!boundary) continue;
        const score=clampLocal(boundary.score,0,1);
        raw.push({
          ...target,
          lat:boundary.lat,
          lng:boundary.lng,
          targetLat:target.lat,
          targetLng:target.lng,
          targetScore:target.score,
          castDistanceM:boundary.distanceM,
          landConfidence:1,
          bankQuality:1,
          onLand:true,
          onGreenBoundary:true,
          greenBoundaryStand:VERSION,
          shorelineLine:boundary.line,
          shorelineSegment:boundary.seg,
          score,
          structureName:`緑線境界釣り座：${target.structureName || target.hydroLabel || '水面標的'}`,
          reason:`緑線の水面・陸地境界上に配置 / ${Math.round(boundary.distanceM)}m先の水面標的 / ${target.reason || ''}`
        });
      }
      raw.sort((a,b)=>b.score-a.score);
      const chosen=[];
      const bankSep=(typeof CAST_MODEL !== 'undefined' && CAST_MODEL.bankSepM) ? CAST_MODEL.bankSepM : 85;
      const targetSep=(typeof CAST_MODEL !== 'undefined' && CAST_MODEL.targetSepM) ? CAST_MODEL.targetSepM : 90;
      for(const c of raw){
        if(noStand(c.lat,c.lng) || castBlocked(c.lat,c.lng,c.targetLat,c.targetLng)) continue;
        let ok=true;
        for(const h of chosen){
          if(havM(c.lat,c.lng,h.lat,h.lng)<bankSep || havM(c.targetLat,c.targetLng,h.targetLat,h.targetLng)<targetSep){ ok=false; break; }
        }
        if(ok) chosen.push(c);
        if(chosen.length>=n) break;
      }
      return chosen.map((h,i)=>({...h,rank:i+1,score100:Math.round(h.score*100),targetScore100:Math.round((h.targetScore||h.score)*100)}));
    };
  }
  if(typeof updateWaterStatus === 'function'){
    const prevUpdateWaterStatus = updateWaterStatus;
    updateWaterStatus = function(){
      const r=prevUpdateWaterStatus.apply(this,arguments);
      const el=document.getElementById('waterStatus');
      if(el && !el.textContent.includes('釣り座=緑線境界')) el.textContent += ' / v4.6.4: 釣り座=緑線境界上';
      return r;
    };
  }
  if(typeof bindUI === 'function'){
    const prevBindUI = bindUI;
    bindUI = function(){
      const r=prevBindUI.apply(this,arguments);
      const h1=document.querySelector('h1');
      if(h1) h1.textContent = h1.textContent.replace(/v4\.6\.3|v4\.6\.2|v4\.6|v4\.5|v4\.4|v4\.3|v4\.2|v4\.1|v4\.0/g,'v4.6.4');
      const sub=document.querySelector('.sub');
      if(sub) sub.textContent = '釣り座は提供画像の緑線（水面・陸地境界）上に固定し、河口堰・橋・魚道の除外と横断禁止を適用します。';
      return r;
    };
  }
  window.ONGA_GREEN_SHORELINE_STANDS = {version:VERSION, shorelines:SHORELINES, boundarySamples:buildBoundarySamples, nearestGreenBoundaryForTarget};
  try{
    if(typeof state !== 'undefined'){
      state.waterSampleCache?.clear?.(); state.fluidCache?.clear?.(); state.fluidBaseCache?.clear?.(); state.validationCache?.clear?.();
      if(state.timeline?.length && typeof computeAndRender === 'function') setTimeout(()=>computeAndRender(true),0);
    }
  }catch(e){ console.warn('[green shoreline stands] refresh failed',e); }
})();
