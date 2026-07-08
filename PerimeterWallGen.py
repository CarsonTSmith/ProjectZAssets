# PerimeterWallGen.py — modular "Perimeter Wall - Patrolling" asset kit for ProjectZ
# Data-driven generator: run inside Blender (runpy). Idempotent — purges PW_* and rebuilds.
# Conventions:
#   - Meters, Z-up. Every module origin = bottom-center (snap point).
#   - Wall panel length L=4.0, wall height H=4.0. Pillar pitch = 4.0 (panels end at pillar centers).
#   - "Topper" modules (railing / extension / light / roof) have origin at their base plane,
#     meant to sit on the wall top (z = 4.0) or tower top.
import bpy, bmesh, math, random
from mathutils import Vector, Matrix, Euler

D90 = math.pi / 2
D45 = math.pi / 4
UV_SCALE = 0.5          # box-projected UVs: 1 texture repeat per 2m

# ---------------------------------------------------------------- purge (idempotent re-run)
def purge():
    for ob in list(bpy.data.objects):
        if ob.name.startswith(("PW_", "PWL_", "PWE_", "PWtmp")):
            bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        if c.name.startswith("PW"):
            bpy.data.collections.remove(c)
    for blocks in (bpy.data.meshes, bpy.data.curves, bpy.data.lights):
        for b in list(blocks):
            if b.users == 0:
                blocks.remove(b)

purge()

# ---------------------------------------------------------------- collections
def get_col(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(col)
    return col

ROOT   = get_col("PW_PerimeterWallKit")
C_TWR  = get_col("PW_Towers", ROOT)
C_WALL = get_col("PW_Walls", ROOT)
C_TOP  = get_col("PW_Toppers", ROOT)
C_WLK  = get_col("PW_Walkway", ROOT)
C_PRP  = get_col("PW_Props", ROOT)
C_ASM  = get_col("PW_Assemblies", ROOT)
C_LBL  = get_col("PW_Labels", ROOT)

# ---------------------------------------------------------------- materials
# BlenderKit stylized tileable materials (downloaded into this .blend):
#   "PWK Stylized Concrete" (asset ab2b148a...) -> light + darkened concrete slots
#   "PWK Stylized Metal"    (asset e08b2593...) -> dark structural metal slots,
#     with a roughness floor so the big surfaces stay matte, + darker accent copy.
# Falls back to flat PW_* colors if these materials are missing from the file.
def make_variant(src, name, val=1.0, sat=1.0, rough_min=None):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = src.copy()
    m.name = name
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    if val != 1.0 or sat != 1.0:
        link = next((l for l in nt.links if l.to_node == bsdf and l.to_socket.name == 'Base Color'), None)
        if link:
            hsv = nt.nodes.new('ShaderNodeHueSaturation')
            hsv.inputs['Value'].default_value = val
            hsv.inputs['Saturation'].default_value = sat
            hsv.location = (bsdf.location.x - 220, bsdf.location.y)
            s = link.from_socket
            nt.links.remove(link)
            nt.links.new(s, hsv.inputs['Color'])
            nt.links.new(hsv.outputs['Color'], bsdf.inputs['Base Color'])
    if rough_min is not None:
        rl = next((l for l in nt.links if l.to_node == bsdf and l.to_socket.name == 'Roughness'), None)
        if rl:
            mx = nt.nodes.new('ShaderNodeMath')
            mx.operation = 'MAXIMUM'
            mx.inputs[1].default_value = rough_min
            mx.location = (bsdf.location.x - 220, bsdf.location.y - 260)
            s = rl.from_socket
            nt.links.remove(rl)
            nt.links.new(s, mx.inputs[0])
            nt.links.new(mx.outputs[0], bsdf.inputs['Roughness'])
        else:
            bsdf.inputs['Roughness'].default_value = max(bsdf.inputs['Roughness'].default_value, rough_min)
    c = src.diffuse_color
    m.diffuse_color = (c[0] * val, c[1] * val, c[2] * val, 1.0)
    return m

MAT_OVERRIDES = {}
_conc = bpy.data.materials.get("PWK Stylized Concrete")
_met = bpy.data.materials.get("PWK Stylized Metal")
if _conc:
    MAT_OVERRIDES["PW_ConcreteLight"] = _conc
    MAT_OVERRIDES["PW_ConcreteMid"] = make_variant(_conc, "PWK Stylized Concrete Dark", val=0.55, sat=0.90)
if _met:
    MAT_OVERRIDES["PW_MetalDark"] = make_variant(_met, "PWK Stylized Metal Matte", rough_min=0.45)
    MAT_OVERRIDES["PW_MetalDarker"] = make_variant(_met, "PWK Stylized Metal Matte Dark", val=0.50, rough_min=0.50)

def mat(name, color, rough=0.8, metallic=0.0, emit=0.0):
    if name in MAT_OVERRIDES:
        return MAT_OVERRIDES[name]
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if emit:
        try:
            bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
            bsdf.inputs["Emission Strength"].default_value = emit
        except KeyError:
            bsdf.inputs["Emission"].default_value = (*color, 1.0)
    m.diffuse_color = (*color, 1.0)
    return m

CON_L  = mat("PW_ConcreteLight", (0.700, 0.685, 0.640), 0.92)
CON_M  = mat("PW_ConcreteMid",   (0.430, 0.425, 0.410), 0.92)
MET_D  = mat("PW_MetalDark",     (0.100, 0.108, 0.122), 0.62, 0.55)
MET_DD = mat("PW_MetalDarker",   (0.048, 0.052, 0.060), 0.55, 0.70)
GRATE  = mat("PW_Grate",         (0.030, 0.033, 0.038), 0.45, 0.90)
WIRE   = mat("PW_WireMetal",     (0.420, 0.430, 0.450), 0.40, 0.90)
HAZ_Y  = mat("PW_HazardYellow",  (0.800, 0.560, 0.040), 0.75)
BLUE   = mat("PW_SignBlue",      (0.165, 0.330, 0.480), 0.80)
WHITE  = mat("PW_SignWhite",     (0.850, 0.855, 0.860), 0.70)
VINE   = mat("PW_Vine",          (0.100, 0.280, 0.065), 0.95)
EMIT   = mat("PW_LampEmissive",  (1.000, 0.870, 0.550), 0.40, 0.0, 5.0)

# ---------------------------------------------------------------- module builder
class B:
    """Accumulates primitives into one bmesh -> one object per module."""
    def __init__(self, name, col):
        self.name, self.col = name, col
        self.bm = bmesh.new()
        self.mats = []

    def mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def _merge(self, tmp, mi, mtx):
        for f in tmp.faces:
            f.material_index = mi
        tmp.transform(mtx)
        me = bpy.data.meshes.new("PWtmp_merge")
        tmp.to_mesh(me)
        tmp.free()
        self.bm.from_mesh(me)
        bpy.data.meshes.remove(me)

    def box(self, size, center, m, rot=None):
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        mtx = Matrix.LocRotScale(Vector(center), Euler(rot or (0, 0, 0)), Vector(size))
        self._merge(tmp, self.mi(m), mtx)

    def sheared_box(self, size, center, slope, m, rot=None):
        """Box sheared in X by Z (hazard stripes): x' = x + slope*z. Ends stay vertical.
        Optional rot tilts the sheared slab (e.g. onto a battered wall face)."""
        sx, sy, sz = size
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        for v in tmp.verts:
            x, y, z = v.co
            v.co = Vector((x * sx + slope * (z * sz), y * sy, z * sz))
        self._merge(tmp, self.mi(m),
                    Matrix.LocRotScale(Vector(center), Euler(rot or (0, 0, 0)), Vector((1, 1, 1))))

    def frustum(self, bottom, top, h, base_center, m, rot=None):
        bw, bd = bottom
        tw, td = top
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        for v in tmp.verts:
            if v.co.z > 0:
                v.co.x *= tw / bw
                v.co.y *= td / bd
        c = Vector((base_center[0], base_center[1], base_center[2] + h / 2))
        self._merge(tmp, self.mi(m), Matrix.LocRotScale(c, Euler(rot or (0, 0, 0)), Vector((bw, bd, h))))

    def cyl(self, r1, r2, h, center, m, seg=12, rot=None):
        tmp = bmesh.new()
        try:
            bmesh.ops.create_cone(tmp, cap_ends=True, segments=seg, radius1=r1, radius2=r2, depth=h)
        except TypeError:
            bmesh.ops.create_cone(tmp, cap_ends=True, segments=seg, diameter1=r1, diameter2=r2, depth=h)
        self._merge(tmp, self.mi(m), Matrix.LocRotScale(Vector(center), Euler(rot or (0, 0, 0)), Vector((1, 1, 1))))

    def chainlink(self, w, h, center, m, rot_z=0.0, spacing=0.18, t=0.016, d=0.010):
        """Diagonal lattice panel in local XZ plane (facing +/-Y), optionally yawed by rot_z."""
        mi = self.mi(m)
        Mp = Matrix.Translation(Vector(center)) @ Matrix.Rotation(rot_z, 4, 'Z')
        step = spacing * math.sqrt(2)
        c = -h + step / 2
        while c < w:                                    # +45 strips: x = z + c
            z0, z1 = max(0.0, -c), min(h, w - c)
            if z1 - z0 > 0.05:
                L = (z1 - z0) * math.sqrt(2)
                zm = (z0 + z1) / 2
                loc = Matrix.LocRotScale(Vector((zm + c - w / 2, 0, zm - h / 2)),
                                         Euler((0, -D45, 0)), Vector((L, d, t)))
                tmp = bmesh.new(); bmesh.ops.create_cube(tmp, size=1.0)
                self._merge(tmp, mi, Mp @ loc)
            c += step
        c = step / 2
        while c < w + h:                                # -45 strips: x = c - z
            z0, z1 = max(0.0, c - w), min(h, c)
            if z1 - z0 > 0.05:
                L = (z1 - z0) * math.sqrt(2)
                zm = (z0 + z1) / 2
                loc = Matrix.LocRotScale(Vector((c - zm - w / 2, 0, zm - h / 2)),
                                         Euler((0, D45, 0)), Vector((L, d, t)))
                tmp = bmesh.new(); bmesh.ops.create_cube(tmp, size=1.0)
                self._merge(tmp, mi, Mp @ loc)
            c += step

    def text(self, body, size, depth, center, m, rot=None):
        cu = bpy.data.curves.new("PWtmp_txt", 'FONT')
        cu.body, cu.size, cu.extrude = body, size, depth
        cu.align_x = cu.align_y = 'CENTER'
        ob = bpy.data.objects.new("PWtmp_txt", cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        mi = self.mi(m)
        for p in me.polygons:
            p.material_index = mi
        me.transform(Matrix.LocRotScale(Vector(center), Euler(rot or (0, 0, 0)), Vector((1, 1, 1))))
        self.bm.from_mesh(me)
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
        bpy.data.meshes.remove(me)

    def helix(self, length, r, loops, center, m, ppr=16, bevel=0.012):
        cu = bpy.data.curves.new("PWtmp_helix", 'CURVE')
        cu.dimensions = '3D'
        cu.bevel_depth = bevel
        cu.bevel_resolution = 2
        sp = cu.splines.new('POLY')
        n = loops * ppr
        sp.points.add(n)
        for i in range(n + 1):
            t = i / n
            th = 2 * math.pi * loops * t
            sp.points[i].co = (-length / 2 + length * t, r * math.cos(th), r * math.sin(th), 1)
        ob = bpy.data.objects.new("PWtmp_helix", cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        mi = self.mi(m)
        for p in me.polygons:
            p.material_index = mi
        me.transform(Matrix.Translation(Vector(center)))
        self.bm.from_mesh(me)
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
        bpy.data.meshes.remove(me)

    def lamp(self, center, s=1.0):
        """Small box lamp head with emissive core (railing/walkway lights)."""
        x, y, z = center
        self.box((0.15 * s, 0.13 * s, 0.11 * s), (x, y, z), MET_DD)
        self.box((0.11 * s, 0.15 * s, 0.07 * s), (x, y, z - 0.005), EMIT)

    def build(self, origin):
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        # world-scale box-projected UVs (dominant axis per face)
        uv = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            n = poly.normal
            ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
            for li in poly.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co
                if az >= ax and az >= ay:
                    u, v = co.x, co.y
                elif ax >= ay:
                    u, v = co.y, co.z
                else:
                    u, v = co.x, co.z
                uv.data[li].uv = (u * UV_SCALE, v * UV_SCALE)
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(self.name, me)
        self.col.objects.link(ob)
        ob.location = origin
        return ob

# ---------------------------------------------------------------- shared dims
L, H = 4.0, 4.0          # wall panel length / height

# ---------------------------------------------------------------- wall panel (variants)
def build_panel(name, variant, origin):
    """Battered fortification panel: fat 1.5m plinth, vertical grate band, then the
    body tapers 1.20m -> 0.52m deep up to the cap. Face details tilt with the slope."""
    b = B(name, C_WALL)
    ang = math.atan(((1.20 - 0.52) / 2) / 2.55)      # body batter angle (~7.6 deg)
    def hd(z):                                        # body half-depth at height z
        return 0.60 - math.tan(ang) * (z - 1.15)
    # plinth
    b.box((L, 1.50, 0.42), (0, 0, 0.21), MET_D)
    b.box((L, 1.58, 0.07), (0, 0, 0.455), MET_DD)
    # vertical vent band 0.49..1.15
    b.box((L, 0.70, 0.66), (0, 0, 0.82), MET_DD)
    for x in (-1.334, 0.0, 1.334):
        b.box((0.10, 1.26, 0.66), (x, 0, 0.82), MET_D)
    b.box((L, 1.22, 0.08), (0, 0, 0.53), MET_D)
    b.box((L, 1.22, 0.08), (0, 0, 1.11), MET_D)
    for y in (-0.58, 0.58):
        b.chainlink(3.9, 0.52, (0, y, 0.82), GRATE, spacing=0.15)
    # battered body 1.15..3.70
    b.frustum((L, 1.20), (L, 0.52), 2.55, (0, 0, 1.15), MET_D)
    # tilted concrete insets + bolts, both faces (sgn -1 = front / -Y)
    zc = 2.45
    for sgn in (-1, 1):
        b.box((L - 0.28, 0.10, 2.05), (0, sgn * (hd(zc) + 0.02), zc), CON_L, rot=(sgn * ang, 0, 0))
        for x in (-1.55, 1.55):
            for zb in (1.80, 3.20):
                b.cyl(0.030, 0.030, 0.09, (x, sgn * (hd(zb) + 0.075), zb), MET_DD, seg=8,
                      rot=(-sgn * (D90 - ang), 0, 0))
    # cap beam 3.70..4.00
    b.box((L, 0.68, 0.24), (0, 0, 3.82), MET_D)
    b.box((L, 0.76, 0.06), (0, 0, 3.97), MET_DD)
    for x in (-1.5, -0.5, 0.5, 1.5):
        b.cyl(0.025, 0.025, 0.72, (x, 0, 3.82), MET_DD, seg=8, rot=(D90, 0, 0))
    # handles on plinth front
    for x in (-0.9, 0.9):
        b.box((0.30, 0.06, 0.06), (x, -0.78, 0.30), MET_DD)
        for dx in (-0.11, 0.11):
            b.box((0.05, 0.07, 0.05), (x + dx, -0.755, 0.30), MET_DD)
    # variants
    # proud bands stay 2.60 wide so their ends clear the pillar shafts at the 4m seams
    if variant == 'number':
        zs = 2.95
        for sgn in (-1, 1):
            b.box((2.60, 0.06, 0.62), (0, sgn * (hd(zs) + 0.10), zs), BLUE, rot=(sgn * ang, 0, 0))
        b.text("12", 0.50, 0.020, (0, -(hd(2.93) + 0.150), 2.93), WHITE, rot=(D90 - ang, 0, 0))
        b.text("12", 0.50, 0.020, (0, (hd(2.93) + 0.150), 2.93), WHITE, rot=(D90 - ang, 0, math.pi))
    elif variant == 'hazard':
        zh = 2.42
        for sgn in (-1, 1):
            b.box((2.60, 0.06, 0.58), (0, sgn * (hd(zh) + 0.10), zh), HAZ_Y, rot=(sgn * ang, 0, 0))
            for c in (-0.825, -0.275, 0.275, 0.825):
                b.sheared_box((0.26, 0.05, 0.58), (c, sgn * (hd(zh) + 0.135), zh), 1.0, MET_DD,
                              rot=(sgn * ang, 0, 0))
    elif variant == 'vines':
        rng = random.Random(7)
        for _ in range(7):
            cx = rng.uniform(-1.7, 1.7)
            w = rng.uniform(0.35, 0.70)
            b.box((w, 0.86, 0.09), (cx, 0.0, 4.03), VINE)
            for _ in range(rng.randint(3, 5)):
                x = cx + rng.uniform(-w / 2, w / 2)
                ln = rng.uniform(0.5, 1.7)
                wd = rng.uniform(0.06, 0.13)
                b.box((wd, 0.06, ln), (x, -(0.40 + ln * 0.060 + rng.uniform(0.0, 0.04)),
                                       3.98 - ln / 2), VINE, rot=(-ang, 0, 0))
    return b.build(origin)

# ---------------------------------------------------------------- pillar family
def build_pillar(name, plinth, shaft_b, shaft_t, shaft_h, origin, col=C_WALL, insets=True):
    b = B(name, col)
    pw, ph = plinth
    b.box((pw, pw, ph), (0, 0, ph / 2), MET_D)
    b.box((pw + 0.06, pw + 0.06, 0.08), (0, 0, ph + 0.02), MET_DD)
    z0 = ph + 0.06
    b.frustum((shaft_b, shaft_b), (shaft_t, shaft_t), shaft_h, (0, 0, z0), MET_D)
    if insets:
        ang = math.atan(((shaft_b - shaft_t) / 2) / shaft_h)
        zc = z0 + shaft_h * 0.52
        halfw = shaft_b / 2 - math.tan(ang) * (zc - z0)
        r = halfw + 0.028
        ih = shaft_h * 0.72
        b.box((shaft_b * 0.52, 0.06, ih), (0,  r, zc), CON_M, rot=( ang, 0, 0))
        b.box((shaft_b * 0.52, 0.06, ih), (0, -r, zc), CON_M, rot=(-ang, 0, 0))
        b.box((0.06, shaft_b * 0.52, ih), ( r, 0, zc), CON_M, rot=(0, -ang, 0))
        b.box((0.06, shaft_b * 0.52, ih), (-r, 0, zc), CON_M, rot=(0,  ang, 0))
    zt = z0 + shaft_h
    b.box((shaft_t + 0.14, shaft_t + 0.14, 0.20), (0, 0, zt + 0.10), MET_D)
    b.box((shaft_t - 0.06, shaft_t - 0.06, 0.24), (0, 0, zt + 0.32), MET_D)
    b.box((shaft_t - 0.28, shaft_t - 0.28, 0.10), (0, 0, zt + 0.49), MET_DD)
    return b.build(origin)

# ---------------------------------------------------------------- toppers
def build_top_railing(origin):
    b = B("PW_TopRailing", C_TOP)
    b.box((L, 0.50, 0.12), (0, 0, 0.06), MET_D)
    for x in (-1.93, -0.965, 0.0, 0.965, 1.93):
        b.box((0.07, 0.07, 1.02), (x, 0, 0.63), MET_DD)
    b.box((L, 0.07, 0.08), (0, 0, 1.18), MET_D)
    b.box((L, 0.05, 0.05), (0, 0, 0.72), MET_DD)
    b.box((L, 0.04, 0.16), (0, 0, 0.22), MET_D)
    for x in (-1.93, 1.93):
        b.lamp((x, 0, 1.28))
    return b.build(origin)

def build_top_light(origin):
    b = B("PW_TopLight", C_TOP)
    b.box((0.32, 0.32, 0.06), (0, 0, 0.03), MET_DD)
    b.cyl(0.045, 0.045, 2.10, (0, 0, 1.11), MET_D, seg=10)
    b.cyl(0.062, 0.062, 0.16, (0, 0, 2.12), MET_DD, seg=10)
    tilt = math.radians(-16)
    b.box((0.34, 0.30, 0.16), (0, 0.10, 2.26), MET_D, rot=(tilt, 0, 0))
    b.box((0.28, 0.27, 0.06), (0, 0.115, 2.20), EMIT, rot=(tilt, 0, 0))
    return b.build(origin)

def build_ladder(name, h, origin, col=C_TOP):
    b = B(name, col)
    for x in (-0.20, 0.20):
        b.box((0.06, 0.06, h), (x, 0, h / 2), MET_D)
    z = 0.25
    while z < h - 0.2:
        b.cyl(0.022, 0.022, 0.40, (0, 0, z), MET_DD, seg=8, rot=(0, D90, 0))
        z += 0.30
    for zz in (0.35, h - 0.35):
        for x in (-0.20, 0.20):
            b.box((0.06, 0.14, 0.06), (x, -0.10, zz), MET_DD)
    return b.build(origin)

def build_lower_grate(origin):
    b = B("PW_LowerGrate", C_TOP)
    b.box((1.50, 0.07, 0.07), (0, 0, 0.035), MET_D)
    b.box((1.50, 0.07, 0.07), (0, 0, 1.065), MET_D)
    for x in (-0.715, 0.715):
        b.box((0.07, 0.07, 1.10), (x, 0, 0.55), MET_D)
    b.chainlink(1.36, 0.96, (0, 0, 0.55), GRATE, spacing=0.14)
    return b.build(origin)

def build_fence_panel(origin):
    b = B("PW_FencePanel", C_TOP)
    for x in (-0.975, 0.975):
        b.cyl(0.05, 0.05, 1.70, (x, 0, 0.85), MET_D, seg=10)
        b.cyl(0.062, 0.062, 0.05, (x, 0, 1.72), MET_DD, seg=10)
    b.box((2.0, 0.06, 0.06), (0, 0, 1.62), MET_D)
    b.box((2.0, 0.05, 0.05), (0, 0, 0.12), MET_D)
    b.chainlink(1.85, 1.44, (0, 0, 0.86), GRATE, spacing=0.16)
    return b.build(origin)

def build_top_roof(origin):
    b = B("PW_TopRoof", C_TOP)
    rz = (0, 0, math.pi / 8)
    b.cyl(1.62, 1.62, 0.14, (0, 0, 0.07), MET_D, seg=8, rot=rz)
    b.cyl(1.55, 0.30, 0.48, (0, 0, 0.38), MET_D, seg=8, rot=rz)
    b.cyl(0.32, 0.32, 0.08, (0, 0, 0.64), MET_DD, seg=8, rot=rz)
    return b.build(origin)

# ---------------------------------------------------------------- towers
TOWER_TOP_Z = 4.24

def build_tower_base(origin):
    b = B("PW_TowerBase", C_TWR)
    b.box((3.30, 3.30, 0.30), (0, 0, 0.15), MET_D)
    b.box((3.05, 3.05, 0.30), (0, 0, 0.45), MET_D)
    b.frustum((2.75, 2.75), (2.02, 2.02), 3.30, (0, 0, 0.60), MET_D)
    ang = math.atan(((2.75 - 2.02) / 2) / 3.30)
    zc = 2.30
    r = (2.75 / 2 - math.tan(ang) * (zc - 0.60)) + 0.030
    b.box((1.25, 0.10, 2.55), (0,  r, zc), CON_L, rot=( ang, 0, 0))
    b.box((1.25, 0.10, 2.55), (0, -r, zc), CON_L, rot=(-ang, 0, 0))
    b.box((0.10, 1.25, 2.55), ( r, 0, zc), CON_L, rot=(0, -ang, 0))
    b.box((0.10, 1.25, 2.55), (-r, 0, zc), CON_L, rot=(0,  ang, 0))
    # hatch low on -Y face
    zh = 1.35
    rh = 2.75 / 2 - math.tan(ang) * (zh - 0.60) + 0.035
    b.box((0.85, 0.10, 1.00), (0, -rh, zh), MET_DD, rot=(-ang, 0, 0))
    b.box((2.32, 2.32, 0.26), (0, 0, 4.03), MET_D)
    b.box((2.42, 2.42, 0.08), (0, 0, 4.20), MET_DD)
    return b.build(origin)

def build_tower_top(origin):
    """Wide patrol balcony (4.5m deck on a mount collar + struts), cabin, pyramid roof.
    Railing has a 0.9m gap centered on the -X side where the access ladder lands."""
    b = B("PW_TowerTop", C_TWR)
    DECK = 4.50
    half = DECK / 2
    # mount collar (nests on the tower base collar) + support struts to the deck edge
    b.box((2.20, 2.20, 0.55), (0, 0, 0.275), MET_D)
    ang = math.atan2(0.50, 0.95)
    scx, scz = (1.10 + 2.05) / 2, 0.30
    for s in (-0.85, 0.85):
        b.box((1.15, 0.10, 0.10), ( scx, s, scz), MET_DD, rot=(0, -ang, 0))
        b.box((1.15, 0.10, 0.10), (-scx, s, scz), MET_DD, rot=(0,  ang, 0))
        b.box((0.10, 1.15, 0.10), (s,  scx, scz), MET_DD, rot=( ang, 0, 0))
        b.box((0.10, 1.15, 0.10), (s, -scx, scz), MET_DD, rot=(-ang, 0, 0))
    # deck 0.55..0.75
    b.box((DECK + 0.10, DECK + 0.10, 0.08), (0, 0, 0.55), MET_DD)
    b.box((DECK, DECK, 0.20), (0, 0, 0.65), MET_D)
    dz = 0.75
    # perimeter railing; -X side split around the ladder gap (y in [-0.45, 0.45])
    p = half - 0.11
    posts = set()
    for t in (-p, -p / 2, 0.0, p / 2, p):
        posts |= {(t, p), (t, -p), (p, t)}
    posts |= {(-p, -p), (-p, -p / 2), (-p, -0.45), (-p, 0.45), (-p, p / 2), (-p, p)}
    for x, y in posts:
        b.box((0.07, 0.07, 0.90), (x, y, dz + 0.45), MET_DD)
    for z, (w, hh), m in ((dz + 0.86, (0.07, 0.08), MET_D), (dz + 0.42, (0.05, 0.05), MET_DD)):
        ln = 2 * p + 0.07
        b.box((ln, w, hh), (0,  p, z), m)
        b.box((ln, w, hh), (0, -p, z), m)
        b.box((w, ln, hh), ( p, 0, z), m)
        seg = p - 0.45
        for ym in (-(0.45 + seg / 2), 0.45 + seg / 2):
            b.box((w, seg, hh), (-p, ym, z), m)
    # cabin
    b.box((2.30, 2.30, 0.60), (0, 0, 1.05), MET_D)
    for s in (-1.165, 1.165):
        b.box((1.70, 0.06, 0.40), (0, s, 1.05), CON_M)
        b.box((0.06, 1.70, 0.40), (s, 0, 1.05), CON_M)
    for x in (-1.07, 1.07):
        for y in (-1.07, 1.07):
            b.box((0.16, 0.16, 1.30), (x, y, 2.00), MET_D)
    for s in (-1.10, 1.10):
        b.chainlink(1.85, 1.15, (0, s, 2.00), GRATE, rot_z=0, spacing=0.16)
        b.chainlink(1.85, 1.15, (s, 0, 2.00), GRATE, rot_z=D90, spacing=0.16)
        b.box((2.30, 0.10, 0.08), (0, s, 1.39), MET_DD)
        b.box((2.30, 0.10, 0.08), (0, s, 2.61), MET_DD)
        b.box((0.10, 2.30, 0.08), (s, 0, 1.39), MET_DD)
        b.box((0.10, 2.30, 0.08), (s, 0, 2.61), MET_DD)
    # roof
    b.box((2.55, 2.55, 0.10), (0, 0, 2.70), MET_D)
    b.box((3.05, 3.05, 0.08), (0, 0, 2.79), MET_D)
    b.cyl(2.12, 0.14, 0.72, (0, 0, 3.19), MET_D, seg=4, rot=(0, 0, D45))
    b.box((0.34, 0.34, 0.10), (0, 0, 3.58), MET_DD)
    b.cyl(0.02, 0.02, 0.50, (0, 0, 3.88), MET_DD, seg=6)
    b.box((0.06, 0.06, 0.06), (0, 0, 4.16), MET_DD)
    b.box((0.045, 0.045, 0.045), (0, 0, 4.16), EMIT)
    return b.build(origin)

# ---------------------------------------------------------------- walkway family
def crate(b, cx):
    b.box((1.70, 1.70, 2.10), (cx, 0, 1.05), MET_D)
    for x in (-0.82, 0.82):
        for y in (-0.82, 0.82):
            b.box((0.16, 0.16, 2.20), (cx + x, y, 1.10), MET_DD)
    for z in (0.07, 2.13):
        for s in (-0.82, 0.82):
            b.box((1.80, 0.14, 0.14), (cx, s, z), MET_DD)
            b.box((0.14, 1.80, 0.14), (cx + s, 0, z), MET_DD)
    b.box((1.90, 1.90, 0.14), (cx, 0, 2.25), MET_D)
    for s in (-0.865, 0.865):                       # X-braces on all 4 faces
        for r in (D45, -D45):
            b.box((2.05, 0.04, 0.10), (cx, s, 1.16), MET_DD, rot=(0, r, 0))
            b.box((0.10, 2.05, 0.04), (cx + s, 0, 1.16), MET_DD, rot=(r, 0, 0))

def walkway_rail(b, length, cx, cz_deck_top, sides=(-0.70, 0.70), mesh=True, lamps=()):
    for y in sides:
        n = max(2, int(round(length / 1.0)) + 1)
        for i in range(n):
            x = cx - length / 2 + i * (length / (n - 1))
            b.box((0.06, 0.06, 0.85), (x, y, cz_deck_top + 0.425), MET_DD)
        b.box((length, 0.06, 0.07), (cx, y, cz_deck_top + 0.88), MET_D)
        if mesh:
            b.chainlink(length - 0.1, 0.72, (cx - (length - 0.1) / 2 + (length - 0.1) / 2, y, cz_deck_top + 0.40), GRATE, spacing=0.20)
        for lx in lamps:
            b.lamp((lx, y, cz_deck_top + 0.98), s=0.9)

def build_walkway_module(origin):
    b = B("PW_WalkwayModule", C_WLK)
    crate(b, -2.9)
    crate(b, 2.9)
    b.box((4.0, 1.50, 0.15), (0, 0, 2.245), MET_D)
    for y in (-0.70, 0.70):
        b.box((4.0, 0.10, 0.35), (0, y, 2.00), MET_DD)
    walkway_rail(b, 4.0, 0, 2.32, lamps=(0.0,))
    return b.build(origin)

def build_walkway_endcap(origin):
    b = B("PW_WalkwayEndCap", C_WLK)
    crate(b, 0)
    b.box((1.20, 1.50, 0.15), (1.50, 0, 2.245), MET_D)
    for y in (-0.70, 0.70):
        b.box((1.20, 0.10, 0.30), (1.50, y, 2.02), MET_DD)
    walkway_rail(b, 1.2, 1.5, 2.32, mesh=True)
    return b.build(origin)

def build_walkway_slab(origin):
    """Plain modular metal deck plate — no rails, no frame. Same 2.0 x 1.5 x 0.15
    format as the walkway extension deck, origin at slab underside: chain every 2m,
    lay on wall tops (z=4), or span between crates."""
    b = B("PW_WalkwaySlab", C_WLK)
    b.box((2.0, 1.50, 0.15), (0, 0, 0.075), MET_D)
    return b.build(origin)

def build_walkway_extension(origin):
    """Origin at deck underside — sits directly on a wall top (z=4)."""
    b = B("PW_WalkwayExtension", C_WLK)
    b.box((2.0, 1.50, 0.15), (0, 0, 0.075), MET_D)
    for y in (-0.68, 0.68):
        b.box((2.0, 0.14, 0.10), (0, y, 0.05), MET_DD)
    walkway_rail(b, 2.0, 0, 0.15, lamps=(-0.75, 0.75))
    return b.build(origin)

# ---------------------------------------------------------------- props
def build_barbed_wire(origin):
    b = B("PW_BarbedWire", C_PRP)
    r, loops, length = 0.22, 7, 1.5
    b.helix(length, r, loops, (0, 0, r + 0.02), WIRE)
    for k in range(26):
        th = k * (2 * math.pi * loops) / 26 + 0.4
        t = k / 26
        x = -length / 2 + length * t
        dy, dz = math.cos(th), math.sin(th)
        c = (x, (r + 0.05) * dy, (r + 0.05) * dz + r + 0.02)
        b.cyl(0.016, 0.001, 0.09, c, WIRE, seg=5, rot=(th - D90, 0, 0))
    return b.build(origin)

def build_small_light(origin):
    b = B("PW_SmallLight", C_PRP)
    b.box((0.16, 0.04, 0.20), (0, 0.08, 0.30), MET_DD)
    b.box((0.06, 0.10, 0.06), (0, 0.01, 0.34), MET_DD)
    tilt = math.radians(-14)
    b.box((0.20, 0.18, 0.14), (0, -0.06, 0.33), MET_D, rot=(tilt, 0, 0))
    b.box((0.16, 0.17, 0.06), (0, -0.065, 0.28), EMIT, rot=(tilt, 0, 0))
    b.box((0.10, 0.06, 0.30), (0, 0.075, 0.15), MET_D)
    return b.build(origin)

def build_bolt_plate(origin):
    b = B("PW_BoltPlate", C_PRP)
    b.box((0.50, 0.06, 0.50), (0, 0, 0.25), MET_D)
    for x in (-0.17, 0.17):
        for z in (0.08, 0.42):
            b.cyl(0.040, 0.036, 0.10, (x, -0.03, z), MET_DD, seg=8, rot=(D90, 0, 0))
    return b.build(origin)

def build_drain_spout(origin):
    b = B("PW_DrainSpout", C_PRP)
    b.cyl(0.070, 0.070, 1.15, (0, 0, 0.675), MET_D, seg=10)
    b.cyl(0.075, 0.075, 0.20, (0, -0.07, 1.32), MET_D, seg=10, rot=(D45, 0, 0))
    b.cyl(0.070, 0.070, 0.26, (0, -0.20, 1.39), MET_D, seg=10, rot=(D90, 0, 0))
    b.cyl(0.075, 0.075, 0.22, (0, -0.08, 0.08), MET_D, seg=10, rot=(math.radians(125), 0, 0))
    for z in (0.45, 0.95):
        b.box((0.22, 0.14, 0.05), (0, 0.05, z), MET_DD)
    return b.build(origin)

def build_hook_tie(origin):
    b = B("PW_HookTie", C_PRP)
    b.box((0.30, 0.30, 0.06), (0, 0, 0.03), MET_DD)
    for x in (-0.07, 0.07):
        b.cyl(0.032, 0.032, 0.16, (x, 0, 0.13), WIRE, seg=8)
    b.cyl(0.032, 0.032, 0.21, (0, 0, 0.21), WIRE, seg=8, rot=(0, D90, 0))
    return b.build(origin)

# ---------------------------------------------------------------- build grid
Y0, Y1, Y2, Y3 = 0.0, -9.0, -17.0, -23.0

tower_base = build_tower_base((8, Y0, 0))
tower_top  = build_tower_top((14, Y0, 0))
pillar     = build_pillar("PW_WallPillar", (1.70, 0.50), 1.42, 0.92, 3.45, (34, Y0, 0))
endcap     = build_pillar("PW_WallEndCap", (1.60, 0.45), 1.30, 0.80, 3.50, (38, Y0, 0))

panel_plain  = build_panel("PW_WallPanel_Plain",  'plain',  (0,  Y1, 0))
panel_number = build_panel("PW_WallPanel_Number", 'number', (6,  Y1, 0))
panel_hazard = build_panel("PW_WallPanel_Hazard", 'hazard', (12, Y1, 0))
panel_vines  = build_panel("PW_WallPanel_Vines",  'vines',  (18, Y1, 0))
railing      = build_top_railing((24, Y1, 0))
toplight     = build_top_light((28.5, Y1, 0))
topladder    = build_ladder("PW_TopLadder", 3.5, (32, Y1, 0))
build_lower_grate((35.5, Y1, 0))
build_fence_panel((39.5, Y1, 0))

build_walkway_module((2, Y2, 0))
build_walkway_endcap((11, Y2, 0))
build_walkway_extension((16, Y2, 0))
build_top_roof((21, Y2, 0))
build_walkway_slab((25, Y2, 0))

build_barbed_wire((0, Y3, 0))
build_small_light((3, Y3, 0))
build_bolt_plate((6, Y3, 0))
build_drain_spout((9, Y3, 0))
build_hook_tie((12, Y3, 0))

# ---------------------------------------------------------------- assemblies
def assembly(name, loc):
    e = bpy.data.objects.new(name, None)
    e.empty_display_size = 0.5
    e.location = loc
    C_ASM.objects.link(e)
    return e

def dup(src, name, parent, loc, rot=None):
    d = src.copy()
    d.name = name
    C_ASM.objects.link(d)
    d.parent = parent
    d.location = loc
    if rot:
        d.rotation_euler = rot
    return d

wt = assembly("PWE_Watchtower_Assembly", (0, Y0, 0))
dup(tower_base, "PW_WT_Base", wt, (0, 0, 0))
dup(tower_top, "PW_WT_Top", wt, (0, 0, TOWER_TOP_Z))
wt_ladder = build_ladder("PW_WT_Ladder", 5.0, (0, 0, 0), col=C_ASM)
wt_ladder.parent = wt
wt_ladder.location = (-2.33, 0, 0)   # just outside the widened 4.5m balcony deck
wt_ladder.rotation_euler = (0, 0, D90)

ws = assembly("PWE_WallStraight_Assembly", (22, Y0, 0))
dup(panel_plain, "PW_WS_Panel", ws, (0, 0, 0))
dup(pillar, "PW_WS_PillarL", ws, (-2.0, 0, 0))
dup(pillar, "PW_WS_PillarR", ws, (2.0, 0, 0))
dup(railing, "PW_WS_Railing", ws, (0, 0.10, H))
dup(toplight, "PW_WS_Light", ws, (0.9, -0.14, H))

# single-pillar variant: THE repeatable chain unit — place copies at 4m pitch along X,
# each new pillar covers the previous panel's open end; cap the last end w/ pillar/endcap
ws1 = assembly("PWE_WallStraight_Single_Assembly", (29, Y0, 0))
dup(panel_plain, "PW_WS1_Panel", ws1, (0, 0, 0))
dup(pillar, "PW_WS1_Pillar", ws1, (-2.0, 0, 0))
dup(railing, "PW_WS1_Railing", ws1, (0, 0.10, H))
dup(toplight, "PW_WS1_Light", ws1, (0.9, -0.14, H))

# ---------------------------------------------------------------- wall run demo (16 chained units)
C_RUN = get_col("PW_WallRun", ROOT)
run = bpy.data.objects.new("PWE_WallRun_Assembly", None)
run.empty_display_size = 0.5
run.location = (0, 10, 0)
C_RUN.objects.link(run)

def rdup(src, name, loc):
    d = src.copy()
    d.name = name
    C_RUN.objects.link(d)
    d.parent = run
    d.location = loc
    return d

RUN_N = 16
RUN_SPECIAL = {4: 'hazard', 12: 'hazard', 6: 'vines', 13: 'vines', 9: 'number'}
_variants = {'hazard': panel_hazard, 'vines': panel_vines, 'number': panel_number}
for i in range(RUN_N):
    x = i * L
    d = rdup(_variants.get(RUN_SPECIAL.get(i), panel_plain), "PW_RUN_Panel%02d" % i, (x, 0, 0))
    if RUN_SPECIAL.get(i) == 'vines':
        d.rotation_euler = (0, 0, math.pi)   # vines drape on the far side of the run
    rdup(pillar, "PW_RUN_Pillar%02d" % i, (x - 2.0, 0, 0))
    rdup(railing, "PW_RUN_Railing%02d" % i, (x, 0.10, H))
    if i % 2 == 0:
        rdup(toplight, "PW_RUN_Light%02d" % i, (x + 0.9, -0.14, H))
rdup(pillar, "PW_RUN_Pillar%02d" % RUN_N, (RUN_N * L - 2.0, 0, 0))   # cap the open end

# ---------------------------------------------------------------- labels
def label(txt, x, y, size=0.5):
    cu = bpy.data.curves.new("PWL_" + txt, 'FONT')
    cu.body, cu.size = txt, size
    cu.align_x, cu.align_y = 'CENTER', 'TOP'
    ob = bpy.data.objects.new("PWL_" + txt, cu)
    ob.location = (x, y, 0.01)
    C_LBL.objects.link(ob)

label("PERIMETER WALL — MODULAR KIT", 16, 5.5, 1.2)
label("WALL RUN — 16 PANELS (64m)", 30, 6.9, 0.9)
for t, x in (("WATCHTOWER (ASSEMBLY)", 0), ("TOWER BASE", 8), ("TOWER TOP", 14),
             ("WALL STRAIGHT (ASSEMBLY)", 22), ("WALL STRAIGHT 1-PILLAR", 29),
             ("WALL PILLAR", 34), ("WALL END CAP", 38)):
    label(t, x, Y0 - 2.6)
for t, x in (("PANEL PLAIN", 0), ("PANEL NUMBER", 6), ("PANEL HAZARD", 12), ("PANEL VINES", 18),
             ("TOP RAILING", 24), ("TOP LIGHT", 28.5), ("TOP LADDER", 32),
             ("LOWER GRATE", 35.5), ("FENCE PANEL", 39.5)):
    label(t, x, Y1 - 2.4)
for t, x in (("WALKWAY MODULE", 2), ("WALKWAY END CAP", 11), ("WALKWAY EXTENSION", 16), ("TOP ROOF", 21),
             ("WALKWAY SLAB", 25)):
    label(t, x, Y2 - 2.4)
for t, x in (("BARBED WIRE", 0), ("SMALL LIGHT", 3), ("BOLT PLATE", 6), ("DRAIN SPOUT", 9), ("HOOK / TIE", 12)):
    label(t, x, Y3 - 1.6, 0.35)

# ---------------------------------------------------------------- sun
sun_data = bpy.data.lights.new("PW_Sun", 'SUN')
sun_data.energy = 3.0
sun = bpy.data.objects.new("PW_Sun", sun_data)
sun.rotation_euler = (math.radians(50), 0, math.radians(30))
sun.location = (0, 0, 20)
ROOT.objects.link(sun)

bpy.context.view_layer.update()
print("PerimeterWall kit built:",
      len([o for o in bpy.data.objects if o.name.startswith('PW_')]), "modules /",
      sum(len(o.data.polygons) for o in bpy.data.objects
          if o.name.startswith('PW_') and o.type == 'MESH'), "total faces")
