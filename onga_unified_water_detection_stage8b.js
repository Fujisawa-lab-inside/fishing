// Stage 8B: authoritative water-detection adapter only.
// Intentionally untouched: heatmap, fluid-grid construction, hotspot/stand generation,
// hydrodynamic scoring and long river-direction fields.
(function installOngaUnifiedWaterDetectionStage8B(global){
  'use strict';

  const API_NAME='ONGA_UNIFIED_WATER_DETECTION_STAGE8B';
  const DATA_NAME='ONGA_UNIFIED_SPEC_STAGE8B_DATA';
  const spec=global[DATA_NAME];

  if(!spec) throw new Error('[stage8b] missing '+DATA_NAME);
  if(!['onga_unified_water_spec','onga_unified_water_detection_manifest'].includes(spec.schema)){
    throw new Error('[stage8b] invalid schema: '+String(spec.schema));
  }
  if(!String(spec.status||'').startsWith('approved_stage8a')){
    throw new Error('[stage8b] Stage 8A approval is missing');
  }

  const domain=spec.waterDomain;
  const width=Number(domain&&domain.width);
  const height=Number(domain&&domain.height);
  if(!domain||!Number.isInteger(width)||!Number.isInteger(height)||width<=0||height<=0){
    throw new Error('[stage8b] invalid waterDomain dimensions');
  }

  function base64ToBytes(value){
    const text=String(value||'');
    const binary=(typeof atob==='function')
      ? atob(text)
      : (typeof Buffer!=='undefined'
          ? Buffer.from(text,'base64').toString('binary')
          : (()=>{throw new Error('[stage8b] no base64 decoder');})());
    const bytes=new Uint8Array(binary.length);
    for(let i=0;i<binary.length;i++) bytes[i]=binary.charCodeAt(i)&255;
    return bytes;
  }

  function decodePackedRows(waterDomain){
    if(Array.isArray(waterDomain.rows)) return waterDomain.rows;
    if(waterDomain.encoding!=='row_runs_offsets_uint32_runs_uint16_base64_le_v1'){
      throw new Error('[stage8b] unsupported row encoding: '+String(waterDomain.encoding));
    }
    const offsetsBytes=base64ToBytes(waterDomain.rowOffsetsBase64);
    const runsBytes=base64ToBytes(waterDomain.runsBase64);
    if(offsetsBytes.byteLength!==(height+1)*4) throw new Error('[stage8b] offsets byte length mismatch');
    if(runsBytes.byteLength!==Number(waterDomain.runValueCount)*2) throw new Error('[stage8b] runs byte length mismatch');

    const offsetsView=new DataView(offsetsBytes.buffer,offsetsBytes.byteOffset,offsetsBytes.byteLength);
    const runsView=new DataView(runsBytes.buffer,runsBytes.byteOffset,runsBytes.byteLength);
    const rows=new Array(height);
    for(let y=0;y<height;y++){
      const start=offsetsView.getUint32(y*4,true);
      const end=offsetsView.getUint32((y+1)*4,true);
      if(end<start||end>Number(waterDomain.runValueCount)) throw new Error('[stage8b] invalid row offsets at y='+y);
      const row=new Array(end-start);
      for(let i=start;i<end;i++) row[i-start]=runsView.getUint16(i*2,true);
      if(row.length%2!==0) throw new Error('[stage8b] odd row run count at y='+y);
      rows[y]=row;
    }
    waterDomain.rows=rows;
    return rows;
  }

  const rows=decodePackedRows(domain);
  if(rows.length!==height) throw new Error('[stage8b] row count mismatch');

  const geo=spec.coordinateSystem&&spec.coordinateSystem.geographic;
  const transform=geo&&geo.transform;
  const mesh=geo&&geo.controlMesh;
  if(!transform||!mesh||!Array.isArray(mesh.anchors)||!Array.isArray(mesh.triangles)){
    throw new Error('[stage8b] missing georeference/control mesh');
  }
  if(Number(mesh.triangleFlipCount||0)!==0) throw new Error('[stage8b] control mesh contains flipped triangles');

  const EARTH_CIRCUMFERENCE_M=40075016.68557849;
  const a=Number(transform.a),b=Number(transform.b),tx=Number(transform.tx),ty=Number(transform.ty);
  const determinant=a*a+b*b;
  if(!Number.isFinite(determinant)||determinant<=0) throw new Error('[stage8b] invalid base transform');

  function webMercator(lat,lng){
    const clamped=Math.max(-85.05112878,Math.min(85.05112878,Number(lat)));
    const sin=Math.sin(clamped*Math.PI/180);
    return {
      x:(Number(lng)+180)/360*EARTH_CIRCUMFERENCE_M,
      y:(0.5-Math.log((1+sin)/(1-sin))/(4*Math.PI))*EARTH_CIRCUMFERENCE_M
    };
  }

  function inverseWebMercator(x,y){
    const lng=Number(x)/EARTH_CIRCUMFERENCE_M*360-180;
    const n=Math.PI-2*Math.PI*Number(y)/EARTH_CIRCUMFERENCE_M;
    return {lat:Math.atan(Math.sinh(n))*180/Math.PI,lng};
  }

  function worldToBasePixel(X,Y){
    const dx=Number(X)-tx,dy=Number(Y)-ty;
    return {x:(a*dx+b*dy)/determinant,y:(-b*dx+a*dy)/determinant};
  }

  function basePixelToWorld(x,y){
    return {x:tx+a*Number(x)-b*Number(y),y:ty+b*Number(x)+a*Number(y)};
  }

  function barycentric(point,p0,p1,p2){
    const x=Number(point.x),y=Number(point.y);
    const x0=Number(p0[0]),y0=Number(p0[1]);
    const x1=Number(p1[0]),y1=Number(p1[1]);
    const x2=Number(p2[0]),y2=Number(p2[1]);
    const denominator=(y1-y2)*(x0-x2)+(x2-x1)*(y0-y2);
    if(Math.abs(denominator)<1e-12) return null;
    const w0=((y1-y2)*(x-x2)+(x2-x1)*(y-y2))/denominator;
    const w1=((y2-y0)*(x-x2)+(x0-x2)*(y-y2))/denominator;
    return [w0,w1,1-w0-w1];
  }

  function interpolate(weights,p0,p1,p2){
    return {
      x:weights[0]*Number(p0[0])+weights[1]*Number(p1[0])+weights[2]*Number(p2[0]),
      y:weights[0]*Number(p0[1])+weights[1]*Number(p1[1])+weights[2]*Number(p2[1])
    };
  }

  function meshMap(point,sourceField,targetField){
    const epsilon=1e-7;
    for(const triangle of mesh.triangles){
      const i0=Number(triangle[0]),i1=Number(triangle[1]),i2=Number(triangle[2]);
      const weights=barycentric(
        point,
        mesh.anchors[i0][sourceField],
        mesh.anchors[i1][sourceField],
        mesh.anchors[i2][sourceField]
      );
      if(!weights) continue;
      if(weights.every(value=>value>=-epsilon&&value<=1+epsilon)){
        return interpolate(
          weights,
          mesh.anchors[i0][targetField],
          mesh.anchors[i1][targetField],
          mesh.anchors[i2][targetField]
        );
      }
    }
    return {x:Number(point.x),y:Number(point.y)};
  }

  function latLngToImageXY(lat,lng){
    if(!Number.isFinite(Number(lat))||!Number.isFinite(Number(lng))) return {x:NaN,y:NaN};
    const world=webMercator(lat,lng);
    return meshMap(worldToBasePixel(world.x,world.y),'sourceBasePixel','targetImagePixel');
  }

  function imageXYToLatLng(x,y){
    if(!Number.isFinite(Number(x))||!Number.isFinite(Number(y))) return {lat:NaN,lng:NaN};
    const base=meshMap({x:Number(x),y:Number(y)},'targetImagePixel','sourceBasePixel');
    const world=basePixelToWorld(base.x,base.y);
    return inverseWebMercator(world.x,world.y);
  }

  function rowContains(ix,iy){
    ix=Math.floor(Number(ix));iy=Math.floor(Number(iy));
    if(ix<0||iy<0||ix>=width||iy>=height) return false;
    const row=rows[iy]||[];
    for(let i=0;i<row.length;i+=2){
      if(ix<row[i]) return false;
      if(ix<=row[i+1]) return true;
    }
    return false;
  }

  function containsImagePixel(x,y){return rowContains(x,y);}
  function contains(lat,lng){
    const point=latLngToImageXY(lat,lng);
    return rowContains(point.x,point.y);
  }
  function waterValue(lat,lng){return contains(lat,lng)?1:0;}

  const previous={
    calibratedWaterMaskValueAt:global.calibratedWaterMaskValueAt,
    isKnownWater:global.isKnownWater
  };

  function install(){
    global.calibratedWaterMaskValueAt=waterValue;
    global.isKnownWater=contains;
    try{
      if(typeof state==='object'&&state){
        state.unifiedWaterDetectionStage8B={
          version:String(spec.version),
          specStatus:String(spec.status),
          waterDetectionOnly:true,
          heatmapConnected:false,
          fluidConnected:false,
          standGenerationConnected:false
        };
      }
    }catch(_){}
  }

  function diagnostics(){
    const controlPoints=(geo.controlPoints||[]);
    const semanticById=new Map((spec.controlPointSemantics||[]).map(item=>[String(item.id),String(item.semantic||'')]));
    const controls=controlPoints.map(control=>{
      const mapped=latLngToImageXY(Number(control.lat),Number(control.lng));
      const dx=mapped.x-Number(control.pixel[0]),dy=mapped.y-Number(control.pixel[1]);
      return {
        id:String(control.id),
        semantic:String(control.semantic||semanticById.get(String(control.id))||''),
        expectedPixel:[Number(control.pixel[0]),Number(control.pixel[1])],
        mappedPixel:[mapped.x,mapped.y],
        errorPx:Math.hypot(dx,dy),
        water:contains(Number(control.lat),Number(control.lng))
      };
    });
    const fish=spec.fishway||{};
    return {
      version:String(spec.version),status:String(spec.status),width,height,
      waterDetectionOnly:true,controls,
      fishway:{lat:Number(fish.lat),lng:Number(fish.lng),water:contains(Number(fish.lat),Number(fish.lng))},
      overriddenFunctions:['calibratedWaterMaskValueAt','isKnownWater'],
      intentionallyUntouched:[
        'samplePhotoWaterCandidates','drawHeatmap','buildFluidBaseGrid',
        'makeShoreCastingHotspots','nearestHydroCorridor'
      ]
    };
  }

  const api={
    version:'stage8b-water-detection-only',
    specVersion:String(spec.version),
    specStatus:String(spec.status),
    width,height,rows,
    contains,containsImagePixel,latLngToImageXY,imageXYToLatLng,waterValue,
    install,diagnostics,previous,
    scope:{
      waterDetectionConnected:true,
      heatmapConnected:false,
      fluidConnected:false,
      standGenerationConnected:false
    }
  };

  global.ONGA_UNIFIED_WATER_DETECTION_STAGE8B=api;
  global.__ONGA_UNIFIED_WATER_DETECTION_STAGE8B_INSTALLED__=true;
  install();

  if(typeof document!=='undefined'&&typeof setTimeout==='function'){
    [120,400,1000,2500].forEach(delay=>setTimeout(install,delay));
  }
  if(typeof console!=='undefined'&&console.info){
    console.info('[onga-stage8b-water-detection]',diagnostics());
  }
})(typeof window!=='undefined'?window:globalThis);
