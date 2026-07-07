(async function bootstrapV463Mobile(){
  try{
    const [html,closedPatch,cfdPatch,particlePatch]=await Promise.all([
      fetch('mobile_lite.html?exact=v46',{cache:'no-store'}).then(r=>r.text()),
      fetch('closed_gate_patch.js?v=closedflow1',{cache:'no-store'}).then(r=>r.text()),
      fetch('cfd_patch.js?v=cfd1',{cache:'no-store'}).then(r=>r.text()),
      fetch('flow_particles_patch.js?v=cfdparticles1',{cache:'no-store'}).then(r=>r.text())
    ]);
    const tag='<script>'+closedPatch+'\n'+cfdPatch+'\n'+particlePatch+'\n<\/script>';
    document.open();
    document.write(html.replace('</body>',tag+'</body>'));
    document.close();
  }catch(e){
    document.body.innerHTML='<pre style="white-space:pre-wrap;padding:16px">読込に失敗しました: '+String(e)+'</pre>';
  }
})();
