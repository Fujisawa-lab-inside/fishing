// v4.8.0 unified water domain from the user's annotated blue-water image.
// Authoritative rule:
// - Blue filled area is the only water surface.
// - Yellow bridge lines are bridges above the water; water remains connected under them.
// - Red line is the estuary barrage; it is treated as hydraulic infrastructure, not land.
// - Green line is the water/land boundary; fishing stands are sampled only on this boundary.
//
// Georeferencing:
// The image itself has no corner coordinates.  The raster is therefore registered with
// five user-provided control points: three bridge centers and two confluence land-tip points.
// The affine fit below has ~8.7 m RMS residual, which is logged in diagnostics.
(function installOngaUnifiedWaterDomainV480(){
  'use strict';
  if(window.__ONGA_UNIFIED_WATER_DOMAIN_V480__) return;
  window.__ONGA_UNIFIED_WATER_DOMAIN_V480__ = true;

  const VERSION='onga-unified-water-domain-v4.8.0';
  const REF={lat:33.892724,lng:130.674220};
  const COS_REF=Math.cos(REF.lat*Math.PI/180);
  const SRC={
    source:'user_annotated_blue_water_2026_07_08',
    originalWidth:2048,
    originalHeight:1232,
    maskWidth:1024,
    maskHeight:616,
    rowEncoding:'inclusive RLE intervals, [x0,x1,x0,x1,...] for each mask row',
    notes:'Blue area only. Bridge/barrage pixels were included as underlying water so they do not create artificial land gaps.'
  };
  const CONTROL_POINTS=[{"id":"bridge_1_center","label":"橋1中央","imageX":461.3,"imageY":317.6,"lat":33.89644444444444,"lng":130.66644444444445},{"id":"bridge_2_center","label":"橋2中央","imageX":976.8,"imageY":843.8,"lat":33.89055555555556,"lng":130.67305555555555},{"id":"bridge_3_center","label":"橋3中央","imageX":1504.9,"imageY":728,"lat":33.89183333333333,"lng":130.67969444444445},{"id":"nishi_onga_confluence_tip","label":"西川・遠賀川合流部の細長い地形先端","imageX":1004,"imageY":749,"lat":33.891666666666666,"lng":130.67325},{"id":"magari_onga_confluence_tip","label":"曲川・遠賀川合流部の細長い地形先端","imageX":1170,"imageY":441,"lat":33.894888888888886,"lng":130.6752222222222}];
  const CONTROL_RESIDUALS=[{"id":"bridge_1_center","label":"橋1中央","imageX":461.3,"imageY":317.6,"lat":33.89644444444444,"lng":130.66644444444445,"residualM":6.48,"residualEastM":-5.41,"residualNorthM":-3.56},{"id":"bridge_2_center","label":"橋2中央","imageX":976.8,"imageY":843.8,"lat":33.89055555555556,"lng":130.67305555555555,"residualM":6.18,"residualEastM":-1.96,"residualNorthM":5.86},{"id":"bridge_3_center","label":"橋3中央","imageX":1504.9,"imageY":728,"lat":33.89183333333333,"lng":130.67969444444445,"residualM":10.34,"residualEastM":-8.47,"residualNorthM":-5.93},{"id":"nishi_onga_confluence_tip","label":"西川・遠賀川合流部の細長い地形先端","imageX":1004,"imageY":749,"lat":33.891666666666666,"lng":130.67325,"residualM":9.03,"residualEastM":8.29,"residualNorthM":-3.57},{"id":"magari_onga_confluence_tip","label":"曲川・遠賀川合流部の細長い地形先端","imageX":1170,"imageY":441,"lat":33.894888888888886,"lng":130.6752222222222,"residualM":10.43,"residualEastM":7.55,"residualNorthM":7.2}];
  // image pixel [x,y,1] -> local meters [east,north] around REF.
  const IMAGE_TO_METERS=[[1.156830093692603,0.0342029059734513,-1268.416128996224],[-0.018278140617887443,-1.2012708197465595,797.6511163868391]];
  // local meters -> image pixel: img = METERS_TO_IMAGE_2X2 * ([east,north] - IMAGE_TO_METERS_OFFSET)
  const METERS_TO_IMAGE_2X2=[[0.8648202360806107,0.024623387142131834],[-0.013158815350933194,-0.8328264212369079]];
  const IMAGE_TO_METERS_OFFSET=[-1268.416128996224,797.6511163868391];
  const ROWS=[[],[],[],[],[],[],[31,89],[27,91],[24,94],[20,96],[16,98],[13,101],[9,103],[5,105],[2,107],[0,109],[0,112],[0,114],[0,116],[0,118],[0,121],[0,123],[0,125],[0,127],[0,130],[0,132],[0,134],[0,136],[0,138],[0,141],[0,143],[0,145],[0,147],[0,149],[0,151],[0,154],[0,156],[0,158],[0,160],[0,162],[0,164],[0,166],[0,169],[0,171],[0,173],[0,175],[0,178],[0,180],[0,182],[0,185],[0,187],[0,190],[0,192],[0,195],[0,198],[0,201],[0,204],[0,207],[0,211],[0,214],[0,217],[0,220],[0,224],[0,227],[0,231],[0,234],[0,238],[0,241],[0,245],[0,249],[0,252],[0,256],[0,260],[0,263],[0,267],[0,271],[0,275],[0,278],[0,282],[0,286],[0,289],[0,293],[0,296],[0,300],[0,304],[0,307],[0,311],[0,315],[0,318],[0,322],[0,326],[0,329],[0,333],[0,337],[0,340],[0,344],[0,347],[0,351],[0,355],[0,358],[0,362],[0,365],[0,369],[0,372],[0,375],[0,378],[0,382],[0,385],[0,388],[0,391],[0,394],[0,397],[0,400],[0,403],[0,405],[0,408],[0,411],[0,413],[0,416],[0,418],[0,421],[0,423],[0,425],[0,428],[0,430],[0,432],[0,434],[0,436],[0,437],[0,439],[0,441],[0,443],[0,445],[0,446],[0,448],[0,449],[0,451],[0,452],[0,454],[0,455],[0,457],[0,458],[0,459],[0,461],[0,462],[0,463],[0,465],[0,466],[0,467],[0,469],[0,470],[0,471],[0,473],[0,474],[0,475],[0,476],[0,478],[0,479],[0,480],[0,482],[0,483],[0,484],[0,486],[0,487],[0,488],[0,489],[0,491],[0,492],[0,493],[0,495],[0,496],[0,498],[0,499],[0,500],[0,502],[0,503],[0,505],[0,506],[0,507],[0,509],[0,510],[0,512],[0,513],[0,515],[0,516],[0,517],[0,519],[0,520],[0,522],[0,524],[0,525],[0,527],[0,528],[0,530],[0,532],[0,534],[0,535],[0,537],[0,539],[0,541],[0,543],[0,544],[0,546],[0,548],[0,550],[0,552],[0,554],[0,556],[0,558],[0,560],[0,562],[0,564],[0,566],[0,568],[0,570],[0,572],[0,574],[0,576],[0,578],[0,580],[0,582],[0,584],[0,586],[0,588],[0,590],[0,591],[0,593],[0,595],[0,597],[0,599],[0,601],[0,603],[0,605],[0,606],[0,608],[0,609],[0,611],[0,612],[0,613],[0,615],[0,616],[0,617],[0,619],[0,620],[0,621],[0,622],[0,623],[0,624],[0,625],[0,626],[0,627],[0,628],[0,629],[0,629,783,789],[0,630,783,789],[0,630,783,789],[0,631,783,789],[0,632,783,790],[0,632,783,790],[0,633,783,791],[0,634,783,791],[0,634,784,792],[0,635,784,793],[0,636,784,793],[0,637,785,794],[0,637,785,795],[0,638,786,796],[0,639,786,797],[0,640,787,798],[0,641,788,799],[0,641,789,800],[0,642,789,802],[0,643,790,803],[0,644,791,804],[0,645,792,806],[0,645,793,807],[0,646,794,809],[0,647,795,810],[0,648,796,812],[0,649,797,813],[0,650,798,815],[0,651,799,816],[0,652,800,818],[0,653,801,819],[0,654,802,821],[0,655,803,822],[0,656,805,824],[0,657,806,825],[0,658,807,827],[0,659,809,828],[0,660,810,830],[0,661,811,831],[0,662,812,833],[0,663,814,834],[0,665,815,836],[0,666,816,837],[0,667,818,839],[0,668,819,840],[0,669,821,842],[0,670,822,844],[0,672,824,845],[0,673,825,847],[0,674,827,849],[0,676,829,850],[0,677,830,852],[0,678,832,854],[0,680,833,856],[0,681,835,857],[0,682,837,859],[0,684,839,861],[0,685,841,863],[0,687,843,865],[0,688,845,867],[0,690,847,869],[0,691,849,871],[0,693,851,873],[0,694,853,875],[0,696,855,877],[0,697,857,879],[0,699,859,881],[0,700,861,883],[0,702,863,885],[0,704,865,887],[0,705,867,889],[0,707,869,891],[0,708,871,893],[0,710,873,895],[0,711,875,897],[0,713,877,899],[0,714,879,901],[0,716,881,903],[0,717,883,905],[0,719,885,907],[0,720,887,909],[0,722,889,911],[0,723,891,913],[0,724,893,915],[0,726,895,917],[0,727,897,919],[0,729,899,921],[0,730,901,923],[0,731,903,925],[0,733,905,927],[0,734,907,929],[0,735,909,930],[0,737,911,932],[0,738,913,934],[0,739,915,936],[0,741,917,938],[0,742,918,940],[0,743,920,941],[0,745,922,943],[0,746,924,945],[0,747,926,946],[0,749,927,948],[0,750,929,949],[0,751,931,951],[0,752,932,952],[0,754,934,953],[0,755,935,955],[0,756,937,956],[0,757,938,957],[0,759,940,958],[0,760,941,959],[0,761,942,960],[0,762,943,961],[0,763,945,962],[0,764,946,963],[0,766,947,964],[0,767,948,965],[0,768,949,966],[0,769,950,966],[0,769,951,967],[0,770,952,968],[0,771,953,968],[0,772,954,969],[0,773,955,969],[0,774,956,970],[0,775,957,970],[0,776,958,971],[0,777,959,971],[0,777,960,972],[0,778,960,972],[0,779,961,973],[0,780,962,973],[0,780,963,974],[0,781,963,974],[0,782,964,974],[0,783,965,975],[0,783,965,975],[0,784,966,976],[0,785,966,976],[0,785,967,976],[0,786,968,977],[0,787,968,977],[0,787,969,977],[0,788,969,978],[0,789,970,978],[0,789,970,978],[0,790,971,979],[0,790,971,979],[0,791,972,979],[0,792,972,980],[0,792,973,980],[0,793,973,981],[0,794,974,981],[0,794,975,981],[0,795,975,982],[0,796,976,982],[0,797,976,983],[0,797,977,983],[0,798,977,984],[0,799,978,984],[0,800,979,985],[0,800,979,985],[0,801,980,986],[0,802,981,986],[0,803,981,987],[0,804,982,987],[0,805,983,988],[0,806,984,988],[0,806,984,989],[0,807,985,989],[0,808,986,990],[0,809,987,990],[0,810,988,991],[0,811,989,991],[0,812,989,992],[0,813,990,993],[0,814,991,993],[0,815,992,994],[0,816,993,994],[0,816,994,995],[0,817,994,995],[0,818,995,996],[0,819,996,996],[0,820,997,997],[0,821,998,997],[0,822,999,998],[0,823,1000,998],[0,824,1001,999],[0,824,1002,999],[0,825,1003,1000],[0,826,1004,1000],[0,827,1005,1001],[0,828,1006,1001],[0,829,1007,1002],[0,830,1008,1002],[0,831,1009,1003],[0,832,1010,1004],[0,833,1011,1004],[0,834,1012,1005],[0,834,1013,1005],[0,835,1014,1006],[0,836,1015,1006],[0,837,1016,1007],[0,838,1017,1008],[0,839,1018,1008],[0,840,1019,1009],[0,841,1020,1009],[0,842,1021,1010],[0,843,1022,1010],[0,844,1023],[0,844,1023],[0,845,1023],[0,846,1023],[0,846,1023],[0,847,1023],[0,847,1023],[0,848,1023],[0,848,1023],[0,848,1023],[0,849,1023],[0,849,1023],[0,850,1023],[0,850,1023],[0,851,1023],[0,851,1023],[0,851,1023],[0,852,1023],[0,852,1023],[0,852,1023],[0,853,1023],[0,853,1023],[0,853,1023],[0,854,1023],[0,854,1023],[0,854,1023],[0,855,1023],[0,855,1023],[0,855,1023],[0,856,1023],[0,856,1023],[0,856,1023],[0,857,1023],[0,857,1023],[0,857,1023],[0,858,1023],[0,858,1023],[0,858,1023],[0,859,1023],[0,859,1023],[0,860,1023],[0,860,1023],[0,860,1023],[0,861,1023],[0,862,1023],[0,862,1023],[0,863,1023],[0,864,1023],[0,864,1023],[0,865,1023],[0,866,1023],[0,867,1023],[0,867,1023],[0,868,1023],[0,869,1023],[0,870,1023],[0,871,1023],[0,872,1023],[0,873,1023],[0,873,1023],[0,874,1023],[0,875,1023],[0,876,1023],[0,876,1023],[0,877,1023],[0,878,1023],[0,879,1023],[0,879,1023],[0,879,1023],[0,879,1023],[0,879,1023],[0,878,1023],[0,878,1023],[0,877,1023],[0,876,1023],[0,876,1023],[0,875,1023],[0,874,1023],[0,873,1023],[0,873,1023],[0,872,1023],[0,872,1023],[0,871,1023],[0,871,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,870,1023],[0,871,1023],[0,871,1023],[0,872,1023],[0,872,1023],[0,873,1023],[0,873,1023],[0,874,1023],[0,875,1023],[0,876,1023],[0,877,1023],[0,878,1023],[0,879,1023],[0,880,1023],[0,881,1023],[0,882,1023],[0,884,1023],[0,885,1023],[0,886,1023],[0,887,1023],[0,888,1023],[0,890,1023],[0,891,1023],[0,892,1023],[0,893,1023],[0,895,1023],[0,896,1023],[0,898,1023],[0,899,1023],[0,900,1023],[0,902,1023],[0,903,1023],[0,905,1023],[0,906,1023],[0,908,1023],[0,909,1023],[0,911,1023],[0,912,1023],[0,914,1023],[0,915,1023],[0,917,1023],[0,918,1023],[0,920,1023],[0,922,1023],[0,923,1023],[0,925,1023],[0,926,1023],[0,928,1023],[0,929,1023],[0,931,1023],[0,932,1023],[0,934,1023],[0,935,1023],[0,937,1023],[0,938,1023],[0,939,1023],[0,941,1023],[0,942,1023],[0,943,1023],[0,945,1023],[0,946,1023],[0,947,1023],[0,948,1023],[0,949,1023],[0,950,1023],[0,951,1023],[0,952,1023],[0,953,1023],[0,954,1023],[0,955,1023],[0,956,1023],[0,956,1023],[0,957,1023],[0,958,1023],[0,958,1023],[0,959,1023],[0,959,1023],[0,960,1023],[0,960,1023],[0,961,1023],[0,961,1023],[0,961,1023],[0,962,1023],[0,962,1023],[0,962,1023],[0,962,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,965,1023],[0,965,1023],[0,965,1023],[0,965,1023],[0,965,1023],[0,965,1023],[0,966,1023],[0,966,1023],[0,966,1023],[0,966,1023],[0,966,1023],[0,966,1023],[0,967,1023],[0,967,1023],[0,967,1023],[0,967,1023],[0,967,1023],[0,968,1023],[0,968,1023],[0,968,1023],[0,969,1023],[0,969,1023],[0,970,1023],[0,970,1023],[0,971,1023],[0,971,1023],[0,972,1023],[0,973,1023],[0,974,1023],[0,975,1023],[0,976,1023],[0,977,1023],[0,978,1023],[0,979,1023],[0,980,1023],[0,982,1023],[0,983,1023],[0,984,1023],[0,986,1023],[0,987,1023],[0,989,1023],[0,990,1023],[0,992,1023],[0,993,1023],[0,995,1023],[0,996,1023],[0,998,1023],[0,999,1023],[0,1001,1023],[0,1002,1023],[0,1003,1023],[0,1005,1023],[0,1006,1023],[0,1007,1023],[0,1009,1023],[0,1010,1023],[0,1011,1023],[0,1012,1023],[0,1013,1023],[0,1014,1023],[0,1016,1023],[0,1017,1023],[0,1018,1023],[0,1019,1023],[0,1020,1023],[0,1021,1023],[0,1022],[0,1022],[0,1021],[0,1021],[0,1020],[0,1020],[0,1019],[0,1019],[0,1018],[0,1018],[0,1017],[0,1017],[0,1016],[0,1016],[0,1015],[0,1015],[0,1014],[0,1014],[0,1013],[0,1013],[0,1012],[0,1012],[0,1011],[0,1011],[0,1010],[0,1009],[0,1009],[0,1008],[0,1007],[0,1007],[0,1006],[0,1005],[0,1005],[0,1004],[0,1003],[0,1002],[0,1001],[0,1000],[0,999],[0,998],[0,997],[0,996],[0,995],[0,994],[0,992],[0,991],[0,989],[0,988],[0,986],[0,985],[0,983],[0,981],[0,979],[0,977],[0,976],[0,974],[0,972],[0,970],[0,967],[0,965],[0,963],[0,961],[0,958],[0,956],[0,953],[0,950],[0,947],[0,944],[0,942],[0,939],[0,936],[0,933],[0,930],[0,927],[0,923],[0,920],[0,917],[0,914],[0,911],[0,908],[0,905],[0,902],[0,899],[0,896],[0,893],[0,890],[0,887],[0,884],[0,881],[0,878],[0,875],[0,871],[0,868],[0,865],[0,862],[0,859],[0,856],[0,853],[0,849],[0,846],[0,843],[0,840],[0,837],[0,834],[0,831],[0,828],[0,825],[0,821],[0,818],[0,815],[0,812],[0,809],[0,806],[0,802],[0,799],[0,796],[0,793],[0,790],[0,786],[0,783],[0,779],[0,776],[0,772],[0,768],[0,764],[0,760],[0,755],[0,750],[0,745],[0,740],[0,735],[0,730],[0,724],[0,719],[0,713],[0,708],[0,702],[0,696],[0,691],[0,685],[0,680],[0,674],[0,669],[0,663],[0,658],[0,652],[0,646],[0,641],[0,636],[0,630],[0,625],[0,620],[0,615],[0,610],[0,605],[0,600],[0,595],[0,590],[0,586],[0,581],[0,577],[0,573],[0,569],[0,565],[0,561],[0,557],[0,553],[0,550],[0,546],[0,543],[0,539],[0,535],[0,531],[0,527],[0,523],[0,519],[0,515],[0,511],[0,507],[0,503],[0,499],[0,495],[0,491],[0,487],[0,483],[0,479],[0,474],[0,470],[0,466],[0,462],[0,457],[0,453],[0,448],[0,444],[0,439],[0,435],[0,430],[0,425],[0,421],[0,416],[0,411],[0,406],[0,401],[0,396],[0,391],[0,386],[0,381],[0,376],[0,371],[0,366],[0,361],[0,356],[0,350],[0,345],[0,340],[0,335],[0,329],[0,324],[0,318],[0,313],[0,307],[0,301],[0,295],[0,290],[0,284],[0,278],[0,272],[0,265],[0,259],[0,253],[0,246],[0,240],[0,233],[0,227],[0,220],[0,214],[0,207],[0,201],[0,194],[0,187],[0,180],[0,173],[0,167],[0,160],[0,153],[0,146],[0,139],[0,132],[0,125],[0,118],[0,112],[0,105],[0,98],[0,91],[0,84],[0,77],[0,70],[0,63],[0,56],[0,49],[0,42],[0,35],[0,28],[0,22],[0,15],[0,8],[0,1]];

  const clampLocal=(typeof clamp==='function')?clamp:((v,a,b)=>Math.max(a,Math.min(b,v)));
  const toRad=d=>d*Math.PI/180;
  function llToMeters(lat,lng){return{x:(lng-REF.lng)*111320*COS_REF,y:(lat-REF.lat)*110540};}
  function metersToLL(x,y){return{lat:REF.lat+y/110540,lng:REF.lng+x/(111320*COS_REF)};}
  function imageToMeters(x,y){
    return {
      x:IMAGE_TO_METERS[0][0]*x+IMAGE_TO_METERS[0][1]*y+IMAGE_TO_METERS[0][2],
      y:IMAGE_TO_METERS[1][0]*x+IMAGE_TO_METERS[1][1]*y+IMAGE_TO_METERS[1][2]
    };
  }
  function imageXYToLatLng(x,y){const m=imageToMeters(x,y);return metersToLL(m.x,m.y);}
  function latLngToImageXY(lat,lng){
    const m=llToMeters(lat,lng);
    const dx=m.x-IMAGE_TO_METERS_OFFSET[0], dy=m.y-IMAGE_TO_METERS_OFFSET[1];
    return {
      x:METERS_TO_IMAGE_2X2[0][0]*dx+METERS_TO_IMAGE_2X2[0][1]*dy,
      y:METERS_TO_IMAGE_2X2[1][0]*dx+METERS_TO_IMAGE_2X2[1][1]*dy
    };
  }
  function imageToMaskXY(x,y){return{x:x*SRC.maskWidth/SRC.originalWidth,y:y*SRC.maskHeight/SRC.originalHeight};}
  function maskToImageXY(ix,iy){return{x:ix*SRC.originalWidth/SRC.maskWidth,y:iy*SRC.originalHeight/SRC.maskHeight};}
  function rowContains(ix,iy){
    if(iy<0||iy>=ROWS.length||ix<0||ix>=SRC.maskWidth)return false;
    const r=ROWS[iy]||[];
    for(let k=0;k<r.length;k+=2){if(ix<r[k])return false;if(ix<=r[k+1])return true;}
    return false;
  }
  function contains(lat,lng){
    if(!Number.isFinite(lat)||!Number.isFinite(lng))return false;
    const p=latLngToImageXY(lat,lng), q=imageToMaskXY(p.x,p.y);
    return rowContains(Math.floor(q.x),Math.floor(q.y));
  }
  function maskCellCenterLatLng(ix,iy){
    const p=maskToImageXY(ix+.5,iy+.5);
    return imageXYToLatLng(p.x,p.y);
  }

  let maskBits=null,boundarySamples=null,boundaryBins=null,maskCanvasCache=null;
  function ensureMaskBits(){
    if(maskBits)return maskBits;
    const bits=new Uint8Array(SRC.maskWidth*SRC.maskHeight);
    for(let y=0;y<SRC.maskHeight;y++){
      const r=ROWS[y]||[];
      for(let k=0;k<r.length;k+=2)for(let x=r[k];x<=r[k+1];x++)bits[y*SRC.maskWidth+x]=1;
    }
    maskBits=bits;return bits;
  }
  function ensureMaskCanvas(){
    if(maskCanvasCache)return maskCanvasCache;
    const c=document.createElement('canvas'); c.width=SRC.maskWidth; c.height=SRC.maskHeight;
    const ctx=c.getContext('2d'); ctx.fillStyle='rgba(255,255,255,1)';
    for(let y=0;y<SRC.maskHeight;y++){const r=ROWS[y]||[];for(let k=0;k<r.length;k+=2)ctx.fillRect(r[k],y,r[k+1]-r[k]+1,1);}
    maskCanvasCache=c;return c;
  }
  function isBoundaryCell(ix,iy,bits=ensureMaskBits()){
    const id=iy*SRC.maskWidth+ix;
    if(!bits[id])return false;
    return ix<=0||iy<=0||ix>=SRC.maskWidth-1||iy>=SRC.maskHeight-1||
      !bits[id-1]||!bits[id+1]||!bits[id-SRC.maskWidth]||!bits[id+SRC.maskWidth];
  }
  function buildBoundarySamples(){
    if(boundarySamples)return boundarySamples;
    const bits=ensureMaskBits(),out=[];
    const stride=2;
    for(let y=1;y<SRC.maskHeight-1;y+=stride){
      for(let x=1;x<SRC.maskWidth-1;x+=stride){
        if(!isBoundaryCell(x,y,bits))continue;
        const ll=maskCellCenterLatLng(x,y);
        if(typeof isWithinBounds==='function'&&!isWithinBounds(ll.lat,ll.lng))continue;
        const m=llToMeters(ll.lat,ll.lng);
        out.push({lat:ll.lat,lng:ll.lng,mx:m.x,my:m.y,ix:x,iy:y,onUnifiedBoundary:true});
      }
    }
    boundarySamples=out;
    boundaryBins=null;
    return out;
  }
  function buildBoundaryBins(){
    if(boundaryBins)return boundaryBins;
    const cell=80,bins=new Map();
    for(const s of buildBoundarySamples()){
      const bx=Math.floor(s.mx/cell), by=Math.floor(s.my/cell), key=bx+','+by;
      if(!bins.has(key))bins.set(key,[]);
      bins.get(key).push(s);
    }
    boundaryBins={cell,bins};
    return boundaryBins;
  }
  function nearestBoundaryStand(target){
    if(!target||!Number.isFinite(target.lat)||!Number.isFinite(target.lng)||!contains(target.lat,target.lng))return null;
    const maxM=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.maxM)||100;
    const preferredM=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.preferredM)||45;
    const tm=llToMeters(target.lat,target.lng), bb=buildBoundaryBins(), cell=bb.cell;
    const bx=Math.floor(tm.x/cell), by=Math.floor(tm.y/cell), span=Math.ceil((maxM+cell)/cell);
    let best=null;
    for(let yy=by-span;yy<=by+span;yy++)for(let xx=bx-span;xx<=bx+span;xx++){
      const arr=bb.bins.get(xx+','+yy); if(!arr)continue;
      for(const s of arr){
        const d=Math.hypot(s.mx-tm.x,s.my-tm.y);
        if(d<1.5||d>maxM)continue;
        if(window.ONGA_SPATIAL_SAFETY?.noStandAt?.(s.lat,s.lng))continue;
        if(window.ONGA_SPATIAL_SAFETY?.castBlock?.(s.lat,s.lng,target.lat,target.lng))continue;
        const pref=Math.exp(-.5*Math.pow((d-preferredM)/32,2));
        const reach=clampLocal(1-d/maxM,0,1);
        const score=(target.score||0)*(.72+.20*pref+.08*reach);
        if(!best||score>best.score)best={lat:s.lat,lng:s.lng,distanceM:d,bearing:0,landConfidence:1,bankQuality:1,onUnifiedBoundary:true,score};
      }
    }
    return best;
  }
  function drawCanvasMask(ctx,alpha=1){
    if(!ctx||typeof latLngToCanvas!=='function')return;
    ctx.save();ctx.globalAlpha*=alpha;ctx.fillStyle='rgba(255,255,255,1)';
    for(let y=0;y<SRC.maskHeight;y++){
      const r=ROWS[y]||[]; if(!r.length)continue;
      for(let k=0;k<r.length;k+=2){
        const a=maskToImageXY(r[k],y), b=maskToImageXY(r[k+1]+1,y+1);
        const ll1=imageXYToLatLng(a.x,a.y), ll2=imageXYToLatLng(b.x,a.y), ll3=imageXYToLatLng(b.x,b.y), ll4=imageXYToLatLng(a.x,b.y);
        const p1=latLngToCanvas(ll1.lat,ll1.lng),p2=latLngToCanvas(ll2.lat,ll2.lng),p3=latLngToCanvas(ll3.lat,ll3.lng),p4=latLngToCanvas(ll4.lat,ll4.lng);
        if((p1.x<-80&&p2.x<-80&&p3.x<-80&&p4.x<-80)||(p1.y<-80&&p2.y<-80&&p3.y<-80&&p4.y<-80)||(p1.x>state.width+80&&p2.x>state.width+80&&p3.x>state.width+80&&p4.x>state.width+80)||(p1.y>state.height+80&&p2.y>state.height+80&&p3.y>state.height+80&&p4.y>state.height+80))continue;
        ctx.beginPath();ctx.moveTo(p1.x,p1.y);ctx.lineTo(p2.x,p2.y);ctx.lineTo(p3.x,p3.y);ctx.lineTo(p4.x,p4.y);ctx.closePath();ctx.fill();
      }
    }
    ctx.restore();
  }
  function syntheticHydro(lat,lng,oldHydro=null){
    if(!contains(lat,lng))return null;
    if(oldHydro&&oldHydro.corridor>.01)return {...oldHydro,corridor:1,seed:Math.max(oldHydro.seed||0,1),unifiedWaterDomain:VERSION};
    let main={s:.5,signedDistancePx:0,distancePx:0};
    try{if(typeof nearestRiverProgress==='function')main=nearestRiverProgress(lat,lng)||main;}catch(e){}
    let widthPx=160;
    try{if(typeof modelWidthPixels==='function'&&typeof riverWidthAt==='function')widthPx=modelWidthPixels(riverWidthAt(main.s||.5),lat);}catch(e){}
    return {kind:'unified_water',label:'統一水面',s:clampLocal(main.s??.5,0,1),tributaryProgress:clampLocal(main.s??.5,0,1),signedDistancePx:Number.isFinite(main.signedDistancePx)?main.signedDistancePx:0,distancePx:Number.isFinite(main.distancePx)?main.distancePx:Math.abs(main.signedDistancePx||0),widthPx,maxDistPx:Math.max(widthPx*2.2,260),corridor:1,seed:1,unifiedWaterDomain:VERSION};
  }
  function cellToSample(ix,iy,step){
    const ll=maskCellCenterLatLng(ix,iy);
    if(typeof isWithinBounds==='function'&&!isWithinBounds(ll.lat,ll.lng))return null;
    if(!contains(ll.lat,ll.lng))return null;
    let old=null;try{if(window.__ONGA_PREV_NEAREST_HYDRO__)old=window.__ONGA_PREV_NEAREST_HYDRO__(ll.lat,ll.lng);}catch(e){}
    const hydro=syntheticHydro(ll.lat,ll.lng,old);
    let main={s:hydro?.s??.5,signedDistancePx:hydro?.signedDistancePx??0,distancePx:hydro?.distancePx??0};
    try{if(typeof nearestRiverProgress==='function')main=nearestRiverProgress(ll.lat,ll.lng)||main;}catch(e){}
    let widthPx=hydro?.widthPx||160;try{if(hydro?.kind==='main'||hydro?.kind==='unified_water')widthPx=modelWidthPixels(riverWidthAt(main.s),ll.lat);}catch(e){}
    const signed=(hydro&&hydro.kind!=='main'&&hydro.kind!=='unified_water')?hydro.signedDistancePx:main.signedDistancePx;
    const s=(hydro&&hydro.kind!=='main'&&hydro.kind!=='unified_water')?clampLocal((hydro.s??.05)+.22*(1-(hydro.tributaryProgress??1)),0,1):clampLocal(main.s??hydro?.s??.5,0,1);
    const p=(typeof latLngToCanvas==='function')?latLngToCanvas(ll.lat,ll.lng):{x:0,y:0};
    const mp=(typeof toModelPx==='function')?toModelPx(ll.lat,ll.lng):{x:ix,y:iy};
    return {lat:ll.lat,lng:ll.lng,x:p.x,y:p.y,gx:Math.round(ix/(step||1)),gy:Math.round(iy/(step||1)),s,cr:clampLocal((signed||0)/Math.max(1,widthPx/2),-1.75,1.75),photoWater:1,corridor:1,seed:1,nearestDistancePx:hydro?.distancePx??0,hydroKind:hydro?.kind||'unified_water',hydroLabel:hydro?.label||'統一水面',hydroProgress:hydro?.tributaryProgress??s,mx:mp.x,my:mp.y,unifiedWaterDomain:VERSION};
  }
  function unifiedWaterSamples(){
    const mode=(typeof state!=='undefined'&&state.performanceMode)||'practical';
    const step=mode==='validation'?5:mode==='balanced'?6:mode==='eco'?10:8;
    const key=[mode,step,SRC.maskWidth,SRC.maskHeight].join('|');
    if(window.__ONGA_UNIFIED_SAMPLE_CACHE__?.key===key){
      const cached=window.__ONGA_UNIFIED_SAMPLE_CACHE__.samples;
      state.waterMaskSamples=cached;state.waterMaskPoints=cached.slice(0,3600);return cached;
    }
    const out=[];
    for(let y=Math.floor(step/2);y<SRC.maskHeight;y+=step){
      const r=ROWS[y]||[];
      for(let k=0;k<r.length;k+=2){
        for(let x=r[k]+Math.floor(step/2);x<=r[k+1];x+=step){const p=cellToSample(x,y,step);if(p)out.push(p);}
      }
    }
    const b=buildBoundarySamples();
    for(let i=0;i<b.length;i+=4){
      const p=cellToSample(b[i].ix,b[i].iy,step);if(p)out.push({...p,onUnifiedBoundary:true});
    }
    if(typeof state!=='undefined'){
      state.waterMaskSamples=out;state.waterMaskPoints=out.slice(0,3600);
      state.photoSampleStatus=`統一水面: 青塗り正解マスク ${out.length}点 / 橋下連結 / 釣り座=水面・陸地境界線のみ`;
    }
    window.__ONGA_UNIFIED_SAMPLE_CACHE__={key,samples:out};
    return out;
  }
  function installWaterOverrides(){
    calibratedWaterMaskValueAt=function(lat,lng){return contains(lat,lng)?1:0;};
    if(typeof isKnownWater==='function')isKnownWater=function(lat,lng){return contains(lat,lng);};
    if(typeof nearestHydroCorridor==='function'&&nearestHydroCorridor!==window.__ONGA_UNIFIED_NEAREST_HYDRO__){
      window.__ONGA_PREV_NEAREST_HYDRO__=nearestHydroCorridor;
      window.__ONGA_UNIFIED_NEAREST_HYDRO__=function(lat,lng){let old=null;try{old=window.__ONGA_PREV_NEAREST_HYDRO__?window.__ONGA_PREV_NEAREST_HYDRO__(lat,lng):null;}catch(e){}return syntheticHydro(lat,lng,old);};
      nearestHydroCorridor=window.__ONGA_UNIFIED_NEAREST_HYDRO__;
    }
    if(typeof samplePhotoWaterCandidates==='function')samplePhotoWaterCandidates=unifiedWaterSamples;
    if(typeof drawWaterMask==='function')drawWaterMask=function(ctx){const t=document.getElementById('toggleWaterMask');if(t&&!t.checked)return;if(!ctx)return;ctx.save();ctx.globalAlpha=.24;ctx.fillStyle='rgba(91,212,255,1)';drawCanvasMask(ctx,1);ctx.restore();};
    if(typeof findLandCastPositionForWater==='function')findLandCastPositionForWater=nearestBoundaryStand;
    if(typeof makeShoreCastingHotspots==='function')makeShoreCastingHotspots=function(cands,n=8){
      const M=(typeof CAST_MODEL!=='undefined')?CAST_MODEL:{bankSepM:85,targetSepM:90};
      const sorted=[...(cands||[])].filter(p=>p&&Number.isFinite(p.score)&&p.score>.35&&contains(p.lat,p.lng)).sort((a,b)=>b.score-a.score),raw=[];
      for(const t of sorted.slice(0,1800)){
        const s=nearestBoundaryStand(t);if(!s)continue;
        raw.push({...t,lat:s.lat,lng:s.lng,targetLat:t.lat,targetLng:t.lng,targetScore:t.score,castDistanceM:s.distanceM,landConfidence:1,bankQuality:1,onLand:true,onUnifiedBoundary:true,score:clampLocal(s.score||t.score,0,1),structureName:`境界線釣り座：${t.structureName||t.hydroLabel||'水面標的'}`,reason:`青塗り水面の水面・陸地境界線 / ${Math.round(s.distanceM||0)}m先 / ${t.reason||''}`});
      }
      raw.sort((a,b)=>b.score-a.score);
      const chosen=[];
      for(const c of raw){let ok=true;for(const h of chosen){if(typeof haversine==='function'&&(haversine(c.lat,c.lng,h.lat,h.lng)<(M.bankSepM||85)||haversine(c.targetLat,c.targetLng,h.targetLat,h.targetLng)<(M.targetSepM||90))){ok=false;break;}}if(ok)chosen.push(c);if(chosen.length>=n)break;}
      return chosen.slice(0,n).map((h,i)=>({...h,rank:i+1,score100:Math.round((h.score||0)*100),targetScore100:Math.round((h.targetScore||h.score||0)*100),unifiedWaterDomain:VERSION}));
    };
    if(typeof drawHeatmap==='function')drawHeatmap=function(ctx){
      const toggle=document.getElementById('toggleHeat');if(toggle&&!toggle.checked)return;
      const pts=(state.heatPoints||[]).filter(p=>p&&contains(p.lat,p.lng));if(!pts.length)return;
      const scale=.58,W=Math.max(1,Math.ceil(state.width*scale)),H=Math.max(1,Math.ceil(state.height*scale)),field=new Float32Array(W*H);
      for(const p of pts){
        const s=clampLocal(Number.isFinite(p.heatScore)?p.heatScore:(Number.isFinite(p.score)?p.score:0),0,1);if(s<=.015)continue;
        const pt=latLngToCanvas(p.lat,p.lng);if(pt.x<-110||pt.y<-110||pt.x>state.width+110||pt.y>state.height+110)continue;
        const r=Math.max(5,(22+11*((state.zoom||16)-14))*(.70+s*.58)*scale),cx=pt.x*scale,cy=pt.y*scale,r2=r*r;
        const xmin=Math.max(0,Math.floor(cx-r)),xmax=Math.min(W-1,Math.ceil(cx+r)),ymin=Math.max(0,Math.floor(cy-r)),ymax=Math.min(H-1,Math.ceil(cy+r));
        for(let yy=ymin;yy<=ymax;yy++){const dy=yy-cy,dy2=dy*dy;for(let xx=xmin;xx<=xmax;xx++){const d2=(xx-cx)*(xx-cx)+dy2;if(d2>r2)continue;const q=1-d2/r2,v=s*q*q,id=yy*W+xx;if(v>field[id])field[id]=v;}}
      }
      const heat=document.createElement('canvas');heat.width=W;heat.height=H;const hctx=heat.getContext('2d'),img=hctx.createImageData(W,H),maxAlpha=clampLocal(state.baseOpacity||.15,0,.15);
      for(let i=0,j=0;i<field.length;i++,j+=4){const v=field[i];if(v<=.012){img.data[j+3]=0;continue;}const col=(typeof heatColor==='function')?heatColor(v):[0,160,255];img.data[j]=col[0];img.data[j+1]=col[1];img.data[j+2]=col[2];img.data[j+3]=Math.round(255*maxAlpha*clampLocal(.20+.80*v,0,1));}
      hctx.putImageData(img,0,0);
      const mask=document.createElement('canvas');mask.width=W;mask.height=H;const mctx=mask.getContext('2d');mctx.setTransform(scale,0,0,scale,0,0);drawCanvasMask(mctx,1);mctx.setTransform(1,0,0,1,0,0);
      hctx.globalCompositeOperation='destination-in';hctx.drawImage(mask,0,0);hctx.globalCompositeOperation='source-over';
      ctx.drawImage(heat,0,0,state.width,state.height);
    };
    if(typeof buildFishingModel==='function'&&buildFishingModel!==window.__ONGA_UNIFIED_BUILD_FISHING_MODEL__){
      const prevBuild=buildFishingModel;
      window.__ONGA_UNIFIED_BUILD_FISHING_MODEL__=function(){
        const model=prevBuild.apply(this,arguments);
        try{
          const samples=unifiedWaterSamples();
          if(model&&Array.isArray(model.points)){
            model.points=model.points.filter(p=>p&&contains(p.lat,p.lng));
            if(model.points.length<Math.min(80,samples.length)&&arguments.length>=5&&typeof scoreFishingSample==='function'&&typeof buildScoreEnvironment==='function'){
              const env=buildScoreEnvironment(arguments[0],arguments[1],arguments[2],arguments[3],arguments[4]);
              model.points=samples.map(s=>scoreFishingSample(s,env)).filter(p=>p&&Number.isFinite(p.score)&&contains(p.lat,p.lng));
            }
            if(typeof makeShoreCastingHotspots==='function')model.hotspots=makeShoreCastingHotspots(model.points,8);
          }
          model.unifiedWaterDomain=VERSION;
          if(typeof state!=='undefined'){state.waterMaskSamples=samples;state.waterMaskPoints=samples.slice(0,3600);state.unifiedWaterDomain=window.ONGA_UNIFIED_WATER_DOMAIN;state.photoSampleStatus='統一水面: 青塗り領域のみ / 橋下連結 / 釣り座=水面・陸地境界線';}
          if(typeof updateWaterStatus==='function')updateWaterStatus();
        }catch(e){console.warn('[unified water domain] build model patch failed',e);}
        return model;
      };
      buildFishingModel=window.__ONGA_UNIFIED_BUILD_FISHING_MODEL__;
    }
    if(typeof updateWaterStatus==='function'&&updateWaterStatus!==window.__ONGA_UNIFIED_UPDATE_WATER_STATUS__){
      const prevUpdate=updateWaterStatus;
      window.__ONGA_UNIFIED_UPDATE_WATER_STATUS__=function(){const r=prevUpdate.apply(this,arguments),el=document.getElementById('waterStatus');if(el)el.textContent='統一水面: 青塗り領域のみを唯一の水面 / 橋下連結 / 釣り座=水面・陸地境界線 / ヒート・流体・水面判定共通';return r;};
      updateWaterStatus=window.__ONGA_UNIFIED_UPDATE_WATER_STATUS__;
    }
    try{state.waterSampleCache?.clear?.();state.fluidCache?.clear?.();state.fluidBaseCache?.clear?.();state.validationCache?.clear?.();window.__ONGA_UNIFIED_SAMPLE_CACHE__=null;}catch(e){}
  }

  window.ONGA_UNIFIED_WATER_DOMAIN={version:VERSION,source:SRC,controlPoints:CONTROL_POINTS,controlResiduals:CONTROL_RESIDUALS,rows:ROWS,contains,drawCanvasMask,buildBoundarySamples,unifiedWaterSamples,nearestBoundaryStand,imageXYToLatLng,latLngToImageXY,installWaterOverrides};
  installWaterOverrides();
  [120,360,800,1600,3000].forEach(ms=>setTimeout(()=>{try{installWaterOverrides();if(typeof computeAndRender==='function'&&state?.timeline?.length)computeAndRender(true);else if(typeof renderAll==='function')renderAll();}catch(e){}},ms));
  try{const sub=document.querySelector('.sub');if(sub)sub.textContent='v4.8.0: 青塗り領域だけを唯一の正解水面として、水面判定・ヒートマップ・流体計算・釣り座境界を完全統一。橋下は連結、赤線は河口堰として扱います。';}catch(e){}
  console.info('[onga-unified-water-domain]',VERSION,{source:SRC,controlResiduals:CONTROL_RESIDUALS});
})();
