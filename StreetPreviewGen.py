"""
StreetPreviewGen.py  --  builds a stylized stone walkway + block of buildings
inside Wall.blend so the wall/floor materials can be judged in context.

Everything lands in the "StreetPreview" collection with a PVW_ name prefix,
so it can be deleted in one click without touching the material lab.

UV convention: the lab walls map 1 UV unit per metre, so every surface here is
world-planar projected at 1 unit/m -- materials read at exactly the authored
scale and tile continuously across separate pieces.

Run:  exec(open("/home/carson/Blender/ProjectZAssets/StreetPreviewGen.py").read())
"""

import bpy, bmesh, math
from mathutils import Vector, Matrix, Euler

PVW = "PVW_"
ROOT = "StreetPreview"

# ---------------------------------------------------------------- materials --

def M(name):
    m = bpy.data.materials.get(name)
    if m is None:
        raise KeyError("missing material: " + name)
    return m


# Per-material UV density (repeats per metre). The lab walls are authored at
# 1 repeat/m; chunky stone reads better shrunk, big patterns better enlarged.
MAT_UV_SCALE = {
    "Stylized Stone Gray": 2.2,
    "Stylized Stone Tiles": 0.7,
    "Stylized Stone Sharp": 1.8,
    "Industrial Grid Stone Pavement": 0.5,
    "Stylized Clover Ground": 1.6,
    "Stylized Bricks Pavement": 0.8,
    "Cartoon Stylized Wood": 1.5,
    "Smooth Metal": 1.0,
    "White stone stylized": 0.9,
    "Stone bricks": 1.4,
}


def tinted_glass(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.035, 0.055, 0.075, 1.0)
    b.inputs["Roughness"].default_value = 0.06
    b.inputs["Metallic"].default_value = 0.35
    out.location = (300, 0)
    nt.links.new(b.outputs[0], out.inputs[0])
    return m


def emissive(name, color, strength):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs[0].default_value = (color[0], color[1], color[2], 1.0)
    em.inputs[1].default_value = strength
    out.location = (200, 0)
    nt.links.new(em.outputs[0], out.inputs[0])
    return m

# --------------------------------------------------------------- collections --

def ensure_coll(name, parent):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    if c.name not in [ch.name for ch in parent.children]:
        parent.children.link(c)
    return c


def purge():
    root = bpy.data.collections.get(ROOT)
    if root:
        kids = [root] + list(root.children_recursive)
        for c in kids:
            for o in list(c.objects):
                bpy.data.objects.remove(o, do_unlink=True)
        for c in kids:
            bpy.data.collections.remove(c)
    for me in list(bpy.data.meshes):
        if me.users == 0 and me.name.startswith(PVW):
            bpy.data.meshes.remove(me)

# ------------------------------------------------------------- mesh builder --

class MB:
    """Accumulates many primitives into one mesh with per-face material slots."""

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.mats = []
        # per-face UV density override; 0 means "fall back to MAT_UV_SCALE"
        self.uvlay = self.bm.faces.layers.float.new("uvscale")

    def _mi(self, mat):
        for i, m in enumerate(self.mats):
            if m is mat:
                return i
        self.mats.append(mat)
        return len(self.mats) - 1

    def _tag(self, verts, mi, uvs=0.0):
        for f in {f for v in verts for f in v.link_faces}:
            f.material_index = mi
            f[self.uvlay] = uvs

    def box(self, center, size, mat, rot=None, uvs=0.0):
        mi = self._mi(mat)
        verts = bmesh.ops.create_cube(self.bm, size=1.0)["verts"]
        mtx = Matrix.Translation(Vector(center))
        if rot:
            mtx = mtx @ Euler(rot, "XYZ").to_matrix().to_4x4()
        mtx = mtx @ Matrix.Diagonal(Vector(size).to_4d())
        bmesh.ops.transform(self.bm, matrix=mtx, verts=verts)
        self._tag(verts, mi, uvs)

    def cyl(self, center, radius, height, mat, segments=32, radius_top=None,
            rot=None, uvs=0.0):
        mi = self._mi(mat)
        r2 = radius if radius_top is None else radius_top
        try:
            verts = bmesh.ops.create_cone(
                self.bm, cap_ends=True, cap_tris=False, segments=segments,
                radius1=radius, radius2=r2, depth=height)["verts"]
        except TypeError:
            verts = bmesh.ops.create_cone(
                self.bm, cap_ends=True, cap_tris=False, segments=segments,
                diameter1=radius * 2, diameter2=r2 * 2, depth=height)["verts"]
        mtx = Matrix.Translation(Vector(center))
        if rot:
            mtx = mtx @ Euler(rot, "XYZ").to_matrix().to_4x4()
        bmesh.ops.transform(self.bm, matrix=mtx, verts=verts)
        self._tag(verts, mi, uvs)

    def ring(self, center, r_in, r_out, height, mat, segments=64, uvs=0.0):
        """Solid annulus (paving band), z-centred on center[2]."""
        mi = self._mi(mat)
        bm = self.bm
        cx, cy, cz = center
        zb, zt = cz - height / 2.0, cz + height / 2.0
        loops = {}
        for key, r, z in (("bi", r_in, zb), ("bo", r_out, zb),
                          ("ti", r_in, zt), ("to", r_out, zt)):
            row = []
            for i in range(segments):
                a = 2.0 * math.pi * i / segments
                row.append(bm.verts.new((cx + r * math.cos(a), cy + r * math.sin(a), z)))
            loops[key] = row
        bm.verts.ensure_lookup_table()
        made = []
        for i in range(segments):
            j = (i + 1) % segments
            made.append(bm.faces.new((loops["ti"][i], loops["ti"][j], loops["to"][j], loops["to"][i])))
            made.append(bm.faces.new((loops["bo"][i], loops["bo"][j], loops["bi"][j], loops["bi"][i])))
            made.append(bm.faces.new((loops["to"][i], loops["to"][j], loops["bo"][j], loops["bo"][i])))
            made.append(bm.faces.new((loops["bi"][i], loops["bi"][j], loops["ti"][j], loops["ti"][i])))
        for f in made:
            f.material_index = mi
            f[self.uvlay] = uvs
        bm.normal_update()

    def finish(self, coll, origin=(0, 0, 0), bevel=0.03, uv_scale=1.0):
        origin = Vector(origin)
        bmesh.ops.translate(self.bm, verts=self.bm.verts, vec=-origin)
        me = bpy.data.meshes.new(PVW + self.name)
        self.bm.faces.ensure_lookup_table()
        overrides = [f[self.uvlay] for f in self.bm.faces]   # to_mesh keeps face order
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(PVW + self.name, me)
        ob.location = origin
        coll.objects.link(ob)
        uv_world_project(ob, uv_scale, origin, overrides)
        if bevel:
            mod = ob.modifiers.new("Bevel", "BEVEL")
            mod.width = bevel
            mod.segments = 2
            mod.limit_method = "ANGLE"
            mod.angle_limit = math.radians(40)
        return ob


def uv_world_project(ob, scale, origin, overrides=None):
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers.active.data
    ox, oy, oz = origin
    co = [v.co for v in me.vertices]
    base = scale
    slot_scale = [base * MAT_UV_SCALE.get(m.name, 1.0) if m else base
                  for m in me.materials] or [base]
    for pi, p in enumerate(me.polygons):
        n = p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        ov = overrides[pi] if overrides and pi < len(overrides) else 0.0
        scale = base * ov if ov else slot_scale[min(p.material_index, len(slot_scale) - 1)]
        for li in p.loop_indices:
            v = co[me.loops[li].vertex_index]
            wx, wy, wz = v.x + ox, v.y + oy, v.z + oz
            if ax == 0:
                u, w = wy, wz
            elif ax == 1:
                u, w = wx, wz
            else:
                u, w = wx, wy
            uvl[li].uv = (u * scale, w * scale)

# ------------------------------------------------------------------ facades --

SUN_DIR = Vector((-0.80, 0.18, 0.57)).normalized()   # direction *towards* the sun

BASE_H = 0.7      # plinth
GF_H = 4.6        # ground floor / storefront
FL_H = 3.5        # upper floor
WT = 0.45         # wall thickness


def punched_run(mb, axis, fixed, inward, a0, a1, z0, sill, head, floor_h,
                wall, glass, frame_m, pier=1.0, maxwin=3.0, door=False):
    """One storey of a wall run with window openings. axis 'X' -> runs along X."""
    L = a1 - a0
    n = int(round((L - pier) / (maxwin + pier)))
    n = max(1, n)
    win_w = (L - pier * (n + 1)) / n
    if win_w < 0.7:
        n = 1
        win_w = max(0.7, L - 2 * pier)
    pier_w = (L - win_w * n) / (n + 1)

    def place(ac, asz, zc, zsz, thick, mat, off=0.0):
        if axis == "X":
            mb.box((ac, fixed + inward * (thick / 2.0 + off), zc), (asz, thick, zsz), mat)
        else:
            mb.box((fixed + inward * (thick / 2.0 + off), ac, zc), (thick, asz, zsz), mat)

    mid = (a0 + a1) / 2.0
    door_i = (n // 2) if door else -1
    # header band above the openings
    place(mid, L, z0 + head + (floor_h - head) / 2.0, floor_h - head, WT, wall)
    # piers between openings, plus the wall below them down to floor level
    for i in range(n + 1):
        pc = a0 + i * (pier_w + win_w) + pier_w / 2.0
        place(pc, pier_w, z0 + (sill + head) / 2.0, head - sill, WT, wall)
        place(pc, pier_w, z0 + sill / 2.0, sill, WT, wall)

    BAR = 0.12          # frame bar thickness
    for i in range(n):
        wc = a0 + pier_w * (i + 1) + win_w * i + win_w / 2.0
        is_door = (i == door_i)
        zb = z0 + (0.02 if is_door else sill)
        zt = z0 + head
        if not is_door:                                  # spandrel under the opening
            place(wc, win_w + 0.02, z0 + sill / 2.0, sill, WT, wall)
        # glazing, set back behind the reveal
        place(wc, win_w, (zb + zt) / 2.0, zt - zb, 0.08, glass, off=WT - 0.09)
        # proud frame around the opening + centre mullion
        place(wc, win_w + 2 * BAR, zb + BAR / 2.0, BAR, 0.16, frame_m, off=-0.05)
        place(wc, win_w + 2 * BAR, zt - BAR / 2.0, BAR, 0.16, frame_m, off=-0.05)
        for s in (-1, 1):
            place(wc + s * (win_w + BAR) / 2.0, BAR, (zb + zt) / 2.0, zt - zb,
                  0.16, frame_m, off=-0.05)
        place(wc, 0.08, (zb + zt) / 2.0, zt - zb, 0.13, frame_m, off=-0.03)
        if is_door:                                      # transom over the door
            place(wc, win_w, zb + 2.35, 0.1, 0.13, frame_m, off=-0.03)


def build_building(name, cx, front_y, sign, width, depth, floors,
                   wall, base_m, trim_m, roof_m, glass, interior, frame_m,
                   coll, neon=None, awning=None):
    mb = MB("Bldg_" + name)
    x0, x1 = cx - width / 2.0, cx + width / 2.0
    y_f = front_y
    y_b = front_y + sign * depth
    ylo, yhi = min(y_f, y_b), max(y_f, y_b)
    H = BASE_H + GF_H + (floors - 1) * FL_H
    cy = (y_f + y_b) / 2.0

    # plinth ---------------------------------------------------------------
    mb.box((cx, cy, BASE_H / 2.0), (width + 0.24, depth + 0.24, BASE_H), base_m)

    # storefront + upper storeys on front and both flanks -------------------
    runs = [
        ("X", y_f, sign, x0, x1),                       # street facade
        ("Y", x0, +1, ylo + WT, yhi - WT),              # left flank
        ("Y", x1, -1, ylo + WT, yhi - WT),              # right flank
    ]
    for ri, (axis, fixed, inward, a0, a1) in enumerate(runs):
        punched_run(mb, axis, fixed, inward, a0, a1, BASE_H,
                    0.45, GF_H - 0.55, GF_H, wall, glass, frame_m,
                    pier=0.95, maxwin=3.6, door=(ri == 0))
        for i in range(1, floors):
            z = BASE_H + GF_H + (i - 1) * FL_H
            punched_run(mb, axis, fixed, inward, a0, a1, z,
                        0.95, 2.85, FL_H, wall, glass, frame_m,
                        pier=1.05, maxwin=2.3)

    # blank back wall ------------------------------------------------------
    mb.box((cx, y_b - sign * WT / 2.0, BASE_H + (H - BASE_H) / 2.0),
           (width, WT, H - BASE_H), wall)

    # dark interior so the glazing does not read as a void ------------------
    mb.box((cx, cy, BASE_H + (H - BASE_H) / 2.0),
           (width - 1.7, depth - 1.7, H - BASE_H - 0.2), interior)

    # cornice, roof deck, parapet ------------------------------------------
    mb.box((cx, cy, H + 0.25), (width + 0.55, depth + 0.55, 0.5), trim_m)
    mb.box((cx, cy, H + 0.6), (width - 0.2, depth - 0.2, 0.22), roof_m)
    pz = H + 1.15
    mb.box((cx, y_f + sign * 0.17, pz), (width, 0.34, 1.05), wall)
    mb.box((cx, y_b - sign * 0.17, pz), (width, 0.34, 1.05), wall)
    mb.box((x0 + 0.17, cy, pz), (0.34, depth - 0.68, 1.05), wall)
    mb.box((x1 - 0.17, cy, pz), (0.34, depth - 0.68, 1.05), wall)

    # rooftop clutter ------------------------------------------------------
    mb.box((cx - width * 0.22, cy + sign * depth * 0.18, H + 2.05),
           (3.4, 2.8, 2.6), base_m)
    mb.cyl((cx + width * 0.24, cy - sign * depth * 0.1, H + 1.3), 0.55, 1.2, trim_m)
    mb.cyl((cx + width * 0.24 + 1.5, cy - sign * depth * 0.1, H + 1.15), 0.4, 0.9, trim_m)

    # awning over the storefront -------------------------------------------
    if awning is not None:
        mb.box((cx, y_f - sign * 1.15, BASE_H + GF_H - 1.35),
               (width * 0.66, 2.5, 0.14), awning, rot=(sign * math.radians(14), 0, 0))

    # neon blade sign above the storefront ---------------------------------
    if neon is not None:
        mb.box((cx + width * 0.3, y_f - sign * 0.42, BASE_H + GF_H + 1.6),
               (0.35, 0.9, 3.0), neon)
        mb.box((cx + width * 0.3, y_f - sign * 0.12, BASE_H + GF_H + 1.6),
               (0.5, 0.3, 3.3), trim_m)

    ob = mb.finish(coll, origin=(cx, cy, 0.0))
    return ob

# -------------------------------------------------------------------- build --

def build():
    purge()
    scene = bpy.context.scene
    root = ensure_coll(ROOT, scene.collection)
    c_ground = ensure_coll(PVW + "Ground", root)
    c_walk = ensure_coll(PVW + "Walkway", root)
    c_bldg = ensure_coll(PVW + "Buildings", root)
    c_prop = ensure_coll(PVW + "Props", root)
    c_light = ensure_coll(PVW + "Lighting", root)

    # the walkway uses the material already on the StoneWalkway lab floor
    paving = M(bpy.data.objects["StoneWalkway"].data.materials[0].name
               if bpy.data.objects.get("StoneWalkway") else "Square Floor Tile")
    stone_tile = M("Stylized Stone Tiles")
    stone_gray = M("Stylized Stone Gray")
    stone_sharp = M("Stylized Stone Sharp")
    white_stone = M("White stone stylized")
    curb_m = M("Stone bricks")
    sq_tile = M("Square Floor Tile")
    runner = M("Stylized Bricks Pavement")
    pavement = M("Industrial Grid Stone Pavement")
    clover = M("Stylized Clover Ground")
    metal = M("Stylized Metal Base")
    smooth_metal = M("Smooth Metal")
    wood = M("Cartoon Stylized Wood")
    glass = tinted_glass("PVW_WindowGlass")
    interior = M("Dark Grey Plaster")

    neon_m = emissive("PVW_Neon_Magenta", (1.0, 0.10, 0.55), 3.0)
    neon_c = emissive("PVW_Neon_Cyan", (0.10, 0.85, 1.0), 2.6)
    neon_a = emissive("PVW_Neon_Amber", (1.0, 0.55, 0.12), 2.6)
    lampglow = emissive("PVW_LampGlow", (1.0, 0.86, 0.62), 6.0)

    # ground ---------------------------------------------------------------
    g = MB("Ground")
    g.box((0, 0, -0.35), (190, 190, 0.7), pavement)
    g.finish(c_ground, origin=(0, 0, 0), bevel=0.0)

    # walkway --------------------------------------------------------------
    w = MB("Walkway")
    PATH_HALF = 4.5
    CURB_W = 0.6
    RUN_T = 0.14      # paving slab thickness, top at z=0.14
    ax0, ax1 = 12.0, 19.0          # side alley running north between two blocks
    ay1 = 25.0

    def span(xa, xb, yc, ysz, zc, zsz, mat):
        w.box(((xa + xb) / 2.0, yc, zc), (xb - xa, ysz, zsz), mat)

    # Paving slabs tuck under the plaza rings (which sit higher), so they start
    # inside r=7; the raised runner has to stop clear of the inner ring, and the
    # curbs stay outside the circle entirely -- otherwise coplanar tops z-fight.
    for sx in (-1, 1):
        xa, xb = sorted((sx * 4.6, sx * 46.0))
        for s in (-1, 1):
            span(xa, xb, s * (1.1 + (PATH_HALF - 1.1) / 2.0), PATH_HALF - 1.1,
                 RUN_T / 2.0, RUN_T, paving)
        # same stone as the field, laid at double size so the runner still reads
        ra, rb = sorted((sx * 6.3, sx * 46.0))
        w.box(((ra + rb) / 2.0, 0.0, 0.085), (rb - ra, 2.2, 0.17), paving, uvs=0.5)
        # curbs, broken where the alley opens onto the street
        for s in (-1, 1):
            segs = [(sx * 7.2, sx * 46.0)]
            if s > 0 and sx > 0:
                segs = [(7.2, ax0 - 0.7), (ax1 + 0.7, 46.0)]
            for ca, cb in segs:
                q0, q1 = sorted((ca, cb))
                span(q0, q1, s * (PATH_HALF + CURB_W / 2.0), CURB_W, 0.13, 0.26, curb_m)

    w.box(((ax0 + ax1) / 2.0, (5.1 + ay1) / 2.0, RUN_T / 2.0),
          (ax1 - ax0, ay1 - 5.1, RUN_T), paving)
    for x in (ax0 - 0.3, ax1 + 0.3):
        w.box((x, (5.6 + ay1) / 2.0, 0.13), (0.6, ay1 - 5.6, 0.26), curb_m)

    # circular plaza rosette
    w.cyl((0, 0, 0.08), 2.6, 0.16, paving, segments=64, uvs=0.5)
    w.ring((0, 0, 0.11), 2.6, 3.2, 0.22, curb_m)
    w.ring((0, 0, 0.08), 3.2, 6.2, 0.16, paving)
    w.ring((0, 0, 0.13), 6.2, 7.0, 0.26, curb_m)
    w.finish(c_walk, origin=(0, 0, 0), bevel=0.02)

    # plaza monument -------------------------------------------------------
    mon = MB("Monument")
    mon.cyl((0, 0, 0.32), 2.35, 0.34, curb_m, segments=48)
    mon.cyl((0, 0, 0.64), 1.75, 0.34, curb_m, segments=48)
    mon.cyl((0, 0, 0.96), 1.2, 0.34, white_stone, segments=48)
    mon.cyl((0, 0, 3.35), 0.62, 4.5, white_stone, segments=4, radius_top=0.34,
            rot=(0, 0, math.radians(45)))
    mon.box((0, 0, 5.95), (0.34, 0.34, 0.7), neon_c)
    mon.finish(c_prop, origin=(0, 0, 0), bevel=0.02)

    # buildings ------------------------------------------------------------
    blocks = [
        # name,        cx,   front_y, sign, w,   depth, floors, wall material,                       neon,   awning
        ("Bricks",    -27.5,  6.0,  1, 13.0, 14.0, 4, "Stylized Bricks",                     neon_m, M("Roll painted wall")),
        ("Plaster",   -14.0,  6.0,  1,  8.0, 12.0, 6, "Stylized Plaster.001",                None,   None),
        ("HexGreen",    0.5,  9.0,  1, 15.0, 16.0, 3, "Hexagonal Green tile",                neon_c, None),
        ("Voronoi",    27.0,  6.0,  1, 12.0, 13.0, 5, "Stylized Lime Green Voronoi Tiles",   None,   None),
        ("PaintRed",  -30.0, -6.0, -1, 12.0, 13.0, 5, "Roll painted wall",                   neon_a, None),
        ("SciFi",     -14.0, -6.0, -1, 12.0, 12.0, 3, "Stylized Sci Fi Pattern",             neon_c, None),
        ("Purple",      4.5, -9.0, -1, 15.0, 16.0, 4, "Abstract Purple Geometric Pattern",   neon_m, None),
        ("PaintGreen", 24.0, -6.0, -1, 14.0, 14.0, 3, "Roll painted wall Green",             None,   M("Roll painted wall")),
    ]
    for nm, cx, fy, sg, wd, dp, fl, wall_name, neon, awn in blocks:
        build_building(nm, cx, fy, sg, wd, dp, fl, M(wall_name), curb_m,
                       metal, stone_gray, glass, interior, smooth_metal, c_bldg,
                       neon=neon, awning=awn)

    # street props ---------------------------------------------------------
    p = MB("StreetProps")
    for x in (-38, -26, -14, 14, 26, 38):
        for s in (-1, 1):
            y = s * 4.85
            p.cyl((x, y, 0.15), 0.28, 0.3, stone_gray, segments=16)
            p.cyl((x, y, 2.4), 0.11, 4.5, smooth_metal, segments=16)
            p.box((x, y - s * 0.55, 4.62), (0.22, 1.2, 0.16), smooth_metal)
            p.box((x, y - s * 1.0, 4.46), (0.34, 0.55, 0.2), smooth_metal)
            p.box((x, y - s * 1.0, 4.34), (0.3, 0.5, 0.06), lampglow)
    for x in (-32, -20, 20, 32):
        for s in (-1, 1):
            y = s * 5.65
            p.box((x, y, 0.4), (2.6, 1.3, 0.8), stone_gray)
            p.box((x, y, 0.86), (2.3, 1.05, 0.16), clover)
    for x, s in ((-9.5, -1), (9.5, 1), (-9.5, 1), (9.5, -1)):
        y = s * 3.4
        p.box((x, y, 0.55), (2.6, 0.16, 0.12), wood, rot=(0, 0, 0))
        p.box((x, y - s * 0.3, 0.55), (2.6, 0.16, 0.12), wood)
        p.box((x, y + s * 0.3, 0.55), (2.6, 0.16, 0.12), wood)
        for dx in (-1.05, 1.05):
            p.box((x + dx, y, 0.28), (0.14, 0.75, 0.55), metal)
    p.finish(c_prop, origin=(0, 0, 0), bevel=0.02)

    # lighting + camera ----------------------------------------------------
    old = scene.world
    if old:
        old.use_fake_user = True
    wname = "PVW_DaySky"
    nw = bpy.data.worlds.get(wname)
    if nw is None:
        nw = bpy.data.worlds.new(wname)
    nw.use_nodes = True
    nt = nw.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = ("MULTIPLE_SCATTERING"
                    if "MULTIPLE_SCATTERING" in
                    [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
                    else "NISHITA")
    sky.sun_elevation = math.asin(SUN_DIR.z)
    sky.sun_rotation = math.atan2(SUN_DIR.x, SUN_DIR.y)
    for prop, val in (("sun_intensity", 0.25), ("air_density", 0.9),
                      ("dust_density", 0.35), ("sun_disc", False)):
        if hasattr(sky, prop):
            setattr(sky, prop, val)
    bg.inputs[1].default_value = 0.16
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    scene.world = nw

    sun_d = bpy.data.lights.new("PVW_Sun", "SUN")
    sun_d.energy = 4.5
    sun_d.angle = math.radians(2.0)
    sun_d.color = (1.0, 0.94, 0.85)
    sun = bpy.data.objects.new("PVW_Sun", sun_d)
    # Aim the sun nearly along the street axis. A cross-street sun at this
    # elevation puts the whole 12 m walkway in the buildings' shadow; raking it
    # down +X keeps the south half of the paving lit with long shadows.
    sun.rotation_euler = (-SUN_DIR).to_track_quat("-Z", "Y").to_euler()
    sun.location = (0, 0, 40)
    c_light.objects.link(sun)

    cam_d = bpy.data.cameras.new("PVW_Cam")
    cam_d.lens = 32
    cam = bpy.data.objects.new("PVW_Cam", cam_d)
    c_light.objects.link(cam)
    scene.camera = cam
    aim_camera(cam, SHOTS["street"][0], SHOTS["street"][1], SHOTS["street"][2])

    # The lab slabs all sit at the origin -- dead centre of the plaza -- and were
    # only viewport-hidden, so they still showed up in renders. Mute them for
    # both while the preview is up (clear hide_render to get them back).
    lab = [o for c in ("Walls", "Floors") for o in
           (bpy.data.collections[c].objects if c in bpy.data.collections else [])]
    lab += [o for o in (bpy.data.objects.get("Cube"),) if o]
    for o in lab:
        o.hide_set(True)
        o.hide_render = True

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.eevee.taa_render_samples = 48
    scene.eevee.use_shadows = True
    try:
        scene.eevee.use_raytracing = True
        scene.eevee.ray_tracing_options.use_denoise = True
    except Exception:
        pass

    n_obj = sum(len(c.objects) for c in [c_ground, c_walk, c_bldg, c_prop, c_light])
    n_tris = sum(len(o.data.polygons) for c in [c_ground, c_walk, c_bldg, c_prop]
                 for o in c.objects if o.type == "MESH")
    return n_obj, n_tris


def aim_camera(cam, loc, target, lens=None):
    if lens:
        cam.data.lens = lens
    cam.location = Vector(loc)
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


# name -> (camera position, look-at target, focal length)
SHOTS = {
    "street":  ((-34.0, 0.0, 1.75), (12.0, 0.0, 5.0), 28),
    "plaza":   ((-12.5, -2.6, 1.75), (6.0, 3.0, 4.0), 30),
    "alley":   ((15.5, 31.0, 2.0), (15.5, 4.0, 5.0), 30),
    "corner":  ((-58.0, -40.0, 13.0), (-16.0, -6.0, 8.0), 40),
    # aerial looking straight down the canyon -- a cross-street overview just
    # gets blocked by the front row of buildings
    "overview": ((-88.0, 10.0, 30.0), (14.0, -1.0, 4.0), 48),
}


def render_shots(out_dir, names=None, res=(1280, 720), samples=48, prefix=""):
    sc = bpy.context.scene
    cam = bpy.data.objects["PVW_Cam"]
    sc.render.image_settings.file_format = "PNG"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.eevee.taa_render_samples = samples
    for n in (names or SHOTS):
        loc, tgt, lens = SHOTS[n]
        aim_camera(cam, loc, tgt, lens)
        sc.render.filepath = out_dir.rstrip("/") + "/" + prefix + n + ".png"
        bpy.ops.render.render(write_still=True)
        print("shot", n)
    aim_camera(cam, *SHOTS["street"][:2], lens=SHOTS["street"][2])


if __name__ == "__main__" or True:
    res = build()
    print("StreetPreview built:", res)
