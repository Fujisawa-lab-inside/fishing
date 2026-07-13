#!/usr/bin/env python3
import argparse, hashlib, json, math, platform
from pathlib import Path
import numpy as np
import triangle as tr
from affine import Affine
from rasterio.features import shapes
from shapely.geometry import shape

CIRC=40075016.68557849
RAW_MESH_KEYS=('vertices','triangles','segments','segment_markers')
PACKAGE_KEYS=('vertex_local_mm','vertex_image_millipixel','triangles','internal_face_vertices','internal_face_cells','boundary_face_vertices','boundary_face_cell','boundary_face_tag','barrage_face_ids','barrage_gate_id','fishway_cells','fishway_components')

def j(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def h(a): return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()

def load_water(root, path):
    m=j(path); rows=[None]*int(m['height'])
    for rel in m['chunks']:
        p=root/rel[2:] if rel.startswith('./data/') else Path(path).parent/rel
        c=j(p); s=int(c['startRow'])
        for k,r in enumerate(c['rows']):
            y=s+k
            if rows[y] is not None: raise RuntimeError(f'duplicate row {y}')
            rows[y]=r
    if not all(isinstance(r,list) for r in rows): raise RuntimeError('missing rows')
    w=np.zeros((int(m['height']),int(m['width'])),np.uint8); count=0
    for y,runs in enumerate(rows):
        for k in range(0,len(runs),2):
            x0,x1=map(int,runs[k:k+2]); w[y,x0:x1+1]=1; count+=x1-x0+1
    if count!=int(m['pixelCount']): raise RuntimeError('water count mismatch')
    return m,w

def mesh_from_water(w,c):
    gs=[shape(g) for g,v in shapes(w,mask=w.astype(bool),connectivity=4,transform=Affine.identity()) if int(v)==1]
    if len(gs)!=1: raise RuntimeError('water polygon count mismatch')
    b=np.asarray(gs[0].simplify(.5,preserve_topology=True).exterior.coords[:-1],float)
    vs=b.tolist(); ss=[[i,(i+1)%len(b)] for i in range(len(b))]; mm=[1]*len(b)
    p=c['barrageHardConstraint']; q=len(vs); vs += [p['endpoint0Pixel'],p['endpoint1Pixel']]; ss.append([q,q+1]); mm.append(3)
    x=tr.triangulate({'vertices':np.asarray(vs,float),'segments':np.asarray(ss,np.int32),'segment_markers':np.asarray(mm,np.int32).reshape(-1,1)},'pq30a30')
    return {k:np.asarray(x[k],dtype=np.float64 if k=='vertices' else np.int32).reshape(-1) if k=='segment_markers' else np.asarray(x[k],dtype=np.float64 if k=='vertices' else np.int32) for k in ['vertices','triangles','segments','segment_markers']}

def bary(p,a,b,c):
    d=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
    if abs(d)<1e-12:return None
    u=((b[1]-c[1])*(p[0]-c[0])+(c[0]-b[0])*(p[1]-c[1]))/d
    v=((c[1]-a[1])*(p[0]-c[0])+(a[0]-c[0])*(p[1]-c[1]))/d
    return np.array([u,v,1-u-v])
def mmap(p,m,s,t):
    a=m['anchors']
    for tri in m['triangles']:
        src=[np.asarray(a[i][s],float) for i in tri]; q=bary(p,*src)
        if q is not None and np.all(q>=-1e-7) and np.all(q<=1+1e-7):
            dst=[np.asarray(a[i][t],float) for i in tri]; return q[0]*dst[0]+q[1]*dst[1]+q[2]*dst[2]
    return np.asarray(p,float)
def coords(cs):
    g=cs['geographic']; T=g['transform']; M=g['controlMesh']; a,b,tx,ty=map(float,[T['a'],T['b'],T['tx'],T['ty']]); det=a*a+b*b
    def image_world(p):
        q=mmap(np.asarray(p,float),M,'targetImagePixel','sourceBasePixel'); return np.array([tx+a*q[0]-b*q[1],ty+b*q[0]+a*q[1]])
    def ll_image(lat,lng):
        z=max(-85.05112878,min(85.05112878,float(lat))); s=math.sin(math.radians(z)); X=(float(lng)+180)/360*CIRC; Y=(.5-math.log((1+s)/(1-s))/(4*math.pi))*CIRC; dx=X-tx;dy=Y-ty
        return mmap(np.array([(a*dx+b*dy)/det,(-b*dx+a*dy)/det]),M,'sourceBasePixel','targetImagePixel')
    return image_world,ll_image

def edges(v,t):
    d={}
    for k,x in enumerate(t):
        for a,b in ((x[0],x[1]),(x[1],x[2]),(x[2],x[0])): d.setdefault(tuple(sorted((int(a),int(b)))),[]).append(k)
    c=v[t].mean(1); I=[];B=[]
    for e,adj in d.items():
        p0,p1=v[list(e)]; L=float(np.linalg.norm(p1-p0)); m=(p0+p1)/2
        if len(adj)==2:I.append((e[0],e[1],adj[0],adj[1],L,float(np.linalg.norm(c[adj[1]]-c[adj[0]])),m[0],m[1]))
        elif len(adj)==1:B.append((e[0],e[1],adj[0],L,m[0],m[1]))
        else:raise RuntimeError('nonmanifold edge')
    return d,np.asarray(I,float),np.asarray(B,float),c

def tags(m,B):
    q=B[:,4:6]; ids=np.arange(len(B),dtype=np.int32); z=np.zeros(len(B),np.uint8); used=np.zeros(len(B),bool); out={}; code={'M':1,'N':2,'O':3,'G':4}
    for x in m['openBoundaries']:
        a,b=map(float,x['pixelRun']); r=(q[:,0]>=a-.5)&(q[:,0]<=b+.5); y=q[r,1]; target=float(y.min() if x['edge']=='top' else y.max()); s=r&(np.abs(q[:,1]-target)<=.75)
        if np.any(used&s):raise RuntimeError('boundary overlap')
        used[s]=1; z[s]=code[x['id']]; out[x['id']]=ids[s]
    return z,out

def barrage(w,M,I,c):
    pairs=M['segments'][M['segment_markers']==3]; pts=M['vertices'][np.unique(pairs)]; o=pts.mean(0); _,E=np.linalg.eigh(np.cov(pts-o,rowvar=False)); ax=E[:,-1]
    ts=np.linspace(-1000,1000,40001); s=o+ts[:,None]*ax; x=np.floor(s[:,0]).astype(int); y=np.floor(s[:,1]).astype(int); inside=(x>=0)&(x<w.shape[1])&(y>=0)&(y<w.shape[0]); wet=np.zeros(len(s),bool);wet[inside]=w[y[inside],x[inside]].astype(bool); k=np.argmin(abs(ts));lo=hi=k
    while lo and wet[lo-1]:lo-=1
    while hi+1<len(wet) and wet[hi+1]:hi+=1
    p0,p1=s[lo],s[hi]; v=p1-p0
    em={tuple(sorted((int(r[0]),int(r[1])))):i for i,r in enumerate(I)}; marker=np.unique([em[tuple(sorted(map(int,e)))] for e in pairs])
    L=I[:,2].astype(int);R=I[:,3].astype(int);A=c[L];D=c[R];r=D-A; cross=lambda a,b:a[...,0]*b[...,1]-a[...,1]*b[...,0]; den=cross(r,np.broadcast_to(v,r.shape)); rel=p0-A; good=np.abs(den)>1e-12; te=np.full(len(I),np.nan);ue=te.copy();te[good]=cross(rel[good],np.broadcast_to(v,rel[good].shape))/den[good];ue[good]=cross(rel[good],r[good])/den[good]; sa=cross(v,A-p0);sb=cross(v,D-p0)
    cut=np.where(good&(sa*sb<0)&(te>=0)&(te<=1)&(ue>=0)&(ue<=1))[0]; cut=np.union1d(marker,cut).astype(np.int32); mid=I[cut,6:8]; t=np.clip(((mid-p0)@v)/float(v@v),0,1); gate=(np.minimum((t*8).astype(int),7)+1).astype(np.uint8)
    return cut,gate,p0,p1

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

def fish(m,C,I,B,opens,cut,c):
    u=UF(len(c)); closed=set(map(int,cut))
    for i,r in enumerate(I):
        if i not in closed:u.u(int(r[2]),int(r[3]))
    lab=u.labels(); bc=B[:,2].astype(int); oc={k:np.unique(bc[v]) for k,v in opens.items()}; up=int(lab[oc['O'][0]]);dn=int(lab[oc['M'][0]]); p=np.asarray(C['fishwayApprovedImagePixel'],float); ang=math.radians(float(m['fishway']['flowBearingDeg'])); bv=np.array([math.sin(ang),-math.cos(ang)])
    ui=np.where(lab==up)[0];d=c[ui]-p;q=d@bv;dist=np.linalg.norm(d,axis=1);mask=q<0; a=int(ui[mask][np.argmin(dist[mask])])
    di=np.where(lab==dn)[0];d=c[di]-p;q=d@bv;dist=np.linalg.norm(d,axis=1);mask=q>0; ids=di[mask];dd=d[mask];ds=dist[mask];bearing=(np.degrees(np.arctan2(dd[:,0],-dd[:,1]))+360)%360;err=np.abs(((bearing-45+180)%360)-180);b=int(ids[np.argmin(ds+.15*err)])
    return np.array([a,b],np.int32),np.array([up,dn],np.int32),lab

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--repo-root',default='.')
    ap.add_argument('--water-manifest',default='data/onga_unified_water_manifest_r3.json')
    ap.add_argument('--constraints',default='data/onga_stage16_mesh_constraints_v2.json')
    ap.add_argument('--output',default='stage16-metric-mesh')
    ap.add_argument('--probe',action='store_true',help='emit unpinned diagnostics without accepting them as canonical')
    a=ap.parse_args();root=Path(a.repo_root).resolve();out=root/a.output;out.mkdir(parents=True,exist_ok=True)
    constraints_path=root/a.constraints;manifest_path=root/a.water_manifest
    C=j(constraints_path);m,w=load_water(root,manifest_path);M=mesh_from_water(w,C);E=C.get('expected')
    if not a.probe and not isinstance(E,dict):raise RuntimeError('canonical expected mesh values are not pinned')
    if E is None and C.get('candidateStatus')!='awaiting_linux_x86_64_canonical_probe':raise RuntimeError('unpinned candidate status mismatch')
    if isinstance(E,dict) and C.get('candidateStatus') not in ('linux_x86_64_pinned_awaiting_visual_review','approved_canonical'):raise RuntimeError('pinned candidate status mismatch')
    authority=C['waterAuthority']
    if m['version']!=authority['version'] or int(m['pixelCount'])!=int(authority['pixelCount']):
        raise RuntimeError('water authority mismatch')
    if not a.probe:
        if set(E['meshArrayHashes'])!=set(RAW_MESH_KEYS):raise RuntimeError('mesh hash key set mismatch')
        for k,v in E['meshArrayHashes'].items():
            if h(M[k])!=v:raise RuntimeError(f'{k} hash mismatch')
    em,I,B,c=edges(M['vertices'],M['triangles']);tag,opens=tags(m,B);cut,gate,p0,p1=barrage(w,M,I,c);fc,comp,labels=fish(m,C,I,B,opens,cut,c)
    boundary_vertices=B[:,:2].astype(np.int32); top=np.where(np.all(np.isclose(M['vertices'][boundary_vertices][:,:,1],0.0,atol=1e-12),axis=1))[0].astype(np.int32); top_endpoints=M['vertices'][boundary_vertices[top]]; top_length=float(np.linalg.norm(top_endpoints[:,1]-top_endpoints[:,0],axis=1).sum()); top_x=[float(top_endpoints[:,:,0].min()),float(top_endpoints[:,:,0].max())]; top_m={'faceCount':int(len(top)),'allTaggedM':bool(np.array_equal(np.sort(top),np.sort(opens['M'])) and np.all(tag[top]==1)),'endpointXSpan':top_x,'imageLengthPixels':top_length}
    world,_=coords(m['coordinateSystem']); W=np.asarray([world(x) for x in M['vertices']]); metric=np.column_stack([W[:,0],-W[:,1]]); origin=metric.mean(0); local=metric-origin; qlocal=np.rint(local*1000).astype(np.int32); qimage=np.rint(M['vertices']*1000).astype(np.int32)
    counts={'vertices':len(M['vertices']),'cells':len(M['triangles']),'internalFaces':len(I),'boundaryFaces':len(B),'barrageFaces':len(cut),'boundaryFaceCounts':{'shoreline':int(np.sum(tag==0)),'M':int(np.sum(tag==1)),'N':int(np.sum(tag==2)),'O':int(np.sum(tag==3)),'G':int(np.sum(tag==4))},'gateFaceCounts':{str(k):int(np.sum(gate==k)) for k in range(1,9)},'fishwayCells':fc.tolist(),'fishwayComponents':comp.tolist()}
    if not a.probe:
        for k in ['vertices','cells','internalFaces','boundaryFaces','barrageFaces']:
            if counts[k]!=E[k]:raise RuntimeError(f'{k} mismatch')
        for k in ['boundaryFaceCounts','gateFaceCounts','fishwayCells','fishwayComponents']:
            if counts[k]!=E[k]:raise RuntimeError(f'{k} mismatch')
        if top_m!=E['topBoundaryM']:raise RuntimeError('top boundary M mismatch')
    package={'vertex_local_mm':qlocal,'vertex_image_millipixel':qimage,'triangles':M['triangles'],'internal_face_vertices':I[:,:2].astype(np.int32),'internal_face_cells':I[:,2:4].astype(np.int32),'boundary_face_vertices':B[:,:2].astype(np.int32),'boundary_face_cell':B[:,2].astype(np.int32),'boundary_face_tag':tag,'barrage_face_ids':cut,'barrage_gate_id':gate,'fishway_cells':fc,'fishway_components':comp}
    package_hashes={k:h(v) for k,v in package.items()}
    if not a.probe:
        if set(E['packageArrayHashes'])!=set(PACKAGE_KEYS):raise RuntimeError('package hash key set mismatch')
        for k,v in E['packageArrayHashes'].items():
            if package_hashes.get(k)!=v:raise RuntimeError(f'{k} package hash mismatch')
    artifact_name=C.get('artifactFile','onga_stage16_metric_fv_mesh_v2.npz')
    np.savez_compressed(out/artifact_name,**package)
    pts=local[M['triangles']];area=np.abs((pts[:,1,0]-pts[:,0,0])*(pts[:,2,1]-pts[:,0,1])-(pts[:,1,1]-pts[:,0,1])*(pts[:,2,0]-pts[:,0,0]))/2
    report={'schema':'onga-stage16-metric-mesh-summary-v2','version':C['version'],'candidateStatus':C['candidateStatus'],'status':'probe-only' if a.probe else 'passed','canonical':not a.probe,'platform':{'system':platform.system(),'machine':platform.machine(),'python':platform.python_version()},'inputs':{'waterManifest':a.water_manifest,'waterAuthorityVersion':m['version'],'waterPixelCount':int(m['pixelCount']),'constraints':a.constraints},'artifactFile':artifact_name,'counts':counts,'topBoundaryM':top_m,'meshArrayHashes':{k:h(v) for k,v in M.items()},'packageArrayHashes':package_hashes,'metric':{'originEastM':float(origin[0]),'originNorthM':float(origin[1]),'totalAreaM2':float(area.sum()),'minimumCellAreaM2':float(area.min()),'maximumCellAreaM2':float(area.max()),'quantizationScaleM':.001},'barrageFullSpanImagePixel':[p0.tolist(),p1.tolist()],'safeguards':{'waterAuthorityModifiedDuringGeneration':False,'physicalValuesAssigned':False,'connectedToPublicSimulator':False,'calibrationPerformed':False,'previousMeshAuthorizationReusable':False}}
    (out/'stage16_metric_mesh_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
