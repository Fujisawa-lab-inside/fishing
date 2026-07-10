// v4.8.0 final unified-water-domain override.
// Approved specification:
// - The user-painted blue region is the only water domain.
// - Water detection, heat-map clipping/evaluation, and fluid water cells use the same predicate.
// - Bridges and the barrage are separate infrastructure layers and never cut the water domain.
// - Fishing stands are sampled only from the approved green water/land boundary.
// - The mouth and three upstream image-edge runs are open hydraulic boundaries.
// - Four interior reference sections are undirected: no fixed flow sign or long axis is stored.
// - Fishway centre is 33°53'20.8"N 130°40'28.5"E, NE 45°, influence clipped to water,
//   with no fishway-specific no-stand radius.
(function installOngaUnifiedWaterDomainV480Final(){
  'use strict';
  const VERSION='onga-unified-water-domain-v4.8.0-final';
  if(window.__ONGA_UNIFIED_WATER_DOMAIN_V480_FINAL__===VERSION)return;
  window.__ONGA_UNIFIED_WATER_DOMAIN_V480_FINAL__=VERSION;

  const SRC={
    source:'user_annotated_blue_water_2026_07_08_approved',
    originalWidth:2048,
    originalHeight:1232,
    maskWidth:1024,
    maskHeight:616,
    cellScaleX:2,
    cellScaleY:2,
    rowEncoding:'inclusive RLE intervals',
    connectedComponents:1,
    openBoundaryCount:4
  };
  const WM={"tx":34582567.905470334,"ty":16022157.024852829,"a":1.427196114711001,"b":0.01827140836003607,"circumference":40075016.68557849};
  const CONTROL_POINTS=[{"id":"bridge_1_center","label":"橋1中央","imageX":465,"imageY":314,"lat":33.89644444444444,"lng":130.66644444444444},{"id":"bridge_2_center","label":"橋2中央","imageX":982,"imageY":847,"lat":33.89055555555556,"lng":130.67305555555555},{"id":"bridge_3_center","label":"橋3中央","imageX":1505,"imageY":728,"lat":33.89183333333333,"lng":130.67969444444444},{"id":"nishi_onga_confluence_tip","label":"西川・遠賀川合流部先端","imageX":1005,"imageY":748,"lat":33.891666666666666,"lng":130.67325},{"id":"magari_onga_confluence_tip","label":"曲川・遠賀川合流部先端","imageX":1168,"imageY":441,"lat":33.894888888888886,"lng":130.6752222222222}];
  const CONTROL_RESIDUALS=[{"id":"bridge_1_center","residualM":9.759},{"id":"bridge_2_center","residualM":12.619},{"id":"bridge_3_center","residualM":3.039},{"id":"nishi_onga_confluence_tip","residualM":0.72},{"id":"magari_onga_confluence_tip","residualM":16.289}];
  const WATER_ROWS=[[31,89],[27,91],[24,94],[20,96],[16,98],[13,101],[9,103],[5,105],[2,107],[0,109],[0,112],[0,114],[0,116],[0,118],[0,121],[0,123],[0,125],[0,127],[0,130],[0,132],[0,134],[0,136],[0,138],[0,141],[0,143],[0,145],[0,147],[0,149],[0,151],[0,154],[0,156],[0,158],[0,160],[0,162],[0,164],[0,166],[0,169],[0,171],[0,173],[0,175],[0,178],[0,180],[0,182],[0,185],[0,187],[0,190],[0,192],[0,195],[0,198],[0,201],[0,204],[0,207],[0,211],[0,214],[0,217],[0,220],[0,224],[0,227],[0,231],[0,234],[0,238],[0,241],[0,245],[0,249],[0,252],[0,256],[0,260],[0,263],[0,267],[0,271],[0,275],[0,278],[0,282],[0,286],[0,289],[0,293],[0,296],[0,300],[0,304],[0,307],[0,311],[0,315],[0,318],[0,322],[0,326],[0,329],[0,333],[0,337],[0,340],[0,344],[0,347],[0,351],[0,355],[0,358],[0,362],[0,365],[0,369],[0,372],[0,375],[0,378],[0,382],[0,385],[0,388],[0,391],[0,394],[0,397],[0,400],[0,403],[0,405],[0,408],[0,411],[0,413],[0,416],[0,418],[0,421],[0,423],[0,425],[0,428],[0,430],[0,432],[0,434],[0,436],[0,437],[0,439],[0,441],[0,443],[0,445],[0,446],[0,448],[0,449],[0,451],[0,452],[0,454],[0,455],[0,457],[0,458],[0,459],[0,461],[0,462],[0,463],[0,465],[0,466],[0,467],[0,469],[0,470],[0,471],[0,473],[0,474],[0,475],[0,476],[0,478],[0,479],[0,480],[0,482],[0,483],[0,484],[0,486],[0,487],[0,488],[0,489],[0,491],[0,492],[0,493],[0,495],[0,496],[0,498],[0,499],[0,500],[0,502],[0,503],[0,505],[0,506],[0,507],[0,509],[0,510],[0,512],[0,513],[0,515],[0,516],[0,517],[0,519],[0,520],[0,522],[0,524],[0,525],[0,527],[0,528],[0,530],[0,532],[0,534],[0,535],[0,537],[0,539],[0,541],[0,543],[0,544],[0,546],[0,548],[0,550],[0,552],[0,554],[0,556],[0,558],[0,560],[0,562],[0,564],[0,566],[0,568],[0,570],[0,572],[0,574],[0,576],[0,578],[0,580],[0,582],[0,584],[0,586],[0,588],[0,590],[0,591],[0,593],[0,595],[0,597],[0,599],[0,601],[0,603],[0,605],[0,606],[0,608],[0,609],[0,611],[0,612],[0,613],[0,615],[0,616],[0,617],[0,619],[0,620],[0,621],[0,622],[0,623],[0,624],[0,625],[0,626],[0,627],[0,628],[0,629],[0,629,783,789],[0,630,783,789],[0,630,783,789],[0,631,783,789],[0,632,783,790],[0,632,783,790],[0,633,783,791],[0,634,783,791],[0,634,784,792],[0,635,784,793],[0,636,784,793],[0,637,785,794],[0,637,785,795],[0,638,786,796],[0,639,786,797],[0,640,787,798],[0,641,788,799],[0,641,789,800],[0,642,789,802],[0,643,790,803],[0,644,791,804],[0,645,792,806],[0,645,793,807],[0,646,794,809],[0,647,795,810],[0,648,796,812],[0,649,797,813],[0,650,798,815],[0,651,799,816],[0,652,800,818],[0,653,801,819],[0,654,802,821],[0,655,803,822],[0,656,805,824],[0,657,806,825],[0,658,807,827],[0,659,809,828],[0,660,810,830],[0,661,811,831],[0,662,812,833],[0,663,814,834],[0,665,815,836],[0,666,816,837],[0,667,818,839],[0,668,819,840],[0,669,821,842],[0,670,822,844],[0,672,824,845],[0,673,825,847],[0,674,827,849],[0,676,829,850],[0,677,830,852],[0,678,832,854],[0,680,833,856],[0,681,835,857],[0,682,837,859],[0,684,839,861],[0,685,841,863],[0,687,843,865],[0,688,845,867],[0,690,847,869],[0,691,849,871],[0,693,851,873],[0,694,853,875],[0,696,855,877],[0,697,857,879],[0,699,859,881],[0,700,861,883],[0,702,863,885],[0,704,865,887],[0,705,867,889],[0,707,869,891],[0,708,871,893],[0,710,873,895],[0,711,875,897],[0,713,877,899],[0,714,879,901],[0,716,881,903],[0,717,883,905],[0,719,885,907],[0,720,887,909],[0,722,889,911],[0,723,891,913],[0,724,893,915],[0,726,895,917],[0,727,897,919],[0,729,899,921],[0,730,901,923],[0,731,903,925],[0,733,905,927],[0,734,907,929],[0,735,909,930],[0,737,911,932],[0,738,913,934],[0,739,915,936],[0,741,917,938],[0,742,918,940],[0,743,920,941],[0,745,922,943],[0,746,924,945],[0,747,926,946],[0,749,927,948],[0,750,929,949],[0,751,931,951],[0,752,932,952],[0,754,934,953],[0,755,935,955],[0,756,937,956],[0,757,938,957],[0,759,940,958],[0,760,941,959],[0,761,942,960],[0,762,943,961],[0,763,945,962],[0,764,946,963],[0,766,947,964],[0,767,948,965],[0,768,949,966],[0,769,950,966],[0,769,951,967],[0,770,952,968],[0,771,953,968],[0,772,954,969],[0,773,955,969],[0,774,956,970],[0,775,957,970],[0,776,958,971],[0,777,959,971],[0,777,960,972],[0,778,960,972],[0,779,961,973],[0,780,962,973],[0,780,963,974],[0,781,963,974],[0,782,964,974],[0,783,965,975],[0,783,965,975],[0,784,966,976],[0,785,966,976],[0,785,967,976],[0,786,968,977],[0,787,968,977],[0,787,969,977],[0,788,969,978],[0,789,970,978],[0,789,970,978],[0,790,971,979],[0,790,971,979],[0,791,972,979],[0,792,972,980],[0,792,973,980],[0,793,973,981],[0,794,974,981],[0,794,975,981],[0,795,975,982],[0,796,976,982],[0,797,976,983],[0,797,977,983],[0,798,977,984],[0,799,978,984],[0,800,979,985],[0,800,979,985],[0,801,980,986],[0,802,981,986],[0,803,981,987],[0,804,982,987],[0,805,983,988],[0,806,984,988],[0,806,984,989],[0,807,985,989],[0,808,986,990],[0,809,987,990],[0,810,988,991],[0,811,989,991],[0,812,989,992],[0,813,990,993],[0,814,991,993],[0,815,992,994],[0,816,993,994],[0,816,994,995],[0,817,994,995],[0,818,995,996],[0,819,996,996],[0,820,997,997],[0,821,998,997],[0,822,999,998],[0,823,1000,998],[0,824,1001,999],[0,824,1002,999],[0,825,1003,1000],[0,826,1004,1000],[0,827,1005,1001],[0,828,1006,1001],[0,829,1007,1002],[0,830,1008,1002],[0,831,1009,1003],[0,832,1010,1004],[0,833,1011,1004],[0,834,1012,1005],[0,835,1013,1005],[0,836,1014,1006],[0,837,1015,1006],[0,838,1016,1007],[0,839,1017,1007],[0,840,1018,1008],[0,841,1019,1008],[0,842,1020,1009],[0,842,1021,1009],[0,843,1022,1010],[0,844,1023],[0,844,1023],[0,845,1023],[0,846,1023],[0,846,1023],[0,847,1023],[0,847,1023],[0,848,1023],[0,848,1023],[0,848,1023],[0,849,1023],[0,849,1023],[0,850,1023],[0,850,1023],[0,850,1023],[0,851,1023],[0,851,1023],[0,851,1023],[0,852,1023],[0,852,1023],[0,852,1023],[0,852,1023],[0,853,1023],[0,853,1023],[0,854,1023],[0,854,1023],[0,854,1023],[0,855,1023],[0,855,1023],[0,855,1023],[0,856,1023],[0,856,1023],[0,856,1023],[0,857,1023],[0,857,1023],[0,857,1023],[0,858,1023],[0,858,1023],[0,858,1023],[0,859,1023],[0,859,1023],[0,859,1023],[0,860,1023],[0,860,1023],[0,861,1023],[0,861,1023],[0,862,1023],[0,862,1023],[0,863,1023],[0,864,1023],[0,864,1023],[0,865,1023],[0,866,1023],[0,866,1023],[0,867,1023],[0,868,1023],[0,869,1023],[0,870,1023],[0,871,1023],[0,872,1023],[0,872,1023],[0,873,1023],[0,874,1023],[0,875,1023],[0,876,1023],[0,876,1023],[0,877,1023],[0,878,1023],[0,879,1023],[0,879,1023],[0,879,1023],[0,879,1023],[0,878,1023],[0,878,1023],[0,877,1023],[0,876,1023],[0,875,1023],[0,874,1023],[0,874,1023],[0,873,1023],[0,872,1023],[0,872,1023],[0,871,1023],[0,871,1023],[0,870,1023],[0,870,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,869,1023],[0,870,1023],[0,870,1023],[0,871,1023],[0,871,1023],[0,872,1023],[0,873,1023],[0,874,1023],[0,875,1023],[0,876,1023],[0,877,1023],[0,878,1023],[0,879,1023],[0,880,1023],[0,881,1023],[0,883,1023],[0,884,1023],[0,885,1023],[0,886,1023],[0,888,1023],[0,889,1023],[0,890,1023],[0,891,1023],[0,892,1023],[0,894,1023],[0,895,1023],[0,896,1023],[0,897,1023],[0,898,1023],[0,900,1023],[0,901,1023],[0,902,1023],[0,904,1023],[0,905,1023],[0,906,1023],[0,908,1023],[0,909,1023],[0,911,1023],[0,912,1023],[0,914,1023],[0,915,1023],[0,917,1023],[0,918,1023],[0,919,1023],[0,921,1023],[0,922,1023],[0,924,1023],[0,925,1023],[0,927,1023],[0,928,1023],[0,930,1023],[0,931,1023],[0,932,1023],[0,934,1023],[0,935,1023],[0,936,1023],[0,938,1023],[0,939,1023],[0,940,1023],[0,941,1023],[0,943,1023],[0,944,1023],[0,945,1023],[0,946,1023],[0,947,1023],[0,948,1023],[0,949,1023],[0,950,1023],[0,951,1023],[0,951,1023],[0,952,1023],[0,953,1023],[0,954,1023],[0,954,1023],[0,955,1023],[0,956,1023],[0,956,1023],[0,957,1023],[0,957,1023],[0,958,1023],[0,958,1023],[0,959,1023],[0,959,1023],[0,960,1023],[0,960,1023],[0,960,1023],[0,961,1023],[0,961,1023],[0,961,1023],[0,962,1023],[0,962,1023],[0,962,1023],[0,962,1023],[0,962,1023],[0,962,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,963,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,964,1023],[0,965,1023],[0,965,1023],[0,965,1023],[0,966,1023],[0,966,1023],[0,967,1023],[0,967,1023],[0,968,1023],[0,969,1023],[0,970,1023],[0,971,1023],[0,972,1023],[0,973,1023],[0,974,1023],[0,975,1023],[0,977,1023],[0,978,1023],[0,980,1023],[0,981,1023],[0,982,1023],[0,984,1023],[0,985,1023],[0,987,1023],[0,988,1023],[0,990,1023],[0,991,1023],[0,993,1023],[0,994,1023],[0,996,1023],[0,997,1023],[0,999,1023],[0,1000,1023],[0,1001,1023],[0,1003,1023],[0,1004,1023],[0,1005,1023],[0,1006,1023],[0,1008,1023],[0,1009,1023],[0,1010,1023],[0,1011,1023],[0,1012,1023],[0,1013,1023],[0,1014,1023],[0,1015,1023],[0,1016,1023],[0,1017,1023],[0,1018,1023],[0,1019,1023],[0,1020,1023],[0,1021,1023],[0,1022],[0,1022],[0,1021],[0,1021],[0,1020],[0,1020],[0,1019],[0,1019],[0,1018],[0,1018],[0,1017],[0,1017],[0,1016],[0,1016],[0,1015],[0,1015],[0,1014],[0,1014],[0,1013],[0,1013],[0,1012],[0,1012],[0,1011],[0,1011],[0,1010],[0,1009],[0,1009],[0,1008],[0,1007],[0,1007],[0,1006],[0,1005],[0,1005],[0,1004],[0,1003],[0,1002],[0,1001],[0,1000],[0,999],[0,998],[0,997],[0,996],[0,995],[0,994],[0,992],[0,991],[0,989],[0,988],[0,986],[0,985],[0,983],[0,981],[0,979],[0,977],[0,976],[0,974],[0,972],[0,970],[0,967],[0,965],[0,963],[0,961],[0,958],[0,956],[0,953],[0,950],[0,947],[0,944],[0,942],[0,939],[0,936],[0,933],[0,930],[0,927],[0,923],[0,920],[0,917],[0,914],[0,911],[0,908],[0,905],[0,902],[0,899],[0,896],[0,893],[0,890],[0,887],[0,884],[0,881],[0,878],[0,875],[0,871],[0,868],[0,865],[0,862],[0,859],[0,856],[0,853],[0,849],[0,846],[0,843],[0,840],[0,837],[0,834],[0,831],[0,828],[0,825],[0,821],[0,818],[0,815],[0,812],[0,809],[0,806],[0,802],[0,799],[0,796],[0,793],[0,790],[0,786],[0,783],[0,779],[0,776],[0,772],[0,768],[0,764],[0,760],[0,755],[0,750],[0,745],[0,740],[0,735],[0,730],[0,724],[0,719],[0,713],[0,708],[0,702],[0,696],[0,691],[0,685],[0,680],[0,674],[0,669],[0,663],[0,658],[0,652],[0,646],[0,641],[0,636],[0,630],[0,625],[0,620],[0,615],[0,610],[0,605],[0,600],[0,595],[0,590],[0,586],[0,581],[0,577],[0,573],[0,569],[0,565],[0,561],[0,557],[0,553],[0,550],[0,546],[0,543],[0,539],[0,535],[0,531],[0,527],[0,523],[0,519],[0,515],[0,511],[0,507],[0,503],[0,499],[0,495],[0,491],[0,487],[0,483],[0,479],[0,474],[0,470],[0,466],[0,462],[0,457],[0,453],[0,448],[0,444],[0,439],[0,435],[0,430],[0,425],[0,421],[0,416],[0,411],[0,406],[0,401],[0,396],[0,391],[0,386],[0,381],[0,376],[0,371],[0,366],[0,361],[0,356],[0,350],[0,345],[0,340],[0,335],[0,329],[0,324],[0,318],[0,313],[0,307],[0,301],[0,295],[0,290],[0,284],[0,278],[0,272],[0,265],[0,259],[0,253],[0,246],[0,240],[0,233],[0,227],[0,220],[0,214],[0,207],[0,201],[0,194],[0,187],[0,180],[0,173],[0,167],[0,160],[0,153],[0,146],[0,139],[0,132],[0,125],[0,118],[0,112],[0,105],[0,98],[0,91],[0,84],[0,77],[0,70],[0,63],[0,56],[0,49],[0,42],[0,35],[0,28],[0,22],[0,15],[0,8],[0,1]];
  const SHORE_ROWS=[];
  const OPEN_BOUNDARIES=[{"id":"M","role":"mouth_tidal","edge":"top","run":[58,342],"sampleCount":18},{"id":"N","role":"nishi_upstream","edge":"bottom","run":[920,1012],"sampleCount":8},{"id":"O","role":"onga_upstream","edge":"bottom","run":[1135,1496],"sampleCount":18},{"id":"G","role":"magari_upstream","edge":"bottom","run":[1768,1903],"sampleCount":10}];
  const BOUNDARY_SECTIONS=[{"id":"M","name":"河口・潮汐参照断面","role":"mouth_tidal","endpointA":[347.16,30.72],"endpointB":[215.54,167.74],"endpointALL":{"lat":33.8993943463019,"lng":130.6649389350739},"endpointBLL":{"lat":33.89795417645117,"lng":130.66322898204015}},{"id":"N","name":"西川上流参照断面","role":"nishi_upstream","endpointA":[982.41,1171.07],"endpointB":[895.73,1178.5],"endpointALL":{"lat":33.88645197794984,"lng":130.67301750376958},"endpointBLL":{"lat":33.88635012586129,"lng":130.67189936538505}},{"id":"O","name":"遠賀川本流上流参照断面","role":"onga_upstream","endpointA":[1467.13,1155.39],"endpointB":[1137.93,1194.31],"endpointALL":{"lat":33.88675020644527,"lng":130.6792608547054},"endpointBLL":{"lat":33.886216743172665,"lng":130.67502833028718}},{"id":"G","name":"曲川上流参照断面","role":"magari_upstream","endpointA":[1847.26,1142.33],"endpointB":[1767.78,1217.65],"endpointALL":{"lat":33.886996829479896,"lng":130.68415248956922},"endpointBLL":{"lat":33.88604292686652,"lng":130.68315184330593}}];
  const FISHWAY={
    lat:33.88911111111111,
    lng:130.67458333333333,
    directionLabel:'北東',
    bearingDeg:45,
    flowAxis:{east:Math.SQRT1_2,north:Math.SQRT1_2},
    noStandRadiusM:0,
    influenceClippedToWater:true,
    source:'user_confirmed_2026_07_10'
  };
  const SOLVER={
    nx:(typeof FLUID_SOLVER!=='undefined'&&FLUID_SOLVER.nx)||54,
    ny:(typeof FLUID_SOLVER!=='undefined'&&FLUID_SOLVER.ny)||54,
    maxIterations:112,
    minIterations:28,
    tolerance:7.5e-5,
    omega:1.30,
    cacheLimit:14,
    sampleNormal:900,
    sampleValidation:2200
  };
  const clampLocal=(typeof clamp==='function')?clamp:((v,a,b)=>Math.max(a,Math.min(b,v)));

  function projectWM(lat,lng){
    const x=(lng+180)/360*WM.circumference;
    const s=Math.sin(lat*Math.PI/180);
    const y=(.5-Math.log((1+s)/(1-s))/(4*Math.PI))*WM.circumference;
    return{x,y};
  }
  function unprojectWM(x,y){
    const lng=x/WM.circumference*360-180;
    const n=Math.PI-2*Math.PI*y/WM.circumference;
    const lat=180/Math.PI*Math.atan(Math.sinh(n));
    return{lat,lng};
  }
  function imageXYToLatLng(x,y){
    return unprojectWM(WM.tx+WM.a*x-WM.b*y,WM.ty+WM.b*x+WM.a*y);
  }
  function latLngToImageXY(lat,lng){
    const p=projectWM(lat,lng),dx=p.x-WM.tx,dy=p.y-WM.ty;
    const det=WM.a*WM.a+WM.b*WM.b;
    return{x:(WM.a*dx+WM.b*dy)/det,y:(-WM.b*dx+WM.a*dy)/det};
  }
  function imageToMaskXY(x,y){return{x:x/SRC.cellScaleX,y:y/SRC.cellScaleY};}
  function maskToImageXY(ix,iy){return{x:ix*SRC.cellScaleX,y:iy*SRC.cellScaleY};}
  function rowContains(rows,ix,iy){
    if(iy<0||iy>=rows.length||ix<0||ix>=SRC.maskWidth)return false;
    const row=rows[iy]||[];
    for(let k=0;k<row.length;k+=2){
      if(ix<row[k])return false;
      if(ix<=row[k+1])return true;
    }
    return false;
  }
  function contains(lat,lng){
    if(!Number.isFinite(lat)||!Number.isFinite(lng))return false;
    const p=latLngToImageXY(lat,lng),q=imageToMaskXY(p.x,p.y);
    return rowContains(WATER_ROWS,Math.floor(q.x),Math.floor(q.y));
  }
  function isApprovedShore(lat,lng){
    if(!Number.isFinite(lat)||!Number.isFinite(lng))return false;
    const p=latLngToImageXY(lat,lng),q=imageToMaskXY(p.x,p.y);
    return rowContains(SHORE_ROWS,Math.round(q.x),Math.round(q.y));
  }
  function maskCellCenterLatLng(ix,iy){
    const p=maskToImageXY(ix+.5,iy+.5);
    return imageXYToLatLng(p.x,p.y);
  }
  function localMeters(lat,lng){
    const ref=CONTROL_POINTS[3],cos=Math.cos(ref.lat*Math.PI/180);
    return{x:(lng-ref.lng)*111320*cos,y:(lat-ref.lat)*110540};
  }
  function distanceToSegmentM(lat,lng,a,b){
    const p=localMeters(lat,lng),aa=localMeters(a.lat,a.lng),bb=localMeters(b.lat,b.lng);
    const vx=bb.x-aa.x,vy=bb.y-aa.y,wx=p.x-aa.x,wy=p.y-aa.y;
    const t=clampLocal((wx*vx+wy*vy)/(vx*vx+vy*vy||1),0,1);
    return Math.hypot(p.x-(aa.x+vx*t),p.y-(aa.y+vy*t));
  }
  function sectionById(id){return BOUNDARY_SECTIONS.find(s=>s.id===id)||null;}

  let waterBits=null,shoreBits=null,shoreSamples=null,shoreBins=null,waterCanvas=null;
  function rowsToBits(rows){
    const bits=new Uint8Array(SRC.maskWidth*SRC.maskHeight);
    for(let y=0;y<SRC.maskHeight;y++){
      const row=rows[y]||[];
      for(let k=0;k<row.length;k+=2){
        for(let x=row[k];x<=row[k+1];x++)bits[y*SRC.maskWidth+x]=1;
      }
    }
    return bits;
  }
  function getWaterBits(){return waterBits||(waterBits=rowsToBits(WATER_ROWS));}
  function getShoreBits(){return shoreBits||(shoreBits=rowsToBits(SHORE_ROWS));}
  function ensureWaterCanvas(){
    if(waterCanvas)return waterCanvas;
    if(typeof document==='undefined')return null;
    const c=document.createElement('canvas');c.width=SRC.maskWidth;c.height=SRC.maskHeight;
    const ctx=c.getContext('2d');ctx.fillStyle='rgba(255,255,255,1)';
    for(let y=0;y<SRC.maskHeight;y++){
      const row=WATER_ROWS[y]||[];
      for(let k=0;k<row.length;k+=2)ctx.fillRect(row[k],y,row[k+1]-row[k]+1,1);
    }
    waterCanvas=c;return c;
  }
  function buildShoreSamples(){
    if(shoreSamples)return shoreSamples;
    const bits=getShoreBits(),out=[];
    for(let y=0;y<SRC.maskHeight;y+=1){
      for(let x=0;x<SRC.maskWidth;x+=1){
        if(!bits[y*SRC.maskWidth+x])continue;
        const ll=maskCellCenterLatLng(x,y),m=localMeters(ll.lat,ll.lng);
        out.push({lat:ll.lat,lng:ll.lng,mx:m.x,my:m.y,ix:x,iy:y,onUnifiedBoundary:true});
      }
    }
    shoreSamples=out;shoreBins=null;return out;
  }
  function buildShoreBins(){
    if(shoreBins)return shoreBins;
    const cell=70,bins=new Map();
    for(const p of buildShoreSamples()){
      const key=Math.floor(p.mx/cell)+','+Math.floor(p.my/cell);
      if(!bins.has(key))bins.set(key,[]);
      bins.get(key).push(p);
    }
    shoreBins={cell,bins};return shoreBins;
  }
  function nearestBoundaryStand(target){
    if(!target||!contains(target.lat,target.lng))return null;
    const maxM=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.maxM)||100;
    const preferredM=(typeof CAST_MODEL!=='undefined'&&CAST_MODEL.preferredM)||45;
    const tm=localMeters(target.lat,target.lng),index=buildShoreBins(),cell=index.cell;
    const bx=Math.floor(tm.x/cell),by=Math.floor(tm.y/cell),span=Math.ceil((maxM+cell)/cell);
    let best=null;
    for(let yy=by-span;yy<=by+span;yy++)for(let xx=bx-span;xx<=bx+span;xx++){
      const arr=index.bins.get(xx+','+yy);if(!arr)continue;
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
  function drawCanvasMask(ctx,alpha=1){
    if(!ctx||typeof latLngToCanvas!=='function')return;
    ctx.save();ctx.globalAlpha*=alpha;ctx.fillStyle='rgba(255,255,255,1)';
    for(let y=0;y<SRC.maskHeight;y++){
      const row=WATER_ROWS[y]||[];if(!row.length)continue;
      for(let k=0;k<row.length;k+=2){
        const ia=maskToImageXY(row[k],y),ib=maskToImageXY(row[k+1]+1,y+1);
        const ll1=imageXYToLatLng(ia.x,ia.y),ll2=imageXYToLatLng(ib.x,ia.y),ll3=imageXYToLatLng(ib.x,ib.y),ll4=imageXYToLatLng(ia.x,ib.y);
        const p1=latLngToCanvas(ll1.lat,ll1.lng),p2=latLngToCanvas(ll2.lat,ll2.lng),p3=latLngToCanvas(ll3.lat,ll3.lng),p4=latLngToCanvas(ll4.lat,ll4.lng);
        if((p1.x<-80&&p2.x<-80&&p3.x<-80&&p4.x<-80)||(p1.y<-80&&p2.y<-80&&p3.y<-80&&p4.y<-80)||(p1.x>state.width+80&&p2.x>state.width+80&&p3.x>state.width+80&&p4.x>state.width+80)||(p1.y>state.height+80&&p2.y>state.height+80&&p3.y>state.height+80&&p4.y>state.height+80))continue;
        ctx.beginPath();ctx.moveTo(p1.x,p1.y);ctx.lineTo(p2.x,p2.y);ctx.lineTo(p3.x,p3.y);ctx.lineTo(p4.x,p4.y);ctx.closePath();ctx.fill();
      }
    }
    ctx.restore();
  }

  function syntheticHydro(lat,lng,oldHydro=null){
    if(!contains(lat,lng))return null;
    if(oldHydro&&oldHydro.corridor>.01)return{...oldHydro,corridor:1,seed:1,unifiedWaterDomain:VERSION};
    let main={s:.5,signedDistancePx:0,distancePx:0};
    try{if(typeof nearestRiverProgress==='function')main=nearestRiverProgress(lat,lng)||main;}catch(_){}
    let widthPx=160;
    try{if(typeof modelWidthPixels==='function'&&typeof riverWidthAt==='function')widthPx=modelWidthPixels(riverWidthAt(main.s||.5),lat);}catch(_){}
    return{kind:'unified_water',label:'統一水面',s:clampLocal(main.s??.5,0,1),tributaryProgress:clampLocal(main.s??.5,0,1),signedDistancePx:Number.isFinite(main.signedDistancePx)?main.signedDistancePx:0,distancePx:Number.isFinite(main.distancePx)?main.distancePx:Math.abs(main.signedDistancePx||0),widthPx,maxDistPx:Math.max(widthPx*2.2,260),corridor:1,seed:1,unifiedWaterDomain:VERSION};
  }
  function cellToSample(ix,iy,step){
    const ll=maskCellCenterLatLng(ix,iy);
    if(typeof isWithinBounds==='function'&&!isWithinBounds(ll.lat,ll.lng))return null;
    if(!contains(ll.lat,ll.lng))return null;
    let old=null;try{old=window.__ONGA_PREV_NEAREST_HYDRO__?.(ll.lat,ll.lng)||null;}catch(_){}
    const hydro=syntheticHydro(ll.lat,ll.lng,old);
    let main={s:hydro?.s??.5,signedDistancePx:hydro?.signedDistancePx??0,distancePx:hydro?.distancePx??0};
    try{if(typeof nearestRiverProgress==='function')main=nearestRiverProgress(ll.lat,ll.lng)||main;}catch(_){}
    let widthPx=hydro?.widthPx||160;
    try{if((hydro?.kind==='main'||hydro?.kind==='unified_water')&&typeof modelWidthPixels==='function')widthPx=modelWidthPixels(riverWidthAt(main.s),ll.lat);}catch(_){}
    const signed=(hydro&&hydro.kind!=='main'&&hydro.kind!=='unified_water')?hydro.signedDistancePx:main.signedDistancePx;
    const s=(hydro&&hydro.kind!=='main'&&hydro.kind!=='unified_water')?clampLocal((hydro.s??.05)+.22*(1-(hydro.tributaryProgress??1)),0,1):clampLocal(main.s??hydro?.s??.5,0,1);
    const p=(typeof latLngToCanvas==='function')?latLngToCanvas(ll.lat,ll.lng):{x:0,y:0};
    const mp=(typeof toModelPx==='function')?toModelPx(ll.lat,ll.lng):{x:ix,y:iy};
    return{lat:ll.lat,lng:ll.lng,x:p.x,y:p.y,gx:Math.round(ix/(step||1)),gy:Math.round(iy/(step||1)),s,cr:clampLocal((signed||0)/Math.max(1,widthPx/2),-1.75,1.75),photoWater:1,corridor:1,seed:1,nearestDistancePx:hydro?.distancePx??0,hydroKind:hydro?.kind||'unified_water',hydroLabel:hydro?.label||'統一水面',hydroProgress:hydro?.tributaryProgress??s,mx:mp.x,my:mp.y,unifiedWaterDomain:VERSION};
  }
  function unifiedWaterSamples(){
    const mode=(typeof state!=='undefined'&&state.performanceMode)||'practical';
    const target=mode==='validation'?SOLVER.sampleValidation:mode==='balanced'?1500:mode==='eco'?500:SOLVER.sampleNormal;
    const bits=getWaterBits(),total=bits.reduce((a,b)=>a+b,0),step=Math.max(1,Math.floor(Math.sqrt(total/Math.max(1,target))));
    const key=mode+'|'+step+'|'+VERSION;
    if(window.__ONGA_UNIFIED_SAMPLE_CACHE__?.key===key){
      const cached=window.__ONGA_UNIFIED_SAMPLE_CACHE__.samples;
      if(typeof state!=='undefined'){state.waterMaskSamples=cached;state.waterMaskPoints=cached.slice(0,3600);}
      return cached;
    }
    const out=[];
    for(let y=Math.floor(step/2);y<SRC.maskHeight;y+=step){
      const row=WATER_ROWS[y]||[];
      for(let k=0;k<row.length;k+=2){
        for(let x=row[k]+Math.floor(step/2);x<=row[k+1];x+=step){
          const p=cellToSample(x,y,step);if(p)out.push(p);
        }
      }
    }
    if(typeof state!=='undefined'){
      state.waterMaskSamples=out;state.waterMaskPoints=out.slice(0,3600);
      state.photoSampleStatus='統一水面: 青塗り正解領域 '+out.length+'点 / 1連結水域 / 開境界4 / 境界釣り座のみ';
    }
    window.__ONGA_UNIFIED_SAMPLE_CACHE__={key,samples:out};return out;
  }

  function canonicalGridKey(nx,ny){
    const b=(typeof GSI!=='undefined'&&GSI.bounds)||{south:33.8832,west:130.6578,north:33.90065,east:130.68735};
    return VERSION+'|'+nx+'x'+ny+'|'+[b.south,b.west,b.north,b.east].join(',');
  }
  function buildCanonicalBase(nx=SOLVER.nx,ny=SOLVER.ny){
    if(typeof state!=='undefined'){
      state.unifiedDomainBaseCache=state.unifiedDomainBaseCache||new Map();
      const key=canonicalGridKey(nx,ny),cached=state.unifiedDomainBaseCache.get(key);
      if(cached)return cached;
    }
    const b=(typeof GSI!=='undefined'&&GSI.bounds)||{south:33.8832,west:130.6578,north:33.90065,east:130.68735};
    const n=nx*ny,water=new Uint8Array(n),K=new Float32Array(n),depth=new Float32Array(n),latArr=new Float32Array(n),lngArr=new Float32Array(n),imageX=new Float32Array(n),imageY=new Float32Array(n);
    const idx=(i,j)=>j*nx+i;let waterCount=0;
    for(let j=0;j<ny;j++){
      const lat=b.north-(b.north-b.south)*(j+.5)/ny;
      for(let i=0;i<nx;i++){
        const lng=b.west+(b.east-b.west)*(i+.5)/nx,k=idx(i,j),im=latLngToImageXY(lat,lng);
        latArr[k]=lat;lngArr[k]=lng;imageX[k]=im.x;imageY[k]=im.y;
        if(!contains(lat,lng))continue;
        water[k]=1;waterCount++;
        let dm=null;try{if(typeof fluidDepthAndMobility==='function')dm=fluidDepthAndMobility(lat,lng);}catch(_){}
        depth[k]=clampLocal(dm?.depth??1.2,.25,5);
        K[k]=Math.max(.05,dm?.hydraulic??Math.pow(depth[k],1.25));
      }
    }
    const dx=(typeof haversine==='function')?haversine((b.north+b.south)/2,b.west,(b.north+b.south)/2,b.east)/nx:50;
    const dy=(typeof haversine==='function')?haversine(b.north,(b.west+b.east)/2,b.south,(b.west+b.east)/2)/ny:50;
    const base={key:canonicalGridKey(nx,ny),nx,ny,n,idx,b,water,K,depth,latArr,lngArr,imageX,imageY,dx,dy,waterCount};
    if(typeof state!=='undefined')state.unifiedDomainBaseCache.set(base.key,base);
    return base;
  }
  function nearestWaterCell(base,lat,lng,used=null){
    let best=-1,bestD=Infinity;
    for(let k=0;k<base.n;k++){
      if(!base.water[k])continue;
      const dx=(base.lngArr[k]-lng)*111320*Math.cos(lat*Math.PI/180),dy=(base.latArr[k]-lat)*110540,d=dx*dx+dy*dy;
      if(d<bestD&&(!used||!used.has(k))){bestD=d;best=k;}
    }
    return best;
  }
  function assignOpenBoundaryCells(base){
    const type=new Uint8Array(base.n),ids={M:1,O:2,N:3,G:4},used=new Set(),members={M:[],N:[],O:[],G:[]};
    for(const boundary of OPEN_BOUNDARIES){
      const count=Math.max(3,boundary.sampleCount||8),y=boundary.edge==='top'?3:SRC.originalHeight-4;
      for(let s=0;s<count;s++){
        const x=boundary.run[0]+(boundary.run[1]-boundary.run[0])*(s+.5)/count,ll=imageXYToLatLng(x,y),k=nearestWaterCell(base,ll.lat,ll.lng,used);
        if(k>=0){used.add(k);type[k]=ids[boundary.id];members[boundary.id].push(k);}
      }
    }
    return{type,members};
  }
  function boundaryHead(type,env,flux){
    const falling=clampLocal(env?.falling||0,0,1),rising=clampLocal(env?.rising||0,0,1),tideMove=clampLocal(env?.tideMove||0,0,1),gate=clampLocal(env?.gate?.gateOpening??env?.gate?.risk??0,0,1);
    const mouth=.82*rising*tideMove-.58*falling*tideMove-.20*gate;
    const onga=flux?.closedOngaMain?mouth:(.42+.58*(flux?.ongaUpQ||0)+.55*gate+.18*falling*tideMove-.24*rising*tideMove);
    const nishi=.22+.72*(flux?.nishiQ||0)+.20*falling*tideMove-.18*rising*tideMove;
    const magari=.18+.66*(flux?.magariQ||0)+.20*falling*tideMove-.16*rising*tideMove;
    return type===1?mouth:type===2?onga:type===3?nishi:type===4?magari:0;
  }
  function fluidCacheKey(env){
    const e=env?.entry?.key||(env?.entry?.date?String(env.entry.date):'no-time'),gate=Math.round(clampLocal(env?.gate?.gateOpening??env?.gate?.risk??0,0,1)*1000),slope=Math.round((env?.tide?.slope??0)*10000),tide=Math.round(clampLocal(env?.highTide??.5,0,1)*1000),rain=Math.round(clampLocal(env?.rainBoost??0,0,1)*1000);
    return VERSION+'|'+e+'|g'+gate+'|s'+slope+'|t'+tide+'|r'+rain+'|'+SOLVER.nx+'x'+SOLVER.ny;
  }
  function buildUnifiedFluidGrid(env){
    if(typeof state!=='undefined'){
      state.fluidCache=state.fluidCache||new Map();
      const key=fluidCacheKey(env),cached=state.fluidCache.get(key);
      if(cached){state.lastSolverStats=cached.stats;return cached;}
    }
    const start=(typeof performance!=='undefined'&&performance.now)?performance.now():Date.now(),base=buildCanonicalBase(),nx=base.nx,ny=base.ny,n=base.n,idx=base.idx;
    const boundary=assignOpenBoundaryCells(base),fixed=new Uint8Array(n),phi=new Float32Array(n),u=new Float32Array(n),v=new Float32Array(n),speed=new Float32Array(n),shear=new Float32Array(n),conv=new Float32Array(n),vort=new Float32Array(n);
    const flux=(typeof hydrodynamicBoundaryFluxes==='function')?hydrodynamicBoundaryFluxes(env):{ongaUpQ:.5,nishiQ:.3,magariQ:.25,riverDown:.4,tidalFlood:0,tidalEbb:0,netMain:.4};
    const fixedList=[];let fixedCount=0;
    for(let k=0;k<n;k++){
      if(!base.water[k])continue;
      const bt=boundary.type[k];
      if(bt){fixed[k]=1;fixedCount++;phi[k]=boundaryHead(bt,env,flux);fixedList.push(k);}
    }
    for(let k=0;k<n;k++){
      if(!base.water[k]||fixed[k])continue;
      let sum=0,wsum=0;
      for(const q of fixedList){
        const dx=(base.lngArr[k]-base.lngArr[q])*111320*Math.cos(base.latArr[k]*Math.PI/180),dy=(base.latArr[k]-base.latArr[q])*110540,w=1/(dx*dx+dy*dy+2500);
        sum+=w*phi[q];wsum+=w;
      }
      phi[k]=wsum?sum/wsum:0;
    }
    let iterations=0,residual=Infinity;
    for(let iter=0;iter<SOLVER.maxIterations;iter++){
      residual=0;
      for(let colour=0;colour<2;colour++){
        for(let j=0;j<ny;j++){
          for(let i=((j+colour)&1);i<nx;i+=2){
            const k=idx(i,j);if(!base.water[k]||fixed[k])continue;
            let sum=0,wsum=0;
            if(i>0){const q=k-1;if(base.water[q]){const w=.5*(base.K[k]+base.K[q])+.015;sum+=w*phi[q];wsum+=w;}}
            if(i<nx-1){const q=k+1;if(base.water[q]){const w=.5*(base.K[k]+base.K[q])+.015;sum+=w*phi[q];wsum+=w;}}
            if(j>0){const q=k-nx;if(base.water[q]){const w=.5*(base.K[k]+base.K[q])+.015;sum+=w*phi[q];wsum+=w;}}
            if(j<ny-1){const q=k+nx;if(base.water[q]){const w=.5*(base.K[k]+base.K[q])+.015;sum+=w*phi[q];wsum+=w;}}
            if(!wsum)continue;
            const old=phi[k],next=old+SOLVER.omega*(sum/wsum-old),d=Math.abs(next-old);phi[k]=next;if(d>residual)residual=d;
          }
        }
      }
      iterations=iter+1;
      if(iterations>=SOLVER.minIterations&&iterations%4===0&&residual<SOLVER.tolerance)break;
    }
    const val=(arr,i,j)=>{if(i<0||i>=nx||j<0||j>=ny)return null;const k=idx(i,j);return base.water[k]?arr[k]:null;};
    const gross=Math.max(.12,Math.abs(flux.netMain||0)+(flux.tidalFlood||0)+(flux.tidalEbb||0)+(flux.nishiQ||0)*.45+(flux.magariQ||0)*.42);
    for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
      const k=idx(i,j);if(!base.water[k])continue;
      const e=val(phi,i+1,j),w=val(phi,i-1,j),nn=val(phi,i,j-1),s=val(phi,i,j+1),c=phi[k],xd=base.dx*((e!==null?1:0)+(w!==null?1:0)||1),yd=base.dy*((s!==null?1:0)+(nn!==null?1:0)||1),scale=28*gross;
      u[k]=-base.K[k]*((e??c)-(w??c))/xd*scale;
      v[k]=-base.K[k]*((s??c)-(nn??c))/yd*scale;
      speed[k]=Math.hypot(u[k],v[k]);
    }
    for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){
      const k=idx(i,j);if(!base.water[k])continue;
      const ue=val(u,i+1,j)??u[k],uw=val(u,i-1,j)??u[k],un=val(u,i,j-1)??u[k],us=val(u,i,j+1)??u[k],ve=val(v,i+1,j)??v[k],vw=val(v,i-1,j)??v[k],vn=val(v,i,j-1)??v[k],vs=val(v,i,j+1)??v[k],dudx=(ue-uw)/(2*base.dx),dudy=(us-un)/(2*base.dy),dvdx=(ve-vw)/(2*base.dx),dvdy=(vs-vn)/(2*base.dy),div=dudx+dvdy;
      shear[k]=clampLocal(Math.hypot(dudx-dvdy,dudy+dvdx)*38,0,1);conv[k]=clampLocal(-div*42,0,1);vort[k]=clampLocal(Math.abs(dvdx-dudy)*42,0,1);
    }
    if(typeof state!=='undefined'){
      state.flowVectors=[];
      for(let j=2;j<ny;j+=6)for(let i=2;i<nx;i+=6){const k=idx(i,j);if(base.water[k]&&speed[k]>.01)state.flowVectors.push({lat:base.latArr[k],lng:base.lngArr[k],u:u[k],v:v[k],speed:speed[k]});}
    }
    const elapsed=((typeof performance!=='undefined'&&performance.now)?performance.now():Date.now())-start,stats={iterations,residual,waterCount:base.waterCount,fixedCount,ms:elapsed,mode:'unified-domain red-black SOR',differenceCells:0};
    const grid={key:fluidCacheKey(env),nx,ny,water:base.water,fixed,phi,K:base.K,depth:base.depth,u,v,speed,shear,conv,vort,latArr:base.latArr,lngArr:base.lngArr,dx:base.dx,dy:base.dy,waterCount:base.waterCount,fixedCount,flux,gross,model:'unified_authoritative_water_potential_flow',stats,boundaryMembers:boundary.members};
    if(typeof state!=='undefined'){
      state.lastSolverStats=stats;state.fluidCache.set(grid.key,grid);
      while(state.fluidCache.size>SOLVER.cacheLimit){const first=state.fluidCache.keys().next().value;state.fluidCache.delete(first);}
      state.unifiedDomainDiagnostics={version:VERSION,nx,ny,waterDetectionCells:base.water,heatmapDomainCells:base.water,fluidWaterCells:grid.water,differenceCells:0,waterCount:base.waterCount,openBoundaries:boundary.members,boundarySections:BOUNDARY_SECTIONS};
    }
    return grid;
  }

  function installFishwayAndSafety(){
    if(window.ONGA_FISHWAY)Object.assign(window.ONGA_FISHWAY,FISHWAY);
    const safety=window.ONGA_SPATIAL_SAFETY;
    if(safety&&!safety.__unifiedFishwayZeroRadius){
      const prevNoStand=safety.noStandAt?.bind(safety);
      if(prevNoStand)safety.noStandAt=function(lat,lng){const hit=prevNoStand(lat,lng);return hit&&hit.kind==='fishway'?null:hit;};
      const prevAllowed=safety.hotspotAllowed?.bind(safety);
      safety.hotspotAllowed=function(h){if(!h)return false;const stand=safety.noStandAt?.(h.lat,h.lng);if(stand)return false;if(Number.isFinite(h.targetLat)&&Number.isFinite(h.targetLng)){if(safety.noStandAt?.(h.targetLat,h.targetLng))return false;if(safety.castBlock?.(h.lat,h.lng,h.targetLat,h.targetLng))return false;}return prevAllowed?prevAllowed(h)||true:true;};
      if(safety.rules?.noStand) safety.rules.noStand=safety.rules.noStand.filter(r=>r.kind!=='fishway'&&r.id!=='onga_fishway');
      safety.__unifiedFishwayZeroRadius=true;
    }
  }
  function installOverrides(){
    calibratedWaterMaskValueAt=function(lat,lng){return contains(lat,lng)?1:0;};
    if(typeof isKnownWater==='function')isKnownWater=function(lat,lng){return contains(lat,lng);};
    if(typeof nearestHydroCorridor==='function'&&nearestHydroCorridor!==window.__ONGA_UNIFIED_NEAREST_HYDRO__){
      window.__ONGA_PREV_NEAREST_HYDRO__=nearestHydroCorridor;
      window.__ONGA_UNIFIED_NEAREST_HYDRO__=function(lat,lng){let old=null;try{old=window.__ONGA_PREV_NEAREST_HYDRO__?.(lat,lng)||null;}catch(_){}return syntheticHydro(lat,lng,old);};
      nearestHydroCorridor=window.__ONGA_UNIFIED_NEAREST_HYDRO__;
    }
    if(typeof samplePhotoWaterCandidates==='function')samplePhotoWaterCandidates=unifiedWaterSamples;
    if(typeof drawWaterMask==='function')drawWaterMask=function(ctx){const toggle=typeof document!=='undefined'&&document.getElementById('toggleWaterMask');if(toggle&&!toggle.checked)return;if(!ctx)return;ctx.save();ctx.globalAlpha=.24;ctx.fillStyle='rgba(91,212,255,1)';drawCanvasMask(ctx,1);ctx.restore();};
    if(typeof findLandCastPositionForWater==='function')findLandCastPositionForWater=nearestBoundaryStand;
    if(typeof makeShoreCastingHotspots==='function')makeShoreCastingHotspots=function(candidates,n=8){
      const M=(typeof CAST_MODEL!=='undefined')?CAST_MODEL:{bankSepM:85,targetSepM:90},sorted=[...(candidates||[])].filter(p=>p&&Number.isFinite(p.score)&&p.score>.35&&contains(p.lat,p.lng)).sort((a,b)=>b.score-a.score),raw=[];
      for(const target of sorted.slice(0,1800)){const stand=nearestBoundaryStand(target);if(!stand)continue;raw.push({...target,lat:stand.lat,lng:stand.lng,targetLat:target.lat,targetLng:target.lng,targetScore:target.score,castDistanceM:stand.distanceM,landConfidence:1,bankQuality:1,onLand:true,onUnifiedBoundary:true,score:clampLocal(stand.score||target.score,0,1),structureName:'境界線釣り座：'+(target.structureName||target.hydroLabel||'水面標的'),reason:'承認済み緑境界 / '+Math.round(stand.distanceM||0)+'m先 / '+(target.reason||'')});}
      raw.sort((a,b)=>b.score-a.score);const chosen=[];
      for(const c of raw){let ok=true;for(const h of chosen){if(typeof haversine==='function'&&(haversine(c.lat,c.lng,h.lat,h.lng)<(M.bankSepM||85)||haversine(c.targetLat,c.targetLng,h.targetLat,h.targetLng)<(M.targetSepM||90))){ok=false;break;}}if(ok)chosen.push(c);if(chosen.length>=n)break;}
      return chosen.map((h,i)=>({...h,rank:i+1,score100:Math.round((h.score||0)*100),targetScore100:Math.round((h.targetScore||h.score||0)*100),unifiedWaterDomain:VERSION}));
    };
    if(typeof drawHeatmap==='function')drawHeatmap=function(ctx){
      const toggle=typeof document!=='undefined'&&document.getElementById('toggleHeat');if(toggle&&!toggle.checked)return;
      const points=(state.heatPoints||[]).filter(p=>p&&contains(p.lat,p.lng));if(!points.length)return;
      const scale=.58,W=Math.max(1,Math.ceil(state.width*scale)),H=Math.max(1,Math.ceil(state.height*scale)),field=new Float32Array(W*H);
      for(const p of points){const score=clampLocal(Number.isFinite(p.heatScore)?p.heatScore:(Number.isFinite(p.score)?p.score:0),0,1);if(score<=.015)continue;const pt=latLngToCanvas(p.lat,p.lng);if(pt.x<-110||pt.y<-110||pt.x>state.width+110||pt.y>state.height+110)continue;const r=Math.max(5,(22+11*((state.zoom||16)-14))*(.70+score*.58)*scale),cx=pt.x*scale,cy=pt.y*scale,r2=r*r,xmin=Math.max(0,Math.floor(cx-r)),xmax=Math.min(W-1,Math.ceil(cx+r)),ymin=Math.max(0,Math.floor(cy-r)),ymax=Math.min(H-1,Math.ceil(cy+r));for(let y=ymin;y<=ymax;y++){const dy=y-cy,dy2=dy*dy;for(let x=xmin;x<=xmax;x++){const d2=(x-cx)*(x-cx)+dy2;if(d2>r2)continue;const q=1-d2/r2,v=score*q*q,id=y*W+x;if(v>field[id])field[id]=v;}}}
      const heat=document.createElement('canvas');heat.width=W;heat.height=H;const hctx=heat.getContext('2d'),img=hctx.createImageData(W,H),alpha=clampLocal(state.baseOpacity||.15,0,.15);
      for(let i=0,j=0;i<field.length;i++,j+=4){const v=field[i];if(v<=.012){img.data[j+3]=0;continue;}const col=(typeof heatColor==='function')?heatColor(v):[0,160,255];img.data[j]=col[0];img.data[j+1]=col[1];img.data[j+2]=col[2];img.data[j+3]=Math.round(255*alpha*clampLocal(.20+.80*v,0,1));}
      hctx.putImageData(img,0,0);const mask=document.createElement('canvas');mask.width=W;mask.height=H;const mctx=mask.getContext('2d');mctx.setTransform(scale,0,0,scale,0,0);drawCanvasMask(mctx,1);mctx.setTransform(1,0,0,1,0,0);hctx.globalCompositeOperation='destination-in';hctx.drawImage(mask,0,0);hctx.globalCompositeOperation='source-over';ctx.drawImage(heat,0,0,state.width,state.height);
    };
    if(typeof buildFluidGrid==='function')buildFluidGrid=buildUnifiedFluidGrid;
    if(typeof hydrodynamicFlowAt==='function'&&hydrodynamicFlowAt!==window.__ONGA_UNIFIED_HYDRO_FLOW__){
      const prev=hydrodynamicFlowAt;window.__ONGA_UNIFIED_HYDRO_FLOW__=function(sample,env){if(!sample||!contains(sample.lat,sample.lng))return{ux:0,uy:0,speed:0,signedSpeed:0,shear:0,convergence:0,divergence:0,vorticity:0,salinityEdge:0,baitConvergence:0,score:0,label:'水面外',outsideUnifiedWater:true};return prev(sample,env);};hydrodynamicFlowAt=window.__ONGA_UNIFIED_HYDRO_FLOW__;
    }
    if(typeof scoreFishingSample==='function'&&scoreFishingSample!==window.__ONGA_UNIFIED_SCORE_SAMPLE__){
      const prev=scoreFishingSample;window.__ONGA_UNIFIED_SCORE_SAMPLE__=function(sample,env){const out=prev(sample,env);if(!contains(out?.lat??sample?.lat,out?.lng??sample?.lng))return{...out,score:0,heatScore:0,outsideUnifiedWater:true};return out;};scoreFishingSample=window.__ONGA_UNIFIED_SCORE_SAMPLE__;
    }
    if(typeof buildFishingModel==='function'&&buildFishingModel!==window.__ONGA_UNIFIED_BUILD_MODEL__){
      const prev=buildFishingModel;window.__ONGA_UNIFIED_BUILD_MODEL__=function(){const model=prev.apply(this,arguments);try{const samples=unifiedWaterSamples();if(model&&Array.isArray(model.points)){model.points=model.points.filter(p=>p&&contains(p.lat,p.lng));if(model.points.length<80&&arguments.length>=5&&typeof buildScoreEnvironment==='function'){const env=buildScoreEnvironment(arguments[0],arguments[1],arguments[2],arguments[3],arguments[4]);model.points=samples.map(s=>scoreFishingSample(s,env)).filter(p=>p&&Number.isFinite(p.score)&&contains(p.lat,p.lng));}model.hotspots=makeShoreCastingHotspots(model.points,8);}model.unifiedWaterDomain=VERSION;if(typeof state!=='undefined'){state.waterMaskSamples=samples;state.waterMaskPoints=samples.slice(0,3600);state.unifiedWaterDomain=window.ONGA_UNIFIED_WATER_DOMAIN;}if(typeof updateWaterStatus==='function')updateWaterStatus();}catch(e){console.warn('[unified-water] model patch',e);}return model;};buildFishingModel=window.__ONGA_UNIFIED_BUILD_MODEL__;
    }
    if(typeof updateWaterStatus==='function'&&updateWaterStatus!==window.__ONGA_UNIFIED_STATUS__){
      const prev=updateWaterStatus;window.__ONGA_UNIFIED_STATUS__=function(){const result=prev.apply(this,arguments),el=typeof document!=='undefined'&&document.getElementById('waterStatus');if(el){const d=state?.unifiedDomainDiagnostics;el.textContent='統一水面 v4.8: 青領域のみ / 1連結 / 開境界4 / 水面・ヒート・流体差分 '+(d?.differenceCells??0)+'セル / 魚道NE45°・no-standなし';}return result;};updateWaterStatus=window.__ONGA_UNIFIED_STATUS__;
    }
    installFishwayAndSafety();
    try{state?.waterSampleCache?.clear?.();state?.fluidCache?.clear?.();state?.fluidBaseCache?.clear?.();state?.unifiedDomainBaseCache?.clear?.();state?.validationCache?.clear?.();window.__ONGA_UNIFIED_SAMPLE_CACHE__=null;}catch(_){}
  }

  window.ONGA_UNIFIED_WATER_DOMAIN={
    version:VERSION,source:SRC,controlPoints:CONTROL_POINTS,controlResiduals:CONTROL_RESIDUALS,
    waterRows:WATER_ROWS,shoreRows:SHORE_ROWS,openBoundaries:OPEN_BOUNDARIES,boundarySections:BOUNDARY_SECTIONS,fishway:FISHWAY,
    contains,isApprovedShore,imageXYToLatLng,latLngToImageXY,drawCanvasMask,buildShoreSamples,unifiedWaterSamples,nearestBoundaryStand,
    buildCanonicalBase,buildFluidGrid:buildUnifiedFluidGrid,installOverrides,
    diagnostics:function(){const base=buildCanonicalBase();return{version:VERSION,waterCount:base.waterCount,differenceCells:0,nx:base.nx,ny:base.ny,openBoundaryCount:OPEN_BOUNDARIES.length,boundarySectionCount:BOUNDARY_SECTIONS.length};}
  };

  installOverrides();
  [120,360,800,1600,3000].forEach(ms=>setTimeout(()=>{try{installOverrides();if(typeof computeAndRender==='function'&&state?.timeline?.length)computeAndRender(true);else if(typeof renderAll==='function')renderAll();}catch(e){console.warn('[unified-water install]',e);}},ms));
  try{const sub=typeof document!=='undefined'&&document.querySelector('.sub');if(sub)sub.textContent='v4.8.0: 承認済み青領域を唯一の水面とし、水面判定・ヒートマップ・流体waterセルを完全統一。1連結水域、開境界4、無方向参照断面4、魚道NE45°・固有no-standなし。';}catch(_){}
  console.info('[onga-unified-water-domain]',VERSION,{controlResiduals:CONTROL_RESIDUALS,openBoundaries:OPEN_BOUNDARIES,boundarySections:BOUNDARY_SECTIONS});
})();
