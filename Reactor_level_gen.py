import json, math
mods=[]; DOORS=[]; LIGHTS=[]; OFF=[0.0,0.0]
def set_off(x,y): OFF[0]=float(x); OFF[1]=float(y)
def _L(l): return [l[0]+OFF[0], l[1]+OFF[1], l[2]]
def M(name,coll,parts):
    if parts: mods.append({"name":name,"collection":coll,"at":[0,0,0],"parts":parts})
def box(s,l,m,r=None,b=True,flip=False):
    d={"p":"box","s":[round(x,3) for x in s],"l":[round(x,3) for x in _L(l)],"m":m}
    if r:d["r"]=[round(x,2) for x in r]
    if not b:d["b"]=False
    if flip:d["flip"]=True
    return d
def cyl(rad,h,l,m,r=None,v=16,b=True,flip=False):
    d={"p":"cyl","rad":rad,"h":h,"l":[round(x,3) for x in _L(l)],"m":m,"v":v}
    if r:d["r"]=[round(x,2) for x in r]
    if not b:d["b"]=False
    if flip:d["flip"]=True
    return d
def cone(rad,h,l,m,rad2=0.0,r=None,v=16,cap=True,flip=False):
    d={"p":"cone","rad":rad,"rad2":rad2,"h":h,"l":[round(x,3) for x in _L(l)],"m":m,"v":v}
    if r:d["r"]=[round(x,2) for x in r]
    if not cap:d["cap"]=False
    if flip:d["flip"]=True
    return d
def addlight(x,y,z,e,c,s=2.5,kind="POINT"):
    LIGHTS.append([round(x+OFF[0],1),round(y+OFF[1],1),round(z,1),e,list(c),s,kind])
def wall(orient,fixed,a,b,z0,ztop,t,m,openings=None):
    openings=sorted(openings or [],key=lambda o:o["c"]); out=[]
    def seg(p,q,zlo,zhi,mm):
        if q-p<1e-3 or zhi-zlo<1e-3:return
        if orient=='x':out.append(box([q-p,t,zhi-zlo],[(p+q)/2,fixed,(zlo+zhi)/2],mm))
        else:out.append(box([t,q-p,zhi-zlo],[fixed,(p+q)/2,(zlo+zhi)/2],mm))
    cur=a
    for o in openings:
        L=o["c"]-o["w"]/2;R=o["c"]+o["w"]/2;sill=o.get("sill",z0);top=sill+o.get("h",ztop-z0)
        seg(cur,L,z0,ztop,m)
        if sill>z0+1e-3:seg(L,R,z0,sill,m)
        if top<ztop-1e-3:seg(L,R,top,ztop,m)
        if o.get("glass"):
            gp=(L+R)/2;gw=R-L
            if orient=='x':out.append(box([gw,0.08,top-sill],[gp,fixed,(sill+top)/2],"M_Glass",b=False))
            else:out.append(box([0.08,gw,top-sill],[fixed,gp,(sill+top)/2],"M_Glass",b=False))
        cur=R
    seg(cur,b,z0,ztop,m); return out
def room(x0,x1,y0,y1,z0,ztop,wm="M_Concrete",fm="M_Concrete",t=0.5,px=None,nx=None,py=None,ny=None,floor=True,light=True):
    p=[]
    if floor:p.append(box([x1-x0,y1-y0,0.4],[(x0+x1)/2,(y0+y1)/2,z0-0.2],fm))
    p+=wall('x',y0,x0,x1,z0,ztop,t,wm,ny);p+=wall('x',y1,x0,x1,z0,ztop,t,wm,py)
    p+=wall('y',x0,y0,y1,z0,ztop,t,wm,nx);p+=wall('y',x1,y0,y1,z0,ztop,t,wm,px)
    if light:rlight(x0,x1,y0,y1,ztop)
    return p
def ceil_of(name,x0,x1,y0,y1,ztop,m="M_Concrete_Dark"):
    M(name,"Ceilings",[box([x1-x0,y1-y0,0.4],[(x0+x1)/2,(y0+y1)/2,ztop+0.2],m)])
def corridor(name,axis,a,b,cc,w,z0,ztop,m="M_Concrete",ceil=True,light=True):
    p=[]
    if axis=='x':
        p.append(box([b-a,w,0.4],[(a+b)/2,cc,z0-0.2],m));p+=wall('x',cc-w/2,a,b,z0,ztop,0.4,m);p+=wall('x',cc+w/2,a,b,z0,ztop,0.4,m)
    else:
        p.append(box([w,b-a,0.4],[cc,(a+b)/2,z0-0.2],m));p+=wall('y',cc-w/2,a,b,z0,ztop,0.4,m);p+=wall('y',cc+w/2,a,b,z0,ztop,0.4,m)
    M(name,"Structure",p)
    if ceil:
        if axis=='x':M(name+"_C","Ceilings",[box([b-a,w,0.4],[(a+b)/2,cc,ztop+0.2],"M_Concrete_Dark")])
        else:M(name+"_C","Ceilings",[box([w,b-a,0.4],[cc,(a+b)/2,ztop+0.2],"M_Concrete_Dark")])
    if light:
        n=max(1,int((b-a)//8))
        for i in range(n):
            t=a+(i+0.5)*(b-a)/n
            if axis=='x':addlight(t,cc,ztop-0.5,150,(1,.95,.85),2.5)
            else:addlight(cc,t,ztop-0.5,150,(1,.95,.85),2.5)
def door(c,w=4,sill=0,h=3.5,glass=False): return {"c":c,"w":w,"sill":sill,"h":h,"glass":glass}
def reg_door(axis,fixed,c,w,ap):
    if axis=='x': DOORS.append((axis,fixed+OFF[1],c+OFF[0],w,ap))
    else: DOORS.append((axis,fixed+OFF[0],c+OFF[1],w,ap))
def build_scanners():
    p=[]
    for axis,fixed,c,w,ap in DOORS:
        bx=c+(w/2+0.5)
        if axis=='x':
            p+= [box([0.34,0.16,0.62],[bx,fixed+ap*0.22,1.42],"M_Metal_Dark",b=False),
                 box([0.22,0.05,0.34],[bx,fixed+ap*0.31,1.5],"M_Emit_Cyan",b=False),
                 box([0.07,0.05,0.07],[bx-0.09,fixed+ap*0.31,1.18],"M_Emit_Red",b=False)]
        else:
            p+= [box([0.16,0.34,0.62],[fixed+ap*0.22,bx,1.42],"M_Metal_Dark",b=False),
                 box([0.05,0.22,0.34],[fixed+ap*0.31,bx,1.5],"M_Emit_Cyan",b=False),
                 box([0.05,0.07,0.07],[fixed+ap*0.31,bx-0.09,1.18],"M_Emit_Red",b=False)]
    M("KeycardScanners","Security",p)
def rlight(x0,x1,y0,y1,ztop,energy=300,color=(1.0,0.96,0.88),step=11):
    nx=max(1,round((x1-x0)/step));ny=max(1,round((y1-y0)/step))
    for i in range(nx):
        for j in range(ny):
            addlight(x0+(i+0.5)*(x1-x0)/nx,y0+(j+0.5)*(y1-y0)/ny,ztop-0.6,energy,color,4.0,"AREA")
def acc(x,y,z,e,c,s=1.5):addlight(x,y,z,e,c,s,"POINT")
def lstrip(p,x,y,z,length,axis='x',m="M_Emit_Warm",wdt=0.5):
    p.append(box([length,wdt,0.15],[x,y,z],m,b=False) if axis=='x' else box([wdt,length,0.15],[x,y,z],m,b=False))
def pipe(p,axis,a,b,c1,z,rad=0.2,m="M_Pipe"):
    p.append(cyl(rad,b-a,[(a+b)/2,c1,z],m,r=[0,90,0],v=10) if axis=='x' else cyl(rad,b-a,[c1,(a+b)/2,z],m,r=[90,0,0],v=10))
# ---- circular helpers ----
def ring_wall(R,z0,ztop,t,m,segs=48,doors=None):
    out=[];doors=doors or [];chord=2*math.pi*R/segs*1.07
    for i in range(segs):
        a=i*360.0/segs;ar=math.radians(a);cx,cy=R*math.cos(ar),R*math.sin(ar);dd=None
        for dc,dw,sill,h in doors:
            if abs(((a-dc+180)%360)-180)<dw/2:dd=(sill,h);break
        if dd:
            sill,h=dd;top=sill+h
            if sill>z0+1e-3:out.append(box([chord,t,sill-z0],[cx,cy,(z0+sill)/2],m,r=[0,0,a+90]))
            if top<ztop-1e-3:out.append(box([chord,t,ztop-top],[cx,cy,(top+ztop)/2],m,r=[0,0,a+90]))
        else:
            out.append(box([chord,t,ztop-z0],[cx,cy,(z0+ztop)/2],m,r=[0,0,a+90]))
    return out
def ring_floor(r_in,r_out,z,m,segs=48,thick=0.4,max_ratio=1.15):
    # SOLID annulus: split into thin concentric bands, each band's chord sized at its
    # OUTER radius (worst case) so a constant-width box can't under-cover. A single wide
    # band sized at mid-radius leaves radial wedge gaps near r_out (the old bug).
    out=[];edges=[max(r_in,0.01)]
    while edges[-1]*max_ratio<r_out:edges.append(edges[-1]*max_ratio)
    edges.append(r_out)
    for bi in range(len(edges)-1):
        ri,ro=edges[bi],edges[bi+1];rm=(ri+ro)/2;chord=2*math.pi*ro/segs*1.06
        for i in range(segs):
            a=(i+0.5)*360.0/segs;ar=math.radians(a)
            out.append(box([chord,ro-ri+0.06,thick],[rm*math.cos(ar),rm*math.sin(ar),z-thick/2],m,r=[0,0,a+90]))
    return out
def ring_bar(R,z,m,segs=48,th=0.06):
    out=[];chord=2*math.pi*R/segs*1.05
    for i in range(segs):
        a=(i+0.5)*360.0/segs;ar=math.radians(a)
        out.append(box([chord,th*2,th*2],[R*math.cos(ar),R*math.sin(ar),z],m,r=[0,0,a+90]))
    return out
def dome(R,z0,apex,rings,m,segs=40,top_f=0.86):
    out=[]
    for k in range(rings):
        f0=top_f*k/rings;f1=top_f*(k+1)/rings
        r0=R*math.cos(f0*math.pi/2);r1=R*math.cos(f1*math.pi/2)
        z_0=z0+(apex-z0)*math.sin(f0*math.pi/2);z_1=z0+(apex-z0)*math.sin(f1*math.pi/2)
        out.append(cone(r0,z_1-z_0,[0,0,(z_0+z_1)/2],m,rad2=max(r1,0.05),v=segs,cap=False,flip=True))
    return out
def stair_out(angle,r_in,z_top,steps,m="M_Mesh_Silver",width=3.6):
    out=[];ar=math.radians(angle);ca,sa=math.cos(ar),math.sin(ar);rise=z_top/steps;run=0.62
    for k in range(steps):
        top=(k+1)*rise;r=r_in+k*run
        out.append(box([width,run+0.04,top],[r*ca,r*sa,top/2],m,r=[0,0,angle+90]))
    return out

# ============================ GRAND CIRCULAR REACTOR HALL (3x) ===============
R=66.0;ZW=14.0;APEX=40.0;POOL=22.0;PDEPTH=16.0;WIN=58.0;WOUT=63.0;WKZ=6.0
set_off(0,0)
M("ReactorHall_Floor","Structure",ring_floor(POOL,R,0,"M_Concrete",segs=84,thick=0.5))
dlist=[(0,6,0,4.5),(90,6,0,4.5),(180,6,0,4.5),(270,6,0,4.5)]
M("ReactorHall_Wall","Structure",ring_wall(R,0,ZW,0.8,"M_Concrete",segs=84,doors=dlist))
reg_door('y',R,0,5,1);reg_door('x',R,0,5,1);reg_door('y',-R,0,5,-1);reg_door('x',-R,0,5,-1)
# grand curved dome + oculus skylight + 2 downlight rings
M("ReactorHall_Dome","Ceilings",dome(R-0.4,ZW,APEX,7,"M_Concrete_Dark",segs=64))
rtop=(R-0.4)*math.cos(0.86*math.pi/2);ztp=ZW+(APEX-ZW)*math.sin(0.86*math.pi/2)
dl=[cyl(rtop,0.4,[0,0,ztp],"M_Emit_Warm",v=64)]
for rr in [30,49]:
    nf=max(8,int(rr/3.2))
    for i in range(nf):
        a=i*360.0/nf;dl.append(box([2.4,0.7,0.25],[rr*math.cos(math.radians(a)),rr*math.sin(math.radians(a)),ZW-0.3],"M_Emit_Warm",r=[0,0,a+90],b=False))
M("ReactorHall_DomeLights","Lighting",dl)
# deep pool (2x deeper) + walls + bottom + hazard rim
pl=ring_wall(POOL,-PDEPTH,0,0.8,"M_Concrete_Dark",segs=64)
pl.append(cyl(POOL+0.1,0.6,[0,0,-PDEPTH-0.3],"M_Metal_Dark",v=64))
M("ReactorPool_Structure","Structure",pl)
M("ReactorPool_Rim","Structure",ring_floor(POOL,POOL+1.0,0.15,"M_Hazard_Yellow",segs=64,thick=0.15))
# submerged glowing-blue reactor (scaled up, deeper)
rc=[cyl(8.0,0.9,[0,0,-PDEPTH+0.45],"M_Metal_Dark",v=32),cyl(6.0,7.0,[0,0,-PDEPTH+4.0],"M_Metal_Panel",v=28),
    cyl(5.4,7.6,[0,0,-PDEPTH+4.0],"M_Emit_Blue",v=28),cyl(6.2,0.6,[0,0,-PDEPTH+7.6],"M_Metal_Dark",v=28)]
for gx in range(-4,5):
    for gy in range(-4,5):
        if gx*gx+gy*gy<=16.5:rc.append(cyl(0.3,7.8,[gx*1.05,gy*1.05,-PDEPTH+4.0],"M_Emit_Blue",v=6,b=False))
M("ReactorCore_Blue","ReactorCore",rc)
M("ReactorPool_Water","Pool",[cyl(POOL-0.3,0.3,[0,0,-0.6],"M_Water",v=72,b=False)])
# PERIMETER silver mesh-metal walkway + inner rail + posts
wk=ring_floor(WIN,WOUT,WKZ,"M_Mesh_Silver",segs=80,thick=0.25)
wk+=ring_bar(WIN,WKZ+1.1,"M_Metal_Dark",segs=80)
for i in range(48):
    a=math.radians(i*7.5);wk.append(cyl(0.06,1.1,[WIN*math.cos(a),WIN*math.sin(a),WKZ+0.55],"M_Metal_Dark",v=6))
for i in range(32):
    a=math.radians(i*11.25);wk.append(cyl(0.16,WKZ,[(WIN+0.5)*math.cos(a),(WIN+0.5)*math.sin(a),WKZ/2],"M_Metal_Dark",v=8))
M("ReactorHall_Walkway","Catwalks",wk)
# stairs up to the perimeter walkway in SEVERAL places (avoid door angles)
stairs=[]
for ang in [30,60,120,150,210,240,300,330]:
    stairs+=stair_out(ang, WIN-7.4, WKZ, 13)  # 13 steps: top tread overlaps the z6 deck (12 fell ~0.25m short)
M("ReactorHall_Stairs","Catwalks",stairs)
# lighting: deep blue pool spectacle + dome rings + walkway + floor fill
acc(0,0,-PDEPTH+5,5000,(0.2,0.5,1.0),9);acc(0,0,-2,1800,(0.3,0.6,1.0),11)
for i in range(12):
    a=math.radians(i*30+15);acc(48*math.cos(a),48*math.sin(a),ZW-0.5,520,(0.95,0.97,1.0),5)
for i in range(8):
    a=math.radians(i*45+22);acc(30*math.cos(a),30*math.sin(a),ZW+8,520,(1,0.96,0.85),5)
acc(0,0,ztp-1.2,1100,(1,0.96,0.85),7)
for i in range(8):
    a=math.radians(i*45);acc(WIN*math.cos(a),WIN*math.sin(a),WKZ+2.0,220,(0.5,0.7,1.0),2)
for i in range(10):
    a=math.radians(i*36+18);acc(36*math.cos(a),36*math.sin(a),ZW-1.0,460,(0.95,0.97,1.0),5)

# ============================ CONNECTOR CORRIDORS (hall -> wings) ============
set_off(0,0)
corridor("Corr_E",'x',R,R+4,0,5,0,4.5);corridor("Corr_W",'x',-R-4,-R,0,5,0,4.5)
corridor("Corr_S",'y',-R-4,-R,0,5,0,4.5);corridor("Corr_N",'y',R,R+8,0,5,0,4.5)
# door aprons: bridge the curved hall floor edge (84-gon at r=R) to the straight corridor floors
ap=[]
for ddx,ddy,sx,sy in [(R,0,5,6),(-R,0,5,6),(0,-R,6,5),(0,R,6,5)]:
    ap.append(box([sx,sy,0.5],[ddx,ddy,-0.25],"M_Concrete"))
M("DoorAprons","Structure",ap)

# ============================ EAST WING (turbine/switchgear/gen/cooling) =====
set_off(44,0)
th=room(26,56,-14,14,0,11,nx=[door(0)],px=[door(0)]);reg_door('y',26,0,4,-1);reg_door('y',56,0,4,1)
M("TurbineHall_Shell","Structure",th);ceil_of("TurbineHall_C",26,56,-14,14,11)
tc=[]
for ty in[-6.5,6.5]:
    bx=41
    tc+=[box([16,3,1.2],[bx,ty,0.6],"M_Metal_Dark"),cyl(1.6,6,[bx-3.5,ty,2.6],"M_Steel",r=[0,90,0],v=20),
         cyl(2.0,3.0,[bx+4.5,ty,2.8],"M_Metal_Panel",r=[0,90,0],v=20),cyl(1.75,0.3,[bx-0.7,ty,2.6],"M_Hazard_Yellow",r=[0,90,0],v=20),
         box([1.2,1.0,1.6],[bx-7.8,ty,0.8],"M_Metal_Panel"),box([1.0,0.07,0.6],[bx-7.8,ty-0.55,1.0],"M_Screen"),cyl(0.4,3.2,[bx+4.5,ty,4.6],"M_Pipe",v=12)]
for z in[9.5,9.0]:pipe(tc,'x',27,55,0,z,0.3)
M("TurbineHall_Machinery","Machinery",tc)
corridor("Corr_E2",'x',56,64,0,5,0,4.5)
sw=room(64,84,-12,12,0,7,nx=[door(0)],px=[door(0)],py=[door(74,2.5,0,3)]);reg_door('y',64,0,4,-1);reg_door('y',84,0,4,1);reg_door('x',12,74,2.5,1)
M("Switchgear_Shell","Structure",sw);ceil_of("Switchgear_C",64,84,-12,12,7)
swc=[]
for x in range(68,82,3):
    swc+=[box([2.0,1.4,3.0],[x,-9,1.5],"M_Metal_Dark"),box([2.0,1.4,3.0],[x,9,1.5],"M_Metal_Dark"),
          box([0.05,1.0,0.4],[x-1.0,-9,2.4],"M_Emit_Red",b=False),box([0.05,1.0,0.4],[x-1.0,9,2.4],"M_Emit_Green",b=False)]
swc+=[box([3,2.4,2.6],[74,0,1.3],"M_Metal_Panel")];pipe(swc,'x',65,83,0,6.3,0.25)
M("Switchgear_Content","Machinery",swc)
corridor("Corr_E3",'x',84,90,0,5,0,4.5)
gh=room(90,118,-16,16,0,11,nx=[door(0)]);reg_door('y',90,0,4,-1)
M("GenHall_Shell","Structure",gh);ceil_of("GenHall_C",90,118,-16,16,11)
ghc=[]
for gy in[-8,0,8]:
    bx=104
    ghc+=[box([14,3,1.0],[bx,gy,0.5],"M_Metal_Dark"),cyl(1.4,9,[bx,gy,2.3],"M_Metal_Panel",r=[0,90,0],v=18),
          cyl(1.45,0.3,[bx-2,gy,2.3],"M_Hazard_Yellow",r=[0,90,0],v=18),cyl(0.35,2.6,[bx+3,gy,4.0],"M_Pipe",v=10),box([1.0,0.8,1.4],[bx-6.5,gy,0.7],"M_Metal_Panel")]
M("GenHall_Machinery","Machinery",ghc)
corridor("Corr_CT",'y',12,18,74,5,0,4.5)
ct2=room(64,86,18,40,0,14,ny=[door(74,2.5,0,3)]);reg_door('x',18,74,2.5,-1)
M("CoolTower_Shell","Structure",ct2);ceil_of("CoolTower_C",64,86,18,40,14)
ctc=[]
for tx in[71,79]:
    ctc+=[cyl(4.0,10,[tx,29,5.0],"M_Concrete",v=20),cone(4.0,3.0,[tx,29,11.5],"M_Concrete_Dark",rad2=2.8,v=20),cyl(4.1,0.5,[tx,29,1.2],"M_Hazard_Yellow",v=20)]
M("CoolTower_Content","Machinery",ctc)

# ============================ WEST WING (coolant/pump/waste/reactor2) ========
set_off(-44,0)
cg=room(-52,-26,-13,13,0,9,px=[door(0)],nx=[door(0)]);reg_door('y',-26,0,4,1);reg_door('y',-52,0,4,-1)
M("CoolantGallery_Shell","Structure",cg);ceil_of("CoolantGallery_C",-52,-26,-13,13,9)
cgc=[]
for x in[-30,-34,-38,-42]:cgc+=[box([2.4,1.8,1.8],[x,-10.5,0.9],"M_Metal_Panel"),cyl(0.6,1.3,[x,-10.5,2.3],"M_Metal_Dark",r=[0,90,0],v=14)]
for x in[-30,-37,-44]:cgc+=[cyl(1.8,5.5,[x,9.5,2.75],"M_Metal_Panel",v=20),cone(1.8,0.7,[x,9.5,5.85],"M_Metal_Dark",rad2=0.5,v=20),cyl(1.85,0.45,[x,9.5,1.0],"M_Hazard_Yellow",v=20)]
cgc+=[cyl(1.5,10,[-48.5,0,2.0],"M_Steel",r=[90,0,0],v=20)]
for z in[8.3,7.9,7.5]:pipe(cgc,'x',-51,-27,-12,z,0.22)
M("CoolantGallery_Machinery","Machinery",cgc)
pl2=[];px0,px1,py0,py1=-50,-40,-12,-4
pl2+=wall('x',py0,px0,px1,0,0.6,0.4,"M_Concrete")+wall('x',py1,px0,px1,0,0.6,0.4,"M_Concrete")+wall('y',px0,py0,py1,0,0.6,0.4,"M_Concrete")+wall('y',px1,py0,py1,0,0.6,0.4,"M_Concrete")
pl2+=[box([px1-px0-0.6,py1-py0-0.6,0.1],[(px0+px1)/2,(py0+py1)/2,-0.1],"M_Emit_Blue",b=False)]
for yy in[py0-0.4,py1+0.4]:pl2.append(box([px1-px0+0.8,0.06,0.06],[(px0+px1)/2,yy,1.0],"M_Metal_Dark"))
M("SpentFuelPool","Pool",pl2);acc(-45,-8,1.2,500,(0.2,0.6,1),2.5)
corridor("Corr_W2",'x',-64,-52,0,5,0,4.5)
ph=room(-84,-64,-12,12,0,7,px=[door(0)],nx=[door(0)],ny=[door(-74,2.5,0,3)]);reg_door('y',-64,0,4,1);reg_door('y',-84,0,4,-1);reg_door('x',-12,-74,2.5,-1)
M("PumpHouse_Shell","Structure",ph);ceil_of("PumpHouse_C",-84,-64,-12,12,7)
phc=[]
for x in[-80,-74,-68]:phc+=[box([3,2.4,2.2],[x,-7,1.1],"M_Metal_Panel"),cyl(0.8,1.6,[x,-7,2.5],"M_Metal_Dark",r=[0,90,0],v=16),cyl(0.3,2.2,[x,-5,1.0],"M_Copper",r=[90,0,0],v=10)]
for z in[6.3,5.9]:pipe(phc,'x',-83,-65,8,z,0.25)
M("PumpHouse_Content","Machinery",phc)
corridor("Corr_W3",'x',-90,-84,0,5,0,4.5)
wc=room(-118,-90,-14,14,0,9,px=[door(0)]);reg_door('y',-90,0,4,1)
M("WasteContain_Shell","Structure",wc);ceil_of("WasteContain_C",-118,-90,-14,14,9)
wcc=[]
for x in range(-114,-92,3):
    for y in[-10,-7,7,10]:wcc+=[cyl(0.55,1.5,[x,y,0.75],"M_Hazard_Yellow",v=12),cyl(0.57,0.2,[x,y,1.4],"M_Metal_Dark",v=12)]
for x in[-110,-100]:wcc+=[box([4,3,2.5],[x,0,1.25],"M_Metal_Dark"),box([4.1,3.1,0.3],[x,0,2.55],"M_Hazard_Yellow")]
M("WasteContain_Content","Machinery",wcc)
corridor("Corr_R2",'y',-26,-12,-74,5,0,4.5)
r2=room(-90,-58,-50,-26,0,12,py=[door(-74,2.5,0,3)]);reg_door('x',-26,-74,2.5,1)
M("Reactor2_Shell","Structure",r2);ceil_of("Reactor2_C",-90,-58,-50,-26,12)
r2c=[cyl(3.5,0.6,[-74,-38,0.3],"M_Metal_Dark",v=20),cyl(2.4,7,[-74,-38,4.0],"M_Steel",v=20),
     cyl(2.5,0.3,[-74,-38,3.5],"M_Rust",v=20),cone(2.4,2.0,[-74,-38,8.5],"M_Steel",rad2=0.8,v=20),cyl(2.55,0.45,[-74,-38,0.9],"M_Hazard_Yellow",v=20)]
for k in range(5):h=(k+1)*0.6;r2c.append(box([2.4,0.55,h],[-67,-44+k*0.55,h/2],"M_Metal_Dark"))
M("Reactor2_Content","Machinery",r2c);acc(-74,-38,4,300,(0.5,0.9,0.3),2.5)

# ============================ SOUTH WING (entrance complex) ==================
set_off(0,-44)
sa=room(-8,8,-44,-26,0,6,py=[door(0)],ny=[door(0,5,0,4.2)]);reg_door('x',-26,0,4,1)
M("SurfaceAccess_Shell","Structure",sa);ceil_of("SurfaceAccess_C",-8,8,-44,-26,6)
sac=[box([5.4,0.7,4.6],[0,-44.1,2.3],"M_Metal_Dark"),box([4.2,0.4,3.8],[0,-43.7,2.2],"M_Steel")]
for zz in[1.0,2.2,3.4]:sac.append(box([4.2,0.45,0.35],[0,-43.55,zz],"M_Hazard_Yellow",b=False))
ex0,ex1,ey0,ey1=2.0,7.0,-34,-28
sac+=wall('y',ex0,ey0,ey1,0,24,0.5,"M_Concrete_Dark")+wall('x',ey0,ex0,ex1,0,24,0.5,"M_Concrete_Dark")+wall('x',ey1,ex0,ex1,6,24,0.5,"M_Concrete_Dark")
sac+=[box([4.0,4.6,2.6],[(ex0+ex1)/2,(ey0+ey1)/2,1.5],"M_Metal_Dark"),box([0.1,0.6,1.4],[(ex0+ex1)/2,ey1-0.2,1.6],"M_Emit_Cyan",b=False),cyl(0.06,21,[(ex0+ex1)/2,(ey0+ey1)/2,13],"M_Metal_Dark",v=6)]
M("SurfaceAccess_Content","Surface",sac);acc(0,-42,2.2,200,(1,.2,.15),1.5);acc(4.5,-31,1.6,150,(.3,.9,1),1.5)
sec=room(-14,14,-60,-44,0,6,py=[door(0,5,0,4.2)],ny=[door(0,4,0,3.5)]);reg_door('x',-44,0,4,1);reg_door('x',-60,0,4,1)
M("Security_Shell","Structure",sec);ceil_of("Security_C",-14,14,-60,-44,6)
secc=[]
for gx in[-7,0,7]:
    secc+=[box([0.6,2.0,1.1],[gx-0.9,-52,0.55],"M_Metal_Panel"),box([0.6,2.0,1.1],[gx+0.9,-52,0.55],"M_Metal_Panel"),
           box([0.18,0.18,1.3],[gx-0.9,-51,0.65],"M_Metal_Dark"),box([0.1,0.1,0.3],[gx-0.9,-51,1.4],"M_Emit_Red",b=False)]
secc+=[box([6,1.2,1.2],[10,-57,0.6],"M_Metal_Panel"),box([5.5,0.1,0.5],[10,-56.4,1.4],"M_Screen")]
M("Security_Content","Security",secc)
lob=room(-22,22,-90,-60,0,8,py=[door(0,4,0,3.5)],nx=[door(-69,2.5,0,3)],px=[door(-69,2.5,0,3)]);reg_door('x',-60,0,4,-1);reg_door('y',-22,-69,2.5,-1);reg_door('y',22,-69,2.5,1)
M("Lobby_Shell","Structure",lob);ceil_of("Lobby_C",-22,22,-90,-60,8)
lobc=[box([10,2,1.1],[0,-64,0.55],"M_Metal_Panel"),box([9,0.1,0.4],[0,-63,1.3],"M_Emit_Cyan",b=False)]
for sx in[-14,-9]:
    for sy in[-80,-76,-72]:lobc.append(box([3,1.4,0.8],[sx,sy,0.4],"M_Metal_Dark"))
lobc+=[box([8,8,0.05],[0,-86,0.03],"M_Emit_Blue",b=False)]
M("Lobby_Content","Controls",lobc)
locker=room(16,34,-78,-60,0,4.5,nx=[door(-69,2.5,0,3)]);reg_door('y',16,-69,2.5,1)
M("Locker_Shell","Structure",locker);ceil_of("Locker_C",16,34,-78,-60,4.5)
lkc=[]
for y in[-76,-74,-72,-64,-62]:lkc.append(box([14,0.5,2.2],[25,y,1.1],"M_Metal_Panel"))
M("Locker_Content","Machinery",lkc)
guard=room(-34,-16,-78,-60,0,4.5,px=[door(-69,2.5,0,3)]);reg_door('y',-16,-69,2.5,-1)
M("Guard_Shell","Structure",guard);ceil_of("Guard_C",-34,-16,-78,-60,4.5)
M("Guard_Content","Controls",[box([2.2,1.1,1.0],[-25,-63,0.5],"M_Metal_Panel"),box([1.9,0.12,0.7],[-25,-62.5,1.25],"M_Screen",r=[28,0,0])])

# ============================ NORTH WING (control/server/storage/admin) ======
set_off(0,44)
crm=room(-14,14,30,46,0,5,wm="M_Metal_Panel",ny=[door(0,4,0,3.5)],py=[door(0,4,0,3.5)],px=[door(38,3,0,3)],nx=[door(38,3,0,3)])
reg_door('x',30,0,4,-1);reg_door('x',46,0,4,1);reg_door('y',14,38,3,1);reg_door('y',-14,38,3,-1)
M("ControlRoom_Shell","Structure",crm);ceil_of("ControlRoom_C",-14,14,30,46,5)
cc=[]
for x in[-9,-4.5,0,4.5,9]:cc+=[box([3.0,1.3,1.05],[x,32.2,0.52],"M_Metal_Panel"),box([2.7,0.12,0.8],[x,31.7,1.35],"M_Screen",r=[28,0,0]),box([2.6,0.07,0.12],[x,31.55,0.92],"M_Emit_Cyan",b=False)]
for x in[-7,0,7]:cc.append(box([4.5,0.12,2.4],[x,45.6,3.2],"M_Screen"))
M("ControlRoom_Content","Controls",cc);acc(0,38,2.5,150,(0.3,0.7,1),2)
corridor("Corr_Sv",'x',14,18,38,4,0,4.5)
sv=room(18,32,31,45,0,4.5,wm="M_Metal_Panel",nx=[door(38,3,0,3)]);reg_door('y',18,38,3,-1)
M("ServerRoom_Shell","Structure",sv);ceil_of("ServerRoom_C",18,32,31,45,4.5)
svc=[]
for ry in[33,35.5,38,40.5,43]:
    for rx in[21,28]:
        svc.append(box([1.2,1.6,2.6],[rx,ry,1.3],"M_Metal_Dark"))
        for dz in[1.6,2.0,2.4]:svc.append(box([0.04,0.9,0.08],[rx-0.62,ry,dz],"M_Emit_Green",b=False))
M("ServerRoom_Content","Machinery",svc)
corridor("Corr_St",'x',-18,-14,38,4,0,4.5)
stg=room(-32,-18,31,45,0,4.5,px=[door(38,3,0,3)]);reg_door('y',-18,38,3,1)
M("Storage_Shell","Structure",stg);ceil_of("Storage_C",-32,-18,31,45,4.5)
stc=[]
for x in[-29,-26,-23,-20]:
    for y in[33,35]:stc.append(box([1.6,1.6,1.4],[x,y,0.7],"M_Metal_Panel"))
for x in[-29,-26,-23]:stc+=[cyl(0.5,1.4,[x,43,0.7],"M_Hazard_Yellow",v=12),cyl(0.52,0.2,[x,43,1.3],"M_Metal_Dark",v=12)]
M("Storage_Content","Machinery",stc)
corridor("Corr_N2",'y',46,50,0,5,0,4.5)
admin=room(-32,46,50,54,0,4.5,ny=[door(0,4,0,3.5)]);reg_door('x',50,0,4,-1)
M("AdminCorr_Shell","Structure",admin);ceil_of("AdminCorr_C",-32,46,50,54,4.5)
off=room(-30,-8,54,76,0,4.5,ny=[door(-19,2.5,0,3)]);reg_door('x',54,-19,2.5,1)
M("Offices_Shell","Structure",off);ceil_of("Offices_C",-30,-8,54,76,4.5)
ofc=[]
for x in[-26,-19,-12]:
    for y in[58,63,68,73]:ofc+=[box([2.2,1.2,0.8],[x,y,0.4],"M_Metal_Panel"),box([0.04,0.9,0.5],[x-0.9,y,0.95],"M_Screen",b=False)]
M("Offices_Content","Controls",ofc)
brk=room(-6,16,54,72,0,4.5,ny=[door(5,2.5,0,3)]);reg_door('x',54,5,2.5,1)
M("Break_Shell","Structure",brk);ceil_of("Break_C",-6,16,54,72,4.5)
M("Break_Content","Controls",[box([6,1.4,0.8],[5,63,0.4],"M_Metal_Panel"),box([2,2,1.0],[13,69,0.5],"M_Metal_Panel")])
lab=room(20,46,54,78,0,5,ny=[door(33,2.5,0,3)]);reg_door('x',54,33,2.5,1)
M("Labs_Shell","Structure",lab);ceil_of("Labs_C",20,46,54,78,5)
lbc=[]
for x in[24,30,36,42]:lbc+=[box([1.4,5,0.9],[x,63,0.45],"M_Metal_Panel"),box([1.0,0.08,0.5],[x,60,1.2],"M_Emit_Cyan",b=False)]
lbc+=[cyl(0.8,1.6,[42,74,0.8],"M_Emit_Green",v=14,b=False),box([3,2,2.4],[24,74,1.2],"M_Metal_Dark")]
M("Labs_Content","Machinery",lbc);acc(42,74,1.2,200,(0.3,1,0.4),1.5)

set_off(0,0)
build_scanners()
json.dump(mods,open("reactor_level.json","w"));json.dump(LIGHTS,open("reactor_lights.json","w"))
print("MODULES:",len(mods)," PARTS:",sum(len(x['parts']) for x in mods)," DOORS:",len(DOORS)," LIGHTS:",len(LIGHTS))
xs=[p['l'][0] for mm in mods for p in mm['parts'] if 'l' in p];ys=[p['l'][1] for mm in mods for p in mm['parts'] if 'l' in p];zs=[p['l'][2] for mm in mods for p in mm['parts'] if 'l' in p]
print("FOOTPRINT x[%.0f,%.0f] y[%.0f,%.0f] z[%.0f,%.0f]"%(min(xs),max(xs),min(ys),max(ys),min(zs),max(zs)))
