import json, math
mods=[]; DOORS=[]; LIGHTS=[]
def M(name,coll,parts):
    if parts: mods.append({"name":name,"collection":coll,"at":[0,0,0],"parts":parts})
def box(s,l,m,r=None,b=True):
    d={"p":"box","s":[round(x,3) for x in s],"l":[round(x,3) for x in l],"m":m}
    if r:d["r"]=r
    if not b:d["b"]=False
    return d
def cyl(rad,h,l,m,r=None,v=16,b=True):
    d={"p":"cyl","rad":rad,"h":h,"l":[round(x,3) for x in l],"m":m,"v":v}
    if r:d["r"]=r
    if not b:d["b"]=False
    return d
def cone(rad,h,l,m,rad2=0.0,r=None,v=16):
    return {"p":"cone","rad":rad,"rad2":rad2,"h":h,"l":[round(x,3) for x in l],"m":m,"v":v,**({"r":r} if r else {})}
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
            if axis=='x':LIGHTS.append([round(t,1),cc,ztop-0.5,150,[1,.95,.85],2.5,"POINT"])
            else:LIGHTS.append([cc,round(t,1),ztop-0.5,150,[1,.95,.85],2.5,"POINT"])
# doors registry -> wall opening dict + a scanner beside it on the approach side
def door(c,w=4,sill=0,h=3.5,glass=False): return {"c":c,"w":w,"sill":sill,"h":h,"glass":glass}
def reg_door(axis,fixed,c,w,approach):  # axis 'x' wall along X (normal Y); approach=+/-1
    DOORS.append((axis,fixed,c,w,approach))
def build_scanners():
    p=[]
    for axis,fixed,c,w,ap in DOORS:
        bx=c+(w/2+0.5)
        if axis=='x':  # wall along X at y=fixed, normal Y, approach side ap
            hy=fixed+ap*0.22
            p.append(box([0.34,0.16,0.62],[bx,hy,1.42],"M_Metal_Dark",b=False))
            p.append(box([0.22,0.05,0.34],[bx,fixed+ap*0.31,1.5],"M_Emit_Cyan",b=False))
            p.append(box([0.07,0.05,0.07],[bx-0.09,fixed+ap*0.31,1.18],"M_Emit_Red",b=False))
        else:          # wall along Y at x=fixed, normal X
            hx=fixed+ap*0.22; by=c+(w/2+0.5)
            p.append(box([0.16,0.34,0.62],[hx,by,1.42],"M_Metal_Dark",b=False))
            p.append(box([0.05,0.22,0.34],[fixed+ap*0.31,by,1.5],"M_Emit_Cyan",b=False))
            p.append(box([0.05,0.07,0.07],[fixed+ap*0.31,by-0.09,1.18],"M_Emit_Red",b=False))
    M("KeycardScanners","Security",p)
def rlight(x0,x1,y0,y1,ztop,energy=300,color=(1.0,0.96,0.88),step=11):
    nx=max(1,round((x1-x0)/step));ny=max(1,round((y1-y0)/step))
    for i in range(nx):
        for j in range(ny):
            LIGHTS.append([round(x0+(i+0.5)*(x1-x0)/nx,1),round(y0+(j+0.5)*(y1-y0)/ny,1),round(ztop-0.6,1),energy,list(color),4.0,"AREA"])
def acc(x,y,z,e,c,s=1.5):LIGHTS.append([x,y,z,e,list(c),s,"POINT"])
def lstrip(p,x,y,z,length,axis='x',m="M_Emit_Warm",wdt=0.5):
    p.append(box([length,wdt,0.15],[x,y,z],m,b=False) if axis=='x' else box([wdt,length,0.15],[x,y,z],m,b=False))
def pipe(p,axis,a,b,c1,z,rad=0.2,m="M_Pipe"):
    p.append(cyl(rad,b-a,[(a+b)/2,c1,z],m,r=[0,90,0],v=10) if axis=='x' else cyl(rad,b-a,[c1,(a+b)/2,z],m,r=[90,0,0],v=10))

# ============================ CENTRAL CLUSTER (kept) =========================
v=[cyl(4.0,0.6,[0,0,0.3],"M_Metal_Dark",v=24),cyl(4.1,0.45,[0,0,0.55],"M_Hazard_Yellow",v=24),
   cyl(3.0,3.5,[0,0,2.55],"M_Steel",v=24),cyl(3.12,0.9,[0,0,4.75],"M_Emit_Green",v=24),
   cyl(3.0,3.2,[0,0,6.8],"M_Steel",v=24),cyl(3.15,0.3,[0,0,2.2],"M_Metal_Dark",v=24),
   cyl(3.15,0.3,[0,0,6.6],"M_Metal_Dark",v=24),cyl(3.16,0.25,[0,0,8.25],"M_Emit_Cyan",v=24),
   {"p":"sphere","rad":3.0,"l":[0,0,8.4],"m":"M_Steel","sub":2}]
for i in range(6):
    a=math.radians(i*60);v.append(box([0.2,0.2,7.4],[3.05*math.cos(a),3.05*math.sin(a),4.5],"M_Metal_Dark"))
v.append(cyl(1.0,0.4,[0,0,11.4],"M_Metal_Panel",v=16))
for dx,dy in[(0.5,0.5),(-0.5,0.5),(0.5,-0.5),(-0.5,-0.5)]:v.append(cyl(0.09,1.6,[dx,dy,11.4],"M_Metal_Dark",v=8))
M("ReactorVessel","ReactorCore",v); acc(0,0,5,800,(0.4,1,0.5),3)
for i in range(3):
    a=math.radians(i*120+30);acc(4.6*math.cos(a),4.6*math.sin(a),4.75,350,(0.4,1,0.5),1)
s=[box([30,30,0.4],[0,0,-0.2],"M_Concrete")]
s+=wall('y',15,-15,15,0,12,0.6,"M_Concrete",[door(0)]);reg_door('y',15,0,4,-1)
s+=wall('y',-15,-15,15,0,12,0.6,"M_Concrete",[door(0)]);reg_door('y',-15,0,4,1)
s+=wall('x',-15,-15,15,0,12,0.6,"M_Concrete",[door(0)]);reg_door('x',-15,0,4,-1)
s+=wall('x',15,-15,15,0,12,0.6,"M_Concrete",[door(-9,3,0,3),{"c":2,"w":12,"sill":1.5,"h":3.0,"glass":True}]);reg_door('x',15,-9,3,1)
for px,py in[(10,10),(-10,10),(10,-10),(-10,-10)]:s.append(box([1.2,1.2,12],[px,py,6],"M_Concrete_Dark"))
for cx,cy in[(0,5),(0,-5)]:s.append(box([10.4,0.5,0.08],[cx,cy,0.04],"M_Hazard_Yellow"))
s+=[box([0.5,10.4,0.08],[5,0,0.04],"M_Hazard_Yellow"),box([0.5,10.4,0.08],[-5,0,0.04],"M_Hazard_Yellow")]
M("CoreHall_Shell","Structure",s);ceil_of("CoreHall_Ceiling",-15,15,-15,15,12)
rlight(-15,15,-15,15,12,360)
c=[]
for l in[[0,6,3],[0,-6,3]]:c.append(box([12,1.6,0.18],l,"M_Steel"))
for l in[[6,0,3],[-6,0,3]]:c.append(box([1.6,12,0.18],l,"M_Steel"))
for cx,cy in[(6,6),(-6,6),(6,-6),(-6,-6)]:c.append(box([1.6,1.6,0.18],[cx,cy,3],"M_Steel"))
for l in[[0,6.78,3.95],[0,-6.78,3.95]]:c.append(box([13.4,0.08,0.1],l,"M_Metal_Dark"))
for l in[[6.78,0,3.95],[-6.78,0,3.95]]:c.append(box([0.08,13.4,0.1],l,"M_Metal_Dark"))
for l in[[0,5.22,3.95],[0,-5.22,3.95]]:c.append(box([10.6,0.08,0.1],l,"M_Metal_Dark"))
for l in[[5.22,0,3.95],[-5.22,0,3.95]]:c.append(box([0.08,10.6,0.1],l,"M_Metal_Dark"))
for k in range(5):h=(k+1)*0.6;c.append(box([2.6,0.55,h],[0,-8.4+k*0.55,h/2],"M_Metal_Dark"))
M("CoreHall_Catwalk","Catwalks",c)
m=[cyl(0.5,10.5,[9.7,2.5,1.5],"M_Pipe",r=[0,90,0]),cyl(0.5,10.5,[-9.7,-2.5,1.5],"M_Pipe",r=[0,90,0]),
   cyl(0.5,10.5,[2.5,9.7,1.5],"M_Pipe",r=[90,0,0]),cyl(0.5,10.5,[-2.5,-9.7,1.5],"M_Pipe",r=[90,0,0]),
   box([3,2,2.2],[11,-11,1.1],"M_Metal_Panel"),cyl(1.6,4,[-11,11,2],"M_Metal_Panel",v=20),
   cone(1.6,0.7,[-11,11,4.35],"M_Metal_Dark",rad2=0.4,v=20),cyl(1.65,0.4,[-11,11,1.0],"M_Hazard_Yellow",v=20)]
M("CoreHall_Machinery","Machinery",m)
cl=[]
for y in[-9,-3,3,9]:lstrip(cl,0,y,11.85,20,'x')
for l,r in[([14.6,0,8],[0,90,0]),([-14.6,0,8],[0,90,0]),([0,14.6,8],[90,0,0]),([0,-14.6,8],[90,0,0])]:cl.append(cyl(0.28,0.25,l,"M_Emit_Red",r=r,v=12))
M("CoreHall_Lighting","Lighting",cl)
# control room (overlooks reactor)
cr=room(-12,12,15,30,0,5,wm="M_Metal_Panel",py=[door(0,3,0,3)]);reg_door('x',30,0,3,-1)
M("ControlRoom_Shell","Structure",cr);ceil_of("ControlRoom_Ceiling",-12,12,15,30,5)
cc=[]
for x in[-7,-3.5,0,3.5,7]:cc+=[box([3.0,1.3,1.05],[x,17.2,0.52],"M_Metal_Panel"),box([2.7,0.12,0.8],[x,16.7,1.35],"M_Screen",r=[28,0,0]),box([2.6,0.07,0.12],[x,16.55,0.92],"M_Emit_Cyan",b=False)]
for x in[-6,0,6]:cc.append(box([4.5,0.12,2.4],[x,29.6,3.2],"M_Screen"))
for y in[22,24.2,26.4]:cc+=[box([1.4,1.6,2.4],[10.6,y,1.2],"M_Metal_Dark"),box([0.05,1.2,2.0],[9.88,y,1.2],"M_Emit_Blue",b=False)]
M("ControlRoom_Content","Controls",cc);acc(0,18,2.5,150,(0.3,0.7,1),2)
# central corridors + support rooms
corridor("Corr_E",'x',15,26,0,5,0,4.5);corridor("Corr_W",'x',-26,-15,0,5,0,4.5);corridor("Corr_S",'y',-26,-15,0,5,0,4.5)
sv=room(16,25,3.5,13,0,4.5,wm="M_Metal_Panel",ny=[door(20.5,2.5,0,2.8)]);reg_door('x',3.5,20.5,2.5,1)
M("ServerRoom_Shell","Structure",sv);ceil_of("ServerRoom_C",16,25,3.5,13,4.5)
svc=[]
for ry in[5,7.2,9.4,11.6]:
    for rx in[18,22.5]:
        svc.append(box([1.2,1.6,2.6],[rx,ry,1.3],"M_Metal_Dark"))
        for dz in[1.6,2.0,2.4]:svc.append(box([0.04,0.9,0.08],[rx-0.62,ry,dz],"M_Emit_Green",b=False))
M("ServerRoom_Content","Machinery",svc)
st=room(3.5,12,-25,-16,0,4.5,nx=[door(-20.5,2.5,0,2.8)]);reg_door('y',3.5,-20.5,2.5,1)
M("Storage_Shell","Structure",st);ceil_of("Storage_C",3.5,12,-25,-16,4.5)
stc=[]
for x in[6,8.5,11]:
    for y in[-23,-21]:stc.append(box([1.6,1.6,1.4],[x,y,0.7],"M_Metal_Panel"))
for x in[5,7,9]:stc+=[cyl(0.5,1.4,[x,-18,0.7],"M_Hazard_Yellow",v=12),cyl(0.52,0.2,[x,-18,1.3],"M_Metal_Dark",v=12)]
M("Storage_Content","Machinery",stc)

# ============================ TURBINE HALL + EAST WING =======================
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
    swc+=[box([2.0,1.4,3.0],[x,-9,1.5],"M_Metal_Dark"),box([2.0,1.4,3.0],[x,9,1.5],"M_Metal_Dark")]
    swc+=[box([0.05,1.0,0.4],[x-1.0,-9,2.4],"M_Emit_Red",b=False),box([0.05,1.0,0.4],[x-1.0,9,2.4],"M_Emit_Green",b=False)]
swc+=[box([3,2.4,2.6],[74,0,1.3],"M_Metal_Panel")];pipe(swc,'x',65,83,0,6.3,0.25)
M("Switchgear_Content","Machinery",swc)
corridor("Corr_E3",'x',84,90,0,5,0,4.5)
gh=room(90,118,-16,16,0,11,nx=[door(0)]);reg_door('y',90,0,4,-1)
M("GenHall_Shell","Structure",gh);ceil_of("GenHall_C",90,118,-16,16,11)
ghc=[]
for gy in[-8,0,8]:
    bx=104
    ghc+=[box([14,3,1.0],[bx,gy,0.5],"M_Metal_Dark"),cyl(1.4,9,[bx,gy,2.3],"M_Metal_Panel",r=[0,90,0],v=18),
          cyl(1.45,0.3,[bx-2,gy,2.3],"M_Hazard_Yellow",r=[0,90,0],v=18),cyl(0.35,2.6,[bx+3,gy,4.0],"M_Pipe",v=10),
          box([1.0,0.8,1.4],[bx-6.5,gy,0.7],"M_Metal_Panel")]
M("GenHall_Machinery","Machinery",ghc)
# cooling towers north of switchgear
corridor("Corr_CT",'y',12,18,74,5,0,4.5)
ct2=room(64,86,18,40,0,14,nx=[door(0)] if False else None,ny=[door(74,2.5,0,3)]);reg_door('x',18,74,2.5,-1)
M("CoolTower_Shell","Structure",ct2);ceil_of("CoolTower_C",64,86,18,40,14)
ctc=[]
for tx in[71,79]:
    ctc+=[cyl(4.0,10,[tx,29,5.0],"M_Concrete",v=20),cone(4.0,3.0,[tx,29,11.5],"M_Concrete_Dark",rad2=2.8,v=20),cyl(4.1,0.5,[tx,29,1.2],"M_Hazard_Yellow",v=20)]
M("CoolTower_Content","Machinery",ctc)

# ============================ COOLANT GALLERY + WEST WING ====================
cg=room(-52,-26,-13,13,0,9,px=[door(0)],nx=[door(0)]);reg_door('y',-26,0,4,1);reg_door('y',-52,0,4,-1)
M("CoolantGallery_Shell","Structure",cg);ceil_of("CoolantGallery_C",-52,-26,-13,13,9)
cgc=[]
for x in[-30,-34,-38,-42]:cgc+=[box([2.4,1.8,1.8],[x,-10.5,0.9],"M_Metal_Panel"),cyl(0.6,1.3,[x,-10.5,2.3],"M_Metal_Dark",r=[0,90,0],v=14)]
for x in[-30,-37,-44]:cgc+=[cyl(1.8,5.5,[x,9.5,2.75],"M_Metal_Panel",v=20),cone(1.8,0.7,[x,9.5,5.85],"M_Metal_Dark",rad2=0.5,v=20),cyl(1.85,0.45,[x,9.5,1.0],"M_Hazard_Yellow",v=20)]
cgc+=[cyl(1.5,10,[-48.5,0,2.0],"M_Steel",r=[90,0,0],v=20)]
for z in[8.3,7.9,7.5]:pipe(cgc,'x',-51,-27,-12,z,0.22)
M("CoolantGallery_Machinery","Machinery",cgc)
pool=[];px0,px1,py0,py1=-50,-40,-12,-4
pool+=wall('x',py0,px0,px1,0,0.6,0.4,"M_Concrete")+wall('x',py1,px0,px1,0,0.6,0.4,"M_Concrete")+wall('y',px0,py0,py1,0,0.6,0.4,"M_Concrete")+wall('y',px1,py0,py1,0,0.6,0.4,"M_Concrete")
pool+=[box([px1-px0-0.6,py1-py0-0.6,0.1],[(px0+px1)/2,(py0+py1)/2,-0.1],"M_Emit_Blue",b=False)]
for yy in[py0-0.4,py1+0.4]:pool.append(box([px1-px0+0.8,0.06,0.06],[(px0+px1)/2,yy,1.0],"M_Metal_Dark"))
M("SpentFuelPool","Pool",pool);acc(-45,-8,1.2,500,(0.2,0.6,1),2.5)
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
# reactor 2 south of pump house
corridor("Corr_R2",'y',-26,-12,-74,5,0,4.5)
r2=room(-90,-58,-50,-26,0,12,py=[door(-74,2.5,0,3)]);reg_door('x',-26,-74,2.5,1)
M("Reactor2_Shell","Structure",r2);ceil_of("Reactor2_C",-90,-58,-50,-26,12)
r2c=[cyl(3.5,0.6,[-74,-38,0.3],"M_Metal_Dark",v=20),cyl(2.4,7,[-74,-38,4.0],"M_Steel",v=20),
     cyl(2.5,0.3,[-74,-38,3.5],"M_Rust",v=20),cone(2.4,2.0,[-74,-38,8.5],"M_Steel",rad2=0.8,v=20),
     cyl(2.55,0.45,[-74,-38,0.9],"M_Hazard_Yellow",v=20)]
for k in range(5):h=(k+1)*0.6;r2c.append(box([2.4,0.55,h],[-67,-44+k*0.55,h/2],"M_Metal_Dark"))
M("Reactor2_Content","Machinery",r2c);acc(-74,-38,4,300,(0.5,0.9,0.3),2.5)

# ============================ SOUTH ENTRANCE COMPLEX =========================
sa=room(-8,8,-44,-26,0,6,py=[door(0)],ny=[door(0,5,0,4.2)]);reg_door('x',-26,0,4,1)
M("SurfaceAccess_Shell","Structure",sa);ceil_of("SurfaceAccess_C",-8,8,-44,-26,6)
sac=[box([5.4,0.7,4.6],[0,-44.1,2.3],"M_Metal_Dark"),box([4.2,0.4,3.8],[0,-43.7,2.2],"M_Steel")]
for zz in[1.0,2.2,3.4]:sac.append(box([4.2,0.45,0.35],[0,-43.55,zz],"M_Hazard_Yellow",b=False))
ex0,ex1,ey0,ey1=2.0,7.0,-34,-28
sac+=wall('y',ex0,ey0,ey1,0,24,0.5,"M_Concrete_Dark")+wall('x',ey0,ex0,ex1,0,24,0.5,"M_Concrete_Dark")+wall('x',ey1,ex0,ex1,6,24,0.5,"M_Concrete_Dark")
sac+=[box([4.0,4.6,2.6],[(ex0+ex1)/2,(ey0+ey1)/2,1.5],"M_Metal_Dark"),box([0.1,0.6,1.4],[(ex0+ex1)/2,ey1-0.2,1.6],"M_Emit_Cyan",b=False)]
sac+=[cyl(0.06,21,[(ex0+ex1)/2,(ey0+ey1)/2,13],"M_Metal_Dark",v=6)]
M("SurfaceAccess_Content","Surface",sac);acc(0,-42,2.2,200,(1,.2,.15),1.5);acc(4.5,-31,1.6,150,(.3,.9,1),1.5)
# security checkpoint (lots of scanners/gates)
sec=room(-14,14,-60,-44,0,6,py=[door(0,5,0,4.2)],ny=[door(0,4,0,3.5)]);reg_door('x',-44,0,4,1);reg_door('x',-60,0,4,1)
M("Security_Shell","Structure",sec);ceil_of("Security_C",-14,14,-60,-44,6)
secc=[]
for gx in[-7,0,7]:  # turnstile gates
    secc+=[box([0.6,2.0,1.1],[gx-0.9,-52,0.55],"M_Metal_Panel"),box([0.6,2.0,1.1],[gx+0.9,-52,0.55],"M_Metal_Panel"),
           box([0.18,0.18,1.3],[gx-0.9,-51,0.65],"M_Metal_Dark"),box([0.1,0.1,0.3],[gx-0.9,-51,1.4],"M_Emit_Red",b=False)]
secc+=[box([6,1.2,1.2],[10,-57,0.6],"M_Metal_Panel"),box([5.5,0.1,0.5],[10,-56.4,1.4],"M_Screen")]  # guard booth desk
M("Security_Content","Security",secc)
# reception lobby (big)
lob=room(-22,22,-90,-60,0,8,py=[door(0,4,0,3.5)],nx=[door(-69,2.5,0,3)],px=[door(-69,2.5,0,3)]);reg_door('x',-60,0,4,-1);reg_door('y',-22,-69,2.5,-1);reg_door('y',22,-69,2.5,1)
M("Lobby_Shell","Structure",lob);ceil_of("Lobby_C",-22,22,-90,-60,8)
lobc=[box([10,2,1.1],[0,-64,0.55],"M_Metal_Panel"),box([9,0.1,0.4],[0,-63,1.3],"M_Emit_Cyan",b=False)]  # reception desk
for sx in[-14,-9]:
    for sy in[-80,-76,-72]:lobc.append(box([3,1.4,0.8],[sx,sy,0.4],"M_Metal_Dark"))  # seating
lobc+=[box([8,8,0.05],[0,-86,0.03],"M_Emit_Blue",b=False)]  # floor logo glow
M("Lobby_Content","Controls",lobc)
locker=room(16,34,-78,-60,0,4.5,nx=[door(-69,2.5,0,3)]);reg_door('y',16,-69,2.5,1)
M("Locker_Shell","Structure",locker);ceil_of("Locker_C",16,34,-78,-60,4.5)
lkc=[]
for y in[-76,-74,-72,-64,-62]:lkc.append(box([14,0.5,2.2],[25,y,1.1],"M_Metal_Panel"))
M("Locker_Content","Machinery",lkc)
guard=room(-34,-16,-78,-60,0,4.5,px=[door(-69,2.5,0,3)]);reg_door('y',-16,-69,2.5,-1)
M("Guard_Shell","Structure",guard);ceil_of("Guard_C",-34,-16,-78,-60,4.5)
gdc=[box([2.2,1.1,1.0],[-25,-63,0.5],"M_Metal_Panel"),box([1.9,0.12,0.7],[-25,-62.5,1.25],"M_Screen",r=[28,0,0])]
M("Guard_Content","Controls",gdc)

# ============================ NORTH ADMIN / LABS =============================
corridor("Corr_N",'y',30,42,0,5,0,4.5)
admin=room(-30,46,42,46,0,4.5,nx=None,px=None,ny=[door(0,4,0,3.5)]);reg_door('x',42,0,4,-1)
# admin is a wide E-W corridor/junction; add doors into rooms
M("AdminCorr_Shell","Structure",admin);ceil_of("AdminCorr_C",-30,46,42,46,4.5)
off=room(-30,-8,46,68,0,4.5,ny=[door(-19,2.5,0,3)]);reg_door('x',46,-19,2.5,1)
M("Offices_Shell","Structure",off);ceil_of("Offices_C",-30,-8,46,68,4.5)
ofc=[]
for x in[-26,-19,-12]:
    for y in[50,55,60,65]:ofc+=[box([2.2,1.2,0.8],[x,y,0.4],"M_Metal_Panel"),box([0.04,0.9,0.5],[x-0.9,y,0.95],"M_Screen",b=False)]
M("Offices_Content","Controls",ofc)
brk=room(-6,16,46,64,0,4.5,ny=[door(5,2.5,0,3)]);reg_door('x',46,5,2.5,1)
M("Break_Shell","Structure",brk);ceil_of("Break_C",-6,16,46,64,4.5)
brc=[box([6,1.4,0.8],[5,55,0.4],"M_Metal_Panel"),box([2,2,1.0],[13,61,0.5],"M_Metal_Panel")]
M("Break_Content","Controls",brc)
lab=room(20,46,46,70,0,5,ny=[door(33,2.5,0,3)]);reg_door('x',46,33,2.5,1)
M("Labs_Shell","Structure",lab);ceil_of("Labs_C",20,46,46,70,5)
lbc=[]
for x in[24,30,36,42]:lbc+=[box([1.4,5,0.9],[x,55,0.45],"M_Metal_Panel"),box([1.0,0.08,0.5],[x,52,1.2],"M_Emit_Cyan",b=False)]
lbc+=[cyl(0.8,1.6,[42,66,0.8],"M_Emit_Green",v=14,b=False),box([3,2,2.4],[24,66,1.2],"M_Metal_Dark")]
M("Labs_Content","Machinery",lbc);acc(42,66,1.2,200,(0.3,1,0.4),1.5)

build_scanners()
json.dump(mods,open("reactor_level.json","w"))
json.dump(LIGHTS,open("reactor_lights.json","w"))
from collections import Counter
print("MODULES:",len(mods)," PARTS:",sum(len(x['parts']) for x in mods)," DOORS/SCANNERS:",len(DOORS)," LIGHTS:",len(LIGHTS))
print("ROOMS:",[x['name'] for x in mods if x['name'].endswith('_Shell')])
xs=[];ys=[]
for mm in mods:
    for p in mm['parts']:
        if 'l' in p:xs.append(p['l'][0]);ys.append(p['l'][1])
print("FOOTPRINT x[%.0f,%.0f] y[%.0f,%.0f]"%(min(xs),max(xs),min(ys),max(ys)))
