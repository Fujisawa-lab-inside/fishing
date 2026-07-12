#!/usr/bin/env python3
import argparse,json
from pathlib import Path
import numpy as np
G=9.80665

def check(n,v,e,ok):return {'name':n,'value':v,'expected':e,'ok':bool(ok)}
def maxabs(x):return float(np.max(np.abs(x))) if np.size(x) else 0.0

def phys(U,n):
 h=np.maximum(U[:,0],0);un=np.divide(U[:,1]*n[:,0]+U[:,2]*n[:,1],h,out=np.zeros_like(h),where=h>1e-12);p=.5*G*h*h
 return np.stack([U[:,1]*n[:,0]+U[:,2]*n[:,1],U[:,1]*un+p*n[:,0],U[:,2]*un+p*n[:,1]],axis=1),un

def rusanov(UL,UR,n):
 FL,uL=phys(UL,n);FR,uR=phys(UR,n);s=np.maximum(np.abs(uL)+np.sqrt(G*np.maximum(UL[:,0],0)),np.abs(uR)+np.sqrt(G*np.maximum(UR[:,0],0)));return .5*(FL+FR)-.5*s[:,None]*(UR-UL)

def hydro(UL,UR,zL,zR,n):
 etaL=UL[:,0]+zL;etaR=UR[:,0]+zR;zi=np.maximum(zL,zR);hL=np.maximum(0,etaL-zi);hR=np.maximum(0,etaR-zi);RL=np.zeros_like(UL);RR=np.zeros_like(UR);RL[:,0]=hL;RR[:,0]=hR
 ml=UL[:,0]>1e-12;mr=UR[:,0]>1e-12;RL[ml,1:]=UL[ml,1:]*(hL[ml]/UL[ml,0])[:,None];RR[mr,1:]=UR[mr,1:]*(hR[mr]/UR[mr,0])[:,None]
 F=rusanov(RL,RR,n);cl=.5*G*(UL[:,0]**2-hL**2);cr=.5*G*(UR[:,0]**2-hR**2);FL=F.copy();FR=F.copy();FL[:,1]+=cl*n[:,0];FL[:,2]+=cl*n[:,1];FR[:,1]+=cr*n[:,0];FR[:,2]+=cr*n[:,1];return F[:,0],FL[:,1:],FR[:,1:],hL,hR

def main():
 ap=argparse.ArgumentParser();ap.add_argument('mesh');ap.add_argument('--output',default='stage16-actual-mesh-well-balanced-validation.json');a=ap.parse_args();p=np.load(a.mesh);v=p['vertex_local_mm'].astype(float)*1e-3;tri=p['triangles'].astype(int);pts=v[tri];c=pts.mean(1);area=np.abs((pts[:,1,0]-pts[:,0,0])*(pts[:,2,1]-pts[:,0,1])-(pts[:,1,1]-pts[:,0,1])*(pts[:,2,0]-pts[:,0,0]))/2;n=len(tri)
 ifv=p['internal_face_vertices'].astype(int);ifc=p['internal_face_cells'].astype(int);L=ifc[:,0];R=ifc[:,1];e=v[ifv[:,1]]-v[ifv[:,0]];le=np.linalg.norm(e,axis=1);nn=np.column_stack([e[:,1],-e[:,0]])/le[:,None];nn[np.einsum('ij,ij->i',nn,c[R]-c[L])<0]*=-1
 bfv=p['boundary_face_vertices'].astype(int);bc=p['boundary_face_cell'].astype(int);e=v[bfv[:,1]]-v[bfv[:,0]];lb=np.linalg.norm(e,axis=1);bn=np.column_stack([e[:,1],-e[:,0]])/lb[:,None];mid=(v[bfv[:,0]]+v[bfv[:,1]])/2;bn[np.einsum('ij,ij->i',bn,mid-c[bc])<0]*=-1
 def residual(U,z):
  m,ml,mr,hL,hR=hydro(U[L],U[R],z[L],z[R],nn);res=np.zeros_like(U);np.add.at(res[:,0],L,m*le);np.add.at(res[:,0],R,-m*le);np.add.at(res[:,1:],L,ml*le[:,None]);np.add.at(res[:,1:],R,-mr*le[:,None]);Ub=U[bc].copy();dot=Ub[:,1]*bn[:,0]+Ub[:,2]*bn[:,1];Ug=Ub.copy();Ug[:,1]=Ub[:,1]-2*dot*bn[:,0];Ug[:,2]=Ub[:,2]-2*dot*bn[:,1];mb,mbl,mbr,_,_=hydro(Ub,Ug,z[bc],z[bc],bn);np.add.at(res[:,0],bc,mb*lb);np.add.at(res[:,1:],bc,mbl*lb[:,None]);return res,(hL,hR)
 x=(c[:,0]-c[:,0].min())/np.ptp(c[:,0]);y=(c[:,1]-c[:,1].min())/np.ptp(c[:,1]);z=.3*x+.15*np.sin(2*np.pi*y);eta=2.;U=np.zeros((n,3));U[:,0]=eta-z;res,recon=residual(U,z);lake_err=maxabs(res);mass_sum=abs(float(np.sum(res[:,0])));min_recon=float(min(recon[0].min(),recon[1].min()))
 zshift=z+100;reshift,_=residual(U,zshift);datum_err=maxabs(reshift-res)
 flat=np.zeros(n);Uflat=np.zeros((n,3));Uflat[:,0]=2;flat_res,_=residual(Uflat,flat);flat_err=maxabs(flat_res)
 zdry=.6*x+.8*y;etad=.7;Ud=np.zeros((n,3));Ud[:,0]=np.maximum(0,etad-zdry);rd,recd=residual(Ud,zdry);dry_finite=bool(np.isfinite(rd).all());dry_min=float(min(recd[0].min(),recd[1].min()));dry_mass=abs(float(np.sum(rd[:,0])))
 Um=np.zeros((n,3));Um[:,0]=1+.2*np.exp(-((x-.5)**2+(y-.5)**2)/.05);Um[:,1]=.6*Um[:,0];Um[:,2]=-.3*Um[:,0];rough=.03+.01*x;dt=.5;speed=np.hypot(Um[:,1],Um[:,2])/Um[:,0];factor=1+dt*G*rough**2*speed/np.maximum(Um[:,0],1e-12)**(4/3);M=Um.copy();M[:,1]/=factor;M[:,2]/=factor;before=np.hypot(Um[:,1],Um[:,2]);after=np.hypot(M[:,1],M[:,2]);friction_nonincrease=float(np.max(after-before));direction=np.max(np.abs(Um[:,1]*M[:,2]-Um[:,2]*M[:,1]));depth_err=maxabs(M[:,0]-Um[:,0]);volume_err=abs(float(np.sum(M[:,0]*area)-np.sum(Um[:,0]*area)))
 checks=[check('variable-bed lake at rest residual',lake_err,'<1e-8',lake_err<1e-8),check('variable-bed internal mass balance',mass_sum,'<1e-10',mass_sum<1e-10),check('nonnegative reconstructed depth',min_recon,'>=0',min_recon>=0),check('vertical datum invariance',datum_err,'<1e-8',datum_err<1e-8),check('flat-bed lake at rest residual',flat_err,'<1e-8',flat_err<1e-8),check('dry reconstruction finite',dry_finite,True,dry_finite),check('dry reconstruction nonnegative',dry_min,'>=0',dry_min>=0),check('dry reconstruction global mass balance',dry_mass,'<1e-10',dry_mass<1e-10),check('Manning momentum nonincrease',friction_nonincrease,'<=0',friction_nonincrease<=1e-12),check('Manning direction preservation',direction,'<1e-12',direction<1e-12),check('Manning depth unchanged',depth_err,'<1e-12',depth_err<1e-12),check('Manning volume unchanged',volume_err,'<1e-8',volume_err<1e-8)]
 report={'schema':'onga-stage16-actual-mesh-well-balanced-validation-v1','status':'passed' if all(q['ok'] for q in checks) else 'failed','counts':{'cells':n,'internalFaces':len(L),'boundaryFaces':len(bc)},'diagnostics':{'lakeAtRestResidual':lake_err,'datumShiftError':datum_err,'dryMinimumReconstructedDepth':dry_min,'dryGlobalMassBalance':dry_mass,'frictionMomentumIncrease':friction_nonincrease,'frictionDirectionError':direction,'frictionVolumeError':volume_err},'safeguards':{'syntheticBathymetryOnly':True,'syntheticRoughnessOnly':True,'connectedToPublicSimulator':False,'approvedWaterGeometryChanged':False,'physicalValuesAssigned':False,'calibrationPerformed':False},'checks':checks};Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2));
 if report['status']!='passed':raise RuntimeError('actual mesh well-balanced verification failed')
if __name__=='__main__':main()
