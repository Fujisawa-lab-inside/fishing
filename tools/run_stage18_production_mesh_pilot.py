#!/usr/bin/env python3
import argparse, json, math, resource, sys, time
from pathlib import Path

RETIRED_CLI_MESSAGE = (
 'The v1 production-mesh pilot runner is retired after the Ashiya bridge geometry correction; '
 'no numerical cases were started.'
)

if __name__=='__main__':
 print(RETIRED_CLI_MESSAGE,file=sys.stderr)
 raise SystemExit(2)

import numpy as np
G=9.80665

def reject_retired_cli():
 raise RuntimeError(RETIRED_CLI_MESSAGE)

class NumericalStateError(RuntimeError):
 def __init__(self,message,nan_count,negative_depth_count):
  super().__init__(message);self.nan_count=nan_count;self.negative_depth_count=negative_depth_count

def peak_rss_mib():
 rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss;return rss/(1024*1024) if sys.platform=='darwin' else rss/1024

def geom(mesh):
 p=np.load(mesh);v=p['vertex_local_mm'].astype(float)*1e-3;tri=p['triangles'].astype(int);pts=v[tri];cent=pts.mean(1)
 area=np.abs((pts[:,1,0]-pts[:,0,0])*(pts[:,2,1]-pts[:,0,1])-(pts[:,1,1]-pts[:,0,1])*(pts[:,2,0]-pts[:,0,0]))/2
 ifv=p['internal_face_vertices'].astype(int);ifc=p['internal_face_cells'].astype(int);L=ifc[:,0];R=ifc[:,1]
 ev=v[ifv[:,1]]-v[ifv[:,0]];ilen=np.linalg.norm(ev,axis=1);n=np.column_stack([ev[:,1],-ev[:,0]])/ilen[:,None];n[np.einsum('ij,ij->i',n,cent[R]-cent[L])<0]*=-1
 bfv=p['boundary_face_vertices'].astype(int);bc=p['boundary_face_cell'].astype(int);bev=v[bfv[:,1]]-v[bfv[:,0]];blen=np.linalg.norm(bev,axis=1);bn=np.column_stack([bev[:,1],-bev[:,0]])/blen[:,None];mid=(v[bfv[:,0]]+v[bfv[:,1]])/2;bn[np.einsum('ij,ij->i',bn,mid-cent[bc])<0]*=-1
 return p,cent,area,L,R,ilen,n,bc,blen,bn

def phys(U,n):
 h=np.maximum(U[:,0],1e-12);hu=U[:,1];hv=U[:,2];un=(hu*n[:,0]+hv*n[:,1])/h;p=.5*G*h*h
 return np.column_stack((hu*n[:,0]+hv*n[:,1],hu*un+p*n[:,0],hv*un+p*n[:,1])),un

def rus(UL,UR,n):
 FL,uL=phys(UL,n);FR,uR=phys(UR,n);s=np.maximum(np.abs(uL)+np.sqrt(G*np.maximum(UL[:,0],0)),np.abs(uR)+np.sqrt(G*np.maximum(UR[:,0],0)))
 return .5*(FL+FR)-.5*s[:,None]*(UR-UL),s

def refl(U,n):
 R=U.copy();q=U[:,1]*n[:,0]+U[:,2]*n[:,1];R[:,1]-=2*q*n[:,0];R[:,2]-=2*q*n[:,1];return R

def run_case_result(case,steps,g,include_fields=False):
 if not isinstance(steps,int) or steps<=0: raise ValueError('steps must be a positive integer')
 p,cent,area,L,R,ilen,n,bc,blen,bn=g;ncell=len(area);active=np.ones(len(L),bool);cut=p['barrage_face_ids'].astype(int);gate=p['barrage_gate_id'].astype(int)
 scenario=case['barrage']['scenario'];active[cut]=False
 frac={'fully_closed':0.0,'uniform_25_percent':.25,'uniform_50_percent':.5,'uniform_100_percent':1.0}[scenario]
 if frac>0: active[cut]=True
 depth=max(.5,float(case['bathymetry']['mainstemMeanDepthM']));r2=np.sum((cent-cent.mean(0))**2,axis=1);scale=max(float(np.quantile(r2,.25)),1.0)
 U=np.zeros((ncell,3));U[:,0]=depth*(1+.015*np.exp(-r2/scale));phase=float(case['boundaries']['M']['phaseShiftMinutes'])*math.pi/180;U[:,1]=U[:,0]*.015*math.cos(phase);U[:,2]=U[:,0]*.015*math.sin(phase)
 v0=float(np.sum(U[:,0]*area));maxc=0.;mind=float(U[:,0].min());nan=neg=0;sim_time=0.;dt_min=math.inf;dt_max=0.
 fish=p['fishway_cells'].astype(int);fish_on=case['fishway']['mode']!='disabled';qfish=1e-4*float(case['fishway']['effectiveDischargeCoefficient'])*float(case['fishway']['effectiveAreaM2'])
 for _ in range(steps):
  F,s=rus(U[L],U[R],n);F*=active[:,None];den=np.zeros(ncell);np.add.at(den,L,s*ilen*active);np.add.at(den,R,s*ilen*active)
  UG=refl(U[bc],bn);FB,sb=rus(U[bc],UG,bn);np.add.at(den,bc,sb*blen);dt=.12*float(np.min(area/np.maximum(den,1e-30)));cfl=.12;maxc=max(maxc,cfl);sim_time+=dt;dt_min=min(dt_min,dt);dt_max=max(dt_max,dt)
  res=np.zeros_like(U);np.add.at(res,L,F*ilen[:,None]);np.add.at(res,R,-F*ilen[:,None]);np.add.at(res,bc,FB*blen[:,None]);rhs=-res
  if fish_on:
   q=min(qfish,0.02*U[fish[0],0]*area[fish[0]]/max(dt,1e-12));rhs[fish[0],0]-=q;rhs[fish[1],0]+=q
  Un=U+dt*rhs/area[:,None]
  ncoef=float(case['roughness']['manningOpenChannel']);h=np.maximum(Un[:,0],1e-8);vel=np.sqrt(Un[:,1]**2+Un[:,2]**2)/h;damp=1+dt*G*ncoef*ncoef*vel/np.power(h,4/3);Un[:,1]/=damp;Un[:,2]/=damp
  nan+=int(np.size(Un)-np.isfinite(Un).sum());neg+=int(np.sum(Un[:,0]<0));
  if nan or neg: raise NumericalStateError('nonfinite or negative depth',nan,neg)
  U=Un;mind=min(mind,float(U[:,0].min()))
 v1=float(np.sum(U[:,0]*area));result={'massBalanceError':abs(v1-v0)/max(abs(v0),1.0),'maxCfl':maxc,'minimumDepthM':mind,'nanCount':nan,'negativeDepthCount':neg,'stepsCompleted':steps,'simulatedTimeSeconds':sim_time,'minimumTimeStepSeconds':dt_min,'maximumTimeStepSeconds':dt_max}
 if include_fields:
  h=U[:,0].copy();result['waterDepthM']=h;result['velocityUms']=np.divide(U[:,1],h,out=np.zeros_like(h),where=h>1e-12);result['velocityVms']=np.divide(U[:,2],h,out=np.zeros_like(h),where=h>1e-12)
 return result

def run_case(case,steps,g):
 result=run_case_result(case,steps,g)
 return result['massBalanceError'],result['maxCfl'],result['minimumDepthM']

def main():
 reject_retired_cli()
 ap=argparse.ArgumentParser();ap.add_argument('mesh');ap.add_argument('ensemble');ap.add_argument('config');ap.add_argument('tier');ap.add_argument('--output',required=True);a=ap.parse_args()
 cfg=json.loads(Path(a.config).read_text());ens=json.loads(Path(a.ensemble).read_text());
 if cfg.get('schema')!='onga-stage18-production-mesh-pilot-v1': raise RuntimeError('unsupported pilot config schema')
 if cfg.get('geometry')!={'approvedWaterPixelCount':679791,'metricMeshCellCount':50333,'frozen':True}: raise RuntimeError('pilot geometry contract mismatch')
 if cfg.get('full64CaseRun',{}).get('enabled') is not False: raise RuntimeError('pilot runner cannot authorize full64 execution')
 tier=next(x for x in cfg['tiers'] if x['id']==a.tier)
 if tier['caseCount']>16: raise RuntimeError('pilot runner is limited to at most 16 cases')
 if ens.get('schema')!='onga-stage18-inference-ensemble-v1': raise RuntimeError('unsupported ensemble schema')
 if ens.get('geometry')!=cfg['geometry']: raise RuntimeError('ensemble geometry mismatch')
 g=geom(a.mesh)
 if len(g[2])!=50333: raise RuntimeError(f"production mesh must contain 50333 cells, got {len(g[2])}")
 if len(ens.get('cases',[]))<tier['caseCount']: raise RuntimeError(f"ensemble has {len(ens.get('cases',[]))} cases; {tier['caseCount']} required")
 selected=ens['cases'][:tier['caseCount']]
 if len({case.get('caseId') for case in selected})!=tier['caseCount']: raise RuntimeError('pilot case IDs must be unique')
 start=time.perf_counter();fail=[];errs=[];cfls=[];mins=[];nan=neg=0
 for case in selected:
  try:
   e,c,m=run_case(case,tier['maxSteps'],g);errs.append(e);cfls.append(c);mins.append(m)
  except Exception as ex:
   nan+=int(getattr(ex,'nan_count',0));neg+=int(getattr(ex,'negative_depth_count',0));fail.append({'caseId':case['caseId'],'reason':str(ex)})
 wall=time.perf_counter()-start;rss=peak_rss_mib()
 report={'schema':'onga-stage18-pilot-run-report-v1','tierId':a.tier,'geometry':{'approvedWaterPixelCount':679791,'metricMeshCellCount':50333},'requestedCaseCount':tier['caseCount'],'completedCaseCount':len(errs),'failedCaseCount':len(fail),'wallSeconds':wall,'peakResidentMemoryMiB':rss,'maxCfl':max(cfls,default=0.0),'maxAbsoluteMassBalanceError':max(errs,default=math.inf),'minimumDepthM':min(mins,default=0.0),'nanCount':nan,'negativeDepthCount':neg,'failures':fail,'classification':'synthetic_inference_runtime_and_numerical_stability_evidence_only'}
 Path(a.output).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
 if fail: raise RuntimeError(f'{len(fail)} pilot cases failed')
if __name__=='__main__':main()
