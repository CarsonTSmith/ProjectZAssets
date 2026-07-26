"""
BuildingKitGen.py -- a modular building kit in the Deceive Inc. idiom, authored
for export into Unity.

Scene "BuildingKit" inside Wall.blend. Four kit collections plus a palette and a
demo street:

    BK_Walls    14 wall modules   (solid / window / shuttered / shopfront /
                                   double door / half-width fillers / corners)
    BK_Roof      7 roof pieces    (deck, parapets, deco crest, fin sign, vent,
                                   skylight)
    BK_Ground    7 ground pieces  (interior floor, foundation podium, paving,
                                   kerb, steps, stoop)
    BK_Details   6 dressing       (awning, door canopy, blade sign, balcony,
                                   planter, wall lamp)

------------------------------------------------------------------- THE GRID --
Module W = 4 m, wall H = 8 m, thickness T = 0.40 m. Half-width filler = 2 m.
Corners = 1x1 m footprint. Ground plane sits at z = -0.45 (top of the paving),
the building's finished floor at z = 0, wall top at z = 8, roof deck
8.00 -> 8.30, parapet 8.00 -> 9.00.

Pivots: every piece's origin is at the *bottom centre of its module footprint*,
on the wall centre-line, with the exterior facing -Y. Blender -Y becomes Unity
+Z, so an unrotated piece faces Unity-forward. Walls, awnings, canopies,
balconies, signs, foundations, steps and parapets all share that same pivot, so
a detail piece drops onto a wall with an identical transform.

--------------------------------------------------------------- ANTI-TILING --
1. UV density is 0.5 repeats/m and every module dimension is a whole number of
   metres, so W*0.5 = 2 and H*0.5 = 4 are integers: the plaster runs
   *continuously* across a module join instead of restarting. UVs are projected
   in each piece's LOCAL space (origin 0,0,0) so this holds wherever Unity
   places the instance.
2. Several variants of every role, with asymmetric detail on some so an X-mirror
   yields yet another face. Shutters come open AND closed, which is the cheapest
   way to make one window read as three.
3. 2 m half-modules break the 4 m rhythm and let you build odd spans.
4. The plinth and cornice are continuous horizontal bands -- they read across the
   vertical module joins and hide them.
5. Body colour AND interior colour each live in ONE material slot (BK_Body,
   BK_Inner). Every kit piece here overrides both at OBJECT level, so the meshes
   stay shared and a building recolours inside and out by swapping two
   materials in Unity.

Run:  exec(open("/home/carson/Blender/ProjectZAssets/BuildingKitGen.py").read())
"""

import bpy, math, sys, importlib
from mathutils import Vector, Euler

sys.path.insert(0, "/home/carson/Blender/ProjectZAssets")
import BlockoutKit as BK
importlib.reload(BK)
MB = BK.MB

PFX = "BK_"
ROOT = "BuildingKit"
SCENE = "BuildingKit"
RAD = math.radians


def srgb(h):
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f((h >> 16) & 255), f((h >> 8) & 255), f(h & 255))


# ---------------------------------------------------------------- metrics --
W, H, T = 4.0, 8.0, 0.40
HW, HT = W / 2.0, T / 2.0
W2 = 2.0                     # half-width filler
CW = 1.0                     # corner footprint

# Exterior trim. Deliberately heavy: this style lives on thick white plaster,
# and a thin band reads as a pinstripe rather than as masonry.
# "Chunky" is carried by how far the trim PROJECTS, not by how tall the bands
# are. Deep and short keeps the shadow line heavy while leaving the wall its
# colour -- tall bands turn the whole facade white at street distance.
PL_B, PLINTH_T = 0.62, 0.80  # plinth: base band then a projecting cap
PL_P1, PL_P2 = 0.14, 0.24
CORN_B, CORN_M1, CORN_M2 = 6.95, 7.32, 7.66    # three-step cornice
CO_P1, CO_P2, CO_P3 = 0.18, 0.32, 0.48
STR_B, STR_T, STR_P = 5.95, 6.30, 0.14         # optional string course

# Interior: skirting, panelled wainscot, dado rail, then the colour field.
SKIRT_T = 0.45
WAIN_T, DADO_T = 1.45, 1.62
# STACKING: a wall's top face at z = H is the next storey's floor datum, so the
# floor/roof slab is authored DOWNWARD from it (-DECK_T -> 0). That puts every
# ceiling at CEIL_Z and keeps the storey pitch exactly H, which is what lets a
# wall be dropped at z = 0, 8, 16 ... and still line up.
DECK_T = 0.30
CEIL_Z = 8.0 - DECK_T                          # 7.70 -- underside of the slab
ICORN_B = 7.10                                 # interior cornice meets it

CASE, CASE_P = 0.34, 0.26    # exterior architrave
ICASE, ICASE_P = 0.26, 0.14  # interior architrave
LINER = 0.16                 # reveal liner inside an opening
MULL = 0.20                  # mullion / glazing bar
OVL = 0.03                   # trim lap -- see casing()

WIN_W, WIN_H, WIN_S = 1.40, 4.00, 1.50         # head 5.50
WIDE_W = 2.60
FRENCH_S = WIN_S              # every window sill lines up
SHOP_W, SHOP_S = 2.80, 0.55
SHUT_W, SHUT_T = 0.52, 0.12  # open shutter leaf: width, thickness
HEAD_Z = WIN_S + WIN_H                         # 5.50 -- everything lines up

# Doors are monumental. A 4 m module cannot carry a 6 m opening wide enough for
# three abreast AND an architrave, so there are two: Wall_Door fills its whole
# bay edge to edge, and Wall_Door_Grand is a TWO-module (8 m) frontispiece.
# Clear width is the structural opening less two reveal liners -- that is the
# number a character controller actually has to fit through.
DOOR_W, DOOR_HEAD, DOOR_LEAF_T = 3.32, 6.00, 4.60   # clear 3.00 m
DOOR_CASE, DOOR_LINER, DOOR_CASE_P = 0.34, 0.16, 0.30
DG_HW = 4.00                                        # two modules
DG_W, DG_HEAD, DG_LEAF_T = 3.60, 6.10, 4.70         # clear 3.24 m
DG_CASE, DG_LINER, DG_CASE_P = 0.44, 0.18, 0.34
DG_PILASTER = 3.00                                  # flanking pilaster centres

# Anything that swings is its OWN mesh, with its origin on the hinge axis so
# Unity can rotate it about local Z (Blender) / Y (Unity) and nothing else.
# These are the hinge offsets in module-local X: drop the leaf at the wall's
# transform +/- the offset, no other displacement.
DOOR_HINGE = DOOR_W / 2 - DOOR_LINER - 0.02         # 1.48
DOOR_LEAF_W = DOOR_HINGE - 0.03                     # 1.45
DG_HINGE = DG_W / 2 - DG_LINER - 0.02               # 1.60
DG_LEAF_W = DG_HINGE - 0.03                         # 1.57
# The openable window is the WIDE one -- a pair of casements big enough to read
# as french doors when they part in the middle. No shutters on this piece:
# 2.80 + two 0.34 architraves already leaves only 0.26 m of wall each side.
# Sill matches every other window so the whole facade reads on one line; at
# 1.50 the exterior sill shelf also clears the plinth cap (0.80).
OPEN_W, OPEN_SILL, OPEN_H = 2.80, WIN_S, 4.00       # sill AND head line up
SASH_HINGE = OPEN_W / 2 - LINER                     # 1.24
SASH_W = SASH_HINGE - 0.01                          # 1.23
SASH_Z0, SASH_Z1 = OPEN_SILL + LINER, OPEN_SILL + OPEN_H - LINER

# Quoins reach QUOIN_L - HT = 0.40 m into the neighbouring bay, so the window
# group (glass + architrave + both shutters) is sized to keep 0.44 m of plain
# wall at each module edge. Widen the window or the shutters and the corner
# blocks start growing through them.
QUOIN_P = 0.13                                 # projection off the wall face
QUOIN_L, QUOIN_S = 0.60, 0.34                  # long and short block lengths
QUOIN_H = 0.46                                 # nominal course height

GROUND_Z = -0.45             # exterior pavement top
FND = 0.45                   # podium height (GROUND_Z -> 0)
PARA_H = 1.00

# ---------------------------------------------------------------- palette --
# Sources are the user's own library materials; the kit never references them
# directly, it aliases every one into a BK_* namespace so an exported FBX
# carries a clean, self-contained material list.
SRC_PLASTER = "White plaster"
SRC_STONE = "PZ_M_Stone"
SRC_TILE = "Stone tiles"
SRC_WOOD = "Stylized Wooden Planks"
# Picked by hand on BK_Door_Leaf_L and adopted for every leaf: a real wood pair
# and a real metal, rather than the tinted plaster stand-ins they replaced.
SRC_DOOR_FRAME = "Stylized Vertical Wood"     # stiles, rails, raised fields
SRC_DOOR_PANEL = "Wood.002"                   # recessed panel ground
SRC_BRASS = "Brushed Brass"                   # pull bars, kick strip, handles

WHITE = PFX + "Trim"
STONE = PFX + "Stone"
TILE = PFX + "Floor"
WOOD = PFX + "Wood"

BODY = PFX + "Body"
INNER = PFX + "Inner"
CEIL = PFX + "Ceiling"
ACCENT = PFX + "Accent"
SHUTM = PFX + "Shutter"
BRASS = PFX + "Brass"
GLASS = PFX + "Glass"
DOORM = PFX + "DoorLeaf"
DPANEL = PFX + "DoorPanel"
DECK = PFX + "RoofDeck"
PAVE = PFX + "Paving"
LEAF = PFX + "Foliage"
LABEL = PFX + "Label"
STAGE = PFX + "Stage"        # catalogue floor only, not part of the kit

PALETTE = [
    ("Coral",      0xE8694B),
    ("Teal",       0x1B8B80),
    ("Mustard",    0xF0AF3A),
    ("Sage",       0x86B57A),
    ("Sky",        0x4CA6D9),
    ("Plum",       0x8A4C8E),
    ("Cream",      0xF2DEB6),
    ("Terracotta", 0xBD5238),
]
# Interiors are their own palette, deeper and warmer than the facades -- a room
# painted the same colour as the outside wall reads as an unfinished shell.
INTERIORS = [
    ("Emerald",   0x1F6B52),
    ("Ochre",     0xD9A045),
    ("Sienna",    0xB65B3C),
    ("Midnight",  0x2A3E6B),
    ("Rose",      0xD98B94),
    ("Olive",     0x7C8A4A),
    ("Bone",      0xEADCC4),
    ("Aubergine", 0x6B3F63),
]
BODYMATS = []
INNERMATS = []

# repeats per metre. 0.5 keeps 4 m and 8 m modules on integer UV units, which is
# what makes the plaster run through a module join without a seam.
UVS = {
    WHITE: 0.5, BODY: 0.5, INNER: 0.5, CEIL: 0.5, ACCENT: 0.5, SHUTM: 0.5,
    BRASS: 0.5, GLASS: 0.5, DOORM: 1.0, DPANEL: 0.5, DECK: 0.5, LEAF: 0.5,
    STONE: 0.5, TILE: 0.25, WOOD: 1.0, PAVE: 0.25, STAGE: 0.25,
}


# ---------------------------------------------------------- material slots --
# Every piece's slots are written in THIS order, subset to what it actually
# uses. That makes the two swappable ones land at fixed indices on every wall
# piece -- slot 0 is the exterior colour and slot 1 the interior colour -- so a
# Unity prefab variant, or a script walking Renderer.sharedMaterials, can
# recolour any piece in the kit without looking up names.
CANON_MATS = [BODY, INNER, WHITE, ACCENT, GLASS, STONE, TILE, DOORM, DPANEL,
              SHUTM, BRASS, DECK, CEIL, LEAF, WOOD, PAVE, STAGE]


def M(n):
    return bpy.data.materials[n]


def canonicalise(mb):
    """Reorder a piece's material slots into CANON_MATS order, remapping the
    faces. Left alone, slots come out in first-touched order, which differs from
    piece to piece and makes slot indices useless on the Unity side."""
    rank = {n: i for i, n in enumerate(CANON_MATS)}
    order = sorted(range(len(mb.mats)), key=lambda i: rank.get(mb.mats[i].name, 999))
    remap = {old: new for new, old in enumerate(order)}
    for f in mb.bm.faces:
        f.material_index = remap[f.material_index]
    mb.mats = [mb.mats[i] for i in order]


# ------------------------------------------------------------- primitives --
def face_key(n):
    ax = max(range(3), key=lambda i: abs(n[i]))
    return ("+" if n[ax] > 0 else "-") + "xyz"[ax]


def sl(mb, x0, x1, y0, y1, z0, z1, mat, faces=None, uvs=0.0):
    """Axis-aligned slab from min/max corners -- the whole kit is built of these.

    `faces` optionally overrides the material per direction ('-y', '+y', ...)."""
    if x1 - x0 <= 1e-6 or y1 - y0 <= 1e-6 or z1 - z0 <= 1e-6:
        return
    before = set(mb.bm.faces)
    mb.box(((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0),
           (x1 - x0, y1 - y0, z1 - z0), mat, uvs=uvs)
    if faces:
        for f in mb.bm.faces:
            if f in before:
                continue
            m = faces.get(face_key(f.normal))
            if m is not None:
                f.material_index = mb._mi(m)
                f[mb.uvlay] = uvs


def mark_bevel_weights(ob, planes, angle_deg=40.0):
    """Weight every sharp edge for bevelling EXCEPT the ones lying flat in a
    module-boundary plane.

    Two modules butt exactly on the grid line. Bevelling that meeting edge cuts
    a V-notch into both of them, and whatever material happens to sit behind the
    notch -- the exterior body colour, a z-fighting pair of coincident end faces
    -- shows through it as a hairline down every joint. No amount of material
    juggling fixes that; the edge simply must not be bevelled. Everything else
    still gets its chamfer, so the pieces keep their soft stylised highlight."""
    import bmesh as _bm
    me = ob.data
    bm = _bm.new()
    bm.from_mesh(me)
    bm.edges.ensure_lookup_table()
    lim = math.radians(angle_deg)
    vals = []
    for e in bm.edges:
        w = 0.0
        if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > lim:
            w = 1.0
            for ax, val in planes:
                i = "xyz".index(ax)
                if (abs(e.verts[0].co[i] - val) < 1e-4
                        and abs(e.verts[1].co[i] - val) < 1e-4):
                    w = 0.0
                    break
        vals.append(w)
    bm.free()
    at = me.attributes.get("bevel_weight_edge")
    if at is None:
        at = me.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
    at.data.foreach_set("value", vals)
    me.update()


def fix_tilted_uvs(ob):
    """Re-project faces that are NOT axis-aligned into their own plane.

    The kit's planar projection picks a world axis per face, which is exactly
    what makes the modules tile -- but on a tilted face it foreshortens one
    direction only, so the texture reads as stretched. Bracket undersides,
    awning slopes and the planter foliage were running ~25-30% short. Rebuilding
    those in a tangent frame makes them isotropic; axis-aligned faces are left
    strictly alone so the tiling guarantee is untouched. The frame is built from
    the face normal alone, so coplanar neighbours stay continuous."""
    me = ob.data
    if not me.uv_layers:
        return 0
    uvl = me.uv_layers.active.data
    fixed = 0
    for p in me.polygons:
        n = p.normal
        if max(abs(n.x), abs(n.y), abs(n.z)) > 0.999:
            continue
        mat = (me.materials[p.material_index]
               if p.material_index < len(me.materials) else None)
        s = BK.MAT_UV_SCALE.get(mat.name, 1.0) if mat else 1.0
        up = Vector((0.0, 0.0, 1.0)) if abs(n.z) < 0.9 else Vector((1.0, 0.0, 0.0))
        t = n.cross(up)
        if t.length < 1e-6:
            continue
        t.normalize()
        b = n.cross(t)
        for li in p.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uvl[li].uv = (v.dot(t) * s, v.dot(b) * s)
        fixed += 1
    return fixed


def out(mb, coll, loc, bevel=0.025, segments=1, seam=None):
    """Finish with LOCAL uvs (origin 0,0,0) then move the object into place --
    keeping the projection local is what makes instances tile in Unity."""
    canonicalise(mb)
    ob = mb.finish(coll, origin=(0, 0, 0), bevel=bevel, uv_scale=1.0)
    ob.data.name = ob.name          # mesh name is what Unity shows
    fix_tilted_uvs(ob)
    ob.location = Vector(loc)
    md = ob.modifiers.get("Bevel")
    if md:
        md.segments = segments
        if seam:
            mark_bevel_weights(ob, seam)
            md.limit_method = "WEIGHT"
    return ob


def spans(hw, opens, z0, z1):
    """x-intervals of a horizontal band left over after the openings cut it."""
    blk = sorted((o[0], o[1]) for o in opens
                 if not (z1 <= o[2] + 1e-6 or z0 >= o[3] - 1e-6))
    res, cur = [], -hw
    for a, b in blk:
        if a > cur + 1e-6:
            res.append((cur, a))
        cur = max(cur, b)
    if cur < hw - 1e-6:
        res.append((cur, hw))
    return res


def shell(mb, hw, opens, h=H, t=HT):
    """Solid double-faced wall slab minus the openings, merged row by row.

    Emitted as TWO leaves, exterior and interior, rather than one box with
    per-face materials. Two modules butt exactly on the grid line, and the bevel
    chamfers that meeting edge -- a single box makes that chamfer inherit
    whichever of the two finishes it likes, which paints a hairline of exterior
    body colour down every joint *inside* the room."""
    body, inner = M(BODY), M(INNER)
    xs = sorted({-hw, hw} | {v for o in opens for v in (o[0], o[1])})
    zs = sorted({0.0, h} | {v for o in opens for v in (o[2], o[3])})

    def leaf(a, b, z0, z1):
        sl(mb, a, b, -t, 0.0, z0, z1, body)
        sl(mb, a, b, 0.0, t, z0, z1, inner)

    for j in range(len(zs) - 1):
        z0, z1 = zs[j], zs[j + 1]
        zc = (z0 + z1) / 2.0
        run = None
        for i in range(len(xs) - 1):
            x0, x1 = xs[i], xs[i + 1]
            xc = (x0 + x1) / 2.0
            solid = not any(o[0] < xc < o[1] and o[2] < zc < o[3] for o in opens)
            if solid:
                run = (run[0], x1) if run else (x0, x1)
            elif run:
                leaf(run[0], run[1], z0, z1)
                run = None
        if run:
            leaf(run[0], run[1], z0, z1)


def bands(mb, hw, opens):
    """Plinth + three-step cornice outside; skirting, panelled wainscot, dado
    rail and cornice inside. Continuous horizontal trim is the main thing hiding
    the vertical module joins, and it is what carries the 'chunky' read."""
    w = M(WHITE)
    # split on the trim footprint where casing() recorded one, else the opening
    ext_op = getattr(mb, "env_ext", None) or opens
    int_op = getattr(mb, "env_int", None) or opens

    def ext(z0, z1, p):
        for a, b in spans(hw, ext_op, z0, z1):
            sl(mb, a, b, -HT - p, -HT + 0.001, z0, z1, w)

    def inn(z0, z1, p):
        for a, b in spans(hw, int_op, z0, z1):
            sl(mb, a, b, HT - 0.001, HT + p, z0, z1, w)

    ext(0.0, PL_B, PL_P1)
    ext(PL_B, PLINTH_T, PL_P2)
    ext(CORN_B, CORN_M1, CO_P1)
    ext(CORN_M1, CORN_M2, CO_P2)
    ext(CORN_M2, H, CO_P3)

    inn(0.0, SKIRT_T, 0.11)
    inn(SKIRT_T, WAIN_T, 0.05)                 # wainscot ground
    inn(WAIN_T, DADO_T, 0.13)                  # dado rail
    inn(ICORN_B, ICORN_B + 0.30, 0.10)
    inn(ICORN_B + 0.30, CEIL_Z, 0.17)
    # raised panels on the wainscot, two to a full module
    for a, b in spans(hw, int_op, SKIRT_T + 0.12, WAIN_T - 0.12):
        n = max(1, int(round((b - a) / 1.9)))
        for k in range(n):
            p0 = a + (b - a) * k / n + 0.16
            p1 = a + (b - a) * (k + 1) / n - 0.16
            if p1 - p0 < 0.25:
                continue
            for q0, q1, r0, r1 in ((p0, p1, SKIRT_T + 0.14, SKIRT_T + 0.24),
                                   (p0, p1, WAIN_T - 0.24, WAIN_T - 0.14),
                                   (p0, p0 + 0.10, SKIRT_T + 0.14, WAIN_T - 0.14),
                                   (p1 - 0.10, p1, SKIRT_T + 0.14, WAIN_T - 0.14)):
                sl(mb, q0, q1, HT + 0.049, HT + 0.11, r0, r1, w)


def string_course(mb, hw, opens):
    w = M(WHITE)
    for a, b in spans(hw, opens, STR_B, STR_T):
        sl(mb, a, b, -HT - STR_P, -HT + 0.001, STR_B, STR_T, w)
        sl(mb, a, b, -HT - STR_P - 0.07, -HT + 0.001, STR_T - 0.11, STR_T, w)


def reveal(mb, op, sill=True, liner=LINER):
    """White plaster lining the full depth of an opening, so the hole reads as
    trimmed from inside as well as out."""
    x0, x1, z0, z1 = op
    w = M(WHITE)
    y0, y1 = -HT - 0.012, HT + 0.012
    sl(mb, x0, x0 + liner, y0, y1, z0, z1, w)
    sl(mb, x1 - liner, x1, y0, y1, z0, z1, w)
    sl(mb, x0 + liner, x1 - liner, y0, y1, z1 - liner, z1, w)
    if sill:
        sl(mb, x0 + liner, x1 - liner, y0, y1, z0, z0 + liner, w)


def casing(mb, op, sill=True, entab=0.0, case=None, case_p=None, hw=HW):
    """Moulded architrave on both faces + a sill shelf, all white plaster.

    Every piece laps OVL past the edge of the opening. Butting the architrave
    exactly against the reveal liner leaves the bevel a hairline groove right on
    the joint, and what shows through it is the body colour -- which draws a
    coloured pinstripe around every window and door."""
    x0, x1, z0, z1 = op
    w = M(WHITE)
    cs = CASE if case is None else case
    cp = CASE_P if case_p is None else case_p
    zb = z0 - cs if sill else z0
    # Record the footprint the trim actually occupies, so bands() can stop the
    # plinth, wainscot and dado rail AT the surround instead of running through
    # it. Splitting on the bare opening is not enough -- the architrave is
    # wider and drops below the sill, which is what makes a low window look
    # like it is punched through the panelling.
    if not hasattr(mb, "env_ext"):
        mb.env_ext, mb.env_int = [], []
    mb.env_ext.append((x0 - cs, x1 + cs,
                       (z0 - cs - 0.22) if sill else z0, z1 + cs + entab))
    mb.env_int.append((x0 - ICASE, x1 + ICASE,
                       (z0 - ICASE) if sill else z0, z1 + ICASE))
    # two-step profile: a wide flat band with a proud outer bead
    for p, inset in ((cp - 0.10, 0.0), (cp, 0.10)):
        ey0, ey1 = -HT - p, -HT + 0.001
        sl(mb, x0 - cs + inset, x0 + OVL, ey0, ey1, zb + inset, z1 + cs - inset, w)
        sl(mb, x1 - OVL, x1 + cs - inset, ey0, ey1, zb + inset, z1 + cs - inset, w)
        sl(mb, x0, x1, ey0, ey1, z1 - OVL, z1 + cs - inset, w)
        if sill:
            sl(mb, x0, x1, ey0, ey1, z0 - cs + inset, z0 + OVL, w)
    if sill:
        # sill shelf only -- no corbels under it
        sl(mb, x0 - cs - 0.12, x1 + cs + 0.12, -HT - cp - 0.20,
           -HT + 0.001, z0 - cs - 0.22, z0 - cs, w)
    if entab:
        zf = z1 + cs
        # Clamped to the PIECE (hw), not the 4 m module -- the grand door is two
        # modules wide. On the doors the entablature runs right up to the wall
        # top and projects further than the cornice, so it reads as the cornice
        # breaking forward over the entrance rather than colliding with it.
        sl(mb, max(x0 - cs, -hw), min(x1 + cs, hw), -HT - cp - 0.06, -HT + 0.001,
           zf, zf + entab * 0.52, w)                                 # frieze
        sl(mb, max(x0 - cs - 0.20, -hw), min(x1 + cs + 0.20, hw),
           -HT - cp - 0.26, -HT + 0.001,
           zf + entab * 0.52, zf + entab * 0.78, w)                  # bed mould
        sl(mb, max(x0 - cs - 0.30, -hw), min(x1 + cs + 0.30, hw),
           -HT - cp - 0.40, -HT + 0.001,
           zf + entab * 0.78, zf + entab, w)                         # corona
        for cx in (x0 + 0.10, x1 - 0.10):                            # consoles
            sl(mb, cx - 0.10, cx + 0.10, -HT - cp - 0.30, -HT + 0.001,
               zf + 0.04, zf + entab * 0.52, w)
    iy0, iy1 = HT - 0.001, HT + ICASE_P
    zi = z0 - (ICASE if sill else 0.0)
    sl(mb, x0 - ICASE, x0 + OVL, iy0, iy1, zi, z1 + ICASE, w)
    sl(mb, x1 - OVL, x1 + ICASE, iy0, iy1, zi, z1 + ICASE, w)
    sl(mb, x0, x1, iy0, iy1, z1 - OVL, z1 + ICASE, w)
    if sill:
        sl(mb, x0 - ICASE, x1 + ICASE, HT - 0.001, HT + 0.26,
           z0 - 0.12, z0 + 0.02, w)


def glazing(mb, x0, x1, z0, z1, nv, nh, inset=LINER):
    """Glass plane + chunky white bars spanning the full wall depth, so the grid
    reads the same from the room side."""
    g0, g1 = x0 + inset, x1 - inset
    b0, b1 = z0 + inset, z1 - inset
    sl(mb, g0, g1, -0.05, 0.05, b0, b1, M(GLASS))
    w = M(WHITE)
    for k in range(1, nv):
        c = g0 + (g1 - g0) * k / float(nv)
        sl(mb, c - MULL / 2, c + MULL / 2, -HT - 0.02, HT + 0.02, b0, b1, w)
    for k in range(1, nh):
        c = b0 + (b1 - b0) * k / float(nh)
        sl(mb, g0, g1, -HT - 0.02, HT + 0.02, c - MULL / 2, c + MULL / 2, w)


def window(mb, cx, w_, h_, sill, nv, nh, entab=0.0):
    op = (cx - w_ / 2, cx + w_ / 2, sill, sill + h_)
    reveal(mb, op, sill=True)
    casing(mb, op, sill=True, entab=entab)
    glazing(mb, *op, nv=nv, nh=nh)
    return op


# ---------------------------------------------------------------- shutters --
def shutter_leaf(mb, x0, x1, z0, z1, y0, y1, mat, hinge_left=True):
    """One louvered leaf: stiles and rails as a frame, real tilted slats in the
    two fields between them. Slats as geometry rather than a texture is the same
    call as the awning stripes -- it is where the crisp graphic edge comes from."""
    w = x1 - x0
    st = min(0.11, w * 0.18)
    rail = 0.15
    # backing goes on the INNER face (y1 side). Put it on y0 and it caps the
    # front of the leaf, hiding every louver behind a flat slab.
    sl(mb, x0, x1, y1 - 0.035, y1, z0, z1, mat)
    sl(mb, x0, x0 + st, y0, y1, z0, z1, mat)                    # stiles
    sl(mb, x1 - st, x1, y0, y1, z0, z1, mat)
    zm = z0 + (z1 - z0) * 0.5
    for a, b in ((z0, z0 + rail), (zm - rail / 2, zm + rail / 2), (z1 - rail, z1)):
        sl(mb, x0, x1, y0, y1, a, b, mat)
    cy = (y0 + y1) / 2.0
    for f0, f1 in ((z0 + rail, zm - rail / 2), (zm + rail / 2, z1 - rail)):
        n = max(2, int((f1 - f0) / 0.145))
        for k in range(n):
            zc = f0 + (f1 - f0) * (k + 0.5) / n
            mb.box(((x0 + x1) / 2.0, cy, zc), (w - 2 * st, 0.105, 0.032), mat,
                   rot=(RAD(-32), 0, 0))
    hx = x0 + st / 2 if hinge_left else x1 - st / 2
    for hz in (z0 + 0.35, (z0 + z1) / 2.0, z1 - 0.35):
        sl(mb, hx - 0.05, hx + 0.05, y1 - 0.02, y1 + 0.05, hz - 0.09, hz + 0.09,
           M(BRASS))


def shutters_open(mb, op):
    """A pair thrown back flat against the wall, clear of the architrave."""
    x0, x1, z0, z1 = op
    y0, y1 = -HT - SHUT_T, -HT - 0.01
    # lap OVL under the architrave: butting the leaf against it leaves the bevel
    # a groove on the joint and the body colour behind shows as a pinstripe
    shutter_leaf(mb, x0 - CASE - SHUT_W, x0 - CASE + OVL, z0, z1, y0, y1,
                 M(SHUTM), hinge_left=False)
    shutter_leaf(mb, x1 + CASE - OVL, x1 + CASE + SHUT_W, z0, z1, y0, y1,
                 M(SHUTM), hinge_left=True)


def shutters_closed(mb, op):
    """The same leaves swung across the opening -- one extra piece from geometry
    you already have, and a shuttered bay next to a glazed one does more against
    visible repetition than another window variant would."""
    x0, x1, z0, z1 = op
    y0, y1 = -HT - SHUT_T, -HT - 0.01
    mid = (x0 + x1) / 2.0
    shutter_leaf(mb, x0 + 0.02, mid - 0.015, z0 + 0.02, z1 - 0.02, y0, y1,
                 M(SHUTM), hinge_left=True)
    shutter_leaf(mb, mid + 0.015, x1 - 0.02, z0 + 0.02, z1 - 0.02, y0, y1,
                 M(SHUTM), hinge_left=False)


# ---------------------------------------------------------- wall variants --
def w_solid_a(mb):
    shell(mb, HW, [])
    bands(mb, HW, [])


def w_solid_b(mb):
    """Two proud panel mouldings + a string course."""
    shell(mb, HW, [])
    bands(mb, HW, [])
    string_course(mb, HW, [])
    w = M(WHITE)
    for cx in (-1.0, 1.0):
        x0, x1, z0, z1 = cx - 0.72, cx + 0.72, 1.75, 5.45
        for a, b, c, d in ((x0, x1, z0, z0 + 0.17), (x0, x1, z1 - 0.17, z1),
                           (x0, x0 + 0.17, z0, z1), (x1 - 0.17, x1, z0, z1)):
            sl(mb, a, b, -HT - 0.12, -HT + 0.001, c, d, w)


def w_solid_c(mb):
    """Asymmetric: one pilaster strip, an accent inlay and a dentil frieze --
    mirror it in X and you get a different-looking piece for free."""
    shell(mb, HW, [])
    bands(mb, HW, [])
    sl(mb, -HW + 0.08, -HW + 0.80, -HT - 0.19, -HT + 0.001, PLINTH_T, CORN_B, M(WHITE))
    sl(mb, -HW + 0.02, -HW + 0.86, -HT - 0.25, -HT + 0.001, CORN_B - 0.34,
       CORN_B, M(WHITE))
    sl(mb, -0.20, 1.75, -HT - 0.13, -HT + 0.001, 3.00, 5.00, M(WHITE))
    sl(mb, -0.02, 1.57, -HT - 0.18, -HT + 0.001, 3.18, 4.82, M(BODY))
    for k in range(3):
        z = 3.50 + k * 0.60
        sl(mb, 0.14, 1.41, -HT - 0.23, -HT + 0.001, z, z + 0.22, M(WHITE))
    for k in range(9):                                        # dentils
        cx = -HW + 0.95 + k * 0.34
        sl(mb, cx, cx + 0.19, -HT - 0.26, -HT + 0.001, CORN_B - 0.30,
           CORN_B - 0.04, M(WHITE))


def w_win_a(mb):
    op = window(mb, 0.0, WIN_W, WIN_H, WIN_S, 2, 4)
    shutters_open(mb, op)
    shell(mb, HW, [op])
    bands(mb, HW, [op])


def w_win_shut(mb):
    op = window(mb, 0.0, WIN_W, WIN_H, WIN_S, 2, 4)
    shutters_closed(mb, op)
    shell(mb, HW, [op])
    bands(mb, HW, [op])


def w_win_b(mb):
    """Wide three-light with a full entablature over the head -- no shutters:
    at 2.6 m a pair would not fit inside the module."""
    op = window(mb, 0.0, WIDE_W, WIN_H, WIN_S, 3, 4, entab=0.84)
    shell(mb, HW, [op])
    bands(mb, HW, [op])


def w_win_c(mb):
    """French window with full-height shutters; pair it with Balcony_4m."""
    op = window(mb, 0.0, WIN_W, HEAD_Z - FRENCH_S, FRENCH_S, 2, 5)
    shutters_open(mb, op)
    shell(mb, HW, [op])
    bands(mb, HW, [op])


def w_win_twin(mb):
    ops = [window(mb, cx, 1.00, WIN_H, WIN_S, 1, 4) for cx in (-0.90, 0.90)]
    shell(mb, HW, ops)
    bands(mb, HW, ops)


def w_shopfront(mb):
    op = (-SHOP_W / 2, SHOP_W / 2, SHOP_S, HEAD_Z)
    reveal(mb, op, sill=True)
    casing(mb, op, sill=False, entab=0.72)
    glazing(mb, *op, nv=3, nh=2)
    shell(mb, HW, [op])
    bands(mb, HW, [op])
    sl(mb, op[0] - CASE, op[1] + CASE, -HT - CASE_P - 0.02, -HT + 0.001,
       0.0, SHOP_S, M(BODY))
    sl(mb, max(op[0] - CASE - 0.08, -HW), min(op[1] + CASE + 0.08, HW),
       -HT - CASE_P - 0.14, -HT + 0.001, SHOP_S - 0.18, SHOP_S, M(WHITE))


def door_bay(mb, hw, ow, oh, leaf_top, case, liner, case_p, pilaster=0.0):
    """A monumental double-door bay. Square-headed leaves under a tall glazed
    fanlight, the whole thing framed in the same white plaster as the roofline
    and capped by an entablature that runs to the wall top.

    Leaves are raised-and-fielded: the recessed panel ground is the ACCENT
    colour and everything proud of it -- stiles, rails, fields -- is the door
    colour. Done the other way round the fields read as flat stickers."""
    op = (-ow / 2, ow / 2, 0.0, oh)
    entab = H - (oh + case)
    reveal(mb, op, sill=False, liner=liner)
    casing(mb, op, sill=False, entab=entab, case=case, case_p=case_p, hw=hw)
    shell(mb, hw, [op])
    bands(mb, hw, [op])
    w, d, br, st = M(WHITE), M(DOORM), M(BRASS), M(STONE)

    for cx in (op[0] - case / 2, op[1] + case / 2):     # architrave plinth blocks
        sl(mb, max(cx - case / 2 - 0.07, -hw), min(cx + case / 2 + 0.07, hw),
           -HT - case_p - 0.08, -HT + 0.001, 0.0, PLINTH_T + 0.12, w)

    if pilaster:                                        # flanking order
        for cx in (-pilaster, pilaster):
            sl(mb, cx - 0.36, cx + 0.36, -HT - 0.24, -HT + 0.001,
               PLINTH_T, oh + case, w)
            sl(mb, cx - 0.48, cx + 0.48, -HT - 0.34, -HT + 0.001,
               oh + case - 0.46, oh + case, w)          # capital
            sl(mb, cx - 0.46, cx + 0.46, -HT - 0.32, -HT + 0.001,
               PLINTH_T, PLINTH_T + 0.26, w)            # base
            for k in range(3):                          # fluting
                fx = cx - 0.20 + k * 0.20
                sl(mb, fx - 0.04, fx + 0.04, -HT - 0.29, -HT - 0.21,
                   PLINTH_T + 0.34, oh + case - 0.54, w)

    # name panel let into the frieze: the whole bay is white plaster edge to
    # edge, and this is the one place a colour accent can go without weakening
    # the portal
    zf = oh + case
    sl(mb, op[0] - case * 0.4, op[1] + case * 0.4, -HT - case_p - 0.12,
       -HT + 0.001, zf + entab * 0.10, zf + entab * 0.44, w)
    sl(mb, op[0] - case * 0.1, op[1] + case * 0.1, -HT - case_p - 0.17,
       -HT + 0.001, zf + entab * 0.16, zf + entab * 0.38, M(BODY))

    x0, x1 = op[0] + liner, op[1] - liner
    sl(mb, x0 - 0.07, x1 + 0.07, -HT - 0.22, HT + 0.04,
       leaf_top, leaf_top + 0.26, w)                    # transom bar
    glazing(mb, x0, x1, leaf_top + 0.26, oh - liner, 5, 2, inset=0.0)
    sl(mb, x0, x1, -HT - 0.24, HT + 0.16, -0.08, 0.08, st)      # threshold

    # NOTE: no leaves here -- they are separate meshes so they can swing in
    # game. See door_leaf(). The frame, fanlight and threshold stay put.


# ------------------------------------------------------------- openables ---
def door_leaf(mb, width, leaf_top, side):
    """One raised-and-fielded door leaf, ORIGIN ON ITS HINGE.

    side = -1 is the left leaf (hinge on the left, geometry runs +X), side = +1
    the right (geometry runs -X). Local z is still the wall's floor datum, so
    the leaf's transform relative to its wall is a pure X offset -- rotate it
    about local Z in Blender / Y in Unity and it swings correctly."""
    lx0, lx1 = (0.0, width) if side < 0 else (-width, 0.0)
    free = lx1 if side < 0 else lx0          # the edge away from the hinge
    d, a, br = M(DOORM), M(DPANEL), M(BRASS)
    LT, SW, RL = leaf_top, 0.30, 0.30
    rails = [(0.08, 0.08 + RL * 1.8), (1.15, 1.15 + RL * 1.2),
             (LT * 0.60, LT * 0.60 + RL * 1.15), (LT - RL * 1.3, LT)]
    sl(mb, lx0, lx1, -0.07, 0.05, 0.08, LT, a)                  # panel ground
    for yy0, yy1 in ((-0.15, -0.065), (0.045, 0.13)):           # both faces
        for r0, r1 in rails:
            sl(mb, lx0, lx1, yy0, yy1, r0, r1, d)
        sl(mb, lx0, lx0 + SW, yy0, yy1, 0.08, LT, d)            # stiles
        sl(mb, lx1 - SW, lx1, yy0, yy1, 0.08, LT, d)
        for (_, f0), (f1, _) in zip(rails[:-1], rails[1:]):
            if f1 - f0 < 0.34:
                continue
            q0, q1 = lx0 + SW + 0.11, lx1 - SW - 0.11
            # field sits 30 mm below the rail plane -- relief, not inlay
            fy0, fy1 = (yy0 + 0.03, yy1) if yy0 < 0 else (yy0, yy1 - 0.03)
            sl(mb, q0, q1, fy0, fy1, f0 + 0.11, f1 - 0.11, d)
    hx = free - 0.38 if side < 0 else free + 0.38
    for by0, by1, sy0, sy1 in ((-0.355, -0.255, -0.255, -0.145),
                               (0.225, 0.325, 0.125, 0.225)):
        sl(mb, hx - 0.05, hx + 0.05, by0, by1, 1.10, 3.10, br)  # pull bar
        for hz in (1.20, 3.00):
            sl(mb, hx - 0.04, hx + 0.04, sy0, sy1, hz - 0.04, hz + 0.04, br)
    sl(mb, lx0 + 0.34, lx1 - 0.34, -0.165, -0.145, 0.16, 0.36, br)  # kick strip
    if side < 0:        # meeting bead, on the left leaf, covers the joint
        sl(mb, free - 0.02, free + 0.06, -0.18, 0.16, 0.08, LT, a)


def win_sash(mb, width, z0, z1, side, nv=2, nh=4):
    """One casement sash, ORIGIN ON ITS HINGE -- same convention as door_leaf,
    so the pair opens out from the middle exactly like a double door."""
    lx0, lx1 = (0.0, width) if side < 0 else (-width, 0.0)
    free = lx1 if side < 0 else lx0
    w, g, br = M(WHITE), M(GLASS), M(BRASS)
    y0, y1 = -0.07, 0.07
    st, rl = 0.12, 0.16
    sl(mb, lx0, lx1, -0.025, 0.025, z0, z1, g)                  # glass
    sl(mb, lx0, lx0 + st, y0, y1, z0, z1, w)                    # stiles
    sl(mb, lx1 - st, lx1, y0, y1, z0, z1, w)
    sl(mb, lx0, lx1, y0, y1, z0, z0 + rl, w)                    # rails
    sl(mb, lx0, lx1, y0, y1, z1 - rl, z1, w)
    for k in range(1, nh):                                      # glazing bars
        zc = z0 + (z1 - z0) * k / float(nh)
        sl(mb, lx0, lx1, y0, y1, zc - 0.055, zc + 0.055, w)
    for k in range(1, nv):
        xc = lx0 + (lx1 - lx0) * k / float(nv)
        sl(mb, xc - 0.055, xc + 0.055, y0, y1, z0, z1, w)
    hx = free - 0.05 if side < 0 else free + 0.05
    zc = z0 + (z1 - z0) * 0.42
    sl(mb, hx - 0.035, hx + 0.035, y1, y1 + 0.11, zc, zc + 0.10, br)   # handle
    sl(mb, hx - 0.03, hx + 0.03, y1 + 0.07, y1 + 0.11, zc - 0.34, zc + 0.06, br)
    if side < 0:        # meeting bead
        sl(mb, free - 0.015, free + 0.045, -0.05, 0.05, z0, z1, w)


def o_door_leaf_l(mb):
    door_leaf(mb, DOOR_LEAF_W, DOOR_LEAF_T, -1)


def o_door_leaf_r(mb):
    door_leaf(mb, DOOR_LEAF_W, DOOR_LEAF_T, 1)


def o_door_grand_leaf_l(mb):
    door_leaf(mb, DG_LEAF_W, DG_LEAF_T, -1)


def o_door_grand_leaf_r(mb):
    door_leaf(mb, DG_LEAF_W, DG_LEAF_T, 1)


def o_win_sash_l(mb):
    win_sash(mb, SASH_W, SASH_Z0, SASH_Z1, -1)


def o_win_sash_r(mb):
    win_sash(mb, SASH_W, SASH_Z0, SASH_Z1, 1)


OPENABLE = [
    ("Door_Leaf_L",        o_door_leaf_l),
    ("Door_Leaf_R",        o_door_leaf_r),
    ("Door_Grand_Leaf_L",  o_door_grand_leaf_l),
    ("Door_Grand_Leaf_R",  o_door_grand_leaf_r),
    ("Win_Sash_L",         o_win_sash_l),
    ("Win_Sash_R",         o_win_sash_r),
]


def w_win_open(mb):
    """Wide casement window: the opening is left EMPTY and filled by
    Win_Sash_L/R, which hinge at the jambs and part in the middle like a double
    door. No shutters -- at 2.80 m the pair would not fit inside the module."""
    op = (-OPEN_W / 2, OPEN_W / 2, OPEN_SILL, OPEN_SILL + OPEN_H)
    reveal(mb, op, sill=True)
    casing(mb, op, sill=True)
    shell(mb, HW, [op])
    bands(mb, HW, [op])


def w_door(mb):
    """Fills its whole 4 m bay edge to edge: a 6.00 m opening with 3.00 m clear
    between the reveals, which is three characters abreast with room to spare."""
    door_bay(mb, HW, DOOR_W, DOOR_HEAD, DOOR_LEAF_T,
             DOOR_CASE, DOOR_LINER, DOOR_CASE_P)


def w_door_grand(mb):
    """TWO modules wide (8 m). A 6.40 m opening with 3.24 m clear, flanking
    fluted pilasters, and an entablature that breaks the cornice forward.
    Crown it with Parapet_Grand and approach it over Steps_Grand -- all three
    share this pivot and the same 8 m footprint."""
    door_bay(mb, DG_HW, DG_W, DG_HEAD, DG_LEAF_T,
             DG_CASE, DG_LINER, DG_CASE_P, pilaster=DG_PILASTER)


def w_half_solid(mb):
    shell(mb, W2 / 2, [])
    bands(mb, W2 / 2, [])


def w_half_win(mb):
    op = window(mb, 0.0, 1.00, WIN_H, WIN_S, 1, 4)
    shell(mb, W2 / 2, [op])
    bands(mb, W2 / 2, [op])


def w_corner_quoin(mb):
    """European quoins: alternating long-and-short dressed blocks interlocking
    round the corner, long on one face and short on the other, swapping every
    course. Not a projecting pilaster -- the blocks stand only QUOIN_P proud of
    the wall face, which is what makes them read as masonry rather than trim.

    Place rotated 0/90/180/-90 at SW/SE/NE/NW; the exterior faces are -X and -Y,
    and the corner point is at local (-HT, -HT)."""
    w, e = M(WHITE), -HT              # e = the exterior face plane
    # core: fills the small notch the two wall runs leave open at the corner,
    # held 10 mm back so it never fights the walls' own faces
    sl(mb, e + 0.01, HT, e + 0.01, HT, 0.0, H, M(INNER),
       {"-x": M(BODY), "-y": M(BODY)})

    def block(ax, ln, z0, z1, p):
        """ax 'y' = a block on the -Y face running +X; 'x' = on -X running +Y."""
        if ax == "y":
            sl(mb, e - p, e + ln, e - p, e + 0.002, z0, z1, w)
        else:
            sl(mb, e - p, e + 0.002, e + 0.002, e + ln, z0, z1, w)

    # plinth and cornice wrap the corner solidly, deeper than the quoins
    for z0, z1, p in ((0.0, PL_B, PL_P1), (PL_B, PLINTH_T, PL_P2),
                      (CORN_B, CORN_M1, CO_P1), (CORN_M1, CORN_M2, CO_P2),
                      (CORN_M2, H, CO_P3)):
        sl(mb, e - p, HT, e - p, e + 0.002, z0, z1, w)
        sl(mb, e - p, e + 0.002, e + 0.002, HT, z0, z1, w)

    # Courses are contiguous and divide the run exactly. Leaving a gap between
    # them lets the body colour through and the corner reads as orange
    # pinstripes -- the bevel already gives each joint its shadow line.
    z0, z1 = PLINTH_T + 0.02, CORN_B - 0.02
    n = max(1, int(round((z1 - z0) / QUOIN_H)))
    qh = (z1 - z0) / n
    for k in range(n):
        long_on_y = (k % 2 == 0)
        z = z0 + k * qh
        block("y", QUOIN_L if long_on_y else QUOIN_S, z, z + qh, QUOIN_P)
        block("x", QUOIN_S if long_on_y else QUOIN_L, z, z + qh, QUOIN_P)
    # interior skirting / dado / cornice returns
    for z0, z1, p in ((0.0, SKIRT_T, 0.11), (WAIN_T, DADO_T, 0.13),
                      (ICORN_B, CEIL_Z, 0.15)):
        sl(mb, e, HT + p, HT - 0.001, HT + p, z0, z1, w)
        sl(mb, HT - 0.001, HT + p, e, HT + p, z0, z1, w)


def w_corner_inner(mb):
    """Plain interior column on the same 1x1 corner footprint."""
    h = CW / 2
    sl(mb, -h, h, -h, h, 0.0, H, M(INNER))
    for z0, z1, p in ((0.0, SKIRT_T, 0.05), (WAIN_T, DADO_T, 0.06),
                      (ICORN_B, CEIL_Z, 0.07)):
        sl(mb, -h - p, h + p, -h - p, h + p, z0, z1, M(WHITE))


WALLS = [
    ("Wall_Solid_A",    w_solid_a),
    ("Wall_Solid_B",    w_solid_b),
    ("Wall_Solid_C",    w_solid_c),
    ("Wall_Win_A",      w_win_a),
    ("Wall_Win_Shut",   w_win_shut),
    ("Wall_Win_B",      w_win_b),
    ("Wall_Win_C",      w_win_c),
    ("Wall_Win_Open",   w_win_open),
    ("Wall_Win_Twin",   w_win_twin),
    ("Wall_Shopfront",  w_shopfront),
    ("Wall_Door",       w_door),
    ("Wall_Door_Grand", w_door_grand),
    ("Wall_Half_Solid", w_half_solid),
    ("Wall_Half_Win",   w_half_win),
    ("Corner_Quoin",    w_corner_quoin),
    ("Corner_Inner",    w_corner_inner),
]


# ---------------------------------------------------------- roof variants --
def r_deck(mb):
    """Roof slab. Authored -DECK_T -> 0 so its TOP is the storey datum: drop it
    at z = 8 and the roof surface is at 8, with the parapet sitting on it."""
    sl(mb, -HW, HW, -HW, HW, -DECK_T, 0.0, M(DECK),
       {"-z": M(CEIL), "+z": M(DECK)})


def r_floor_storey(mb):
    """Intermediate floor for stacked walls: walking surface on top, finished
    ceiling underneath. Same -DECK_T -> 0 authoring as the roof slab, so a
    storey is exactly H tall whether it is capped by roof or by another floor."""
    sl(mb, -HW, HW, -HW, HW, -DECK_T, 0.0, M(TILE),
       {"-z": M(CEIL), "+z": M(TILE)})


def r_parapet(mb):
    t = 0.22
    sl(mb, -HW, HW, -t, t, 0.0, PARA_H - 0.26, M(BODY),
       {"-y": M(BODY), "+y": M(WHITE)})
    sl(mb, -HW, HW, -t - 0.09, t + 0.09, PARA_H - 0.26, PARA_H - 0.08, M(WHITE))
    sl(mb, -HW, HW, -t - 0.15, t + 0.15, PARA_H - 0.08, PARA_H, M(WHITE))
    sl(mb, -HW, HW, -t - 0.07, -t + 0.001, 0.0, 0.20, M(WHITE))


def r_parapet_deco(mb):
    t = 0.22
    sl(mb, -HW, HW, -t, t, 0.0, PARA_H - 0.26, M(BODY),
       {"-y": M(BODY), "+y": M(WHITE)})
    sl(mb, -HW, HW, -t - 0.09, t + 0.09, PARA_H - 0.26, PARA_H - 0.08, M(WHITE))
    sl(mb, -HW, HW, -t - 0.15, t + 0.15, PARA_H - 0.08, PARA_H, M(WHITE))
    for k in range(4):
        c = -HW + W * (k + 0.5) / 4.0
        sl(mb, c - 0.46, c + 0.46, -t - 0.12, t + 0.12, PARA_H, PARA_H + 0.62, M(WHITE))
        sl(mb, c - 0.26, c + 0.26, -t - 0.17, -t + 0.02, PARA_H + 0.12,
           PARA_H + 0.50, M(ACCENT))
    # no piers on the module ends: two of these side by side put identical boxes
    # in the same place and they z-fight


def r_parapet_grand(mb):
    """8 m crown for Wall_Door_Grand: the parapet run with a raised attic over
    the entrance, so the frontispiece breaks the roofline as well as the
    cornice. Tops out 2.7 m above the wall."""
    t, hw, a = 0.22, DG_HW, 2.70
    sl(mb, -hw, hw, -t, t, 0.0, PARA_H - 0.26, M(BODY),
       {"-y": M(BODY), "+y": M(WHITE)})
    sl(mb, -hw, hw, -t - 0.09, t + 0.09, PARA_H - 0.26, PARA_H - 0.08, M(WHITE))
    sl(mb, -hw, hw, -t - 0.15, t + 0.15, PARA_H - 0.08, PARA_H, M(WHITE))
    for x0, x1 in ((-a - 0.78, -a), (a, a + 0.78)):        # stepped shoulders
        sl(mb, x0, x1, -t - 0.10, t + 0.10, PARA_H, PARA_H + 0.54, M(WHITE))
    sl(mb, -a, a, -t - 0.10, t + 0.10, PARA_H, PARA_H + 1.30, M(BODY),
       {"-y": M(BODY), "+y": M(WHITE)})
    sl(mb, -a - 0.15, a + 0.15, -t - 0.24, t + 0.24,
       PARA_H + 1.30, PARA_H + 1.54, M(WHITE))
    sl(mb, -a - 0.22, a + 0.22, -t - 0.32, t + 0.32,
       PARA_H + 1.54, PARA_H + 1.74, M(WHITE))
    sl(mb, -a + 0.34, a - 0.34, -t - 0.17, -t + 0.02,
       PARA_H + 0.24, PARA_H + 1.06, M(WHITE))            # attic panel
    sl(mb, -a + 0.52, a - 0.52, -t - 0.23, -t + 0.02,
       PARA_H + 0.38, PARA_H + 0.92, M(ACCENT))
    for cx in (-1.30, 0.0, 1.30):                          # finials
        sl(mb, cx - 0.17, cx + 0.17, -t - 0.20, t + 0.20,
           PARA_H + 1.74, PARA_H + 2.16, M(WHITE))


def r_parapet_corner(mb):
    t = 0.22
    sl(mb, -t, t, -t, t, 0.0, PARA_H - 0.26, M(BODY))
    sl(mb, -t - 0.09, t + 0.09, -t - 0.09, t + 0.09, PARA_H - 0.26, PARA_H - 0.08, M(WHITE))
    sl(mb, -t - 0.15, t + 0.15, -t - 0.15, t + 0.15, PARA_H - 0.08, PARA_H, M(WHITE))
    sl(mb, -0.32, 0.32, -0.32, 0.32, PARA_H, PARA_H + 0.80, M(WHITE))
    sl(mb, -0.21, 0.21, -0.21, 0.21, PARA_H + 0.80, PARA_H + 1.02, M(ACCENT))


def r_fin_sign(mb):
    sl(mb, -1.35, 1.35, -0.20, 0.20, 0.0, 3.10, M(WHITE))
    sl(mb, -1.15, 1.15, -0.28, -0.18, 0.22, 2.88, M(ACCENT))
    sl(mb, -1.15, 1.15, 0.18, 0.28, 0.22, 2.88, M(ACCENT))
    for k in range(3):
        z = 0.60 + k * 0.85
        sl(mb, -0.90, 0.90, -0.34, -0.24, z, z + 0.40, M(BODY))
        sl(mb, -0.90, 0.90, 0.24, 0.34, z, z + 0.40, M(BODY))
    sl(mb, -1.55, 1.55, -0.32, 0.32, 0.0, 0.24, M(WHITE))


def r_vent(mb):
    sl(mb, -0.60, 0.60, -0.60, 0.60, 0.0, 0.18, M(WHITE))
    sl(mb, -0.48, 0.48, -0.48, 0.48, 0.18, 0.78, M(BODY))
    for k in range(4):
        z = 0.28 + k * 0.13
        sl(mb, -0.52, 0.52, -0.52, 0.52, z, z + 0.07, M(WHITE))
    sl(mb, -0.62, 0.62, -0.62, 0.62, 0.78, 0.92, M(WHITE))


def r_skylight(mb):
    sl(mb, -1.0, 1.0, -1.0, 1.0, 0.0, 0.40, M(WHITE))
    sl(mb, -0.80, 0.80, -0.80, 0.80, 0.34, 0.44, M(GLASS))
    sl(mb, -0.10, 0.10, -0.80, 0.80, 0.34, 0.50, M(WHITE))
    sl(mb, -0.80, 0.80, -0.10, 0.10, 0.34, 0.50, M(WHITE))


ROOFS = [
    ("Roof_Deck_4x4",     r_deck),
    ("Floor_Storey_4x4",  r_floor_storey),
    ("Parapet_Straight",  r_parapet),
    ("Parapet_Deco",      r_parapet_deco),
    ("Parapet_Grand",     r_parapet_grand),
    ("Parapet_Corner",    r_parapet_corner),
    ("Roof_Fin_Sign",     r_fin_sign),
    ("Roof_Vent",         r_vent),
    ("Roof_Skylight",     r_skylight),
]


# -------------------------------------------------------- ground variants --
def g_floor(mb):
    sl(mb, -HW, HW, -HW, HW, -0.20, 0.0, M(TILE))


def g_foundation(mb):
    sl(mb, -HW, HW, -0.62, 0.62, -FND, -0.10, M(STONE))
    sl(mb, -HW, HW, -0.70, 0.70, -0.10, 0.0, M(WHITE))


def g_foundation_corner(mb):
    h = 0.62
    sl(mb, -h, h, -h, h, -FND, -0.10, M(STONE))
    sl(mb, -h - 0.08, h + 0.08, -h - 0.08, h + 0.08, -0.10, 0.0, M(WHITE))


def g_pavement(mb):
    sl(mb, -HW, HW, -HW, HW, -0.60, GROUND_Z, M(PAVE))


def g_kerb(mb):
    sl(mb, -HW, HW, -0.30, 0.30, -0.72, -0.28, M(STONE))
    sl(mb, -HW, HW, -0.32, -0.22, -0.34, -0.28, M(WHITE))


def g_steps(mb):
    y = -HT
    for k in range(3):
        z0 = GROUND_Z + k * (FND / 3.0)
        sl(mb, -HW, HW, y - (3 - k) * 0.36, y, z0, z0 + FND / 3.0, M(STONE))
    sl(mb, -HW, -HW + 0.34, y - 1.08, y, GROUND_Z, 0.12, M(WHITE))
    sl(mb, HW - 0.34, HW, y - 1.08, y, GROUND_Z, 0.12, M(WHITE))


def g_steps_grand(mb):
    """8 m broad flight with cheek blocks, to match Wall_Door_Grand."""
    y, hw, n = -HT, DG_HW, 3
    for k in range(n):
        z0 = GROUND_Z + k * (FND / n)
        sl(mb, -hw, hw, y - (n - k) * 0.62, y, z0, z0 + FND / n, M(STONE))
    for x0, x1 in ((-hw, -hw + 0.58), (hw - 0.58, hw)):
        sl(mb, x0, x1, y - 1.86, y, GROUND_Z, 0.18, M(WHITE))
        sl(mb, x0, x1, y - 1.93, y, 0.18, 0.38, M(WHITE))


def g_stoop(mb):
    sl(mb, -HW, HW, -HT - 2.0, -HT, -FND, -0.10, M(STONE))
    sl(mb, -HW, HW, -HT - 2.06, -HT, -0.10, 0.0, M(TILE))


GROUNDS = [
    ("Floor_4x4",          g_floor),
    ("Foundation_4m",      g_foundation),
    ("Foundation_Corner",  g_foundation_corner),
    ("Pavement_4x4",       g_pavement),
    ("Kerb_4m",            g_kerb),
    ("Steps_4m",           g_steps),
    ("Steps_Grand",        g_steps_grand),
    ("Stoop_Landing",      g_stoop),
]


# ------------------------------------------------------- detail variants ---
def d_awning(mb):
    """Stripes as alternating geometry, not texture -- that crisp edge is where
    a lot of the Deceive Inc. read comes from."""
    zw, zo, proj = HEAD_Z + 0.70, HEAD_Z + 0.02, 1.90
    n = 8
    span = W - 0.24
    for k in range(n):
        x0 = -HW + 0.12 + span * k / n
        x1 = -HW + 0.12 + span * (k + 1) / n
        mat = M(BODY) if k % 2 == 0 else M(WHITE)
        mb.extrude_poly([(x0, -HT, zw), (x0, -HT - proj, zo),
                         (x0, -HT - proj, zo - 0.12), (x0, -HT, zw - 0.12)],
                        (x1 - x0, 0, 0), mat)
        mb.extrude_poly([(x0, -HT - proj, zo), (x0, -HT - proj, zo - 0.62),
                         (x0, -HT - proj + 0.07, zo - 0.62),
                         (x0, -HT - proj + 0.07, zo)], (x1 - x0, 0, 0), mat)
    sl(mb, -HW + 0.06, HW - 0.06, -HT - 0.22, -HT + 0.001, zw - 0.20, zw + 0.18, M(WHITE))
    for cx in (-HW + 0.30, HW - 0.30):
        sl(mb, cx - 0.07, cx + 0.07, -HT - proj, -HT, zo - 0.08, zw, M(WHITE))


def d_canopy(mb):
    z = 6.46
    sl(mb, -2.10, 2.10, -HT - 1.55, -HT + 0.001, z, z + 0.30, M(WHITE))
    sl(mb, -2.18, 2.18, -HT - 1.64, -HT + 0.001, z + 0.30, z + 0.46, M(BODY))
    for cx in (-1.70, 1.70):
        mb.extrude_poly([(cx - 0.08, -HT, z), (cx - 0.08, -HT - 1.30, z),
                         (cx - 0.08, -HT - 0.10, z - 0.95)],
                        (0.16, 0, 0), M(WHITE))


def d_blade_sign(mb):
    z = 4.30
    sl(mb, -0.18, 0.18, -HT - 0.34, -HT + 0.001, z, z + 1.90, M(WHITE))
    sl(mb, -0.11, 0.11, -HT - 1.70, -HT - 0.26, z + 0.10, z + 1.80, M(WHITE))
    sl(mb, -0.07, 0.07, -HT - 1.62, -HT - 0.32, z + 0.22, z + 1.68, M(ACCENT))
    for k in range(4):
        yy = -HT - 0.50 - k * 0.30
        sl(mb, -0.10, 0.10, yy - 0.08, yy + 0.08, z + 0.34, z + 1.56, M(BRASS))


def d_balcony(mb):
    z = FRENCH_S
    sl(mb, -1.70, 1.70, -HT - 1.15, -HT + 0.001, z - 0.30, z, M(WHITE))
    sl(mb, -1.62, 1.62, -HT - 1.07, -HT - 0.02, z, z + 0.06, M(TILE))
    for (x0, x1, y0, y1) in ((-1.70, 1.70, -HT - 1.15, -HT - 1.01),
                             (-1.70, -1.56, -HT - 1.15, -HT),
                             (1.56, 1.70, -HT - 1.15, -HT)):
        sl(mb, x0, x1, y0, y1, z + 0.98, z + 1.18, M(WHITE))
        sl(mb, x0, x1, y0, y1, z + 0.06, z + 0.22, M(WHITE))
    n = 7
    for k in range(n):
        c = -1.62 + 3.24 * (k + 0.5) / n
        sl(mb, c - 0.10, c + 0.10, -HT - 1.14, -HT - 1.02, z + 0.20, z + 1.00, M(ACCENT))
    for yy in (-HT - 1.10, -HT - 0.25):
        sl(mb, -1.70, -1.56, yy - 0.05, yy + 0.05, z + 0.20, z + 1.00, M(ACCENT))
        sl(mb, 1.56, 1.70, yy - 0.05, yy + 0.05, z + 0.20, z + 1.00, M(ACCENT))
    for cx in (-1.45, 1.45):
        mb.extrude_poly([(cx - 0.09, -HT, z - 0.30), (cx - 0.09, -HT - 1.00, z - 0.30),
                         (cx - 0.09, -HT - 0.08, z - 1.10)], (0.18, 0, 0), M(WHITE))


def d_planter(mb):
    sl(mb, -0.60, 0.60, -0.55, 0.55, 0.0, 0.18, M(WHITE))
    sl(mb, -0.52, 0.52, -0.47, 0.47, 0.18, 0.74, M(BODY))
    sl(mb, -0.62, 0.62, -0.57, 0.57, 0.74, 0.94, M(WHITE))
    sl(mb, -0.46, 0.46, -0.41, 0.41, 0.90, 0.98, M(LEAF))
    for c, r, z in ((0.0, 0.46, 1.34), (-0.28, 0.30, 1.76), (0.26, 0.26, 1.90)):
        mb.sphere((c, 0.0, z), r, M(LEAF), segments=14)
    sl(mb, -0.06, 0.06, -0.06, 0.06, 0.94, 1.64, M(WOOD))


def d_wall_lamp(mb):
    z = 3.60
    sl(mb, -0.26, 0.26, -HT - 0.18, -HT + 0.001, z, z + 0.66, M(WHITE))
    sl(mb, -0.08, 0.08, -HT - 0.62, -HT - 0.12, z + 0.46, z + 0.60, M(BRASS))
    mb.cyl((0.0, -HT - 0.58, z + 0.22), 0.27, 0.44, M(WHITE), segments=16,
           radius_top=0.15)
    mb.sphere((0.0, -HT - 0.58, z + 0.05), 0.15, M(BRASS), segments=12)


DETAILS = [
    ("Awning_4m",    d_awning),
    ("Canopy_Door",  d_canopy),
    ("Blade_Sign",   d_blade_sign),
    ("Balcony_4m",   d_balcony),
    ("Planter",      d_planter),
    ("Wall_Lamp",    d_wall_lamp),
]


# ------------------------------------------------------------- materials ---
def alias(src, name):
    """Namespaced copy of a library material. tint() would work too but it
    reduces the source to luminance, which turns Stone tiles' gold grout grey.

    The SOURCE is given a fake user: a hand-picked library material whose only
    user is a kit object becomes an orphan the moment the kit is rebuilt, and
    is then one purge away from being gone for good."""
    s = bpy.data.materials.get(src)
    if s is None:
        raise KeyError("source material %r is missing -- append it before "
                       "rebuilding" % src)
    s.use_fake_user = True
    if name in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials[name])
    m = s.copy()
    m.name = name
    m.use_fake_user = True
    return m


def materials():
    del BODYMATS[:]
    del INNERMATS[:]
    alias(SRC_PLASTER, WHITE)
    alias(SRC_STONE, STONE)
    alias(SRC_TILE, TILE)
    alias(SRC_WOOD, WOOD)
    for nm, hexv in PALETTE:
        BODYMATS.append(BK.tint(WHITE, PFX + "Body_" + nm, srgb(hexv), roughness=0.62))
        UVS[PFX + "Body_" + nm] = 0.5
    for nm, hexv in INTERIORS:
        INNERMATS.append(BK.tint(WHITE, PFX + "Inner_" + nm, srgb(hexv), roughness=0.70))
        UVS[PFX + "Inner_" + nm] = 0.5
    BK.tint(WHITE, BODY, srgb(PALETTE[0][1]), roughness=0.62)
    BK.tint(WHITE, INNER, srgb(INTERIORS[0][1]), roughness=0.70)
    BK.tint(WHITE, CEIL, srgb(0xF2ECDE), roughness=0.75)
    BK.tint(WHITE, ACCENT, srgb(0x27406E), roughness=0.55)
    BK.tint(WOOD, SHUTM, srgb(0x256B78), roughness=0.52)
    alias(SRC_BRASS, BRASS)
    BK.tint(WHITE, DECK, srgb(0xC3B7A2), roughness=0.80)
    BK.tint(WHITE, LEAF, srgb(0x4C8B4A), roughness=0.75)
    BK.tint(TILE, PAVE, srgb(0xCFC6B3), roughness=0.72)
    BK.tint(TILE, STAGE, srgb(0x6E7C86), roughness=0.80)
    alias(SRC_DOOR_FRAME, DOORM)
    alias(SRC_DOOR_PANEL, DPANEL)
    BK.flat(GLASS, srgb(0xB6DBE9), roughness=0.09)
    BK.flat(LABEL, srgb(0x2A2A2E), roughness=0.60)


def recolor(ob, body=None, inner=None):
    """Object-level override of the shared BK_Body / BK_Inner slots. This is the
    workflow the kit is designed around: one mesh, two swapped materials."""
    for i, s in enumerate(ob.material_slots):
        src = ob.data.materials[i] if i < len(ob.data.materials) else None
        if src is None:
            continue
        if body is not None and src.name == BODY:
            s.link, s.material = "OBJECT", body
        elif inner is not None and src.name == INNER:
            s.link, s.material = "OBJECT", inner


def label(coll, text, loc):
    cu = bpy.data.curves.new(PFX + "L_" + text, type="FONT")
    cu.body = text
    cu.size = 0.42
    cu.align_x = "CENTER"
    cu.extrude = 0.01
    ob = bpy.data.objects.new(PFX + "L_" + text, cu)
    ob.location = Vector(loc)
    ob.rotation_euler = Euler((RAD(90), 0, 0), "XYZ")
    cu.materials.append(M(LABEL))
    coll.objects.link(ob)
    return ob


# ------------------------------------------------------------------ demo ---
FACADE = ["Wall_Win_A", "Wall_Solid_B", "Wall_Win_Open", "Wall_Win_Shut",
          "Wall_Door_Grand", "Wall_Win_C", "Wall_Shopfront", "Wall_Solid_C",
          "Wall_Win_A", "Wall_Win_Twin"]


def place_leaves(coll, p, rot, body, inner, kind="door", angle=0.0):
    """Hang a pair of leaves on a door bay. The hinge offset is a pure X shift
    in the wall's local frame, so it just has to be rotated by the wall's own
    yaw. Left leaf opens on -angle, right on +angle; 0 is shut."""
    K = bpy.data.objects
    if kind == "grand":
        hinge, nm = DG_HINGE, ("Door_Grand_Leaf_L", "Door_Grand_Leaf_R")
    elif kind == "sash":
        hinge, nm = SASH_HINGE, ("Win_Sash_L", "Win_Sash_R")
    else:
        hinge, nm = DOOR_HINGE, ("Door_Leaf_L", "Door_Leaf_R")
    c, s = math.cos(rot), math.sin(rot)
    for sgn, name in ((-1.0, nm[0]), (1.0, nm[1])):
        q = (p[0] + sgn * hinge * c, p[1] + sgn * hinge * s, p[2])
        dup(K[PFX + name], coll, q, rot + sgn * angle, body, inner)


def dup(src, coll, loc, rot=0.0, body=None, inner=None):
    ob = src.copy()                     # copies modifiers, shares the mesh
    ob.location = Vector(loc)
    ob.rotation_euler = Euler((0, 0, rot), "XYZ")
    coll.objects.link(ob)
    if body is not None or inner is not None:
        recolor(ob, body, inner)
    return ob


# Ground-floor-only pieces, and what an upper storey uses in their place. A
# door or a shopfront on the first floor reads as a mistake.
UPPER_SWAP = {"Wall_Door": "Wall_Win_C", "Wall_Door_Grand": "Wall_Win_B",
              "Wall_Shopfront": "Wall_Win_B"}


def demo_building(coll, org, bays, body, inner, seq, deco=True, storeys=1):
    """`storeys` walls stacked on the same footprint at a pitch of H."""
    K = bpy.data.objects
    half = bays * W / 2.0
    ox, oy = org
    top = storeys * H
    for s in range(storeys):
        z = s * H
        ground = (s == 0)
        idx = 0
        for side, rot in (("S", 0.0), ("E", RAD(90)),
                          ("N", RAD(180)), ("W", RAD(-90))):
            for b in range(bays):
                u = -half + W * (b + 0.5)
                if side == "S":
                    p = (ox + u, oy - half, z)
                elif side == "N":
                    p = (ox - u, oy + half, z)
                elif side == "E":
                    p = (ox + half, oy + u, z)
                else:
                    p = (ox - half, oy - u, z)
                name = seq[idx % len(seq)]
                idx += 1
                if not ground:
                    name = UPPER_SWAP.get(name, name)
                dup(K[PFX + name], coll, p, rot, body, inner)
                if name == "Wall_Win_Open":
                    place_leaves(coll, p, rot, body, inner, "sash")
                if ground:
                    dup(K[PFX + "Foundation_4m"], coll, p, rot, body, inner)
                    if name == "Wall_Door":
                        place_leaves(coll, p, rot, body, inner, "door")
                        dup(K[PFX + "Steps_4m"], coll, p, rot, body, inner)
                    elif name == "Wall_Shopfront":
                        dup(K[PFX + "Awning_4m"], coll, p, rot, body, inner)
                if name == "Wall_Win_C":
                    dup(K[PFX + "Balcony_4m"], coll, p, rot, body, inner)
        for sx, sy, rot in ((-1, -1, 0.0), (1, -1, RAD(90)),
                            (1, 1, RAD(180)), (-1, 1, RAD(-90))):
            p = (ox + sx * half, oy + sy * half, z)
            dup(K[PFX + "Corner_Quoin"], coll, p, rot, body, inner)
            if ground:
                dup(K[PFX + "Foundation_Corner"], coll, p, rot, body, inner)
    for sx, sy, rot in ((-1, -1, 0.0), (1, -1, RAD(90)),
                        (1, 1, RAD(180)), (-1, 1, RAD(-90))):
        dup(K[PFX + "Parapet_Corner"], coll,
            (ox + sx * half, oy + sy * half, top), rot, body, inner)
    for side, rot in (("S", 0.0), ("E", RAD(90)), ("N", RAD(180)), ("W", RAD(-90))):
        for b in range(bays):
            u = -half + W * (b + 0.5)
            q = {"S": (ox + u, oy - half), "N": (ox - u, oy + half),
                 "E": (ox + half, oy + u), "W": (ox - half, oy - u)}[side]
            para = "Parapet_Deco" if (deco and b % 2 == 0) else "Parapet_Straight"
            dup(K[PFX + para], coll, (q[0], q[1], top), rot, body, inner)
    for i in range(bays):
        for j in range(bays):
            p = (ox - half + W * (i + 0.5), oy - half + W * (j + 0.5), 0.0)
            dup(K[PFX + "Floor_4x4"], coll, p, 0.0, body, inner)
            for s in range(1, storeys):        # intermediate floors
                dup(K[PFX + "Floor_Storey_4x4"], coll, (p[0], p[1], s * H),
                    0.0, body, inner)
            dup(K[PFX + "Roof_Deck_4x4"], coll, (p[0], p[1], top), 0.0, body, inner)
    dup(K[PFX + "Roof_Fin_Sign"], coll,
        (ox, oy + half - 1.2, top), RAD(180), body, inner)
    dup(K[PFX + "Roof_Vent"], coll, (ox - half + 2.2, oy + 1.4, top), 0.0,
        body, inner)
    dup(K[PFX + "Roof_Skylight"], coll, (ox + 1.6, oy - 1.0, top), 0.0,
        body, inner)


def demo_run(coll, org, seq, body, inner):
    """A straight 40 m facade -- the piece of the demo that proves the kit does
    not visibly repeat."""
    K = bpy.data.objects
    ox, oy = org
    widths = [2 if n.endswith("_Grand") else 1 for n in seq]
    cur = -sum(widths) / 2.0
    for i, (name, wm) in enumerate(zip(seq, widths)):
        p = (ox + W * (cur + wm / 2.0), oy, 0.0)
        cur += wm
        dup(K[PFX + name], coll, p, 0.0, body, inner)
        for k in range(wm):            # ground and roof stay on the 4 m grid
            fx = p[0] + W * (k - (wm - 1) / 2.0)
            dup(K[PFX + "Foundation_4m"], coll, (fx, oy, 0.0), 0.0, body, inner)
            dup(K[PFX + "Roof_Deck_4x4"], coll, (fx, oy + W / 2, H), 0.0, body, inner)
            if wm == 1:
                dup(K[PFX + ("Parapet_Deco" if i % 3 == 1 else "Parapet_Straight")],
                    coll, (fx, oy, H), 0.0, body, inner)
        if name == "Wall_Door_Grand":
            dup(K[PFX + "Parapet_Grand"], coll, (p[0], p[1], H), 0.0, body, inner)
            dup(K[PFX + "Steps_Grand"], coll, p, 0.0, body, inner)
            place_leaves(coll, p, 0.0, body, inner, "grand", angle=RAD(72))
        if name == "Wall_Door":
            place_leaves(coll, p, 0.0, body, inner, "door")
            dup(K[PFX + "Steps_4m"], coll, p, 0.0, body, inner)
        if name == "Wall_Win_Open":
            place_leaves(coll, p, 0.0, body, inner, "sash", angle=RAD(55))
        if name == "Wall_Shopfront":
            dup(K[PFX + "Awning_4m"], coll, p, 0.0, body, inner)
            dup(K[PFX + "Blade_Sign"], coll, p, 0.0, body, inner)
        if name == "Wall_Win_C":
            dup(K[PFX + "Balcony_4m"], coll, p, 0.0, body, inner)
        if name in ("Wall_Solid_A", "Wall_Solid_C"):
            dup(K[PFX + "Wall_Lamp"], coll, p, 0.0, body, inner)
            dup(K[PFX + "Planter"], coll, (p[0] - 1.3, p[1] - 1.5, GROUND_Z), 0.0,
                body, inner)


def ground_plane(coll, name, cx, cy, sx, sy, top=GROUND_Z, mat=None):
    mb = MB(name, PFX)
    sl(mb, -sx / 2, sx / 2, -sy / 2, sy / 2, top - 0.30, top, M(mat or PAVE))
    return out(mb, coll, (cx, cy, 0.0), bevel=0.0)


# ------------------------------------------------------------ scene setup --
# Rows sit 12-14 m apart so the catalogue stays compact to work in. The walls
# are 8 m tall and would block a level camera aimed at the row behind them, so
# the short rows are shot from a steep 3/4 instead of straight on.
SEAM_X4 = [("x", -HW), ("x", HW)]
SEAM_X2 = [("x", -W2 / 2), ("x", W2 / 2)]
SEAM_X8 = [("x", -DG_HW), ("x", DG_HW)]
SEAM_XY4 = SEAM_X4 + [("y", -HW), ("y", HW)]
# Walls also butt vertically when stacked into storeys, so z = 0 and z = H are
# module boundaries too and must not be chamfered -- otherwise every floor line
# carries the same hairline the vertical joints used to.
SEAM_Z = [("z", 0.0), ("z", H)]
SEAM_TILE = ("Roof_Deck_4x4", "Floor_Storey_4x4", "Floor_4x4", "Pavement_4x4")
SEAM_RUN = ("Parapet_Straight", "Parapet_Deco", "Foundation_4m", "Kerb_4m",
            "Steps_4m", "Stoop_Landing")


def seam_for(name):
    """Which planes of this piece butt against an identical neighbour."""
    if name == "Wall_Door_Grand":
        return SEAM_X8 + SEAM_Z
    if name.endswith("_Grand"):
        return SEAM_X8
    if name.startswith("Wall_Half"):
        return SEAM_X2 + SEAM_Z
    if name in SEAM_TILE:
        return SEAM_XY4
    if name.startswith("Corner_"):
        return SEAM_Z
    if name.startswith("Wall_"):
        return SEAM_X4 + SEAM_Z
    if name in SEAM_RUN:
        return SEAM_X4
    return None


ROW_Y = {"Walls": 0.0, "Roof": 14.0, "Ground": 26.0, "Details": 38.0,
         "Palette": 50.0, "Openable": 62.0}
STEP = 6.0
DEMO_Y = -90.0
RUN_Y = DEMO_Y - 46.0
COLOUR_Y = DEMO_Y - 88.0     # one house per palette colour


def build():
    BK.purge_coll(ROOT)
    # Orphaned meshes from the previous build still hold the good names, so a
    # rebuild produces BK_Wall_Win_A.021 -- which is then the mesh name Unity
    # imports. Purge MESHES ONLY: a recursive orphan purge also deletes any
    # library material whose sole user was a kit object, which silently
    # destroys a material hand-assigned to a piece between rebuilds.
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)
    materials()
    BK.MAT_UV_SCALE.clear()
    BK.MAT_UV_SCALE.update(UVS)

    scene = bpy.data.scenes.get(SCENE) or bpy.data.scenes.new(SCENE)
    root = BK.ensure_coll(ROOT, scene.collection)
    c_w = BK.ensure_coll(PFX + "Walls", root)
    c_r = BK.ensure_coll(PFX + "Roof", root)
    c_g = BK.ensure_coll(PFX + "Ground", root)
    c_d = BK.ensure_coll(PFX + "Details", root)
    c_p = BK.ensure_coll(PFX + "Palette", root)
    c_o = BK.ensure_coll(PFX + "Openable", root)
    c_x = BK.ensure_coll(PFX + "Demo", root)
    c_l = BK.ensure_coll(PFX + "Preview", root)
    c_lgt = BK.ensure_coll(PFX + "Lighting", root)

    # Deliberately mid-tone: half the kit is white plaster and pale stone, and
    # on a light stage floor the ground and roof pieces disappear. The Ground
    # row gets a sunken bay -- paving, kerbs and the podium are authored BELOW
    # the finished-floor datum, so on a stage at z=0 they are buried in it.
    ground_plane(c_l, "Stage_Front", 36.0, -7.0, 112.0, 58.0, top=0.0, mat=STAGE)
    ground_plane(c_l, "Stage_Back", 36.0, 50.0, 112.0, 44.0, top=0.0, mat=STAGE)
    ground_plane(c_l, "Stage_Sunken", 36.0, 26.0, 112.0, 12.0, top=-0.78,
                 mat=STAGE)

    for coll, items, row in ((c_w, WALLS, "Walls"), (c_r, ROOFS, "Roof"),
                             (c_g, GROUNDS, "Ground"), (c_d, DETAILS, "Details"),
                             (c_o, OPENABLE, "Openable")):
        y = ROW_Y[row]
        xcur = 0.0
        for name, fn in items:
            mb = MB(name, PFX)
            fn(mb)
            # cursor, not a fixed pitch: the _Grand pieces are 8 m wide and a
            # fixed STEP would drive them straight through their neighbours
            wid = 2.0 * DG_HW if name.endswith("_Grand") else W
            x = xcur + wid / 2.0 - W / 2.0
            xcur += wid + (STEP - W)
            # left on the default BK_Body / BK_Inner: the catalogue is a
            # buildable SET, and cycling a colour per piece made it impossible
            # to read one house out of it
            ob = out(mb, coll, (x, y, 0.0), seam=seam_for(name))
            label(c_l, name, (x, y + 0.9, -1.35))
        label(c_l, row.upper(), (-STEP - 1.0, y + 0.9, 1.2))

    K = bpy.data.objects
    # 1.85 m stand-ins, three abreast, parked in each doorway so the clear width
    # is something you can see rather than something the docs assert
    for pname, clear in (("Wall_Door", DOOR_W - 2 * DOOR_LINER),
                         ("Wall_Door_Grand", DG_W - 2 * DG_LINER)):
        mb = MB("Scale_" + pname, PFX)
        for k in (-1, 0, 1):
            cx = k * 0.90
            mb.cyl((cx, -1.30, 0.78), 0.22, 1.56, M(ACCENT), segments=16)
            mb.sphere((cx, -1.30, 1.68), 0.185, M(ACCENT), segments=14)
        ob = out(mb, c_l, (K[PFX + pname].location.x, ROW_Y["Walls"], 0.0),
                 bevel=0.0)
        label(c_l, "%s  clear %.2f m" % (pname, clear),
              (ob.location.x, ROW_Y["Walls"] - 2.2, -0.75))

    for i, m in enumerate(BODYMATS):
        # two chips on one board: facade colour left, room colour right, so the
        # pairing you would actually ship on a prefab reads at a glance
        mb = MB("Swatch_%02d" % i, PFX)
        sl(mb, -1.20, 1.20, -0.24, 0.24, 0.0, 2.50, M(WHITE))
        sl(mb, -1.10, -0.06, -0.34, -0.23, 0.44, 2.10, M(BODY))
        sl(mb, 0.06, 1.10, -0.34, -0.23, 0.44, 2.10, M(INNER))
        sl(mb, -1.32, 1.32, -0.42, 0.42, 2.50, 2.86, M(WHITE))
        sl(mb, -1.32, 1.32, -0.42, 0.42, 0.0, 0.44, M(WHITE))
        ob = out(mb, c_p, (i * STEP, ROW_Y["Palette"], 0.0))
        recolor(ob, m, INNERMATS[i % len(INNERMATS)])
        label(c_l, PALETTE[i][0] + " / " + INTERIORS[i % len(INTERIORS)][0],
              (i * STEP, ROW_Y["Palette"] + 0.9, -0.9))
    label(c_l, "PALETTE", (-STEP - 1.0, ROW_Y["Palette"] + 0.9, 1.2))

    # ---- demo -------------------------------------------------------------
    ground_plane(c_x, "Demo_Ground", 8.0, DEMO_Y - 26.0, 160.0, 150.0)
    demo_building(c_x, (-24.0, DEMO_Y), 3, BODYMATS[0], INNERMATS[0],
                  ["Wall_Door", "Wall_Win_A", "Wall_Win_B",
                   "Wall_Win_C", "Wall_Solid_B", "Wall_Win_Shut",
                   "Wall_Win_Open", "Wall_Win_Open", "Wall_Win_A",
                   "Wall_Win_B", "Wall_Solid_A", "Wall_Win_A"])
    demo_building(c_x, (2.0, DEMO_Y), 2, BODYMATS[1], INNERMATS[3],
                  ["Wall_Shopfront", "Wall_Win_A", "Wall_Win_B", "Wall_Solid_C",
                   "Wall_Win_C", "Wall_Solid_B", "Wall_Win_Shut", "Wall_Win_A"],
                  deco=False, storeys=2)
    demo_building(c_x, (26.0, DEMO_Y), 3, BODYMATS[4], INNERMATS[5],
                  ["Wall_Shopfront", "Wall_Win_B", "Wall_Solid_C",
                   "Wall_Win_A", "Wall_Win_C", "Wall_Win_Shut",
                   "Wall_Solid_A", "Wall_Win_B", "Wall_Win_A",
                   "Wall_Solid_B", "Wall_Win_Twin", "Wall_Win_C"],
                  storeys=3)
    demo_run(c_x, (8.0, RUN_Y), FACADE, BODYMATS[2], INNERMATS[2])

    # One house per palette colour, all from the SAME meshes -- only the two
    # colour slots differ. This is the "build me a yellow house" set.
    c_c = BK.ensure_coll(PFX + "Colours", root)
    ground_plane(c_c, "Colour_Ground", 8.0, COLOUR_Y, 176.0, 34.0)
    for i, (nm, _) in enumerate(PALETTE):
        demo_building(c_c, (8.0 + 20.0 * (i - 3.5), COLOUR_Y), 2,
                      BODYMATS[i], INNERMATS[i],
                      ["Wall_Door", "Wall_Win_A", "Wall_Win_Shut", "Wall_Win_B",
                       "Wall_Win_A", "Wall_Solid_B", "Wall_Win_Twin", "Wall_Win_A"],
                      deco=(i % 2 == 0), storeys=1 + (i % 2))
        label(c_l, nm, (8.0 + 20.0 * (i - 3.5), COLOUR_Y - 7.0, -0.9))
    for i in range(12):
        dup(K[PFX + "Kerb_4m"], c_x, (8.0 + W * (i - 5.5), RUN_Y - 6.2, 0.0),
            0.0, None)

    world_and_lights(scene, c_lgt)
    cd = bpy.data.cameras.new(PFX + "Cam")
    cam = bpy.data.objects.new(PFX + "Cam", cd)
    c_lgt.objects.link(cam)
    scene.camera = cam
    try:
        scene.render.engine = "BLENDER_EEVEE"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.eevee.taa_render_samples = 64
    scene.eevee.use_shadows = True
    try:
        scene.eevee.use_raytracing = True
        scene.eevee.ray_tracing_options.use_denoise = True
    except Exception:
        pass
    aim(cam, *SHOTS["overview"])

    tris = 0
    for c in (c_w, c_r, c_g, c_d):
        for o in c.objects:
            if o.type == "MESH":
                tris += len(o.data.polygons)
    return tris


def world_and_lights(scene, c_lgt):
    w = bpy.data.worlds.get(PFX + "Sky") or bpy.data.worlds.new(PFX + "Sky")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    ids = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
    sky.sky_type = "MULTIPLE_SCATTERING" if "MULTIPLE_SCATTERING" in ids else "NISHITA"
    sky.sun_elevation = RAD(38)
    sky.sun_rotation = RAD(215)
    for p, v in (("sun_intensity", 0.12), ("air_density", 0.80),
                 ("dust_density", 0.30), ("sun_disc", False)):
        if hasattr(sky, p):
            setattr(sky, p, v)
    bg.inputs[1].default_value = 0.35
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], o.inputs[0])
    scene.world = w
    try:
        scene.view_settings.view_transform = "Khronos PBR Neutral"
    except TypeError:
        pass
    sd = bpy.data.lights.new(PFX + "Sun", "SUN")
    sd.energy, sd.angle = 4.2, RAD(1.8)
    sd.color = (1.0, 0.96, 0.89)
    sun = bpy.data.objects.new(PFX + "Sun", sd)
    sun.rotation_euler = Euler((RAD(52), 0, RAD(212)), "XYZ")
    c_lgt.objects.link(sun)
    for i, (loc, en) in enumerate((((-24.0, DEMO_Y, 5.2), 300.0),
                                   ((-24.0, DEMO_Y - 3.0, 6.6), 200.0))):
        ld = bpy.data.lights.new(PFX + "Fill%d" % i, "AREA")
        ld.energy, ld.size, ld.color = en, 7.0, (1.0, 0.92, 0.82)
        ob = bpy.data.objects.new(PFX + "Fill%d" % i, ld)
        ob.location = loc
        ob.rotation_euler = Euler((RAD(180), 0, 0), "XYZ")
        c_lgt.objects.link(ob)


SHOTS = {
    "overview":    ((122.0, -56.0, 72.0), (34.0, 26.0, 0.0), 42),
    "row_walls_a": ((14.0, -27.0, 4.6), (14.0, 0.0, 4.2), 30),
    "row_walls_b": ((44.0, -27.0, 4.6), (44.0, 0.0, 4.2), 30),
    "row_walls_c": ((76.0, -27.0, 4.6), (76.0, 0.0, 4.2), 30),
    "row_roof":    ((18.0, -5.0, 16.0), (18.0, 14.0, 1.0), 24),
    "row_ground":  ((18.0, 9.0, 10.0), (18.0, 26.0, -0.4), 24),
    "row_detail":  ((15.0, 21.0, 11.0), (15.0, 38.0, 2.6), 24),
    "row_palette_a": ((9.0, 34.0, 10.0), (9.0, 50.0, 1.8), 24),
    "row_palette_b": ((33.0, 34.0, 10.0), (33.0, 50.0, 1.8), 24),
    # catalogue close-ups: WALLS index i sits at x = i*STEP
    "door":        ((54.0, -13.0, 3.2), (54.0, 0.0, 3.4), 46),
    "shutters":    ((18.0, -11.0, 3.6), (18.0, 0.0, 3.6), 42),
    "shut_closed": ((24.0, -11.0, 3.6), (24.0, 0.0, 3.6), 42),
    "quoin":       ((-40.0, DEMO_Y - 20.0, 4.2), (-30.0, DEMO_Y - 6.0, 4.4), 48),
    "demo_hero":   ((-56.0, DEMO_Y - 46.0, 26.0), (4.0, DEMO_Y + 2.0, 9.0), 40),
    "stack":       ((26.0, DEMO_Y - 44.0, 13.0), (26.0, DEMO_Y - 6.0, 13.0), 34),
    "colours":     ((8.0, COLOUR_Y - 62.0, 9.0), (8.0, COLOUR_Y, 7.0), 26),
    "colours_b":   ((-32.0, COLOUR_Y - 26.0, 8.0), (-12.0, COLOUR_Y, 6.0), 34),
    "demo_run":    ((8.0, RUN_Y - 52.0, 5.2), (8.0, RUN_Y, 5.2), 30),
    "demo_close":  ((-32.0, DEMO_Y - 22.0, 3.0), (-22.0, DEMO_Y - 4.0, 4.6), 34),
    "interior":    ((-25.5, DEMO_Y - 3.8, 1.68), (-23.0, DEMO_Y + 4.5, 2.6), 19),
}


def export_fbx(out_dir):
    """One FBX per kit piece, exported AT THE ORIGIN so the Unity prefab pivot
    is the module pivot, with the bevel applied and Unity's axis convention.

    In Unity: import, extract materials, make each mesh a prefab. Every wall
    piece's material slot 0 is BK_Body (exterior) and slot 1 is BK_Inner
    (interior) -- see CANON_MATS -- so a per-colour prefab variant is two slot
    overrides and no new geometry."""
    import os
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.data.scenes[SCENE]
    view = scene.view_layers[0]
    written = []
    for cn in (PFX + "Walls", PFX + "Roof", PFX + "Ground", PFX + "Details",
               PFX + "Openable"):
        for ob in list(bpy.data.collections[cn].objects):
            if ob.type != "MESH":
                continue
            keep = ob.location.copy()
            ob.location = (0.0, 0.0, 0.0)
            for o in view.objects:
                o.select_set(False, view_layer=view)
            ob.select_set(True, view_layer=view)
            view.objects.active = ob
            fp = os.path.join(out_dir, ob.name + ".fbx")
            # temp_override, not window.scene: the operator otherwise runs
            # against whatever scene the UI happens to be showing
            with bpy.context.temp_override(scene=scene, view_layer=view):
                bpy.ops.export_scene.fbx(
                    filepath=fp, use_selection=True, object_types={"MESH"},
                    use_mesh_modifiers=True, mesh_smooth_type="FACE",
                    apply_unit_scale=True, apply_scale_options="FBX_SCALE_NONE",
                    bake_space_transform=False, axis_forward="-Z", axis_up="Y",
                    path_mode="STRIP", use_triangles=False)
            ob.location = keep
            written.append(ob.name)
    return written


def aim(cam, loc, tgt, lens):
    cam.data.lens = lens
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def render_shots(out_dir, names=None, res=(1600, 900), samples=64):
    scene = bpy.data.scenes[SCENE]
    cam = bpy.data.objects[PFX + "Cam"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.eevee.taa_render_samples = samples
    for n in (names or SHOTS):
        if n.startswith("piece:"):
            # framed from the piece's own footprint, so close-ups survive the
            # catalogue being reordered or a piece changing width
            ob = bpy.data.objects[PFX + n.split(":", 1)[1]]
            cx, ht = ob.location.x, ob.dimensions.z
            # long lens far back: a wide lens close in throws enough perspective
            # on an 8 m piece to make its flanking pilasters unreadable
            dist = ht * 1.9
            aim(cam, (cx, ROW_Y["Walls"] - dist, ht * 0.48),
                (cx, ROW_Y["Walls"], ht * 0.50), 45)
        else:
            aim(cam, *SHOTS[n])
        scene.render.filepath = (out_dir.rstrip("/") + "/"
                                 + n.replace("piece:", "") + ".png")
        bpy.ops.render.render(write_still=True, scene=SCENE)
        print("shot", n)
    aim(cam, *SHOTS["overview"])


if not globals().get("BK_NOBUILD"):
    print("BuildingKit quads:", build())
