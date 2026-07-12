#!/usr/bin/env python3
import argparse, json, time
from pathlib import Path
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve

TOL=1e-10

def check(name,value,expected,ok): return {'name':name,'value':value,'expected':expected,'ok':bool(ok)}
def maxabs(x): return float(np.max(np.abs(x))) if len(x) else 0.0

class UF:
    def __init__(self,n): self.p=np.arange(n,dtype=np.int32)
    def f(self,x):
        if self.p[x]!=x:self.p[x]=self.f(int(self.p[x]))
        return int(self.p[x])
    def u(self,a,b):
        a,b=self.f(a),self.f(b)
        if a!=b:self.p[b]=a
    def labels(self):
        d={};z=np.empty(len(self.p),np.int32)
        for i in range(len(z)):
            r=self.f(i);d.setdefault(r,len(d));z[i]=d[r]
        return z

def main():
    ap=argparse.ArgumentParser();ap.add_argument('mesh');ap.add_argument('--output',default='stage16-metric-solver-validation.json');a=ap.parse_args()
    p=np.load(a.mesh)
    v=p['vertex_local_mm'].astype(np.float64)*1e-3; tri=p['triangles'].astype(np.int32); n=len(tri)
    c=v[tri].mean(axis=1); tp=v[tri]; area=np.abs((tp[:,1,0]-tp[:,0,0])*(tp[:,2,1]-tp[:,0,1])-(tp[:,1,1]-tp[:,0,1])*(tp[:,2,0]-tp[:,0,0]))/2
    ifv=p['internal_face_vertices'].astype(np.int32); ifc=p['internal_face_cells'].astype(np.int32); L=ifc[:,0];R=ifc[:,1]
    fl=np.linalg.norm(v[ifv[:,1]]-v[ifv[:,0]],axis=1); cd=np.linalg.norm(c[R]-c[L],axis=1); base_g=fl/cd
    bfv=p['boundary_face_vertices'].astype(np.int32); bc=p['boundary_face_cell'].astype(np.int32); tags=p['boundary_face_tag'].astype(np.uint8)
    bl=np.linalg.norm(v[bfv[:,1]]-v[bfv[:,0]],axis=1); bm=(v[bfv[:,1]]+v[bfv[:,0]])/2; bd=np.linalg.norm(c[bc]-bm,axis=1); bg=bl/bd
    cut=p['barrage_face_ids'].astype(np.int32); gate=p['barrage_gate_id'].astype(np.uint8); fish=p['fishway_cells'].astype(np.int32)

    def assemble(values,multipliers=None,sources=None):
        g=base_g.copy()
        if multipliers is not None:g*=multipliers
        rr=np.r_[L,L,R,R];cc=np.r_[L,R,R,L];vv=np.r_[g,-g,g,-g]
        rhs=np.zeros(n,dtype=np.float64)
        open_mask=tags>0
        rr=np.r_[rr,bc[open_mask]];cc=np.r_[cc,bc[open_mask]];vv=np.r_[vv,bg[open_mask]]
        for tag,value in values.items():
            m=tags==int(tag);rhs+=np.bincount(bc[m],weights=bg[m]*float(value),minlength=n)
        if sources is not None:rhs+=sources
        return sparse.coo_matrix((vv,(rr,cc)),shape=(n,n)).tocsr(),rhs,g

    def solve(values,multipliers=None,sources=None):
        A,rhs,g=assemble(values,multipliers,sources);t=time.perf_counter();x=spsolve(A,rhs);elapsed=time.perf_counter()-t;res=maxabs(A@x-rhs);return x,g,res,elapsed

    def boundary_flux(x,values):
        out={}
        for tag,value in values.items():
            m=tags==int(tag);out[str(tag)]=float(np.sum(bg[m]*(x[bc[m]]-float(value))))
        return out

    all_const={1:2.75,2:2.75,3:2.75,4:2.75}
    const,g,const_res,const_time=solve(all_const);const_err=maxabs(const-2.75);const_flux=boundary_flux(const,all_const)
    down_values={1:0,2:1,3:1,4:1};up_values={1:1,2:0,3:0,4:0}
    down,g,down_res,down_time=solve(down_values);up,_,up_res,up_time=solve(up_values)
    reversal_field=maxabs(up-(1-down));qd=boundary_flux(down,down_values);qu=boundary_flux(up,up_values);reversal_flux=max(abs(qd[k]+qu[k]) for k in qd)
    mass_down=abs(sum(qd.values()));mass_up=abs(sum(qu.values()))

    closed_mult=np.ones(len(base_g));closed_mult[cut]=0
    closed,gclosed,closed_res,closed_time=solve(down_values,closed_mult);closed_flux=maxabs(gclosed[cut]*(closed[L[cut]]-closed[R[cut]]))
    uf=UF(n);closed_set=set(map(int,cut))
    for i,(l,r) in enumerate(zip(L,R)):
        if i not in closed_set:uf.u(int(l),int(r))
    labels=uf.labels();component_count=len(np.unique(labels));open_components={}
    for tag in (1,2,3,4):open_components[str(tag)]=sorted(np.unique(labels[bc[tags==tag]]).tolist())
    topology_ok=component_count==2 and open_components['3']!=open_components['1'] and open_components['1']==open_components['2']==open_components['4']

    sources=np.zeros(n);sources[fish[0]]=-.05;sources[fish[1]]=.05
    fish_values={1:0,2:0,3:0,4:0};fish_sol,fg,fish_res,fish_time=solve(fish_values,closed_mult,sources);qfish=boundary_flux(fish_sol,fish_values);fish_mass=abs(sum(qfish.values())-float(sources.sum()));fish_cut_flux=maxabs(fg[cut]*(fish_sol[L[cut]]-fish_sol[R[cut]]))

    selected_gate=4;gate_mult=np.ones(len(base_g));gate_mult[cut]=0;gate_mult[cut[gate==selected_gate]]=1
    gate_sol,gg,gate_res,gate_time=solve(down_values,gate_mult);other=cut[gate!=selected_gate];selected=cut[gate==selected_gate]
    closed_gate_flux=maxabs(gg[other]*(gate_sol[L[other]]-gate_sol[R[other]]));selected_gate_activity=float(np.sum(np.abs(gg[selected]*(gate_sol[L[selected]]-gate_sol[R[selected]]))))

    checks=[
      check('all cell areas positive',float(area.min()),'>0',float(area.min())>0),
      check('all face lengths positive',float(min(fl.min(),bl.min())),'>0',min(fl.min(),bl.min())>0),
      check('constant field reproduction',const_err,f'<{TOL}',const_err<TOL),
      check('constant residual',const_res,f'<{TOL}',const_res<TOL),
      check('constant boundary net flux',abs(sum(const_flux.values())),f'<{TOL}',abs(sum(const_flux.values()))<TOL),
      check('boundary reversal field symmetry',reversal_field,f'<{TOL}',reversal_field<TOL),
      check('boundary reversal flux symmetry',reversal_flux,f'<{TOL}',reversal_flux<TOL),
      check('down-state mass balance',mass_down,f'<{TOL}',mass_down<TOL),
      check('up-state mass balance',mass_up,f'<{TOL}',mass_up<TOL),
      check('closed barrage flux',closed_flux,f'<{TOL}',closed_flux<TOL),
      check('closed barrage creates two components',component_count,2,topology_ok),
      check('fishway source sum',abs(float(sources.sum())),f'<{TOL}',abs(float(sources.sum()))<TOL),
      check('fishway external mass balance',fish_mass,f'<{TOL}',fish_mass<TOL),
      check('fishway does not leak through closed barrage',fish_cut_flux,f'<{TOL}',fish_cut_flux<TOL),
      check('nonselected gates remain closed',closed_gate_flux,f'<{TOL}',closed_gate_flux<TOL),
      check('selected gate is hydraulically active',selected_gate_activity,'>0',selected_gate_activity>0),
      check('all linear residuals',max(const_res,down_res,up_res,closed_res,fish_res,gate_res),'<1e-9',max(const_res,down_res,up_res,closed_res,fish_res,gate_res)<1e-9),
    ]
    report={'schema':'onga-stage16-actual-metric-mesh-solver-validation-v1','status':'passed' if all(x['ok'] for x in checks) else 'failed','counts':{'cells':n,'internalFaces':len(L),'boundaryFaces':len(bc),'barrageFaces':len(cut)},'diagnostics':{'totalAreaM2':float(area.sum()),'constantError':const_err,'reversalFieldError':reversal_field,'reversalFluxError':reversal_flux,'massBalanceDown':mass_down,'massBalanceUp':mass_up,'closedBarrageFlux':closed_flux,'closedComponents':component_count,'openBoundaryComponents':open_components,'fishwayCells':fish.tolist(),'fishwayMassBalance':fish_mass,'selectedGate':selected_gate,'selectedGateActivity':selected_gate_activity,'solveSeconds':{'constant':const_time,'down':down_time,'up':up_time,'closed':closed_time,'fishway':fish_time,'singleGate':gate_time}},'safeguards':{'syntheticBoundaryValuesOnly':True,'connectedToPublicSimulator':False,'approvedWaterGeometryChanged':False,'physicalValuesAssigned':False,'calibrationPerformed':False},'checks':checks}
    Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['status']!='passed':raise RuntimeError('Stage 16 actual mesh solver verification failed')
if __name__=='__main__':main()
