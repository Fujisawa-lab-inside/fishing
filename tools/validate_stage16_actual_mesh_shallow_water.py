#!/usr/bin/env python3
import argparse,json,math
from pathlib import Path
import numpy as np
G=9.80665

def check(n,v,e,ok):return {'name':n,'value':v,'expected':e,'ok':bool(ok)}
def maxabs(x):return float(np.max(np.abs(x))) if np.size(x) else 0.0
class UF:
 def __init__(self,n):self.p=np.arange(n,dtype=np.int32)
 def f(self,x):
  if self.p[x]!=x:self.p[x]=self.f(int(self.p[x]))
  return int(self.p[x])
 def u(self,a,b):
  a,b=self.f(a),self.f(b)
  if a!=b:self.p[b]=a
 def labels(self):
  d={};z=np.empty(len(self.p),np.int32)
  for i in range(len(z)):r=self.f(i);d.setdefault(r,len(d));z[i]=d[r]
  return z

def flux(h,hu,hv,nx,ny):
 h=np.maximum(h,0);un=np.divide(hu*nx+hv*ny,h,out=np.zeros_like(h),where=h>1e-12);p=.5*G*h*h
 return np.stack([hu*nx+hv*ny,hu*un+p*nx,hv*un+p*ny],axis=-1),un

def rusanov(UL,UR,n):
 FL,uL=flux(UL[:,0],UL[:,1],UL[:,2],n[:,0],n[:,1]);FR,uR=flux(UR[:,0],UR[:,1],UR[:,2],n[:,0],n[:,1]);s=np.maximum(np.abs(uL)+np.sqrt(G*np.maximum(UL[:,0],0)),np.abs(uR)+np.sqrt(G*np.maximum(UR[:,0],0)))
 return .5*(FL+FR)-.5*s[:,None]*(UR-UL),s

def reflect(U,n):
 R=U.copy();dot=U[:,1]*n[:,0]+U[:,2]*n[:,1];R[:,1]=U[:,1]-2*dot*n[:,0];R[:,2]=U[:,2]-2*dot*n[:,1];return R

def main():
 ap=argparse.ArgumentParser();ap.add_argument('mesh');ap.add_argument('--output',default='stage16-actual-mesh-swe-validation.json');a=ap.parse_args();p=np.load(a.mesh)
 v=p['vertex_local_mm'].astype(float)*1e-3;tri=p['triangles'].astype(int);ncell=len(tri);pts=v[tri];cent=pts.mean(1);area=np.abs((pts[:,1,0]-pts[:,0,0])*(pts[:,2,1]-pts[:,0,1])-(pts[:,1,1]-pts[:,0,1])*(pts[:,2,0]-pts[:,0,0]))/2
 ifv=p['internal_face_vertices'].astype(int);ifc=p['internal_face_cells'].astype(int);L=ifc[:,0];R=ifc[:,1];ev=v[ifv[:,1]]-v[ifv[:,0]];ilen=np.linalg.norm(ev,axis=1);normal=np.column_stack([ev[:,1],-ev[:,0]])/ilen[:,None];flip=np.einsum('ij,ij->i',normal,cent[R]-cent[L])<0;normal[flip]*=-1
 bfv=p['boundary_face_vertices'].astype(int);bc=p['boundary_face_cell'].astype(int);bev=v[bfv[:,1]]-v[bfv[:,0]];blen=np.linalg.norm(bev,axis=1);bn=np.column_stack([bev[:,1],-bev[:,0]])/blen[:,None];mid=(v[bfv[:,0]]+v[bfv[:,1]])/2;flip=np.einsum('ij,ij->i',bn,mid-cent[bc])<0;bn[flip]*=-1
 cut=p['barrage_face_ids'].astype(int);gate=p['barrage_gate_id'].astype(int);fish=p['fishway_cells'].astype(int)
 def residual(U,active=None):
  if active is None:active=np.ones(len(L),bool)
  F,s=rusanov(U[L],U[R],normal);F*=active[:,None];res=np.zeros_like(U);np.add.at(res,L,F*ilen[:,None]);np.add.at(res,R,-F*ilen[:,None]);UG=reflect(U[bc],bn);FB,sb=rusanov(U[bc],UG,bn);np.add.at(res,bc,FB*blen[:,None]);return res,s
 def dt_cfl(U,cfl=.18,active=None):
  if active is None:active=np.ones(len(L),bool)
  _,s=rusanov(U[L],U[R],normal);den=np.zeros(ncell);np.add.at(den,L,s*ilen*active);np.add.at(den,R,s*ilen*active);UG=reflect(U[bc],bn);_,sb=rusanov(U[bc],UG,bn);np.add.at(den,bc,sb*blen);return float(cfl*np.min(area/np.maximum(den,1e-30)))
 def advance(U,dt,active=None,source=None):
  res,_=residual(U,active);rhs=-res
  if source is not None:rhs+=source
  return U+dt*rhs/area[:,None]
 def volume(U,mask=None):return float(np.sum(U[:,0]*area)) if mask is None else float(np.sum(U[mask,0]*area[mask]))
 closure=np.zeros((ncell,2));np.add.at(closure,L,normal*ilen[:,None]);np.add.at(closure,R,-normal*ilen[:,None]);np.add.at(closure,bc,bn*blen[:,None]);closure_err=maxabs(closure)
 lake=np.zeros((ncell,3));lake[:,0]=2;lake_res,_=residual(lake);lake_err=maxabs(lake_res)
 r2=np.sum((cent-cent.mean(0))**2,axis=1);scale=np.quantile(r2,.25);U=np.zeros((ncell,3));U[:,0]=1+.15*np.exp(-r2/max(scale,1));dt=dt_cfl(U);v0=volume(U);U1=advance(U,dt);mass_err=abs(volume(U1)-v0);min_depth=float(U1[:,0].min());finite=bool(np.isfinite(U1).all())
 active=np.ones(len(L),bool);active[cut]=False;uf=UF(ncell)
 for i,(l,r) in enumerate(zip(L,R)):
  if active[i]:uf.u(int(l),int(r))
 labels=uf.labels();comps=np.unique(labels);up=int(labels[fish[0]]);down=int(labels[fish[1]]);Uc=np.zeros((ncell,3));Uc[:,0]=1;Uc[labels==up,0]+=.2*np.exp(-np.sum((cent[labels==up]-cent[fish[0]])**2,axis=1)/10000);dtc=dt_cfl(Uc,active=active);before={int(k):volume(Uc,labels==k) for k in comps};Uc1=advance(Uc,dtc,active);after={int(k):volume(Uc1,labels==k) for k in comps};component_err=max(abs(after[k]-before[k]) for k in before)
 selected=4;one=np.ones(len(L),bool);one[cut]=False;one[cut[gate==selected]]=True;Ug=np.zeros((ncell,3));Ug[:,0]=1;Ug[labels==up,0]=1.2;dtg=dt_cfl(Ug,active=one);gate_flux,_=rusanov(Ug[L[cut]],Ug[R[cut]],normal[cut]);integrated=gate_flux[:,0]*ilen[cut]*one[cut];open_exchange=float(np.sum(np.abs(integrated[gate==selected])));closed_exchange=float(np.max(np.abs(integrated[gate!=selected])));vg0=volume(Ug);Ug1=advance(Ug,dtg,one);gate_mass=abs(volume(Ug1)-vg0)
 Uf=np.zeros((ncell,3));Uf[:,0]=1;Q=.05;src=np.zeros_like(Uf);src[fish[0],0]-=Q;src[fish[1],0]+=Q;theta=math.radians(45);speed=.5;mx=Q*speed*math.sin(theta);my=Q*speed*math.cos(theta);src[fish[0],1]-=mx;src[fish[1],1]+=mx;src[fish[0],2]-=my;src[fish[1],2]+=my;dtf=min(dt_cfl(Uf,active=active),.1);bf={k:volume(Uf,labels==k) for k in comps};Uf1=advance(Uf,dtf,active,src);af={k:volume(Uf1,labels==k) for k in comps};fish_global=abs(volume(Uf1)-volume(Uf));fish_up=abs((af[up]-bf[up])+Q*dtf);fish_down=abs((af[down]-bf[down])-Q*dtf);fish_min=float(Uf1[:,0].min())
 checks=[check('metric cell closure',closure_err,'<1e-9',closure_err<1e-9),check('lake at rest residual',lake_err,'<1e-8',lake_err<1e-8),check('closed-domain mass conservation',mass_err,'<1e-8',mass_err<1e-8),check('closed-domain finite state',finite,True,finite),check('closed-domain positive depth',min_depth,'>0',min_depth>0),check('closed barrage components',len(comps),2,len(comps)==2),check('closed barrage component mass conservation',component_err,'<1e-8',component_err<1e-8),check('nonselected gate flux',closed_exchange,'<1e-12',closed_exchange<1e-12),check('selected gate exchange active',open_exchange,'>0',open_exchange>0),check('single-gate global mass conservation',gate_mass,'<1e-8',gate_mass<1e-8),check('fishway global mass conservation',fish_global,'<1e-8',fish_global<1e-8),check('fishway upstream transfer',fish_up,'<1e-8',fish_up<1e-8),check('fishway downstream transfer',fish_down,'<1e-8',fish_down<1e-8),check('fishway positive depth',fish_min,'>0',fish_min>0)]
 report={'schema':'onga-stage16-actual-mesh-shallow-water-validation-v1','status':'passed' if all(x['ok'] for x in checks) else 'failed','counts':{'cells':ncell,'internalFaces':len(L),'boundaryFaces':len(bc),'barrageFaces':len(cut)},'diagnostics':{'geometricClosureError':closure_err,'lakeAtRestResidual':lake_err,'smoothStepDt':dt,'smoothMassError':mass_err,'smoothMinimumDepth':min_depth,'closedComponents':len(comps),'componentMassError':component_err,'singleGate':selected,'singleGateExchange':open_exchange,'closedGateFlux':closed_exchange,'singleGateMassError':gate_mass,'fishwayDt':dtf,'fishwayGlobalMassError':fish_global,'fishwayUpstreamError':fish_up,'fishwayDownstreamError':fish_down},'safeguards':{'flatSyntheticBathymetryOnly':True,'syntheticStatesOnly':True,'connectedToPublicSimulator':False,'approvedWaterGeometryChanged':False,'physicalValuesAssigned':False,'calibrationPerformed':False},'checks':checks};Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2));
 if report['status']!='passed':raise RuntimeError('actual mesh shallow-water verification failed')
if __name__=='__main__':main()
