# TallWallGen.py — "foreboding" 5x-tall variant of the Perimeter Wall kit for ProjectZ.
# Same visual language as PerimeterWallGen.py (battered dark-metal body, concrete insets,
# bolt rows, buttress pillars) but rebuilt PARAMETRICALLY at H=20m so the proportions read
# as monumental instead of a stretched 4m panel. Adds features that only make sense tall:
# heavy footing, horizontal string-course ribs, a corbelled machicolation cap, crenellated
# merlons, and buttress towers with beacon caps.
#
# Idempotent — purges TW_* and rebuilds. Run inside Blender via runpy.run_path.
# Conventions: meters, Z-up, every module origin = bottom-center (z=0 == ground).
import bpy, bmesh, math, random
from mathutils import Vector, Matrix, Euler

D90 = math.pi / 2
D45 = math.pi / 4
UV_SCALE = 0.5          # box-projected UVs: 1 texture repeat per 2m (matches base kit)

# ---------------------------------------------------------------- purge (idempotent re-run)
def purge():
    for ob in list(bpy.data.objects):
        if ob.name.startswith(("TW_", "TWtmp")):
            bpy.data.objects.remove(ob, do_unlink=True)
    for c in list(bpy.data.collections):
        if c.name.startswith("TW_"):
            bpy.data.collections.remove(c)
    for blocks in (bpy.data.meshes, bpy.data.curves):
        for b in list(blocks):
            if b.users == 0 and b.name.startswith(("TW", "PWtmp")):
                blocks.remove(b)
    for m in list(bpy.data.materials):                 # drop orphaned TW_ materials (e.g. old spotlights)
        if m.name.startswith("TW_") and m.users == 0:
            bpy.data.materials.remove(m)

purge()

# ---------------------------------------------------------------- collections
def get_col(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(col)
    return col

ROOT  = get_col("TW_TallWall")
C_MOD = get_col("TW_Modules", ROOT)     # source modules (built once)
C_RUN = get_col("TW_Run", ROOT)         # linked-dup run assembly

# ---------------------------------------------------------------- materials (reuse base kit)
# Resolve each logical slot to the base kit's actual datablock (BlenderKit-textured where it
# exists, flat PW_* otherwise); create a flat fallback only if nothing is present.
def getmat(names, color, rough=0.8, metallic=0.0, emit=0.0):
    for n in names:
        m = bpy.data.materials.get(n)
        if m:
            return m
    m = bpy.data.materials.new(names[0])
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

CON_L  = getmat(["PWK Stylized Concrete",           "PW_ConcreteLight"], (0.700, 0.685, 0.640), 0.92)
CON_M  = getmat(["PWK Stylized Concrete Dark",      "PW_ConcreteMid"],   (0.430, 0.425, 0.410), 0.92)
MET_D  = getmat(["PWK Stylized Metal Matte",        "PW_MetalDark"],     (0.100, 0.108, 0.122), 0.62, 0.55)
MET_DD = getmat(["PWK Stylized Metal Matte Dark",   "PW_MetalDarker"],   (0.048, 0.052, 0.060), 0.55, 0.70)
GRATE  = getmat(["PW_Grate"],        (0.030, 0.033, 0.038), 0.45, 0.90)
HAZ_Y  = getmat(["PW_HazardYellow"], (0.800, 0.560, 0.040), 0.75)
BLUE   = getmat(["PW_SignBlue"],     (0.165, 0.330, 0.480), 0.80)
WHITE  = getmat(["PW_SignWhite"],    (0.850, 0.855, 0.860), 0.70)
EMIT   = getmat(["PW_LampEmissive"], (1.000, 0.550, 0.240), 0.40, 0.0, 6.0)   # amber beacon

# ---------------------------------------------------------------- module builder (from base kit)
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
        me = bpy.data.meshes.new("TWtmp_merge")
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
        """Box sheared in X by Z (chevron stripes). Ends stay vertical."""
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
        while c < w:                                    # +45 strips
            z0, z1 = max(0.0, -c), min(h, w - c)
            if z1 - z0 > 0.05:
                Ln = (z1 - z0) * math.sqrt(2); zm = (z0 + z1) / 2
                loc = Matrix.LocRotScale(Vector((zm + c - w / 2, 0, zm - h / 2)),
                                         Euler((0, -D45, 0)), Vector((Ln, d, t)))
                tmp = bmesh.new(); bmesh.ops.create_cube(tmp, size=1.0)
                self._merge(tmp, mi, Mp @ loc)
            c += step
        c = step / 2
        while c < w + h:                                # -45 strips
            z0, z1 = max(0.0, c - w), min(h, c)
            if z1 - z0 > 0.05:
                Ln = (z1 - z0) * math.sqrt(2); zm = (z0 + z1) / 2
                loc = Matrix.LocRotScale(Vector((c - zm - w / 2, 0, zm - h / 2)),
                                         Euler((0, D45, 0)), Vector((Ln, d, t)))
                tmp = bmesh.new(); bmesh.ops.create_cube(tmp, size=1.0)
                self._merge(tmp, mi, Mp @ loc)
            c += step

    def text(self, body, size, depth, center, m, rot=None):
        cu = bpy.data.curves.new("TWtmp_txt", 'FONT')
        cu.body, cu.size, cu.extrude = body, size, depth
        cu.align_x = cu.align_y = 'CENTER'
        ob = bpy.data.objects.new("TWtmp_txt", cu)
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

    def lamp(self, center, s=1.0):
        x, y, z = center
        self.box((0.28 * s, 0.24 * s, 0.20 * s), (x, y, z), MET_DD)
        self.box((0.20 * s, 0.28 * s, 0.13 * s), (x, y, z - 0.01), EMIT)

    def build(self, origin):
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        uv = me.uv_layers.new(name="UVMap")           # world-scale box-projected UVs
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

# ================================================================ TALL WALL DIMENSIONS
L = 4.0                 # unit width / pillar pitch (unchanged — snaps to base kit grid)
H = 20.0                # total wall height (5x the 4m base panel) -> "that's a wall!"

PLINTH_H = 2.4          # heavy footing
BODY_Z0  = 2.2          # battered body starts here
CAP_Z    = 18.2         # battered body ends / cap begins
BODY_H   = CAP_Z - BODY_Z0
HD0, HD1 = 1.30, 0.58   # body HALF-depth at base / at cap (subtle batter -> massive & vertical)
BATTER   = math.atan((HD0 - HD1) / BODY_H)     # ~2.6 deg

def hd(z):              # body half-depth (Y) at height z
    return HD0 + (HD1 - HD0) * (z - BODY_Z0) / BODY_H

RIB_Z = (5.6, 9.1, 12.6, 16.1)     # horizontal string courses breaking up the height

# ---------------------------------------------------------------- tall wall panel (4m wide unit)
def build_tall_panel(name, variant='plain', top='center'):
    # top: 'center' standalone spine merlons | 'parapet' crenellated crest on the OUTER (-Y)
    #      edge for a rampart | 'flat' clear top for a unit that sits under a tower platform
    b = B(name, C_MOD)

    # --- heavy footing / plinth (proud of the body base) ---
    b.box((L, 2.90, PLINTH_H), (0, 0, PLINTH_H / 2), MET_D)
    b.box((L, 3.02, 0.14), (0, 0, PLINTH_H + 0.05), MET_DD)
    for x in (-1.55, 1.55):                                   # riveted footing pilasters
        b.box((0.34, 3.00, PLINTH_H - 0.2), (x, 0, PLINTH_H / 2), MET_DD)

    # --- battered body (one tall frustum) ---
    b.frustum((L, 2 * HD0), (L, 2 * HD1), BODY_H, (0, 0, BODY_Z0), MET_D)

    # --- base grate / murder-hole band (z ~2.9..5.1), both faces, recessed ---
    zgb = 4.0
    for sgn in (-1, 1):
        yb = sgn * (hd(zgb) + 0.02)
        b.box((L, 0.10, 2.20), (0, yb, zgb), MET_DD, rot=(sgn * BATTER, 0, 0))     # frame back
        for x in (-1.334, 0.0, 1.334):                                            # mullions
            b.box((0.14, 0.16, 2.10), (x, sgn * (hd(zgb) + 0.05), zgb), MET_D, rot=(sgn * BATTER, 0, 0))
        b.chainlink(3.7, 1.9, (0, sgn * (hd(zgb) - 0.06), zgb), GRATE, spacing=0.16)

    # --- horizontal string-course ribs + bolt rows (both faces) ---
    for z in RIB_Z:
        d = hd(z)
        b.box((L, 2 * d + 0.30, 0.44), (0, 0, z), MET_D)
        b.box((L, 2 * d + 0.44, 0.12), (0, 0, z + 0.26), MET_DD)
        for sgn in (-1, 1):
            for x in (-1.6, -0.55, 0.55, 1.6):
                b.cyl(0.05, 0.05, 0.10, (x, sgn * (d + 0.16), z), MET_DD, seg=8,
                      rot=(-sgn * (D90 - BATTER), 0, 0))

    # --- tall concrete insets in the bays between ribs (both faces) ---
    bays = ((RIB_Z[0], RIB_Z[1]), (RIB_Z[1], RIB_Z[2]), (RIB_Z[2], RIB_Z[3]), (RIB_Z[3], CAP_Z))
    for z0, z1 in bays:
        zc = (z0 + z1) / 2
        ih = (z1 - z0) - 1.0
        for sgn in (-1, 1):
            b.box((L - 0.60, 0.12, ih), (0, sgn * (hd(zc) + 0.02), zc), CON_M, rot=(sgn * BATTER, 0, 0))
            b.box((L - 0.60, 0.06, ih), (0, sgn * (hd(zc) + 0.09), zc), CON_L, rot=(sgn * BATTER, 0, 0))

    # --- corbelled machicolation cap + crenellated merlons ---
    dcap = hd(CAP_Z)
    b.box((L, 2 * dcap + 0.30, 0.34), (0, 0, CAP_Z + 0.10), MET_D)               # neck
    b.box((L + 0.04, 2 * dcap + 1.20, 0.55), (0, 0, CAP_Z + 0.55), MET_D)         # overhanging corbel
    for sgn in (-1, 1):                                                           # corbel brackets
        for x in (-1.5, -0.5, 0.5, 1.5):
            b.box((0.30, 0.55, 0.42), (x, sgn * (dcap + 0.30), CAP_Z + 0.16), MET_DD,
                  rot=(sgn * math.radians(38), 0, 0))
    deck_z = CAP_Z + 0.95
    b.box((L + 0.06, 2 * dcap + 1.24, 0.22), (0, 0, deck_z), MET_DD)              # deck cap (walk surface)
    # crown: standalone spine merlons / outward-facing rampart parapet / flat (under a tower)
    if top == 'center':
        for x in (-1.334, 0.0, 1.334):
            b.box((0.98, 2 * dcap + 0.90, 1.15), (x, 0, deck_z + 0.68), MET_D)
            b.box((1.06, 2 * dcap + 1.00, 0.12), (x, 0, deck_z + 1.32), MET_DD)
    elif top == 'parapet':
        ypar = -(dcap + 0.10)                                                    # hug the OUTER edge
        b.box((L, 0.55, 0.40), (0, ypar, deck_z + 0.31), MET_D)                  # solid parapet base
        for x in (-1.5, -0.5, 0.5, 1.5):
            b.box((0.86, 0.55, 1.05), (x, ypar, deck_z + 0.94), MET_D)           # merlons
            b.box((0.94, 0.62, 0.12), (x, ypar, deck_z + 1.52), MET_DD)
    # top == 'flat': leave the deck clear for the tower platform to sit on

    # --- foreboding signage variants (readable band low on the wall) ---
    if variant == 'number':
        zs = 6.9
        for sgn in (-1, 1):
            b.box((2.60, 0.08, 1.30), (0, sgn * (hd(zs) + 0.12), zs), BLUE, rot=(sgn * BATTER, 0, 0))
            b.text("07", 1.00, 0.03, (0, -(hd(zs) + 0.20), zs), WHITE, rot=(D90 - BATTER, 0, 0)) if sgn < 0 else \
            b.text("07", 1.00, 0.03, (0, (hd(zs) + 0.20), zs), WHITE, rot=(D90 - BATTER, 0, math.pi))
    elif variant == 'hazard':
        zh = 3.1
        for sgn in (-1, 1):
            b.box((2.80, 0.08, 0.70), (0, sgn * (hd(zh) + 0.12), zh), HAZ_Y, rot=(sgn * BATTER, 0, 0))
            for c in (-1.0, -0.4, 0.2, 0.8):
                b.sheared_box((0.30, 0.06, 0.70), (c, sgn * (hd(zh) + 0.17), zh), 1.0, MET_DD,
                              rot=(sgn * BATTER, 0, 0))
    return b.build((0, 0, 0))

# ---------------------------------------------------------------- tall buttress pillar / tower
def build_tall_pillar(name, capped=True):
    """Chunky buttress that covers panel seams and punches ~1m above the parapet with a
    corbel cap + amber beacon — the rhythm that makes the wall read as fortified.
    capped=False tucks a flat cap just under the walkway (for seams beneath a tower platform)."""
    b = B(name, C_MOD)
    PB, PH = 3.00, 2.6                          # plinth width / height
    b.box((PB, PB, PH), (0, 0, PH / 2), MET_D)
    b.box((PB + 0.10, PB + 0.10, 0.14), (0, 0, PH + 0.05), MET_DD)
    z0 = PH + 0.10
    SB, ST = 2.30, 1.30                         # shaft base / top width
    SH = CAP_Z - z0                             # shaft height (top flush with wall cap)
    b.frustum((SB, SB), (ST, ST), SH, (0, 0, z0), MET_D)
    ang = math.atan(((SB - ST) / 2) / SH)
    # vertical concrete inset ribs on all 4 faces
    for zc in (z0 + SH * 0.30, z0 + SH * 0.72):
        halfw = SB / 2 - math.tan(ang) * (zc - z0)
        r = halfw + 0.03
        ih = SH * 0.34
        b.box((SB * 0.46, 0.08, ih), (0,  r, zc), CON_M, rot=( ang, 0, 0))
        b.box((SB * 0.46, 0.08, ih), (0, -r, zc), CON_M, rot=(-ang, 0, 0))
        b.box((0.08, SB * 0.46, ih), ( r, 0, zc), CON_M, rot=(0, -ang, 0))
        b.box((0.08, SB * 0.46, ih), (-r, 0, zc), CON_M, rot=(0,  ang, 0))
    # sloped buttress spurs kicking out at the base (foreboding footing)
    for sgn in (-1, 1):
        b.frustum((1.10, 0.60), (0.50, 0.30), 3.6, (0, sgn * (SB / 2 + 0.25), 0.0), MET_DD,
                  rot=(sgn * math.radians(20), 0, 0))
    zt = z0 + SH
    if capped:
        # corbel cap block (overhangs the shaft top), rises above the wall parapet
        b.box((ST + 0.30, ST + 0.30, 0.34), (0, 0, zt + 0.17), MET_D)
        b.box((ST + 0.60, ST + 0.60, 0.30), (0, 0, zt + 0.49), MET_D)    # overhanging machicolation
        b.box((ST + 0.10, ST + 0.10, 1.05), (0, 0, zt + 1.16), MET_D)    # merlon cap tower
        b.box((ST + 0.24, ST + 0.24, 0.14), (0, 0, zt + 1.75), MET_DD)
        b.box((0.34, 0.34, 0.30), (0, 0, zt + 1.98), MET_DD)             # amber beacon
        b.box((0.22, 0.22, 0.20), (0, 0, zt + 2.02), EMIT)
    else:
        b.box((ST + 0.20, ST + 0.20, 0.20), (0, 0, zt + 0.10), MET_DD)   # flat cap, hides under deck
    return b.build((0, 0, 0))

# ================================================================ build source modules
# rampart panels carry an outward-facing crenellated parapet; 'flat' variants clear the top
# for the units that sit under a surveillance-tower platform. Pillars: beacon + flat.
p_parapet = build_tall_panel("TW_Panel_Parapet", 'plain',  'parapet')
p_flat    = build_tall_panel("TW_Panel_Flat",    'plain',  'flat')
p_hazard  = build_tall_panel("TW_Panel_Hazard",  'hazard', 'parapet')
pillar    = build_tall_pillar("TW_Pillar", capped=True)
pillar_lo = build_tall_pillar("TW_Pillar_Flat", capped=False)

# ---------------------------------------------------------------- double-wall rampart demo
# Two parallel tall walls GAP apart, parapet facing outward on each; a walkway bridges their
# tops; base-kit surveillance cabins on bastion platforms straddle it — "like before".
GAP    = 4.0
RUN_N  = 11                                     # ~44m run
Z_WALK = CAP_Z + 0.95 + 0.11                    # top of the deck cap (~19.26) = walk level
TOWER_X = (L * 2, L * 8)                         # tower centres along the walkway
SIGN   = {0: p_hazard, 5: p_hazard, 10: p_hazard}   # concrete + yellow/black hazard accents only

def under_tower(x):                              # inside an ~8m platform footprint?
    return any(abs(x - tx) <= 4.3 for tx in TOWER_X)

run = bpy.data.objects.new("TW_Rampart_Assembly", None)
run.empty_display_size = 1.5
run.location = (0, 40, 0)
C_RUN.objects.link(run)

def rdup(src, name, loc, rot=None):
    d = src.copy(); d.name = name
    C_RUN.objects.link(d); d.parent = run; d.location = loc
    if rot:
        d.rotation_euler = rot
    return d

def build_wall(prefix, y0, flip):
    """flip=True rotates the wall 180 so its parapet faces the far side (both walls face out)."""
    rot = (0, 0, math.pi) if flip else None
    for i in range(RUN_N):
        x = i * L
        panel = p_flat if under_tower(x) else (p_parapet if flip else SIGN.get(i, p_parapet))
        rdup(panel, "%s_Panel%02d" % (prefix, i), (x, y0, 0), rot)
        pil = pillar_lo if under_tower(x - 2.0) else pillar
        rdup(pil, "%s_Pillar%02d" % (prefix, i), (x - 2.0, y0, 0))
    endx = RUN_N * L - 2.0
    rdup(pillar_lo if under_tower(endx) else pillar, "%s_PillarEnd" % prefix, (endx, y0, 0))

build_wall("TW_A", 0.0, False)     # south wall — parapet + signage faces -Y (outward)
build_wall("TW_B", GAP, True)      # north wall — rotated so parapet faces +Y (outward)

# walkway deck bridging the gap between the two wall tops (top flush with the walk level)
DECK_CX = (RUN_N - 1) * L / 2
_d = B("TW_Rampart_Deck", C_RUN)
_d.box((RUN_N * L + 2.0, GAP - 1.2, 0.14), (0, 0, -0.07), MET_D)
for i in range(RUN_N + 1):
    _d.box((0.22, GAP - 0.9, 0.20), ((i * L - 2.0) - DECK_CX, 0, -0.24), MET_DD)   # cross beams
deck = _d.build((0, 0, 0)); deck.parent = run
deck.location = (DECK_CX, GAP / 2, Z_WALK)

# surveillance towers: bastion platform + guard cabin (reused from the base kit) + steps
tp = bpy.data.objects.get("PW_TowerPlatform")
tt = bpy.data.objects.get("PW_TowerTop")
for k, tx in enumerate(TOWER_X):
    if tp:
        rdup(tp, "TW_TowerPlatform%d" % k, (tx, GAP / 2, Z_WALK))
    if tt:
        rdup(tt, "TW_Tower%d" % k, (tx, GAP / 2, Z_WALK + 0.06))
    _s = B("TW_TowerSteps%d" % k, C_RUN)
    _s.box((1.2, 0.30, 0.50), (0, 0.15, 0.25), MET_DD)
    _s.box((1.2, 0.30, 0.25), (0, 0.45, 0.125), MET_DD)
    st = _s.build((0, 0, 0)); st.parent = run
    st.location = (tx - 2.25, GAP / 2, Z_WALK + 0.06); st.rotation_euler = (0, 0, D90)
if not (tp and tt):
    print("WARNING: base-kit PW_TowerPlatform/PW_TowerTop missing -> towers skipped")

# park the source modules as a tidy catalog row well clear of everything else
for k, src in enumerate((p_parapet, p_flat, p_hazard, pillar, pillar_lo)):
    src.location = (k * 6.0, 62.0, 0)

# ---------------------------------------------------------------- sun (only if scene has none)
if not any(o.type == 'LIGHT' for o in bpy.data.objects):
    sd = bpy.data.lights.new("TW_Sun", 'SUN'); sd.energy = 3.0
    su = bpy.data.objects.new("TW_Sun", sd)
    su.rotation_euler = (math.radians(52), 0, math.radians(35))
    su.location = (0, 0, 30)
    ROOT.objects.link(su)

bpy.context.view_layer.update()
print("TallWall built:",
      len([o for o in bpy.data.objects if o.name.startswith('TW_')]), "objects /",
      sum(len(o.data.polygons) for o in bpy.data.objects
          if o.name.startswith('TW_') and o.type == 'MESH'), "unique-mesh faces")
