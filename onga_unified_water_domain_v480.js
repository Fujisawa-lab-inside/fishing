// v4.8.0 unified water domain from user annotated image.
// Rule encoded here:
// - Blue filled area is the only water surface.
// - Yellow bridge lines are over-water infrastructure; water remains connected below them.
// - Red line is the barrage, not land.
// - Green line is the water/land boundary; casting stands are sampled only from this boundary.
// The raster mask below was extracted from the supplied annotated image and downsampled to 1024x616.
// Coordinate registration assumes the image is the simulator's north-up GSI view centered on GSI.center at zoom 16.
(function installOngaUnifiedWaterDomainV480(){
  'use strict';
  if(window.__ONGA_UNIFIED_WATER_DOMAIN_V480__) return;
  window.__ONGA_UNIFIED_WATER_DOMAIN_V480__ = true;

  const VERSION = 'onga-unified-water-domain-v4.8.0';
  const SRC = {
    source: 'user_annotated_blue_water_2026_07_08',
    originalWidth: 2048,
    originalHeight: 1232,
    maskWidth: 1024,
    maskHeight: 616,
    zoom: 16,
    center: (typeof GSI !== 'undefined' && GSI.center) ? {lat:GSI.center.lat,lng:GSI.center.lng} : {lat:33.892800,lng:130.673077},
    notes: 'Blue mask is the single authoritative water domain. Yellow bridges and red barrage are treated as over-water/inside-water infrastructure, not shoreline.'
  };
  const ROWS = [[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[],[0,98],[0,100],[0,103],[0,104],[0,106],[0,108],[0,109],[0,111],[0,113],[0,116],[0,118],[0,120],[0,122],[0,123],[0,125],[0,128],[0,130],[0,132],[0,135],[0,137],[0,139],[0,141],[0,143],[0,145],[0,147],[0,149],[0,151],[0,154],[0,156],[0,158],[0,160],[0,162],[0,164],[0,166],[0,168],[0,170],[0,172],[0,174],[0,176],[0,178],[0,181],[0,183],[0,185],[0,187],[0,190],[0,193],[0,195],[0,198],[0,201],[0,204],[0,207],[0,210],[0,213],[0,217],[0,220],[0,223],[0,226],[0,230],[0,233],[0,237],[0,240],[0,244],[0,247],[0,251],[0,254],[0,258],[0,262],[0,265],[0,269],[0,273],[0,276],[0,280],[0,284],[0,288],[0,291],[0,295],[0,298],[0,302],[0,306],[0,309],[0,313],[0,317],[0,320],[0,324],[0,328],[0,331],[0,335],[0,339],[0,342],[0,346],[0,350],[0,353],[0,357],[0,361],[0,364],[0,368],[0,371],[0,375],[0,378],[0,381],[0,385],[0,388],[0,391],[0,394],[0,397],[0,400],[0,403],[0,406],[0,408],[0,411],[0,413],[0,416],[0,418],[0,420],[0,423],[0,425],[0,427],[0,429],[0,431],[0,433],[0,435],[0,437],[0,438],[0,440],[0,442],[0,443],[0,445],[0,446],[0,448],[0,449],[0,451],[0,452],[0,453],[0,455],[0,456],[0,457],[0,459],[0,460],[0,461],[0,463],[0,464],[0,465],[0,467],[0,468],[0,469],[0,471],[0,472],[0,473],[0,474],[0,476],[0,477],[0,478],[0,480],[0,481],[0,483],[0,484],[0,485],[0,487],[0,488],[0,489],[0,491],[0,492],[0,493],[0,495],[0,496],[0,497],[0,499],[0,500],[0,501],[0,503],[0,504],[0,505],[0,506],[0,507],[0,508],[0,510],[0,511],[0,512],[0,514],[0,515],[0,517],[0,518],[0,520],[0,521],[0,522],[0,524],[0,525],[0,526],[0,528],[0,529],[0,530],[0,531],[0,533],[0,534],[0,535],[0,537],[0,538],[0,540],[0,541],[0,543],[0,544],[0,546],[0,547],[0,549],[0,550],[0,552],[0,554],[0,556],[0,558],[0,559],[0,561],[0,563],[0,565],[0,567],[0,568],[0,570],[0,572],[0,574],[0,576],[0,577],[0,579],[0,581],[0,583],[0,585],[0,587],[0,589],[0,591],[0,593],[0,595],[0,597],[0,599],[0,601],[0,602],[0,604],[0,606],[0,608],[0,610],[0,612],[0,614],[0,616],[0,617],[0,619],[0,620],[0,621],[0,622],[0,624],[0,625],[0,626],[0,627],[0,628],[0,629],[0,629,784,789],[0,630,784,789],[0,630,783,789],[0,631,783,789],[0,632,783,790],[0,633,783,790],[0,633,783,791],[0,634,784,791],[0,635,784,792],[0,636,784,793],[0,637,785,793],[0,637,785,794],[0,638,786,795],[0,639,786,796],[0,639,787,797],[0,640,788,798],[0,641,788,799],[0,642,789,800],[0,642,790,801],[0,643,791,802],[0,644,791,803],[0,645,792,805],[0,646,793,806],[0,647,794,807],[0,647,795,809],[0,648,796,811],[0,649,797,812],[0,650,798,814],[0,651,799,815],[0,652,800,817],[0,653,801,818],[0,655,802,820],[0,656,803,821],[0,657,804,823],[0,658,805,824],[0,659,807,826],[0,660,808,827],[0,661,809,828],[0,662,810,830],[0,663,811,831],[0,664,813,832],[0,665,814,834],[0,667,815,835],[0,668,817,837],[0,669,818,838],[0,670,820,840],[0,671,821,841],[0,672,823,843],[0,674,824,845],[0,675,826,846],[0,676,828,848],[0,678,829,850],[0,679,831,851],[0,680,833,853],[0,682,835,855],[0,683,836,857],[0,684,838,859],[0,686,840,861],[0,687,842,862],[0,689,844,864],[0,690,846,866],[0,692,848,868],[0,693,850,870],[0,695,852,872],[0,696,854,874],[0,698,856,876],[0,699,858,878],[0,701,860,880],[0,702,862,882],[0,704,864,884],[0,705,866,886],[0,706,868,888],[0,708,870,890],[0,709,872,892],[0,711,874,894],[0,713,876,896],[0,714,878,898],[0,716,880,900],[0,717,882,902],[0,719,884,904],[0,720,886,906],[0,722,888,908],[0,723,890,910],[0,724,892,912],[0,726,894,914],[0,727,896,916],[0,729,898,918],[0,730,900,920],[0,731,902,922],[0,733,904,924],[0,734,906,926],[0,736,908,928],[0,737,910,930],[0,738,912,932],[0,740,913,934],[0,741,915,936],[0,742,917,937],[0,744,919,939],[0,745,921,941],[0,746,922,943],[0,748,924,944],[0,749,926,946],[0,750,928,947],[0,752,929,949],[0,753,931,950],[0,754,933,951],[0,755,934,953],[0,756,936,954],[0,758,937,955],[0,759,939,956],[0,760,940,957],[0,761,942,958],[0,762,943,959],[0,763,945,960],[0,765,946,961],[0,766,947,962],[0,767,949,963],[0,768,950,964],[0,769,951,965],[0,770,952,966],[0,771,953,966],[0,772,954,967],[0,773,955,968],[0,774,956,968],[0,774,957,969],[0,775,958,969],[0,776,959,970],[0,777,960,970],[0,778,961,971],[0,779,962,971],[0,779,963,972],[0,780,963,972],[0,781,964,973],[0,782,965,973],[0,782,966,974],[0,783,966,974],[0,784,967,974],[0,784,968,975],[0,785,968,975],[0,786,969,976],[0,786,970,976],[0,787,970,976],[0,788,971,977],[0,788,971,977],[0,789,972,977],[0,790,972,978],[0,790,973,978],[0,791,973,978],[0,792,974,979],[0,792,974,979],[0,793,975,979],[0,793,975,980],[0,794,976,980],[0,795,976,980],[0,795,977,981],[0,796,977,981],[0,797,978,982],[0,797,978,982],[0,798,979,982],[0,798,979,983],[0,799,980,983],[0,800,980,984],[0,800,981,984],[0,801,981,984],[0,802,982,985],[0,802,982,985],[0,803,983,986],[0,803,983,986],[0,804,984,987],[0,805,984,987],[0,805,985,988],[0,806,986,988],[0,807,986,989],[0,808,987,989],[0,809,987,990],[0,810,988,990],[0,811,989,991],[0,811,989,991],[0,812,990,992],[0,813,991,992],[0,814,991,993],[0,815,992,993],[0,816,993,994],[0,817,994,994],[0,817,995,995],[0,818,995,995],[0,819,996,996],[0,820,997,996],[0,821,998,997],[0,822,999,997],[0,823,999,998],[0,824,1000,998],[0,824,1001,999],[0,825,1002,999],[0,826,1003,1000],[0,827,1004,1000],[0,827,1005,1001],[0,828,1006,1001],[0,829,1007,1002],[0,830,1008,1002],[0,831,1009,1003],[0,832,1010,1003],[0,832,1011,1004],[0,833,1012,1004],[0,834,1013,1005],[0,835,1014,1005],[0,836,1015,1006],[0,837,1016,1006],[0,838,1017,1007],[0,839,1018,1008],[0,840,1019,1008],[0,841,1020,1009],[0,842,1020,1009],[0,842,1021,1010],[0,843,1022,1010],[0,844,1023],[0,844,1023],[0,845,1023],[0,846,1023],[0,846,1023],[0,847,1023],[0,847,1023],[0,848,1023],[0,848,1023],[0,848,1023],[0,849,1023],[0,849,1023],[0,850,1023],[0,850,1023],[0,850,1023],[0,851,1023],[0,851,1023],[0,851,1023],[0,852,1023],[0,852,1023],[0,852,1023],[0,852,1023],[0,853,1023],[0,853,1023],[0,853,1023],[0,854,1023],[0,854,1023],[0,854,1023],[0,854,1023],[0,855,1023],[0,855,1023],[0,855,1023],[0,855,1023],[0,856,1023],[0,856,1023],[0,856,1023],[0,857,1023],[0,857,1023],[0,857,1023],[0,858,1023],[0,858,1023],[0,858,1023],[0,859,1023],[0,859,1023],[0,859,1023],[0,860,1023],[0,860,1023],[0,861,1023],[0,861,1023],[0,862,1023],[0,862,1023],[0,863,1023],[0,864,1023],[0,864,1023],[0,865,1023],[0,866,1023],[0,866,1023],[0,867,1023],[0,868,1023],[0,869,1023],[0,870,1023],[0,871,1023],[0,872,1023],[0,872,1023],[0,873,1023],[0,874,1023],[0,875,1023],[0,876,1023],[0,876,1023],[0,877,1023],[0,878,1023],[0,879,1023],[0,879,1023],[0,879,1023],[0,879,1023],[0,878,1023],[0,878,1023],[0,877,1023],[0,876,1023],[0,875,1023],[0,874,1023],[0,874,1023],[0,873,1023],[0,872,1023],[0,872,1023],[0,871,1023],[0,871,1023],[0,870,1023],[0,870,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,870,1023],[0,870,1023],[0,871,1023],[0,871,1023],[0,872,1023],[0,873,1023],[0,874,1023],[0,875,1023],[0,876,1023],[0,877,1023],[0,878,1023],[0,879,1023],[0,880,1023],[0,881,1023],[0,883,1023],[0,884,1023],[0,885,1023],[0,886,1023],[0,888,1023],[0,889,1023],[0,890,1023],[0,891,1023],[0,892,1023],[0,894,1023],[0,895,1023],[0,896,1023],[0,897,1023],[0,898,1023],[0,900,1023],[0,901,1023],[0,902,1023],[0,904,1023],[0,905,1023],[0,906,1023],[0,908,1023],[0,909,1023],[0,911,1023],[0,912,1023],[0,914,1023],[0,915,1023],[0,917,1023],[0,918,1023],[0,919,1023],[0,921,1023],[0,922,1023],[0,924,1023],[0,925,1023],[0,927,1023],[0,928,1023],[0,930,1023],[0,931,1023],[0,932,1023],[0,934,1023],[0,935,1023],[0,936,1023],[0,938,1023],[0,939,1023],[0,940,1023],[0,941,1023],[0,943,1023],[0,944,1023],[0,945,1023],[0,946,1023],[0,947,1023],[0,948,1023],[0,949,1023],[0,950,1023],[0,951,1023],[0,951,1023],[0,952,1023],[0,953,1023],[0,954,1023],[0,954,1023],[0,955,1023],[0,956,1023],[0,956,1023],[0,957,1023],[0,957,1023],[0,958,1023],[0,958,1023],[0,959,1023],[0,959,1023],[0,960,1023],[0,960,1023],[0,960,1023],[0,961,1023],[0,961,1023],[0,961,1023],[0,961,1023],[0,962,1023],[0,962,1023],[0,962,1023],[0,962,1023],[0,962,1023],[0,962,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,965,1023],[0,965,1023],[0,965,1023],[0,966,1023],[0,966,1023],[0,967,1023],[0,967,1023],[0,968,1023],[0,969,1023],[0,970,1023],[0,971,1023],[0,972,1023],[0,973,1023],[0,974,1023],[0,975,1023],[0,977,1023],[0,978,1023],[0,980,1023],[0,981,1023],[0,982,1023],[0,984,1023],[0,985,1023],[0,987,1023],[0,988,1023],[0,990,1023],[0,991,1023],[0,993,1023],[0,994,1023],[0,996,1023],[0,997,1023],[0,999,1023],[0,1000,1023],[0,1001,1023],[0,1003,1023],[0,1004,1023],[0,1005,1023],[0,1006,1023],[0,1008,1023],[0,1009,1023],[0,1010,1023],[0,1011,1023],[0,1012,1023],[0,1013,1023],[0,1014,1023],[0,1015,1023],[0,1016,1023],[0,1017,1023],[0,1018,1023],[0,1019,1023],[0,1020,1023],[0,1021,1023],[0,1022],[0,1022],[0,1021],[0,1021],[0,1020],[0,1020],[0,1019],[0,1019],[0,1018],[0,1018],[0,1017],[0,1017],[0,1016],[0,1016],[0,1015],[0,1015],[0,1014],[0,1014],[0,1013],[0,1013],[0,1012],[0,1012],[0,1011],[0,1011],[0,1010],[0,1009],[0,1009],[0,1008],[0,1007],[0,1007],[0,1006],[0,1005],[0,1005],[0,1004],[0,1003],[0,1002],[0,1001],[0,1000],[0,999],[0,998],[0,997],[0,996],[0,995],[0,994],[0,992],[0,991],[0,989],[0,988],[0,986],[0,985],[0,983],[0,981],[0,979],[0,977],[0,976],[0,974],[0,972],[0,970],[0,967],[0,965],[0,963],[0,961],[0,958],[0,956],[0,953],[0,950],[0,947],[0,944],[0,942],[0,939],[0,936],[0,933],[0,930],[0,927],[0,923],[0,920],[0,917],[0,914],[0,911],[0,908],[0,905],[0,902],[0,899],[0,896],[0,893],[0,890],[0,887],[0,884],[0,881],[0,878],[0,875],[0,871],[0,868],[0,865],[0,862],[0,859],[0,856],[0,853],[0,849],[0,846],[0,843],[0,840],[0,837],[0,834],[0,831],[0,828],[0,825],[0,821],[0,818],[0,815],[0,812],[0,809],[0,806],[0,802],[0,799],[0,796],[0,793],[0,790],[0,786],[0,783],[0,779],[0,776],[0,772],[0,768],[0,764],[0,760],[0,755],[0,750],[0,745],[0,740],[0,735],[0,730],[0,724],[0,719],[0,713],[0,708],[0,702],[0,696],[0,691],[0,685],[0,680],[0,674],[0,669],[0,663],[0,658],[0,652],[0,646],[0,641],[0,636],[0,630],[0,625],[0,620],[0,615],[0,610],[0,605],[0,600],[0,595],[0,590],[0,586],[0,581],[0,577],[0,573],[0,569],[0,565],[0,561],[0,557],[0,553],[0,550],[0,546],[0,543],[0,539],[0,535],[0,531],[0,527],[0,523],[0,519],[0,515],[0,511],[0,507],[0,503],[0,499],[0,495],[0,491],[0,487],[0,483],[0,479],[0,474],[0,470],[0,466],[0,462],[0,457],[0,453],[0,448],[0,444],[0,439],[0,435],[0,430],[0,425],[0,421],[0,416],[0,411],[0,406],[0,401],[0,396],[0,391],[0,386],[0,381],[0,376],[0,371],[0,366],[0,361],[0,356],[0,350],[0,345],[0,340],[0,335],[0,329],[0,324],[0,318],[0,313],[0,307],[0,301],[0,295],[0,290],[0,284],[0,278],[0,272],[0,265],[0,259],[0,253],[0,246],[0,240],[0,233],[0,227],[0,220],[0,214],[0,207],[0,201],[0,194],[0,187],[0,180],[0,173],[0,167],[0,160],[0,153],[0,146],[0,139],[0,132],[0,125],[0,118],[0,112],[0,105],[0,98],[0,91],[0,84],[0,77],[0,70],[0,63],[0,56],[0,49],[0,42],[0,35],[0,28],[0,22],[0,15],[0,8],[0,1]];

  const clampLocal = (typeof clamp === 'function') ? clamp : ((v,a,b)=>Math.max(a,Math.min(b,v)));
  const toRadLocal = d => d*Math.PI/180;
  function worldSizeLocal(z){ return 256*Math.pow(2,z); }
  function projectLocal(lat,lng,z){
    if(typeof project === 'function') return project(lat,lng,z);
    const sin=Math.sin(toRadLocal(clampLocal(lat,-85.05112878,85.05112878))), size=worldSizeLocal(z);
    return {x:(lng+180)/360*size, y:(0.5-Math.log((1+sin)/(1-sin))/(4*Math.PI))*size};
  }
  function unprojectLocal(x,y,z){
    if(typeof unproject === 'function') return unproject(x,y,z);
    const size=worldSizeLocal(z), lng=x/size*360-180, n=Math.PI-2*Math.PI*y/size;
    return {lat:180/Math.PI*Math.atan(0.5*(Math.exp(n)-Math.exp(-n))), lng};
  }
  function refTopLeft(){
    const c=projectLocal(SRC.center.lat,SRC.center.lng,SRC.zoom);
    return {x:c.x-SRC.originalWidth/2, y:c.y-SRC.originalHeight/2};
  }
  function imageXY(lat,lng){
    const p=projectLocal(lat,lng,SRC.zoom), tl=refTopLeft();
    return {
      x:(p.x-tl.x)*SRC.maskWidth/SRC.originalWidth,
      y:(p.y-tl.y)*SRC.maskHeight/SRC.originalHeight
    };
  }
  function rowContains(ix,iy){
    if(iy<0 || iy>=ROWS.length || ix<0 || ix>=SRC.maskWidth) return false;
    const r=ROWS[iy] || [];
    for(let k=0;k<r.length;k+=2){
      if(ix<r[k]) return false;
      if(ix<=r[k+1]) return true;
    }
    return false;
  }
  function contains(lat,lng){
    if(!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
    const q=imageXY(lat,lng);
    return rowContains(Math.floor(q.x), Math.floor(q.y));
  }
  function imageCellCenterLatLng(ix,iy){
    const tl=refTopLeft();
    const wx=tl.x+(ix+.5)*SRC.originalWidth/SRC.maskWidth;
    const wy=tl.y+(iy+.5)*SRC.originalHeight/SRC.maskHeight;
    return unprojectLocal(wx,wy,SRC.zoom);
  }

  let maskBits=null, maskCanvas=null, boundarySamples=null;
  function ensureMaskBits(){
    if(maskBits) return maskBits;
    const bits=new Uint8Array(SRC.maskWidth*SRC.maskHeight);
    for(let y=0;y<SRC.maskHeight;y++){
      const r=ROWS[y] || [];
      for(let k=0;k<r.length;k+=2){
        for(let x=r[k]; x<=r[k+1]; x++) bits[y*SRC.maskWidth+x]=1;
      }
    }
    maskBits=bits;
    return bits;
  }
  function ensureMaskCanvas(){
    if(maskCanvas) return maskCanvas;
    const c=document.createElement('canvas');
    c.width=SRC.maskWidth; c.height=SRC.maskHeight;
    const ctx=c.getContext('2d');
    ctx.fillStyle='rgba(255,255,255,1)';
    for(let y=0;y<SRC.maskHeight;y++){
      const r=ROWS[y] || [];
      for(let k=0;k<r.length;k+=2) ctx.fillRect(r[k],y,r[k+1]-r[k]+1,1);
    }
    maskCanvas=c;
    return c;
  }
  function drawCanvasMask(ctx, alpha=1){
    if(!ctx || typeof state === 'undefined' || typeof topLeftPx !== 'function') return;
    const c=ensureMaskCanvas();
    const currentTopLeft=topLeftPx();
    const tl=refTopLeft();
    const zoomScale=Math.pow(2,(state.zoom ?? SRC.zoom)-SRC.zoom);
    const dx=tl.x*zoomScale-currentTopLeft.x;
    const dy=tl.y*zoomScale-currentTopLeft.y;
    const dw=SRC.originalWidth*zoomScale;
    const dh=SRC.originalHeight*zoomScale;
    ctx.save();
    ctx.globalAlpha*=alpha;
    ctx.imageSmoothingEnabled=false;
    ctx.drawImage(c,dx,dy,dw,dh);
    ctx.restore();
  }
  function isBoundaryCell(ix,iy,bits=ensureMaskBits()){
    const id=iy*SRC.maskWidth+ix;
    if(!bits[id]) return false;
    return ix===0 || iy===0 || ix===SRC.maskWidth-1 || iy===SRC.maskHeight-1 ||
      !bits[id-1] || !bits[id+1] || !bits[id-SRC.maskWidth] || !bits[id+SRC.maskWidth];
  }
  function buildBoundarySamples(){
    if(boundarySamples) return boundarySamples;
    const bits=ensureMaskBits(), out=[];
    const stride=2;
    for(let y=1;y<SRC.maskHeight-1;y+=stride){
      for(let x=1;x<SRC.maskWidth-1;x+=stride){
        if(!isBoundaryCell(x,y,bits)) continue;
        const ll=imageCellCenterLatLng(x,y);
        if(typeof isWithinBounds === 'function' && !isWithinBounds(ll.lat,ll.lng)) continue;
        out.push({lat:ll.lat,lng:ll.lng,ix:x,iy:y,onUnifiedBoundary:true});
      }
    }
    boundarySamples=out;
    return out;
  }
  function nearestBoundaryStand(target){
    if(!target || !Number.isFinite(target.lat) || !Number.isFinite(target.lng)) return null;
    const maxM=(typeof CAST_MODEL !== 'undefined' && CAST_MODEL.maxM) ? CAST_MODEL.maxM : 100;
    const preferredM=(typeof CAST_MODEL !== 'undefined' && CAST_MODEL.preferredM) ? CAST_MODEL.preferredM : 45;
    const samples=buildBoundarySamples();
    let best=null;
    for(const s of samples){
      if(typeof haversine !== 'function') continue;
      const d=haversine(s.lat,s.lng,target.lat,target.lng);
      if(d<1.5 || d>maxM) continue;
      if(window.ONGA_SPATIAL_SAFETY?.noStandAt?.(s.lat,s.lng)) continue;
      if(window.ONGA_SPATIAL_SAFETY?.castBlock?.(s.lat,s.lng,target.lat,target.lng)) continue;
      const pref=Math.exp(-.5*Math.pow((d-preferredM)/32,2));
      const reach=clampLocal(1-d/maxM,0,1);
      const score=(target.score||0)*(.72+.20*pref+.08*reach);
      if(!best || score>best.score) best={lat:s.lat,lng:s.lng,distanceM:d,bearing:0,landConfidence:1,bankQuality:1,onUnifiedBoundary:true,score};
    }
    return best;
  }
  function syntheticHydro(lat,lng,oldHydro=null){
    if(!contains(lat,lng)) return null;
    if(oldHydro && oldHydro.corridor>.01) return oldHydro;
    let main={s:.5,signedDistancePx:0,distancePx:0};
    try{ if(typeof nearestRiverProgress === 'function') main=nearestRiverProgress(lat,lng)||main; }catch(e){}
    let widthPx=160;
    try{ if(typeof modelWidthPixels === 'function' && typeof riverWidthAt === 'function') widthPx=modelWidthPixels(riverWidthAt(main.s||.5),lat); }catch(e){}
    return {
      kind:'unified_water',
      label:'統一水面',
      s:clampLocal(main.s ?? .5,0,1),
      tributaryProgress:clampLocal(main.s ?? .5,0,1),
      signedDistancePx:Number.isFinite(main.signedDistancePx)?main.signedDistancePx:0,
      distancePx:Number.isFinite(main.distancePx)?main.distancePx:Math.abs(main.signedDistancePx||0),
      widthPx,
      maxDistPx:Math.max(widthPx*2.2,260),
      corridor:1,
      seed:1,
      unifiedWaterDomain:VERSION
    };
  }
  function pointFromMaskCell(ix,iy,canvasStep){
    const ll=imageCellCenterLatLng(ix,iy);
    if(typeof isWithinBounds === 'function' && !isWithinBounds(ll.lat,ll.lng)) return null;
    if(!contains(ll.lat,ll.lng)) return null;
    const mp=(typeof toModelPx === 'function') ? toModelPx(ll.lat,ll.lng) : {x:ix,y:iy};
    let hydro=null;
    try{
      if(typeof window.__ONGA_PREV_NEAREST_HYDRO__ === 'function') hydro=window.__ONGA_PREV_NEAREST_HYDRO__(ll.lat,ll.lng);
      else if(typeof nearestHydroCorridor === 'function') hydro=nearestHydroCorridor(ll.lat,ll.lng);
    }catch(e){ hydro=null; }
    hydro=syntheticHydro(ll.lat,ll.lng,hydro);
    let main={s:hydro?.s ?? .5,signedDistancePx:hydro?.signedDistancePx ?? 0,distancePx:hydro?.distancePx ?? 0};
    try{ if(typeof nearestRiverProgress === 'function') main=nearestRiverProgress(ll.lat,ll.lng)||main; }catch(e){}
    let widthPx=hydro?.widthPx || 160;
    try{ if(hydro?.kind==='main' || hydro?.kind==='unified_water') widthPx=modelWidthPixels(riverWidthAt(main.s),ll.lat); }catch(e){}
    const signed=(hydro && hydro.kind!=='main' && hydro.kind!=='unified_water') ? hydro.signedDistancePx : main.signedDistancePx;
    const s=(hydro && hydro.kind!=='main' && hydro.kind!=='unified_water') ? clampLocal((hydro.s ?? .05)+.22*(1-(hydro.tributaryProgress ?? 1)),0,1) : clampLocal(main.s ?? hydro?.s ?? .5,0,1);
    let cxy={x:0,y:0};
    try{ if(typeof latLngToCanvas === 'function') cxy=latLngToCanvas(ll.lat,ll.lng); }catch(e){}
    return {
      lat:ll.lat,lng:ll.lng,x:cxy.x,y:cxy.y,
      gx:Math.round(ix/(canvasStep||1)),gy:Math.round(iy/(canvasStep||1)),
      s,
      cr:clampLocal((signed||0)/Math.max(1,widthPx/2),-1.75,1.75),
      photoWater:1,
      corridor:1,
      seed:1,
      nearestDistancePx:hydro?.distancePx ?? 0,
      hydroKind:hydro?.kind || 'unified_water',
      hydroLabel:hydro?.label || '統一水面',
      hydroProgress:hydro?.tributaryProgress ?? s,
      mx:mp.x,my:mp.y,
      unifiedWaterDomain:VERSION
    };
  }
  function unifiedWaterSamples(){
    const mode=(typeof state !== 'undefined' && state.performanceMode) ? state.performanceMode : 'practical';
    const step = mode==='validation' ? 6 : mode==='balanced' ? 7 : mode==='eco' ? 11 : 8;
    const key=[mode,step,(typeof state!=='undefined'?state.zoom:'z'),SRC.maskWidth,SRC.maskHeight].join('|');
    if(window.__ONGA_UNIFIED_SAMPLE_CACHE__?.key===key){
      const cached=window.__ONGA_UNIFIED_SAMPLE_CACHE__.samples;
      state.waterMaskSamples=cached;
      state.waterMaskPoints=cached.slice(0,3600);
      return cached;
    }
    const out=[];
    for(let y=Math.floor(step/2); y<SRC.maskHeight; y+=step){
      const r=ROWS[y] || [];
      for(let k=0;k<r.length;k+=2){
        const start=r[k]+Math.floor(step/2);
        for(let x=start; x<=r[k+1]; x+=step){
          const p=pointFromMaskCell(x,y,step);
          if(p) out.push(p);
        }
      }
    }
    // Add a lighter boundary representation so shoreline/bridge/barrage edges remain represented in heat clipping and diagnostics.
    for(const b of buildBoundarySamples().filter((_,i)=>i%4===0)){
      const q=imageXY(b.lat,b.lng);
      const p=pointFromMaskCell(Math.round(q.x),Math.round(q.y),step);
      if(p) out.push({...p,onUnifiedBoundary:true});
    }
    if(typeof state !== 'undefined'){
      state.waterMaskSamples=out;
      state.waterMaskPoints=out.slice(0,3600);
      state.photoSampleStatus=`統一水面: 青塗り正解マスク ${out.length}点 / 橋下連結 / 釣り座=水面・陸地境界線のみ`;
    }
    window.__ONGA_UNIFIED_SAMPLE_CACHE__={key,samples:out};
    return out;
  }
  function installWaterOverrides(){
    if(!window.ONGA_UNIFIED_WATER_DOMAIN) {
      window.ONGA_UNIFIED_WATER_DOMAIN={version:VERSION,source:SRC,rows:ROWS,contains,drawCanvasMask,buildBoundarySamples,unifiedWaterSamples,nearestBoundaryStand};
    }
    calibratedWaterMaskValueAt=function(lat,lng){ return contains(lat,lng) ? 1 : 0; };
    if(typeof isKnownWater === 'function') isKnownWater=function(lat,lng){ return contains(lat,lng); };
    if(typeof nearestHydroCorridor === 'function' && nearestHydroCorridor !== window.__ONGA_UNIFIED_NEAREST_HYDRO__){
      window.__ONGA_PREV_NEAREST_HYDRO__ = nearestHydroCorridor;
      window.__ONGA_UNIFIED_NEAREST_HYDRO__ = function(lat,lng){
        const prev=window.__ONGA_PREV_NEAREST_HYDRO__;
        let old=null;
        try{ old=prev ? prev(lat,lng) : null; }catch(e){ old=null; }
        return syntheticHydro(lat,lng,old);
      };
      nearestHydroCorridor = window.__ONGA_UNIFIED_NEAREST_HYDRO__;
    }
    if(typeof samplePhotoWaterCandidates === 'function') samplePhotoWaterCandidates=unifiedWaterSamples;
    if(typeof drawWaterMask === 'function'){
      drawWaterMask=function(ctx){
        if(typeof document !== 'undefined' && document.getElementById('toggleWaterMask') && !document.getElementById('toggleWaterMask').checked) return;
        if(!ctx) return;
        ctx.save();
        ctx.globalAlpha=.24;
        ctx.fillStyle='rgba(91,212,255,1)';
        drawCanvasMask(ctx,1);
        ctx.restore();
      };
    }
    if(typeof findLandCastPositionForWater === 'function') findLandCastPositionForWater=nearestBoundaryStand;
    if(typeof makeShoreCastingHotspots === 'function'){
      makeShoreCastingHotspots=function(cands,n=8){
        const M=(typeof CAST_MODEL !== 'undefined') ? CAST_MODEL : {bankSepM:85,targetSepM:90};
        const sorted=[...(cands||[])].filter(p=>p&&Number.isFinite(p.score)&&p.score>.35&&contains(p.lat,p.lng)).sort((a,b)=>b.score-a.score);
        const raw=[];
        for(const t of sorted.slice(0,1800)){
          const s=nearestBoundaryStand(t);
          if(!s) continue;
          raw.push({...t,lat:s.lat,lng:s.lng,targetLat:t.lat,targetLng:t.lng,targetScore:t.score,castDistanceM:s.distanceM,landConfidence:1,bankQuality:1,onLand:true,onUnifiedBoundary:true,score:clampLocal(s.score||t.score,0,1),structureName:`境界線釣り座：${t.structureName||t.hydroLabel||'水面標的'}`,reason:`青塗り水面の水面・陸地境界線 / ${Math.round(s.distanceM||0)}m先 / ${t.reason||''}`});
        }
        raw.sort((a,b)=>b.score-a.score);
        const chosen=[];
        for(const c of raw){
          let ok=true;
          for(const h of chosen){
            if(typeof haversine === 'function' && (haversine(c.lat,c.lng,h.lat,h.lng)<(M.bankSepM||85) || haversine(c.targetLat,c.targetLng,h.targetLat,h.targetLng)<(M.targetSepM||90))){ ok=false; break; }
          }
          if(ok) chosen.push(c);
          if(chosen.length>=n) break;
        }
        return chosen.slice(0,n).map((h,i)=>({...h,rank:i+1,score100:Math.round((h.score||0)*100),targetScore100:Math.round((h.targetScore||h.score||0)*100),unifiedWaterDomain:VERSION}));
      };
    }
    if(typeof drawHeatmap === 'function'){
      drawHeatmap=function(ctx){
        const toggle=document.getElementById('toggleHeat'); if(toggle && !toggle.checked) return;
        const pts=(state.heatPoints||[]).filter(p=>p&&contains(p.lat,p.lng));
        if(!pts.length) return;
        const heat=document.createElement('canvas'), scale=.58;
        const W=Math.max(1,Math.ceil(state.width*scale)), H=Math.max(1,Math.ceil(state.height*scale));
        heat.width=W; heat.height=H;
        const hctx=heat.getContext('2d');
        const field=new Float32Array(W*H);
        for(const p of pts){
          const s=clampLocal(Number.isFinite(p.heatScore)?p.heatScore:(Number.isFinite(p.score)?p.score:0),0,1);
          if(s<=.015) continue;
          const pt=latLngToCanvas(p.lat,p.lng);
          if(pt.x<-110||pt.y<-110||pt.x>state.width+110||pt.y>state.height+110) continue;
          const baseR=(22+11*((state.zoom||16)-14))*(0.70+s*.58);
          const r=Math.max(5,baseR*scale), cx=pt.x*scale, cy=pt.y*scale;
          const xmin=Math.max(0,Math.floor(cx-r)), xmax=Math.min(W-1,Math.ceil(cx+r));
          const ymin=Math.max(0,Math.floor(cy-r)), ymax=Math.min(H-1,Math.ceil(cy+r)), r2=r*r;
          for(let yy=ymin; yy<=ymax; yy++){
            const dy=yy-cy, dy2=dy*dy;
            for(let xx=xmin; xx<=xmax; xx++){
              const d2=(xx-cx)*(xx-cx)+dy2; if(d2>r2) continue;
              const q=1-d2/r2, v=s*q*q, id=yy*W+xx; if(v>field[id]) field[id]=v;
            }
          }
        }
        const img=hctx.createImageData(W,H);
        const maxAlpha=clampLocal(state.baseOpacity||.15,0,.15);
        for(let i=0,j=0;i<field.length;i++,j+=4){
          const v=field[i]; if(v<=.012){ img.data[j+3]=0; continue; }
          const col=(typeof heatColor === 'function') ? heatColor(v) : [0,160,255];
          img.data[j]=col[0]; img.data[j+1]=col[1]; img.data[j+2]=col[2];
          img.data[j+3]=Math.round(255*maxAlpha*clampLocal(.20+.80*v,0,1));
        }
        hctx.putImageData(img,0,0);
        const mask=document.createElement('canvas'); mask.width=W; mask.height=H;
        const mctx=mask.getContext('2d');
        mctx.setTransform(scale,0,0,scale,0,0);
        drawCanvasMask(mctx,1);
        mctx.setTransform(1,0,0,1,0,0);
        hctx.globalCompositeOperation='destination-in'; hctx.drawImage(mask,0,0); hctx.globalCompositeOperation='source-over';
        ctx.drawImage(heat,0,0,state.width,state.height);
      };
    }
    if(typeof buildFishingModel === 'function' && buildFishingModel !== window.__ONGA_UNIFIED_BUILD_FISHING_MODEL__){
      const prevBuild=buildFishingModel;
      window.__ONGA_UNIFIED_BUILD_FISHING_MODEL__=function(){
        const model=prevBuild.apply(this,arguments);
        try{
          const samples=unifiedWaterSamples();
          if(model && Array.isArray(model.points)){
            model.points=model.points.filter(p=>p&&contains(p.lat,p.lng));
            // Make sure the authoritative water samples are represented even when older scoring layers sampled less densely.
            if(model.points.length<Math.min(80,samples.length) && arguments.length>=5 && typeof scoreFishingSample === 'function' && typeof buildScoreEnvironment === 'function'){
              const env=buildScoreEnvironment(arguments[0],arguments[1],arguments[2],arguments[3],arguments[4]);
              model.points=samples.map(s=>scoreFishingSample(s,env)).filter(p=>p&&Number.isFinite(p.score)&&contains(p.lat,p.lng));
            }
            if(typeof makeShoreCastingHotspots === 'function') model.hotspots=makeShoreCastingHotspots(model.points,8);
          }
          model.unifiedWaterDomain=VERSION;
          if(typeof state !== 'undefined'){
            state.waterMaskSamples=samples;
            state.waterMaskPoints=samples.slice(0,3600);
            state.unifiedWaterDomain=window.ONGA_UNIFIED_WATER_DOMAIN;
            state.photoSampleStatus=`統一水面: 青塗り領域のみ / 橋下連結 / 釣り座=水面・陸地境界線`;
          }
          if(typeof updateWaterStatus === 'function') updateWaterStatus();
        }catch(e){ console.warn('[unified water domain] build model patch failed',e); }
        return model;
      };
      buildFishingModel=window.__ONGA_UNIFIED_BUILD_FISHING_MODEL__;
    }
    if(typeof updateWaterStatus === 'function' && updateWaterStatus !== window.__ONGA_UNIFIED_UPDATE_WATER_STATUS__){
      const prevUpdate=updateWaterStatus;
      window.__ONGA_UNIFIED_UPDATE_WATER_STATUS__=function(){
        const r=prevUpdate.apply(this,arguments);
        const el=document.getElementById('waterStatus');
        if(el) el.textContent='統一水面: 青塗り領域のみを唯一の水面 / 橋下連結 / 釣り座=水面・陸地境界線 / ヒート・流体・水面判定共通';
        return r;
      };
      updateWaterStatus=window.__ONGA_UNIFIED_UPDATE_WATER_STATUS__;
    }
    try{
      state.waterSampleCache?.clear?.();
      state.fluidCache?.clear?.();
      state.fluidBaseCache?.clear?.();
      state.validationCache?.clear?.();
      window.__ONGA_UNIFIED_SAMPLE_CACHE__=null;
    }catch(e){}
  }

  window.ONGA_UNIFIED_WATER_DOMAIN={version:VERSION,source:SRC,rows:ROWS,contains,drawCanvasMask,buildBoundarySamples,unifiedWaterSamples,nearestBoundaryStand,installWaterOverrides};
  installWaterOverrides();
  // Geometry patches are asynchronous; reinstall several times so the unified domain remains the final authority.
  [120,360,800,1600,3000].forEach(ms=>setTimeout(()=>{try{installWaterOverrides(); if(typeof computeAndRender==='function'&&state?.timeline?.length) computeAndRender(true); else if(typeof renderAll==='function') renderAll();}catch(e){}},ms));
  try{
    const sub=document.querySelector('.sub');
    if(sub) sub.textContent='v4.8.0: 青塗り領域だけを唯一の正解水面として、水面判定・ヒートマップ・流体計算・釣り座境界を完全統一。橋下は連結、赤線は河口堰として扱います。';
  }catch(e){}
  console.info('[onga-unified-water-domain]',VERSION,SRC);
})();
