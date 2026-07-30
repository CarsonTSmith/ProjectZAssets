"""
BiteClubKitGen.py -- "Bite Club" haunted-house modular WALL kit, with doors and
windows, authored from the concept sheet for export into Unity.

Builds scene "BiteClubKit" (in BiteClubKit.blend). Four kit collections plus a
catalogue and two demo rooms:

    BC_Walls     14 wall modules  (straight / half / plain / plain half /
                                   pillar / outer + inner corner / broken /
                                   arch / door / double door / window /
                                   small window / round window)
    BC_Walls_Int 14 partitions    -- the same fourteen shapes finished as a ROOM
                                   ON BOTH FACES: no stone anywhere, a panelled
                                   wood pilaster where the outside wall has its
                                   quoin post. Same lattice, same pivots, same
                                   inserts, so the two families mix in one run.
    BC_Doors     11 door pieces   (door, double door, arch door, secret
                                   bookcase, barricaded door, trapdoor -- each
                                   frame plus its own hinged leaf mesh)
    BC_Windows    5 window pieces (small, tall, boarded, round, secret grate)

------------------------------------------------------------------- THE GRID --
Module W = 4 m, wall H = 4 m, thickness T = 0.30 m. Half-width filler = 2 m.
Corner pieces are L-shaped with 2 m wings, so the whole kit lives on ONE 4 m
lattice: corners sit on lattice intersections, straight walls on lattice points
along an edge. A room is therefore any multiple of 4 m and never needs a filler
unless you deliberately break the rhythm with Wall_Half.

Pivots: every wall piece's origin is the bottom centre of its module footprint,
on the wall centre-line, exterior facing -Y (Blender -Y -> Unity +Z, so an
unrotated piece faces Unity-forward). Corner pieces pivot on the corner axis
with wings running +X and +Y.

★ Doors and windows are INSERTS, not baked into the wall. Each insert shares the
  HOST WALL'S PIVOT exactly: drop Wall_Door and Door_Frame at the same transform
  and they fit. Anything that swings (Door_Leaf, the two double leaves, the
  bookcase, the trapdoor lid) is its own mesh with its origin ON THE HINGE AXIS,
  offset from the wall pivot by the constants printed in the README, so Unity
  rotates it about local Z (Blender) / Y (Unity) and nothing else moves.

--------------------------------------------------------------- ANTI-TILING --
1. UV density 0.5 repeats/m and whole-metre module extents, so 4 * 0.5 = 2 is an
   integer: the wallpaper runs continuously across a module join instead of
   restarting. UVs are projected in each piece's LOCAL space so this holds
   wherever Unity puts the instance.
2. The heavy wood top beam and the plank wainscot are continuous horizontal
   bands -- they read across the vertical joins.
3. A full stone quoin post at BOTH module ends. Butt two modules and the pair
   reads as one deliberate 0.68 m column, which is the cheapest possible way to
   make a joint look intentional rather than hidden.
4. The wall field is TWO material slots (BC_Wall_A on the -Y face, BC_Wall_B on
   +Y), so one mesh gives papered-inside / stone-outside with no new geometry.

Run headless:
    blender -b BiteClubKit.blend --python BiteClubKitGen.py
or inside Blender:
    exec(open("/home/carson/Blender/ProjectZAssets/BiteClubKitGen.py").read())
"""

import bpy, bmesh, math, os, sys, importlib
from mathutils import Vector, Euler, Matrix

sys.path.insert(0, "/home/carson/Blender/ProjectZAssets")
import BlockoutKit as BK
importlib.reload(BK)
MB = BK.MB

PFX = "BC_"
ROOT = "BiteClubKit"
SCENE = "BiteClubKit"
RAD = math.radians
TAU = math.pi * 2.0

# The collections that ARE the kit: everything exported, audited and counted.
# One list, because a new family has to be picked up by the build gates the same
# day it is authored -- audit_bevel() and audit_chamfer() looked at a hardcoded
# three and would have skipped the interior walls in silence.
KIT_COLLS = (PFX + "Walls", PFX + "Walls_Int", PFX + "Doors", PFX + "Windows")


def srgb(h):
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f((h >> 16) & 255), f((h >> 8) & 255), f(h & 255))


# ---------------------------------------------------------------- metrics --
W, H, T = 4.0, 4.0, 0.30
HW, HT = W / 2.0, T / 2.0
W2 = 2.0                       # half-width filler
CWING = 2.0                    # corner wing reach from the corner axis

# ------------------------------------------------------------ TRIM STANDARD --
# ★ ONE ladder of projections, ONE stone course, ONE board width, ONE chamfer.
# Every trim member in the kit picks from these constants and nothing gets a
# bespoke number. This is the whole reason a beam, a quoin, an architrave, a
# sill and a window bar read as the same carpentry when they meet on one piece:
# they share a depth, a block size and an edge radius, so the eye resolves them
# as one system rather than as parts from several kits.
#
# ★ Projection ladder -- how far a member stands off the wall face. FOUR rungs,
# a uniform 0.05 m step, and a strict hierarchy: stone is always prouder than
# the joinery it dies into, and the joinery is always prouder than the field.
# That hierarchy is not decoration -- two members at the SAME projection put
# coplanar faces in the same place, and the pillar dropped on a Wall_Plain run
# z-fought against the chair rail for exactly that reason.
# ★★ THE BOTTOM RUNG IS 0.08 BECAUSE OF THE CHAMFER, not because of taste. The
# Bevel modifier runs with use_clamp_overlap, and the clamp is GLOBAL: Blender
# computes ONE safe offset for the whole mesh, so a single member thinner than
# 2 x BEVEL_W silently shrinks the chamfer on EVERY edge of the piece -- the
# same nominal 0.024 in the modifier, a visibly sharper piece on screen (at
# 0.04 the ashlar relief sharpened Wall_Arch and Wall_Broken wholesale; later
# one tangent wedge in the arch cut did it to five walls, see ARC_S). Nothing
# in the kit may be thinner than BEVEL_MIN in any axis; `audit_bevel()`
# enforces that floor and `audit_chamfer()` measures the built result.
P1 = 0.08                      # ashlar relief, wainscot boards, wall-side rings
P2 = 0.13                      # skirting, chair rail, beam body, architraves
P3 = 0.18                      # stone quoins/posts/pillar, beam cap, sills, keys
# Stone: one course height, one block length (2 courses, so the bond half-laps),
# one mortar joint. Voussoirs are cut to VOUSS of ARC LENGTH, so an arch stone
# is the same size on a 0.6 m oculus as on a 1.2 m double door.
COURSE, BLOCK, GAP, VOUSS = 0.45, 0.90, 0.045, 0.30
# Joinery: one board width for every plank run, one applied-board section.
PLANK_W, PLANK_G = 0.26, 0.026
BOARD_W, BOARD_T = 0.26, 0.10  # barricade / boarded-window battens, door ledges
BAR = 0.06                     # glazing bars and tracery ribs
IRON_W = 0.11                  # straps, ring stock, grate bars
CASE = 0.20                    # architrave width, every opening
SILL_H, SILL_LAP = 0.14, 0.06  # the ONE projecting stone block -- see stone_shelf
# ★ Ring depth is set AGAINST the voussoir length, not chosen freely. At 0.26
# the ring measured 0.31 deep against a 0.30 stone -- every voussoir in the kit
# was a perfect square, which nothing else in it is (ashlar and quoins are all
# 2:1). It only became obvious on the oculus, where a closed ring of fifteen
# squares reads as a cog. At 0.16 the stone is 0.30 x 0.21, the same brick
# proportion as the rest of the masonry.
RING = 0.16                    # arch ring depth, every arch
# One chamfer everywhere. Weight-limited on every piece (never angle-limited on
# some and weight-limited on others) so the rounding is identical kit-wide.
BEVEL_W, BEVEL_SEG, BEVEL_ANG = 0.024, 2, 38.0
BEVEL_MIN = 2.0 * BEVEL_W      # thinnest a member may be and still chamfer fully

# --------------------------------------------------- DATUM DECONFLICTION --
# ★★ THE FLICKER, AND WHY THE PROJECTION LADDER ABOVE CANNOT FIX IT.
# Every member here is a closed solid and members interpenetrate freely -- that
# is how a head beam dies into a wall with no seam. Interpenetration is free,
# because the buried faces sit inside solid and are never rasterised. What is
# NOT free is two members ENDING ON THE SAME PLANE. The module datums are
# exactly the planes where every member is REQUIRED to stop flush so that
# modules butt on the lattice, so on z = H the shell's top face, the head beam's
# cap and the heavy block over the post all land together: coplanar, all facing
# +Z, three different materials. The depth buffer then has no basis to choose
# between them and picks per PIXEL, per frame, so the top of the wall strobes
# stone/wood as the camera moves. Measured on the built kit before this pass:
# 1.20 m2 of exact coincidence on the top of EVERY wall module, another 1.20 on
# every bottom, and 0.24-1.78 on each module end.
# The ladder cannot help, because the whole meaning of a datum is that a member
# may not back off it. So instead each datum plane gets exactly ONE owner and
# every other member in the clash recedes by a hairline. The owner is the
# largest face in the clash, which is both the surface the eye actually reads
# (the beam cap on the wall top) and -- at x = +/-HW, where the shell's end cap
# is always the biggest face by far -- the structural shell, so the butt joint
# and the snapping lattice stay bit-exact and no seam can open.
# ★ One rung is 0.5 mm: ~100x the depth resolution of a 24-bit buffer at the
# 300 m far clip this project ships, 1/48 of the chamfer, and far under the
# thinnest member in the kit (BAR, 0.06) so nothing is driven below BEVEL_MIN.
DATUM_EPS = 0.0005
# Greedy colouring keeps real recessions at one rung; the allowance is what
# SEAM_BAND has to be able to hold, not a depth anyone reaches.
DATUM_RANKS = 3
# ★★ Recession moves an edge OFF the datum, and mark_bevel_weights() excludes
# edges from chamfering by testing them against that datum. Left exact, a receded
# trim end at a module joint would start getting the full 24 mm chamfer -- the
# V-notch down every joint that the exclusion exists to prevent. So the
# exclusion is a BAND wide enough to hold the whole recession ladder, not a
# plane. Nothing in the kit is authored between 0.1 mm and 1.6 mm off a datum,
# so the band cannot swallow an edge that was meant to be chamfered.
SEAM_BAND = DATUM_RANKS * DATUM_EPS + 1e-4
# An insert (a frame, a leaf, a grate) is a SEPARATE object sharing its host
# wall's pivot, so the pass above -- which only ever sees one mesh -- is blind to
# the clash between them. Two planes collide by construction: both are built
# from the same constants, so the wall's chair rail and the frame's architrave
# both stand at P2 and land on y = +/-(HT+P2) together (0.07 m2 of coplanar
# joinery at eye level on every door wall), and every insert's underside lands
# on the floor datum alongside the wall's. Joinery applied to a wall reads as
# PROUD of the wall's own joinery, so an insert advances a hairline on the
# wall-face planes; nothing but the wall's structural bottom may sit ON the
# floor datum, so an insert lifts off it.
INSERT_EPS = 0.0015
# ★★ CASE_LAP -- the same hairline, applied to the OPENING planes rather than the
# wall-face rungs. lift_insert() only knows about y = +/-(HT+p) and the floor, so
# a frame's jamb, head and sill returns still landed exactly on the wall's own
# REVEAL: coplanar, same-facing, both plainly visible from inside the opening,
# and belonging to two different meshes, so nothing in the kit could arbitrate
# them. Measured on the assembled demo: 0.30 m2 per jamb on every window wall and
# 0.80 m2 on the small window's head, flickering wood against wood. Every casing
# member therefore laps INSERT_EPS INTO the opening -- the insert covers the cut,
# which is what a lining is for, and the clear opening loses 3 mm.

# Stone quoin post at each module end. Full width (not a half post) because the
# concept sheet draws a complete post on an isolated piece; two butted modules
# then read as one 0.68 m column, which is a feature, not a seam. Wall_Plain
# drops the posts entirely and Pillar is that same column free-standing.
PIL_W, PIL_P = 0.34, P3
QUOIN_STEP = 0.09              # how far a short course steps back off the face
FX = HW - PIL_W                # 1.66 -- field half-width between the posts

# Chunky wood top beam. Deliberately deep rather than tall: projection carries
# the shadow line, height would eat the wall's colour.
BEAM_Z, BEAM_P = 3.52, P2
BEAM_CAP_Z, BEAM_CAP_P = 3.84, P3
BEAM_END = 0.44                # wood block over each post

# Plank wainscot: skirting and chair rail both stand at P2 with the boards
# recessed to P1 between them, which is how the joinery actually works.
SKIRT_Z, SKIRT_P = 0.16, P2
WAIN_Z, WAIN_P = 0.98, P1
RAIL_Z, RAIL_P = 1.14, P2
# ★ The boards are fixed to a GROUND, and it is not decoration: the run leaves
# PLANK_G between boards, the chamfer opens that to about 70 mm, and without a
# panel behind it every groove in the dado showed a stripe of the wallpaper. The
# ground stands half a rung proud so the boards keep their shadow line, and is
# thick enough to chamfer (BEVEL_MIN) by reaching back INTO the wall rather than
# by standing further out. See ground().
GROUND_P, GROUND_T, GROUND_LAP = 0.03, 0.09, 0.02

# Stone plinth on the stone-native pieces: exactly ONE course.
BASE_Z, BASE_P = COURSE, P2

# ------------------------------------------------- interior partition walls --
# ★ THE INTERIOR SET IS THE SAME WALL WITH THE MASONRY TAKEN OUT. Every piece in
# the Wall_Int_* family is finished as a ROOM on BOTH faces -- damask field,
# skirting + plank wainscot + chair rail, wood head beam -- and carries no stone
# anywhere: no quoin post, no voussoir ring, no plinth, no ashlar, no threshold
# steps. Those are the outside of a building, and a partition has two insides.
# What replaces the stone quoin is a PANELLED WOOD PILASTER on the same column
# width and the same projection rung (PIL_W / PIL_P below), so the two families
# live on ONE lattice and butt without a step: an outside wall can turn into a
# partition mid-run and the joint still reads as one deliberate column.
# ★★ THE COLUMN LAPS THE MODULE DATUM, and this is not a nicety. Edges lying in
# a module-boundary plane are excluded from the chamfer (see mark_bevel_weights)
# because two butted modules must not each chamfer the meeting edge of a surface
# that continues across it. A column is NOT such a surface -- nothing of it
# continues into the next module -- so with its outer face flush on the datum the
# arris came out razor sharp while its twin 0.68 m away was rounded: one side of
# every pillar bevelled and the other not. Lapping it past the datum by more than
# SEAM_BAND makes that a real edge again, and the 4 mm sits inside the neighbour's
# wall thickness where it is swallowed by the column's own solid.
POST_LAP = 0.004
PAN_STILE = 0.09               # pilaster stile; an internal division gets two
PAN_RAIL = 0.20                # rail over the plinth and under the capital
PIL_CAP = 0.24                 # capital block, directly under the head beam
PIL_ARM = 0.58                 # corner post arm -- the quoin's own long arm
# ★ The wall's arch band is ONE CONTINUOUS member, never a segmented ring. The
# insert that drops into the hole brings a SEGMENTED architrave (arch_frame), and
# two segmented rings at slightly different radii interleave into noise -- the
# same reason Arch_Door_Frame stopped emitting a ring of its own. Continuous and
# one rung shallower, it reads as the lined reveal the architrave stands over.
INT_RING_P = P1

# --------------------------------------------------------------- openings --
# One opening spec per host wall. Inserts are built from the SAME constants, so
# a frame can never drift out of its hole.
#            half-width  sill   spring  arch r     -> head
OP_D = dict(hw=0.70, z0=0.00, zs=2.10, r=0.70)     # door            head 2.80
OP_DD = dict(hw=1.20, z0=0.00, zs=1.80, r=1.20)    # double door     head 3.00
OP_A = dict(hw=1.10, z0=0.10, zs=1.90, r=1.10)     # walk-through    head 3.00
# ★★ EVERY window sill sits exactly ON the chair rail. The tall window used
# to start at 1.10, four centimetres BELOW the rail top -- enough for spans() to
# treat it as cutting the dado, so Wall_Window lost its wainscot under the
# window while Wall_Straight kept a continuous run. The two rounded cut-ends
# that left mid-wall are what read as a bevel mismatch between the pieces.
# Derived, not typed, so it cannot drift again.
WIN_SILL_Z = RAIL_Z + SILL_H                       # 1.28
OP_W = dict(hw=0.70, z0=WIN_SILL_Z, zs=2.50, r=0.70)   # tall window  head 3.20
# The small window sits LOW: its insert carries a relieving arch on top, and
# that hood's crown is sill + height + hw + 0.34. Any higher and the hood grows
# straight through the head beam at 3.52.
OP_WS = dict(hw=0.60, z0=WIN_SILL_Z, zs=2.38, r=0.0)   # small window (rect)
OP_R = dict(cz=2.30, r=0.62)                       # round window

STEP_D = 0.34                   # arch threshold apron tread depth

# Hinge offsets, measured from the HOST WALL pivot, in module-local X.
DOOR_HINGE = OP_D["hw"] - 0.05                     # 0.65
DD_HINGE = OP_DD["hw"] - 0.05                      # 1.15
SECRET_HINGE = 0.92                                # bookcase is wider than the hole
TRAP_HINGE = -0.78                                 # trapdoor lid, local -X edge

# ---------------------------------------------------------------- palette --
# Sampled off the concept sheet's own swatch strip, plus the wood / stone /
# glass values read out of the piece renders.
C_PAPER = 0x5E3F86        # damask ground
C_PAPER2 = 0x6E4A97       # damask motif -- close in value to the ground on
                          # purpose; a high-contrast checker reads as a
                          # chessboard at 4 m, not as wallpaper
C_STONE = 0x9A8FB5        # lavender ashlar
C_STONE2 = 0x6E6390       # its shadow / mortar
C_WOOD = 0x7A5546
C_WOOD2 = 0x4A322A
C_WOOD_DK = 0x54392F      # door leaves
C_IRON = 0x3A3448
C_GLASS = 0x1E8C99
C_NEON_G = 0x85CA36       # sheet swatch: acid green
C_NEON_P = 0xDB369F       # sheet swatch: hot pink
C_NEON_C = 0x26BBBA       # sheet swatch: cyan
C_PURPLE = 0x5B337B       # sheet swatch: deep purple

PAPER = PFX + "Wall_A"
PAPER_B = PFX + "Wall_B"
STONE = PFX + "Stone"
WOOD = PFX + "Wood"
WOODD = PFX + "WoodDark"
IRON = PFX + "Iron"
GLASS = PFX + "Glass"
BOOK_A = PFX + "Book_A"
BOOK_B = PFX + "Book_B"
BOOK_C = PFX + "Book_C"
LABEL = PFX + "Label"
STAGE = PFX + "Stage"

# Slot order written on every piece, subset to what it uses. Slot 0 is the -Y
# wall face and slot 1 the +Y face on every wall module, so a Unity prefab
# variant recolours a room from the outside in with two overrides.
CANON = [PAPER, PAPER_B, STONE, WOOD, WOODD, IRON, GLASS,
         BOOK_A, BOOK_B, BOOK_C, LABEL, STAGE]

# repeats per metre. 0.5 on the wall finishes keeps 4 m and 2 m modules on
# integer UV units, which is what makes the paper run through a module join.
UVS = {PAPER: 0.5, PAPER_B: 0.5, STONE: 0.5, WOOD: 1.0, WOODD: 1.0,
       IRON: 1.0, GLASS: 0.5, BOOK_A: 2.0, BOOK_B: 2.0, BOOK_C: 2.0,
       STAGE: 0.25}


def M(n):
    return bpy.data.materials[n]


# ------------------------------------------------------------- primitives --
def face_key(n):
    ax = max(range(3), key=lambda i: abs(n[i]))
    return ("+" if n[ax] > 0 else "-") + "xyz"[ax]


def sl(mb, x0, x1, y0, y1, z0, z1, mat, faces=None, uvs=0.0):
    """Axis-aligned slab from min/max corners -- most of the kit is these.

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


def _seal(mb, before):
    """Give the faces just emitted a real, outward normal.

    ★★ `extrude_poly` leaves EVERY face it makes with a zero-length normal --
    bmesh does not compute them until something asks. `face_key` then reads
    (0,0,0), takes axis 0, sees it is not positive and answers "-x" for the top
    cap, the bottom cap and all six sides alike. Both material passes in this kit
    (`shell` and `_corner_core`) sort faces BY NORMAL, so every face of an
    L-shaped corner slab was being handed the convex wall slot: the corner was
    crowned with wallpaper where the beam cap should be, its wing end caps were
    papered instead of lined, and its concave side sat on slot 0 with the convex
    one, so the two rooms a corner divides could not be papered differently. None
    of it was visible in a render because both wall slots ship the same damask.
    Recalculating here rather than in the two consumers means anything authored
    later gets it right by construction -- and it is idempotent with the recalc
    `out()` runs before the datum passes."""
    new = [f for f in mb.bm.faces if f not in before]
    if new:
        bmesh.ops.recalc_face_normals(mb.bm, faces=new)


def poly(mb, pts_xz, y0, y1, mat):
    """Sweep a planar XZ polygon through the wall thickness.

    This is how every curved opening is cut. Blender cannot make a face with a
    hole in it, but a rectangle-minus-an-arc IS a simple concave polygon, so the
    wall around an arch is emitted as a couple of these instead of as a stack of
    stepped boxes -- the soffit comes out as one continuous curved surface."""
    if len(pts_xz) < 3:
        return
    before = set(mb.bm.faces)
    mb.extrude_poly([(x, y0, z) for x, z in pts_xz], (0.0, y1 - y0, 0.0), mat)
    _seal(mb, before)


def lpoly(mb, pts_xy, z0, z1, mat):
    """Sweep a planar XY polygon vertically -- the way every L-shaped member in
    the kit is made.

    ★ Corners must be ONE solid, never two butted boxes. Two boxes meeting at
    the corner put a bevelled edge on each side of the joint, so the chamfer
    cuts a V-groove straight down the corner and the quoin reads as loose bricks
    stacked against a cracked wall. It also leaves the wainscot with a real gap
    at the corner cell, which is what showed up as a slot in the skirting."""
    if len(pts_xy) < 3 or z1 - z0 <= 1e-6:
        return
    before = set(mb.bm.faces)
    mb.extrude_poly([(x, y, z0) for x, y in pts_xy], (0.0, 0.0, z1 - z0), mat)
    _seal(mb, before)


def arc_pts(cx, cz, r, a0, a1, n):
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / n),
             cz + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def mark_bevel_weights(ob, planes, angle_deg=38.0):
    """Weight every sharp edge for bevelling EXCEPT edges lying flat in a
    module-boundary plane.

    Two modules butt exactly on the lattice line. Chamfering that meeting edge
    cuts a V-notch into both, and whatever sits behind the notch shows through
    as a hairline down every joint."""
    me = ob.data
    bm = bmesh.new()
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
                # ★ a BAND, not a plane -- see SEAM_BAND: deconflict() parks
                # receded trim ends up to two rungs off the datum and those
                # edges must stay unchamfered too, or the notch comes back
                if (abs(e.verts[0].co[i] - val) < SEAM_BAND
                        and abs(e.verts[1].co[i] - val) < SEAM_BAND):
                    w = 0.0
                    break
        vals.append(w)
    bm.free()
    at = me.attributes.get("bevel_weight_edge")
    if at is None:
        at = me.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
    at.data.foreach_set("value", vals)
    me.update()


def _plane_group(bm, i, val, sgn):
    """Every face lying flat IN a datum plane and facing one way out of it."""
    return [f for f in bm.faces
            if f.normal[i] * sgn > 0.999
            and all(abs(v.co[i] - val) < 1e-4 for v in f.verts)]


def _surfaces(fs):
    """Fuse the faces of one plane into surfaces that must move together.

    ★ Faces that SHARE VERTS are one surface, and moving one of them alone would
    tear the mesh. A corner's head beam lands on the top datum as three faces
    meeting at the miter, and the welded shell's top is a run of coplanar
    neighbours -- treated as separate candidates, the first one moved locks its
    shared verts and every sibling has to be skipped, which silently leaves the
    clash in place (0.64 m2 of it on each corner). Fused, the whole beam top
    recedes as one and the surface stays watertight."""
    parent = list(range(len(fs)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner = {}
    for p, f in enumerate(fs):
        for v in f.verts:
            if v.index in owner:
                parent[find(p)] = find(owner[v.index])
            else:
                owner[v.index] = p
    out = {}
    for p in range(len(fs)):
        out.setdefault(find(p), []).append(p)
    return list(out.values())


def _overlap_graph(surfs, fs, ax):
    """Which surfaces in one plane actually cover each other.

    Two ashlar blocks side by side in the same plane are not a clash and must not
    be moved -- only surfaces whose footprints genuinely overlap are. Every
    clashing face in this kit is an axis-aligned rectangle, so footprint overlap
    is an interval test on the two in-plane axes; the 1e-4 margin keeps faces that
    merely SHARE AN EDGE (the welded shell is full of those) out of the graph."""
    a1, a2 = [k for k in (0, 1, 2) if k != ax]

    def bbox(p):
        c1 = [v.co[a1] for v in fs[p].verts]
        c2 = [v.co[a2] for v in fs[p].verts]
        return (min(c1), max(c1), min(c2), max(c2))

    bb = [[bbox(p) for p in s] for s in surfs]
    adj = {i: set() for i in range(len(surfs))}
    for i in range(len(surfs)):
        for j in range(i + 1, len(surfs)):
            hit = False
            for bp in bb[i]:
                for bq in bb[j]:
                    if (min(bp[1], bq[1]) - max(bp[0], bq[0]) > 1e-4
                            and min(bp[3], bq[3]) - max(bp[2], bq[2]) > 1e-4):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                adj[i].add(j)
                adj[j].add(i)
    return adj


def deconflict(mb):
    """Give every clashing plane ONE owner and recede the rest a hairline.

    See DATUM_EPS. Runs on the assembled bmesh, so it catches every member
    however it was emitted -- sl(), poly(), lpoly() alike -- instead of asking
    thirty build functions to remember the rule, and it sweeps EVERY plane rather
    than only the declared module datums: the bookcase carcass behind the secret
    door and the grate's own frame clash on planes that are nobody's datum.

    ★ GREEDY COLOURING, not a rank order. Ranking every face in a clash to its
    own depth looks right and is wrong twice over. It buries deep members far
    enough to open a visible gap, and -- because the depth ladder has to stop
    somewhere -- it lands everything past the last rung back on ONE plane, which
    is the clash again with extra steps. What actually has to hold is only that no
    two OVERLAPPING faces share a plane, so each face takes the shallowest rung
    none of its overlaps has taken. Sorting by area first hands rung 0 to the
    biggest face, which is both the surface the eye reads (the beam cap crowning
    the wall) and, at x = +/-HW, the structural shell -- so the butt joint and the
    snapping lattice stay bit-exact. The head beam, skirting and chair rail do not
    overlap EACH OTHER at a module end, so all three share rung 1 and the deepest
    recession anywhere in the kit is one rung.

    ★ Moving a face means moving its verts, and a member's cap verts are shared
    ONLY with that member's own side faces: weld() runs per shell and de-dupes
    nothing across members, so shortening a box here cannot drag a neighbour. The
    guard still refuses to move a vert twice, so two faces that DID share verts
    leave the plane together rather than tear apart."""
    bm = mb.bm
    bm.verts.index_update()
    facing = {}
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        if abs(n[ax]) < 0.999:
            continue            # tilted members carry no datum and no clash here
        co = [v.co[ax] for v in f.verts]
        if max(co) - min(co) > 1e-4:
            continue            # not flat in its own plane
        facing.setdefault((ax, 1 if n[ax] > 0 else -1), []).append(
            (sum(co) / len(co), f))

    # ★ Group by a SWEEP, not by a rounded key. The corner's L beam comes out of
    # the miter maths 0.024 mm off the top datum -- flat to any tolerance that
    # matters, and flickering just as hard as an exact coincidence, but a rounded
    # bucket key drops it and its partner either side of a boundary and they are
    # never compared. Anything closer than CLASH_GAP is one plane for this
    # purpose; a rung is wider than CLASH_GAP, so faces already parked on
    # separate rungs are never re-grouped and cannot cascade deeper.
    CLASH_GAP = 0.6 * DATUM_EPS
    groups = []
    for (ax, sgn), items in facing.items():
        items.sort(key=lambda t: t[0])
        run = [items[0]]
        for val, f in items[1:]:
            if val - run[-1][0] > CLASH_GAP:
                groups.append((ax, sgn, [g for _, g in run]))
                run = []
            run.append((val, f))
        groups.append((ax, sgn, [g for _, g in run]))

    moved = 0
    done = set()
    for ax, sgn, fs in groups:
        if len(fs) < 2:
            continue
        surfs = _surfaces(fs)
        if len(surfs) < 2:
            continue
        adj = _overlap_graph(surfs, fs, ax)
        area = [sum(fs[p].calc_area() for p in s) for s in surfs]
        rung = {}
        for i in sorted(range(len(surfs)), key=lambda j: -area[j]):
            if not adj[i]:
                continue        # nothing covers it: it keeps the plane
            taken = {rung[j] for j in adj[i] if j in rung}
            r = 0
            while r in taken:
                r += 1
            rung[i] = r
            if r == 0:
                continue
            # ★ keyed by AXIS as well as vert: the block over a post caps the top
            # datum AND the module end, so its corner verts have to be free to
            # recede once in z and once in x. Keyed by vert alone, whichever plane
            # ran first claimed them and the other clash survived the pass.
            vs = {v.index: v for p in surfs[i] for v in fs[p].verts}
            if any((ax, k) in done for k in vs):
                continue
            for k, v in vs.items():
                v.co[ax] -= sgn * r * DATUM_EPS
                done.add((ax, k))
            moved += 1
    return moved


def lift_insert(mb):
    """Take an insert off the planes it shares with its host wall.

    See INSERT_EPS. The wall-face rungs get PROUDER (applied joinery stands over
    the wall's own), the floor datum gets vacated upwards (only the wall's
    structural bottom belongs on it)."""
    bm = mb.bm
    bm.verts.index_update()
    moved = 0
    # ★ one `done` set per plane: adjacent coplanar faces (the welded shell and
    # every plank run are full of them) share verts, and a vert nudged once per
    # face it belongs to would travel two or three rungs instead of one
    for p in (0.0, P1, P2, P3):
        for sgn in (-1.0, 1.0):
            val = sgn * (HT + p)
            done = set()
            for f in _plane_group(bm, 1, val, sgn):
                for v in f.verts:
                    if v.index in done:
                        continue
                    v.co[1] += sgn * INSERT_EPS
                    done.add(v.index)
                moved += 1
    done = set()
    for f in _plane_group(bm, 2, 0.0, -1.0):
        for v in f.verts:
            if v.index in done:
                continue
            v.co[2] += INSERT_EPS
            done.add(v.index)
        moved += 1
    return moved


def fix_tilted_uvs(ob):
    """Re-project faces that are NOT axis-aligned into their own plane.

    The kit's planar projection picks a world axis per face, which is what makes
    modules tile -- but on a tilted or curved face it foreshortens one direction
    only. Arch soffits, voussoir flanks and the barricade's diagonal boards all
    read as stretched without this. Axis-aligned faces are left strictly alone so
    the tiling guarantee is untouched."""
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


def canonicalise(mb):
    """Reorder slots into CANON order, remapping faces, so slot indices mean the
    same thing on every piece Unity imports."""
    rank = {n: i for i, n in enumerate(CANON)}
    order = sorted(range(len(mb.mats)), key=lambda i: rank.get(mb.mats[i].name, 999))
    remap = {old: new for new, old in enumerate(order)}
    for f in mb.bm.faces:
        f.material_index = remap[f.material_index]
    mb.mats = [mb.mats[i] for i in order]


def out(mb, coll, loc, bevel=BEVEL_W, segments=BEVEL_SEG, seam=None,
        insert=False, defer_top=False):
    """Finish with LOCAL uvs (origin 0,0,0) then move the object into place --
    keeping the projection local is what makes instances tile in Unity.

    ★ EVERY piece is weight-limited, even the ones with no module seams (they
    just get an empty exclusion list). Leaving those on the modifier's default
    angle limit meant the inserts rounded at 40 degrees and the walls at 38, so
    a door frame and the wall around it carried subtly different edge radii."""
    # ★ Every pass runs on the bmesh BEFORE finish(), so the recession is in the
    # mesh by the time mark_bevel_weights() measures edges against the datums --
    # which is the whole reason SEAM_BAND is a band. See DATUM_EPS.
    # ★ ORDER MATTERS: the cross-object passes move whole planes bodily and can
    # stack two members on the plane they land on (both door-frame architraves
    # arrive on z = INSERT_EPS together), so deconflict() runs LAST and cleans up
    # after them.
    # ★★ NORMALS FIRST. sl() and extrude_poly() do not agree on winding -- half
    # the faces on a corner's top datum come out of the builders pointing DOWN --
    # and finish() only fixes that later, with recalc_face_normals(). A pass that
    # reads f.normal before this line splits one plane into two opposed groups,
    # recedes half of them the wrong way (UP, into the open) and leaves the other
    # half sharing the datum. That is exactly what kept both corners flickering
    # after the first three attempts. Idempotent with finish(), so the winding
    # Unity finally imports is unchanged.
    bmesh.ops.recalc_face_normals(mb.bm, faces=mb.bm.faces[:])
    if insert:
        lift_insert(mb)
    if defer_top:
        # ★ A Pillar is DROPPED ON a finished run: its block and the wall's beam
        # cap both crown z = H, 0.42 m2 of it coplanar, and neither mesh can see
        # the other to arbitrate. An applied column defers to the wall it dresses,
        # so the Pillar leaves the top datum to the beam cap it lands beside.
        # ★★ TWO rungs, not one. A wall's top datum is already occupied twice over
        # -- the beam cap owns rung 0 and the shell behind it takes rung 1 -- and a
        # Pillar's block is wider than both, so it overlaps both. Deferring by one
        # rung just swaps which of them it flickers against (it landed exactly on
        # the shell at H - 1 rung). Wall_Plain, the piece these are made to dress,
        # carries no end block of its own, so rung 2 is free at the joint.
        mb.bm.verts.index_update()
        done = set()
        for f in _plane_group(mb.bm, 2, H, 1.0):
            for v in f.verts:
                if v.index in done:
                    continue
                v.co[2] -= 2.0 * DATUM_EPS
                done.add(v.index)
    deconflict(mb)
    canonicalise(mb)
    ob = mb.finish(coll, origin=(0, 0, 0), bevel=bevel, uv_scale=1.0)
    ob.data.name = ob.name          # the mesh name is what Unity shows
    fix_tilted_uvs(ob)
    for p in ob.data.polygons:
        p.use_smooth = False
    ob.location = Vector(loc)
    md = ob.modifiers.get("Bevel")
    if md:
        md.segments = segments
        md.use_clamp_overlap = True
        md.harden_normals = False
        md.miter_outer = "MITER_ARC"
        mark_bevel_weights(ob, seam or [], BEVEL_ANG)
        md.limit_method = "WEIGHT"
    return ob


# ------------------------------------------------------------------ shell --
# An opening is a dict: kind 'arch' (rect + semicircular head), 'rect',
# 'circle' or 'jag' (a ragged polygon). bb() is its bounding box in x/z; the
# wall is emitted as the rectangle decomposition around those boxes, then each
# opening fills back whatever solid wall its own bounding box still contains.

def op_arch(hw, z0, zs, r, cx=0.0):
    # zs = springline, z1 = the very top. Both are always present on every
    # opening dict so a frame builder never has to ask which kind it got.
    # bb top is the crown FLAT (one chord below z1) -- see ARC_S: the cut stops
    # short of tangency so the bevel clamp never sees a knife wedge. z1 stays
    # the true head height, which is what the insert builders shape against.
    return dict(kind="arch", cx=cx, hw=hw, z0=z0, zs=zs, r=r, z1=zs + r,
                bb=(cx - hw, cx + hw, z0, zs + r * math.cos(ARC_S)))


def op_rect(hw, z0, z1, cx=0.0):
    return dict(kind="rect", cx=cx, hw=hw, z0=z0, z1=z1, zs=z1, r=0.0,
                bb=(cx - hw, cx + hw, z0, z1))


def op_circle(cz, r, cx=0.0):
    # bb is the trimmed square: the circle runs flat over its last TWO chords
    # at all four compass points (see ARC_S), so no cut is tangent to a line
    return dict(kind="circle", cx=cx, cz=cz, r=r,
                bb=(cx - r * math.cos(2 * ARC_S), cx + r * math.cos(2 * ARC_S),
                    cz - r * math.cos(2 * ARC_S), cz + r * math.cos(2 * ARC_S)))


def spec(o, cx=0.0):
    """Build the opening dict for one of the OP_* constants."""
    if "cz" in o:
        return op_circle(o["cz"], o["r"], cx)
    if o["r"] > 0.0:
        return op_arch(o["hw"], o["z0"], o["zs"], o["r"], cx)
    return op_rect(o["hw"], o["z0"], o["zs"], cx)


ARC_N = 20
# ★★ AN ARC MUST NEVER RUN TANGENT INTO A STRAIGHT CUT LINE. The half-arc is
# ARC_N/2 chords; when the last chord landed tangent on the opening's bounding
# line it left a knife wedge only r*(1-cos 9°) deep -- 9..15 mm across the kit
# -- and the Bevel modifier's clamp_overlap is GLOBAL: Blender computes ONE
# safe offset for the whole mesh, so that single wedge clamped the chamfer of
# the ENTIRE piece. Measured strip widths: Wall_Door/Wall_Window 0.0066,
# Wall_Arch 0.0103, Wall_Door_Double 0.0113, Wall_Window_Round 0.0058, against
# 0.0184 kit-wide -- every stone accent on those five walls read sharper than
# the same member one module over. An arch has THREE tangencies (crown vs the
# bb top line, and BOTH springs vs the jamb: hw == r on every arch opening, so
# the circle leaves the jamb vertically); a circle has four, at the compass
# points. The cure is to stop the arc short of tangency and run straight:
#   crown    1 chord  -- flat on the bb line; allowed offset ~ r*sin 9°*sin 13.5°
#            clears at every kit radius, and one chord is all the ring can
#            hide on the big arches (2 chords dip r*(1-cos 18°) = 54 mm at
#            r=1.1, past the ring's 50 mm cover).
#   spring   2 chords -- one straight run leaving the jamb at 9°; a 1-chord
#            trim just recreates the same 4.5° wedge one step up.
#   compass  2 chords -- the 1-chord corner bound at chord*sin 13.5° = 0.0227
#            on the 0.62 oculus, still under the 0.024 offset (measured
#            0.0175 strips); two chords bind at 0.037 with the ring covering
#            the 30 mm dip.
# The replaced runs are the same facet scale the 9° arc already has, and every
# one hides behind that opening's voussoir ring. audit_chamfer() proves it.
ARC_S = (math.pi / 2.0) / (ARC_N // 2)     # one arc chord, 9 degrees


def _filler(mb, o, y0, y1, mat):
    """The solid wall still inside an opening's bounding box.

    ★ Arcs stop one chord short of the apex / compass tangent points (ARC_S,
    see above): the trimmed bb line IS the crown flat, so the filler tops land
    exactly on grid lines and weld into the cells above at full height."""
    k = o["kind"]
    if k == "arch":
        cx, r, zs = o["cx"], o["r"], o["zs"]
        top = o["bb"][3]               # crown flat: zs + r*cos(ARC_S)
        n2 = ARC_N // 2
        # two halves, so the polygon never pinches to a point at the apex;
        # the arc runs 162°..99° / 81°..18° -- ONE chord short of the crown
        # line, TWO short of each jamb, closed with the straight spring chord
        left = [(cx - r, zs)] + arc_pts(cx, zs, r, math.pi - 2 * ARC_S,
                                        math.pi / 2 + ARC_S, n2 - 3) \
            + [(cx - r, top)]
        right = arc_pts(cx, zs, r, math.pi / 2 - ARC_S, 2 * ARC_S, n2 - 3) \
            + [(cx + r, zs), (cx + r, top)]
        poly(mb, _dedupe(left), y0, y1, mat)
        poly(mb, _dedupe(right), y0, y1, mat)
    elif k == "circle":
        cx, cz, r = o["cx"], o["cz"], o["r"]
        rf = r * math.cos(2 * ARC_S)   # compass flats: the trimmed bb square
        for q in range(4):
            a0 = q * math.pi / 2
            a1 = a0 + math.pi / 2
            corner = (cx + rf * math.cos(a0 + math.pi / 4) * math.sqrt(2),
                      cz + rf * math.sin(a0 + math.pi / 4) * math.sqrt(2))
            pts = arc_pts(cx, cz, r, a0 + 2 * ARC_S, a1 - 2 * ARC_S,
                          ARC_N // 2 - 4) + [corner]
            poly(mb, _dedupe(pts), y0, y1, mat)


def _dedupe(pts):
    out_ = []
    for p in pts:
        if not out_ or abs(p[0] - out_[-1][0]) > 1e-5 or abs(p[1] - out_[-1][1]) > 1e-5:
            out_.append(p)
    if len(out_) > 2 and abs(out_[0][0] - out_[-1][0]) < 1e-5 \
            and abs(out_[0][1] - out_[-1][1]) < 1e-5:
        out_.pop()
    return out_


def weld(mb, before_v):
    """Weld a decomposition into ONE solid and drop its interior partitions.

    ★ The shell is emitted as a grid of boxes around the openings. Left as
    separate solids, each box's front face carries its own 90-degree edge at the
    joint; the bevel chamfers BOTH of them and every internal cut shows up as a
    V-groove crease across the wall face -- vertical beside an opening,
    horizontal at its head and sill. That is why walls WITH openings had creases
    and Wall_Straight (a single box) did not.

    Welding the coincident verts and deleting the back-to-back interior faces
    leaves the front faces as coplanar neighbours, which the weight pass then
    correctly leaves flat. It also strips the hidden internal walls, which Unity
    would otherwise have been rendering."""
    bm = mb.bm
    bm.verts.ensure_lookup_table()
    verts = [v for v in bm.verts if v not in before_v]
    if not verts:
        return
    bmesh.ops.remove_doubles(bm, verts=verts, dist=1e-5)
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    bm.faces.ensure_lookup_table()
    seen, dup = {}, set()
    for f in bm.faces:
        key = frozenset(v.index for v in f.verts)
        if len(key) != len(f.verts):
            continue
        if key in seen:
            dup.add(f)
            dup.add(seen[key])
        else:
            seen[key] = f
    if dup:
        bmesh.ops.delete(bm, geom=list(dup), context="FACES")


def shell(mb, hw, opens, h=H, y0=None, y1=None, m_a=None, m_b=None, m_e=None):
    """Wall slab minus its openings, with the two faces on their own slots.

    Emitted as one solid with a material pass by face normal rather than as two
    leaves: the module-boundary edges are excluded from bevelling anyway, so the
    hairline that forces the two-leaf trick elsewhere cannot appear here, and one
    solid keeps the opening reveals as real stone rather than as a seam."""
    y0 = -HT if y0 is None else y0
    y1 = HT if y1 is None else y1
    m_a = M(PAPER) if m_a is None else m_a
    m_b = M(PAPER_B) if m_b is None else m_b
    m_e = M(STONE) if m_e is None else m_e
    before = set(mb.bm.faces)
    before_v = set(mb.bm.verts)
    # ★ A full GRID, cut at every feature of every opening -- not vertical
    # strips each cut only where its own opening needs it. `weld` can only drop
    # an interior partition when the two faces are exact twins, and a strip
    # decomposition abuts a full-height side face against two short ones, which
    # match nothing. Those survivors are what put a 90-degree edge on the wall
    # face for the bevel to chamfer, i.e. the creases.
    xs, zs = {-hw, hw}, {0.0, h}
    for o in opens:
        xs |= {o["bb"][0], o["bb"][1], o["cx"]}
        zs |= {o["bb"][2], o["bb"][3]}
        if o["kind"] == "arch":
            zs.add(o["zs"])          # springline: where the filler's edge lands
            xf = o["r"] * math.sin(ARC_S)
            xs |= {o["cx"] - xf, o["cx"] + xf}   # crown flat ends: the cells
            # over the flat must split there so filler tops meet exact twins
        elif o["kind"] == "circle":
            zs.add(o["cz"])          # ditto for the quarter fillers
            xf = o["r"] * math.sin(2 * ARC_S)
            xs |= {o["cx"] - xf, o["cx"] + xf}   # top/bottom compass flats
            zs |= {o["cz"] - xf, o["cz"] + xf}   # left/right compass flats
    xs, zs = sorted(xs), sorted(zs)
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            xa, xb, za, zb = xs[i], xs[i + 1], zs[j], zs[j + 1]
            if xb - xa < 1e-6 or zb - za < 1e-6:
                continue
            xm, zm = (xa + xb) / 2.0, (za + zb) / 2.0
            if any(o["bb"][0] - 1e-6 < xm < o["bb"][1] + 1e-6
                   and o["bb"][2] - 1e-6 < zm < o["bb"][3] + 1e-6 for o in opens):
                continue
            sl(mb, xa, xb, y0, y1, za, zb, m_a)
    for o in opens:
        _filler(mb, o, y0, y1, m_a)
    weld(mb, before_v)
    ia, ib, ie = mb._mi(m_a), mb._mi(m_b), mb._mi(m_e)
    for f in mb.bm.faces:
        if f in before:
            continue
        k = face_key(f.normal)
        f.material_index = ia if k == "-y" else ib if k == "+y" else ie


# ------------------------------------------------------------- wall dress --
def quoin_col(mb, x0, x1, z0, z1, y0=None, y1=None, p=None, mat=None,
              bond="both"):
    """Stacked ashlar column -- the module-end posts, the free Pillar and the
    opening jambs, all from one function.

    ★ Every course has the SAME projection and the same extent at a module
    boundary; the long/short alternation is an inset on the FIELD side only,
    named by `bond` ('left' steps in at x0, 'right' at x1, 'both' for a
    free-standing column). Courses used to alternate a 0.035 inset on both
    sides, which at a module end put every other course exactly ON the boundary
    plane -- edges there are excluded from the bevel, so they came out sharp --
    and the rest 35 mm inside it, bevelled and rounded. One post, half sharp and
    half rounded, and a notch at every short course when two modules butted.

    Because the inset is field-side only, a butted pair of module-end posts is
    geometrically IDENTICAL to one free-standing Pillar: both give 0.68 m wide
    long courses stepping in to 0.50 m."""
    y0 = -HT if y0 is None else y0
    y1 = HT if y1 is None else y1
    p = PIL_P if p is None else p
    mat = M(STONE) if mat is None else mat
    n = max(1, int(round((z1 - z0) / COURSE)))
    ch = (z1 - z0) / n
    # ★ Never let the step eat the column. On a narrow column QUOIN_STEP took
    # the short courses to zero or negative width, sl() dropped them, and what
    # was meant to be a jamb came out as a row of disconnected blocks floating
    # beside the opening. Clamp the step so a short course keeps real width.
    sides = (1 if bond in ("left", "both") else 0) \
        + (1 if bond in ("right", "both") else 0)
    step = QUOIN_STEP if not sides else \
        min(QUOIN_STEP, max(0.0, (x1 - x0 - 2.0 * PIL_W / 3.0) / sides))
    for i in range(n):
        za, zb = z0 + i * ch + GAP / 2, z0 + (i + 1) * ch - GAP / 2
        s = step if i % 2 else 0.0
        a = x0 + (s if bond in ("left", "both") else 0.0)
        b = x1 - (s if bond in ("right", "both") else 0.0)
        sl(mb, a, b, y0 - p, y1 + p, za, zb, mat)


def quoin_corner(mb, z0, z1, p=None, mat=None, lng=0.58, sht=0.44):
    """Interlocking quoin wrapping the OUTER corner at (-HT, -HT).

    ONE L-shaped solid per course, alternating which face carries the long arm.
    Two separate arm boxes read as loose bricks: the chamfer grooves the joint
    between them and the corner return looks glued on rather than bonded."""
    p = PIL_P if p is None else p
    mat = M(STONE) if mat is None else mat
    n = max(1, int(round((z1 - z0) / COURSE)))
    ch = (z1 - z0) / n
    o, i_ = -HT - p, -HT
    for i in range(n):
        za, zb = z0 + i * ch + GAP / 2, z0 + (i + 1) * ch - GAP / 2
        la, lb = (lng, sht) if i % 2 == 0 else (sht, lng)
        lpoly(mb, [(o, o), (i_ + la, o), (i_ + la, i_), (i_, i_),
                   (i_, i_ + lb), (o, i_ + lb)], za, zb, mat)


def quoin_inner(mb, z0, z1, p=None, mat=None, lng=0.58, sht=0.44):
    """Quoin wrapping the REFLEX corner at (+HT, +HT) -- the same L-solid course
    as `quoin_corner`, mirrored into the notch.

    ★ It used to be a solid square pier filling the whole notch, standing 0.34 m
    off BOTH faces of a wall only 0.30 m thick. A block deeper than the wall it
    is bonded into has nothing behind it at the corner, so it read as driven
    through the wall and out the back. A quoin hugs its two faces; it never
    fills the corner. Sharing `quoin_corner`'s arm lengths, projection, course
    and alternation also means both corner pieces now carry the same masonry."""
    p = PIL_P if p is None else p
    mat = M(STONE) if mat is None else mat
    n = max(1, int(round((z1 - z0) / COURSE)))
    ch = (z1 - z0) / n
    o, i_ = HT + p, HT
    for i in range(n):
        za, zb = z0 + i * ch + GAP / 2, z0 + (i + 1) * ch - GAP / 2
        la, lb = (lng, sht) if i % 2 == 0 else (sht, lng)
        lpoly(mb, [(i_, i_), (i_ + la, i_), (i_ + la, o), (o, o),
                   (o, i_ + lb), (i_, i_ + lb)], za, zb, mat)


def ground(mb, a0, a1, sgn, mat=None, axis="x"):
    """The board GROUND: a continuous DARK wood panel behind a plank run.

    ★ Dark on purpose (WOODD, the skirting's own timber). In the boards' own
    colour the groove between two panels read as a crack in one flat surface,
    because the only thing separating the boards was a chamfer; against the dark
    ground each board reads as a raised panel with a shadowed gap beside it,
    which is what makes a dado look like joinery rather than like cladding.

    ★ A plank run leaves PLANK_G between boards and the chamfer opens that to
    ~70 mm, and behind it was the wall -- so every groove in the wainscot showed
    a stripe of purple damask, the length of the room. Boards are always fixed to
    a ground in real joinery for exactly this reason; there is no wallpaper
    behind a dado.
    ★ It stands GROUND_P proud (half a rung, so the boards keep a real shadow
    line) but is GROUND_T thick, reaching back INTO the wall -- a 30 mm slab
    would be under BEVEL_MIN and would clamp the chamfer of the whole piece. It
    laps GROUND_LAP into the skirting and the chair rail at both ends so it never
    shares a plane with either."""
    mat = M(WOODD) if mat is None else mat
    y0, y1 = sgn * (HT + GROUND_P), sgn * (HT + GROUND_P - GROUND_T)
    z0, z1 = SKIRT_Z - GROUND_LAP, WAIN_Z + GROUND_LAP
    if axis == "x":
        sl(mb, a0, a1, min(y0, y1), max(y0, y1), z0, z1, mat)
    else:
        sl(mb, min(y0, y1), max(y0, y1), a0, a1, z0, z1, mat)


def plank_run(mb, x0, x1, y0, y1, z0, z1, mat, pw=PLANK_W, gap=PLANK_G,
              axis="x", chamf=0.02):
    """Boards with a groove between them, spaced along `axis`.

    'x' and 'y' both give VERTICAL boards -- they differ only in which wall the
    boards are spaced along. Spacing a corner's second wing along z instead
    turned its wainscot into horizontal lapping, which is a different piece of
    carpentry entirely."""
    a0, a1 = {"x": (x0, x1), "y": (y0, y1), "z": (z0, z1)}[axis]
    span = a1 - a0
    n = max(1, int(round(span / pw)))
    step = span / n
    for i in range(n):
        b0, b1 = a0 + i * step + gap / 2.0, a0 + (i + 1) * step - gap / 2.0
        if axis == "x":
            sl(mb, b0, b1, y0, y1, z0 + chamf, z1 - chamf, mat)
        elif axis == "y":
            sl(mb, x0, x1, b0, b1, z0 + chamf, z1 - chamf, mat)
        else:
            sl(mb, x0 + chamf, x1 - chamf, y0, y1, b0, b1, mat)


def corner_band(mb, p, z0, z1, mat, sgn=-1.0, inset=0.0):
    """Skirting or chair rail mitred round a corner as ONE L-shaped solid.

    `inset` pushes the band's INNER face back into the wall, which is how the
    ground behind the wainscot boards is made thick enough to chamfer while
    standing only GROUND_P proud."""
    if sgn < 0:
        o, i_ = -HT - p, -HT + inset
        pts = [(o, o), (CWING, o), (CWING, i_), (i_, i_), (i_, CWING), (o, CWING)]
    else:
        o, i_ = HT + p, HT - inset
        pts = [(i_, i_), (CWING, i_), (CWING, o), (o, o), (o, CWING), (i_, CWING)]
    lpoly(mb, pts, z0, z1, mat)


def corner_wainscot(mb, sgn=-1.0):
    """The full wainscot turning a corner: mitred skirting, boards on both
    wings, mitred chair rail.

    The bands run right THROUGH the corner and right under the quoin -- the
    quoin projects P3 and the bands P2, so the stone simply stands in front of
    the joinery the way it does on a real building. Stopping the bands short of
    the quoin instead left a slot at every short course, and stopping them at
    the corner left a slot down the corner itself."""
    mat, dark = M(WOOD), M(WOODD)
    corner_band(mb, SKIRT_P, 0.0, SKIRT_Z, dark, sgn)
    corner_band(mb, RAIL_P, WAIN_Z, RAIL_Z, mat, sgn)
    corner_band(mb, GROUND_P, SKIRT_Z - GROUND_LAP, WAIN_Z + GROUND_LAP, dark,
                sgn, inset=GROUND_T - GROUND_P)
    q0, q1 = sgn * HT, sgn * (HT + WAIN_P)
    lo, hi = min(q0, q1), max(q0, q1)
    # the X-wing boards start a board-depth early so they fill the corner cell;
    # the Y-wing boards then butt onto them
    if sgn < 0:
        plank_run(mb, -HT - WAIN_P, CWING, lo, hi, SKIRT_Z, WAIN_Z, mat, axis="x")
        plank_run(mb, lo, hi, -HT, CWING, SKIRT_Z, WAIN_Z, mat, axis="y")
    else:
        plank_run(mb, HT, CWING, lo, hi, SKIRT_Z, WAIN_Z, mat, axis="x")
        plank_run(mb, lo, hi, HT + WAIN_P, CWING, SKIRT_Z, WAIN_Z, mat, axis="y")


def beam_block(mb, x0, x1, mat=None, p=None, z0=BEAM_Z):
    """The heavy dark block that caps a post where it meets the head beam.

    Factored out so Wall_Straight's ends, the corner and the free-standing
    Pillar all emit the IDENTICAL block -- a pillar dropped into a Wall_Plain
    run has to be indistinguishable from the doubled post at a Wall_Straight
    joint, and that only holds if there is one definition of it.

    ★ `p` is the projection, because the interior family wants the block FLUSH
    with the column under it (PIL_P) rather than the extra 20 mm the masonry
    blocks stand proud. A block wider or prouder than its own post turns the top
    of the column into a step -- see `int_dress`.

    ★★ `z0` is how a FREE-STANDING column (Pillar, Pilaster) drops below the beam
    datum. On a wall the block and the head beam are one mesh and deconflict()
    arbitrates their shared underside; dropped onto a finished run they are two
    meshes and nothing can, so the block's soffit and the beam's soffit flicker
    against each other over the whole footprint of the column. A hairline lower
    and the applied column simply stands over the beam it dresses, which is the
    same rule lift_insert applies to a door frame."""
    p = BEAM_CAP_P + 0.02 if p is None else p
    # starts exactly AT the beam datum, so it sits on the post rather than
    # cutting 100 mm into its top course
    sl(mb, x0, x1, -HT - p, HT + p, z0, H,
       M(WOODD) if mat is None else mat)


def top_beam(mb, x0, x1, mat=None, ends=True, one_tier=False):
    """Wood head beam plus its cap, with a heavier block over each post.

    ★★★ `one_tier` drops the P3 cap, and the interior family needs it. A HAIRLINE
    CANNOT SURVIVE A CHAMFER: the cap ran the full module width at P3, the dark
    head block stood over it at P3 + INSERT_EPS, and 1.5 mm of relief is nothing
    against a 24 mm bevel -- the block's chamfer facet dives from 0.3315 to
    0.3075 and the cap at 0.3300 surfaces straight through it, so the light beam
    appeared as a wedge in the upper corners of every dark column. Adding relief
    instead would mean a 26 mm step where the head meets the shaft, which is the
    L this family already got rid of. Take the tier away and the head has the
    whole P3 - P2 = 50 mm to itself: flush with the shaft, nothing behind it, and
    the same answer for a free-standing Pilaster dropped on a Wall_Int_Plain,
    whose cap no wall-side trick could ever have reached."""
    mat = M(WOOD) if mat is None else mat
    if one_tier:
        sl(mb, x0, x1, -HT - BEAM_P, HT + BEAM_P, BEAM_Z, H, mat)
    else:
        sl(mb, x0, x1, -HT - BEAM_P, HT + BEAM_P, BEAM_Z, BEAM_CAP_Z, mat)
        sl(mb, x0, x1, -HT - BEAM_CAP_P, HT + BEAM_CAP_P, BEAM_CAP_Z, H, mat)
    if ends:
        for xs in (x0, x1 - BEAM_END):
            beam_block(mb, xs, xs + BEAM_END)


def wainscot(mb, segs, mat=None, dark=None):
    """Skirting, vertical planks and chair rail over the x-intervals `segs`."""
    mat = M(WOOD) if mat is None else mat
    dark = M(WOODD) if dark is None else dark
    for x0, x1 in segs:
        if x1 - x0 < 0.06:
            continue
        sl(mb, x0, x1, -HT - SKIRT_P, HT + SKIRT_P, 0.0, SKIRT_Z, dark)
        for sgn in (-1.0, 1.0):
            ya = sgn * HT
            yb = sgn * (HT + WAIN_P)
            ground(mb, x0, x1, sgn, dark)
            plank_run(mb, x0, x1, min(ya, yb), max(ya, yb), SKIRT_Z, WAIN_Z, mat)
        sl(mb, x0, x1, -HT - RAIL_P, HT + RAIL_P, WAIN_Z, RAIL_Z, mat)


def _in_open(o, x, z):
    k = o["kind"]
    if k == "arch":
        if o["bb"][0] <= x <= o["bb"][1]:
            if o["z0"] <= z <= o["zs"]:
                return True
            if z > o["zs"] and math.hypot(x - o["cx"], z - o["zs"]) <= o["r"]:
                return True
        return False
    if k == "rect":
        return o["bb"][0] <= x <= o["bb"][1] and o["z0"] <= z <= o["z1"]
    if k == "circle":
        return math.hypot(x - o["cx"], z - o["cz"]) <= o["r"]
    return False


def _rect_free(opens, x0, x1, z0, z1, pad=0.06):
    """True if no opening touches this block, sampled rather than solved: the
    ashlar only has to stop short of a hole, and the voussoir ring covers the
    last few centimetres either way."""
    for o in opens:
        for x in (x0 - pad, (x0 + x1) / 2.0, x1 + pad):
            for z in (z0 - pad, (z0 + z1) / 2.0, z1 + pad):
                if _in_open(o, x, z):
                    return False
    return True


def ashlar(mb, x0, x1, z0, z1, opens=(), mat=None, course=COURSE, blk=BLOCK,
           gap=GAP, proj=P1, faces=(-1.0, 1.0), jitter=0.0, seed=1):
    """Running-bond stone courses laid on the wall faces as REAL blocks.

    Modelled, not textured: the concept sheet's stone reads as chunky carved
    masonry, and at 4 m the shadow under each course is doing all of that work.
    A texture flattens the moment a light moves."""
    mat = M(STONE) if mat is None else mat
    n = max(1, int(round((z1 - z0) / course)))
    ch = (z1 - z0) / n
    s = seed
    for i in range(n):
        za, zb = z0 + i * ch, z0 + (i + 1) * ch
        x = x0 - (blk * 0.5 if i % 2 else 0.0)
        while x < x1 - 0.03:
            s = (s * 1103515245 + 12345) & 0x7FFFFFFF
            wid = blk * (1.0 - jitter + 2.0 * jitter * (s % 1000) / 1000.0)
            a, b = max(x0, x), min(x1, x + wid)
            if b - a > 0.15 and _rect_free(opens, a, b, za, zb):
                for sgn in faces:
                    ya, yb = sgn * HT, sgn * (HT + proj)
                    sl(mb, a + gap / 2, b - gap / 2, min(ya, yb), max(ya, yb),
                       za + gap / 2, zb - gap / 2, mat)
            x += wid


def stone_base(mb, segs, opens=(), mat=None):
    for x0, x1 in segs:
        if x1 - x0 < 0.06:
            continue
        ashlar(mb, x0, x1, 0.0, BASE_Z, opens, mat=mat, course=BASE_Z,
               blk=BLOCK * 0.8, proj=BASE_P, seed=7)


def spans(hw, opens, z0, z1):
    """x-intervals of a horizontal band left after the openings cut it."""
    blk = sorted((o["bb"][0], o["bb"][1]) for o in opens
                 if not (z1 <= o["bb"][2] + 1e-6 or z0 >= o["bb"][3] - 1e-6))
    res, cur = [], -hw
    for a, b in blk:
        if a > cur + 1e-6:
            res.append((cur, a))
        cur = max(cur, b)
    if cur < hw - 1e-6:
        res.append((cur, hw))
    return res


def dress(mb, hw, opens, stone=False, posts=True):
    """The shared wall vocabulary: posts, beam, and either wainscot or plinth.

    `stone` also lays ashlar over the whole field, which is what separates the
    sheet's stone family (arch, broken) from its papered family. `posts=False`
    drops the end quoins AND their beam blocks and runs the field, wainscot and
    beam edge to edge -- that is Wall_Plain, the piece you butt in runs when you
    want the stone pillars spaced further apart than every 4 m."""
    # ★ The field trim runs the FULL module width and the posts ride over it,
    # so Wall_Straight and (Wall_Plain + Pillar) emit identical wainscot,
    # plinth and ashlar. Clamping the trim to stop at the posts made the two
    # ways of building a wall differ, and left a gap wherever a quoin course
    # stepped back off the clamp line.
    top_beam(mb, -hw, hw, ends=posts)
    band = spans(hw, opens, 0.0, RAIL_Z)
    if stone:
        stone_base(mb, band, opens)
        ashlar(mb, -hw, hw, BASE_Z, BEAM_Z, opens, jitter=0.16, seed=3)
    else:
        wainscot(mb, band)
    if posts:
        quoin_col(mb, -hw, -hw + PIL_W, 0.0, BEAM_Z, bond="right")
        quoin_col(mb, hw - PIL_W, hw, 0.0, BEAM_Z, bond="left")


def spall_patch(mb, x0, x1, z0, z1, seed=17, mat=None, y=None):
    """Plaster torn off to the masonry underneath, on the -Y face.

    Two things make this read: the patch OUTLINE is ragged course by course (a
    neat rectangle of blocks looks like a tiled panel someone hung on the wall),
    and the exposed stone sits barely 12 mm proud, so the eye takes it as a hole
    in the paper rather than as something stuck on top."""
    mat = M(STONE) if mat is None else mat
    y = -HT if y is None else y
    # ★ The exposed stone is the wall's OWN masonry, so it runs on the SAME
    # course height and the SAME block length as `ashlar()`, half-lapped course
    # to course. Two earlier versions failed for the same underlying reason --
    # they invented a bond for the patch. Small regular blocks in a dark border
    # read as a ladder; big blocks with a heavy per-course jitter read as four
    # floating tiles in a cross-shaped frame. Bond it to the wall and it reads
    # as masonry the moment the plaster comes off.
    n = max(3, int(round((z1 - z0) / COURSE)))
    ch = (z1 - z0) / n
    s = seed
    for i in range(n):
        za, zb = z0 + i * ch, z0 + (i + 1) * ch
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        # gentle end jitter only: the courses have to stay recognisably stacked
        a = x0 + 0.15 * ((s >> 5) % 100) / 100.0
        b = x1 - 0.15 * ((s >> 11) % 100) / 100.0
        if i == 0:
            a, b = a + 0.20, b - 0.12
        if i == n - 1:
            a, b = a + 0.12, b - 0.22
        # one cavity slab per course, CONTIGUOUS in z so the silhouette is a
        # staircase rather than a stack of separated rectangles
        sl(mb, a, b, y - 0.004, y + 0.09, za, zb + 0.002, M(IRON))
        x = a - (BLOCK / 2.0 if i % 2 else 0.0)
        while x < b - 0.05:
            s = (s * 1103515245 + 12345) & 0x7FFFFFFF
            wid = BLOCK * (0.80 + 0.34 * ((s >> 7) % 100) / 100.0)
            ba, bb = max(a, x), min(b, x + wid)
            if bb - ba > 0.13:
                sl(mb, ba + GAP / 2, bb - GAP / 2, y - 0.014, y + 0.07,
                   za + GAP / 2, zb - GAP / 2, mat)
            x += wid
    # the crack running on out of the patch, rooted in the top course
    cz, cx = z1 - 0.04, (x0 + x1) / 2.0
    for i in range(3):
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF
        dx = 0.18 * (((s >> 6) % 100) / 50.0 - 1.0)
        sl(mb, min(cx, cx + dx) - BEVEL_MIN / 2, max(cx, cx + dx) + BEVEL_MIN / 2,
           y - 0.030, y + 0.032, cz, cz + 0.22, M(IRON))
        cx += dx
        cz += 0.20


def stone_shelf(mb, x0, x1, top, p=P3, h=SILL_H, mat=None):
    """★ THE projecting stone block of the kit -- window sill, flat lintel, door
    plinth are all this one section: SILL_H tall, standing P3 proud.

    Every one of these used to be written out by hand with its own numbers, and
    they drifted into SIX different sections for the same member: sills 0.12 and
    0.14 tall, a lintel at 0.16 standing only P1 proud, door plinths at 0.22 /
    0.24 / 0.26 / 0.30 on P2 and P3. That is why Wall_Window and
    Wall_Window_Small did not match -- same nominal chamfer, different blocks
    under it."""
    mat = M(STONE) if mat is None else mat
    sl(mb, x0, x1, -HT - p, HT + p, top - h, top, mat)


def opening_sill(mb, o, top=None):
    """Sill under an opening, or -- with `top` given -- the lintel over one."""
    w = o["hw"] + CASE + SILL_LAP
    stone_shelf(mb, -w, w, o["z0"] if top is None else top)


def opening_plinths(mb, o, mat=None):
    """Blocks at the feet of an opening's jambs: the concept sheet's square
    stones at the bottom of a door surround.

    Deliberately NOT carried across the opening. The door frames used to lay a
    full-width block there, which is a 0.22 m threshold you walk into."""
    for sgn in (-1.0, 1.0):
        a = sgn * (o["hw"] - INSERT_EPS)    # laps the reveal, as arch_frame does
        b = sgn * (o["hw"] + CASE + SILL_LAP)
        stone_shelf(mb, min(a, b), max(a, b), SILL_H, mat=mat)


def voussoirs(mb, cx, cz, r_in, r_out, y0, y1, mat=None, n=None, gap=0.015,
              a0=0.0, a1=math.pi):
    """Arch ring of real blocks. Its inner face sits INSIDE the wall's own hole,
    so the ring -- not the cut -- defines the opening, and any tolerance in the
    cut disappears behind it.

    ★ The stone COUNT is derived from arc length, never passed in: every
    voussoir in the kit is VOUSS long, so a stone in the little oculus is the
    same size as one over the double door. Hand-picked counts were what made
    the arches look like they came from different sets."""
    mat = M(STONE) if mat is None else mat
    if n is None:
        n = max(5, int(round(abs(a1 - a0) * (r_in + r_out) / 2.0 / VOUSS)))
    # ★ The alternating outer radius is masonry variety on an ARCH, where you
    # read the curve against the wall above it. On a CLOSED ring it turns the
    # silhouette into a cog -- the single loudest reason the oculus read as
    # square rather than round -- so a full circle gets a true circular back.
    closed = abs(a1 - a0) > 1.9 * math.pi
    for i in range(n):
        b0 = a0 + (a1 - a0) * i / n + gap
        b1 = a0 + (a1 - a0) * (i + 1) / n - gap
        r2 = r_out + (0.0 if closed else (0.05 if i % 2 else 0.0))
        pts = [(cx + r_in * math.cos(b0), cz + r_in * math.sin(b0)),
               (cx + r_in * math.cos(b1), cz + r_in * math.sin(b1)),
               (cx + r2 * math.cos(b1), cz + r2 * math.sin(b1)),
               (cx + r2 * math.cos(b0), cz + r2 * math.sin(b0))]
        poly(mb, pts, y0, y1, mat)


# ★ There is deliberately NO jamb piece on the host walls. A 0.12-0.16 m stone
# jamb standing proud of the reveal reads as a strip of blocks stuck on beside
# the opening rather than as masonry, and the insert that drops into the hole
# brings its own architrave anyway -- so the jamb was always doubling up on it.
# The wall now gives an opening a stone reveal and a voussoir ring, nothing else.


# ------------------------------------------------------------ wall pieces --
def w_straight(mb):
    shell(mb, HW, [])
    dress(mb, HW, [])


def w_half(mb):
    shell(mb, W2 / 2.0, [])
    dress(mb, W2 / 2.0, [])


def w_plain(mb):
    """4 m of wall with NO end quoins -- butt these in a run and drop `Pillar`
    wherever you actually want a stone column. The field, wainscot and beam all
    run edge to edge, and because the UV projection is local at 0.5 repeats/m
    over a whole-metre module, the damask continues across the butt joint
    instead of restarting."""
    shell(mb, HW, [])
    dress(mb, HW, [], posts=False)


def w_plain_half(mb):
    shell(mb, W2 / 2.0, [])
    dress(mb, W2 / 2.0, [], posts=False)


def w_pillar(mb):
    """The stone column on its own, 0.68 m wide -- exactly what two butted
    Wall_Straight ends make, so a Wall_Plain run dressed with these is
    indistinguishable from a Wall_Straight run. Pivot is the column centre;
    drop it on a wall JOINT (2 m from a wall's own pivot along the run)."""
    quoin_col(mb, -PIL_W, PIL_W, 0.0, BEAM_Z, bond="both")
    beam_block(mb, -BEAM_END, BEAM_END,   # = two module-end blocks butted
               z0=BEAM_Z - INSERT_EPS)    # ...standing over the run's own beam


def _corner_core(mb, outer_is_a, m_e=None):
    """The L slab shared by both corner pieces, with each face on the right slot.

    `outer_is_a` selects which side gets slot 0. On the outer corner the convex
    faces are the building's outside; on the inner corner the CONCAVE faces are
    (that is what a reflex corner of an L-shaped plan means), so the two pieces
    disagree about which side is which and a room still recolours consistently.

    `m_e` is the edge/reveal material -- stone on the exterior family, wood on the
    interior one, which is the only reason the interior pieces carry no stone
    slot at all."""
    ma, mb_, me = M(PAPER), M(PAPER_B), M(STONE) if m_e is None else m_e
    before = set(mb.bm.faces)
    # ONE L-solid. Two butted wing boxes leave a bevelled seam running the full
    # height of the corner -- clearly visible as a bright crack on the outside
    # and a groove on the inside.
    lpoly(mb, [(-HT, -HT), (CWING, -HT), (CWING, HT), (HT, HT),
               (HT, CWING), (-HT, CWING)], 0.0, H, ma)
    ia, ib, ie = mb._mi(ma), mb._mi(mb_), mb._mi(me)
    convex, concave = (ia, ib) if outer_is_a else (ib, ia)
    for f in mb.bm.faces:
        if f in before:
            continue
        k = face_key(f.normal)
        c = f.calc_center_median()
        if k in ("-y", "-x"):
            f.material_index = convex
        elif (k == "+y" and c.x < HT) or (k == "+x" and c.y < HT):
            f.material_index = ie          # the two stub ends inside the notch
        elif k in ("+y", "+x"):
            f.material_index = concave
        else:
            f.material_index = ie


def corner_solid(mb, p, z0, z1, mat):
    """The wall's own L footprint grown by `p` on BOTH faces, as ONE solid.

    ★★ This is the corner head beam, and it used to be four members: a mitred
    band down each face plus two boxes filling the core between them. Two
    problems, both of which land on the one surface you look straight down at.
    The boxes butt the bands on y = +/-HT with a 90-degree edge each side, so the
    chamfer cuts a V-groove along the whole top of the beam -- the same defect
    that made butted quoin boxes read as loose bricks. And `deconflict()` gives a
    datum plane to its LARGEST surface: split four ways, not one of the beam's
    top faces could beat the shell's 1.20 m2 L, so the STRUCTURE won z = H and the
    entire wood cap was pushed half a millimetre under it -- wallpaper crowning
    the corner, showing through those grooves. One solid is bigger than the shell,
    so it takes the datum the way a straight wall's cap box always did."""
    o, i_ = -HT - p, HT + p
    lpoly(mb, [(o, o), (CWING, o), (CWING, i_), (i_, i_), (i_, CWING), (o, CWING)],
          z0, z1, mat)


def _corner_beam(mb, block=True, one_tier=False):
    """Head beam mitred round both wings, with the standard block over the
    corner -- the same `beam_block` section a post gets.

    `block=False` for the interior corners, where the post carries its own L
    head through the beam instead (see `corner_post`)."""
    wood = M(WOOD)
    if one_tier:                 # see top_beam: no cap for the head to fight
        corner_solid(mb, BEAM_P, BEAM_Z, H, wood)
    else:
        corner_solid(mb, BEAM_P, BEAM_Z, BEAM_CAP_Z, wood)
        corner_solid(mb, BEAM_CAP_P, BEAM_CAP_Z, H, wood)
    if block:
        # symmetric about the corner, so it caps a quoin on either side and
        # matches the 0.70 m section of a straight wall's end block
        o = HT + BEAM_CAP_P + 0.02
        sl(mb, -o, o, -o, o, BEAM_Z, H, M(WOODD))


def w_corner(mb):
    """Outer (convex) corner. Wings run +X and +Y; the finished outside faces
    -X and -Y, which is the same exterior side a straight wall shows, so a run
    leaves the corner without a flip."""
    _corner_core(mb, outer_is_a=True)
    corner_wainscot(mb, -1.0)
    corner_wainscot(mb, 1.0)
    _corner_beam(mb)
    quoin_corner(mb, 0.0, BEAM_Z)


def w_corner_inside(mb):
    """Inner (concave) corner: the pilaster moves to the reflex side, and the
    wall carries the concept sheet's torn patch where the plaster came away."""
    _corner_core(mb, outer_is_a=False)
    corner_wainscot(mb, -1.0)
    corner_wainscot(mb, 1.0)
    _corner_beam(mb)
    quoin_inner(mb, 0.0, BEAM_Z)
    spall_patch(mb, 0.42, 1.92, 1.38, 2.82, seed=17)


# ★ The breach is cut COURSE BY COURSE on the ashlar bond, not as a smooth
# ragged curve. A curve has to be sampled into wall strips and comes out as a
# staircase of tiny steps that reads as a low-resolution mask; masonry actually
# fails by losing whole stones, so a block-aligned outline is both easier to
# build and the more convincing of the two. Rows are indices into the ashlar
# courses, x extents in module-local metres.
BREACH = [(1, -0.45, 0.35), (2, -0.95, 0.70), (3, -1.20, 0.95),
          (4, -1.10, 1.15), (5, -0.70, 0.80)]


def w_broken(mb):
    """Stone wall with the middle blown out, plus half-stones left hanging on
    the rim so the break has thickness instead of being a knife cut."""
    nc = max(1, int(round((BEAM_Z - BASE_Z) / 0.44)))
    ch = (BEAM_Z - BASE_Z) / nc
    opens = [op_rect((b - a) / 2.0, BASE_Z + i * ch, BASE_Z + (i + 1) * ch,
                     cx=(a + b) / 2.0) for i, a, b in BREACH]
    shell(mb, HW, opens, m_a=M(STONE), m_b=M(STONE), m_e=M(STONE))
    dress(mb, HW, opens, stone=True)
    # half-stones clinging to the rim: one at each end of every breached course,
    # sitting proud on both faces so the edge is chipped rather than sawn
    s = 29
    for i, a, b in BREACH:
        za = BASE_Z + i * ch
        for x, d in ((a, 1.0), (b, -1.0)):
            s = (s * 1103515245 + 12345) & 0x7FFFFFFF
            w = 0.16 + 0.20 * ((s >> 7) % 100) / 100.0
            h = ch * (0.34 + 0.30 * ((s >> 13) % 100) / 100.0)
            zz = za + ch * 0.10 + (ch - h) * ((s >> 17) % 100) / 100.0
            # straddle the rim -- rooted in the solid wall, hanging into the
            # breach. Placed wholly inside the void they read as floating debris
            x0c, x1c = x - d * w * 0.45, x + d * w * 0.55
            for sgn in (-1.0, 1.0):
                sl(mb, min(x0c, x1c), max(x0c, x1c),
                   sgn * HT, sgn * (HT + P1), zz, zz + h, M(STONE))
    for x, w in ((-1.34, 0.34), (-0.96, 0.26), (1.24, 0.30), (1.50, 0.22),
                 (-1.10, 0.20), (1.32, 0.18)):
        sl(mb, x - w / 2, x + w / 2, -HT - P3 - w, -HT - P3, 0.0, w,
           M(STONE))


def w_arch(mb):
    """Walk-through arch: 2.20 m clear, springing at 1.90, head at 3.00."""
    o = spec(OP_A)
    shell(mb, HW, [o], m_a=M(STONE), m_b=M(STONE), m_e=M(STONE))
    dress(mb, HW, [o], stone=True)
    yp = HT + P1
    voussoirs(mb, 0.0, o["zs"], o["hw"] - 0.05, o["hw"] + RING, -yp, yp)
    # Threshold apron -- the concept's steps, kept low enough to walk. Step
    # heights are derived from the chamfer floor, not from a fixed subtraction:
    # z0 minus a constant left the outer step 0.040 tall, under BEVEL_MIN, so it
    # was the one riser in the kit carrying a half-size chamfer.
    for i, top in enumerate((o["z0"], max(BEVEL_MIN + 0.008, o["z0"] * 0.55))):
        d = STEP_D * (2 - i)
        sl(mb, -o["hw"] - 0.30 + i * 0.16, o["hw"] + 0.30 - i * 0.16,
           -HT - d, -HT + 0.02, 0.0, top, M(STONE))


def w_door(mb):
    o = spec(OP_D)
    shell(mb, HW, [o])
    dress(mb, HW, [o])
    yp = HT + P1
    voussoirs(mb, 0.0, o["zs"], o["hw"] - 0.05, o["hw"] + RING, -yp, yp)


def w_door_double(mb):
    o = spec(OP_DD)
    shell(mb, HW, [o])
    dress(mb, HW, [o])
    yp = HT + P1
    voussoirs(mb, 0.0, o["zs"], o["hw"] - 0.05, o["hw"] + RING, -yp, yp)


def w_window(mb):
    o = spec(OP_W)
    shell(mb, HW, [o])
    dress(mb, HW, [o])
    yp = HT + P1
    voussoirs(mb, 0.0, o["zs"], o["hw"] - 0.05, o["hw"] + RING, -yp, yp)
    opening_sill(mb, o)


def w_window_small(mb):
    o = spec(OP_WS)
    shell(mb, HW, [o])
    dress(mb, HW, [o])
    yp = HT + P1
    # no side jambs here either -- see the note above `w_straight`
    opening_sill(mb, o, top=o["zs"] + SILL_H)      # flat head -> same block
    opening_sill(mb, o)


def w_window_round(mb):
    o = spec(OP_R)
    shell(mb, HW, [o])
    dress(mb, HW, [])
    yp = HT + P1
    voussoirs(mb, 0.0, o["cz"], o["r"] - 0.05, o["r"] + RING, -yp, yp,
              a0=0.0, a1=TAU)


WALLS = [("Wall_Straight", w_straight), ("Wall_Half", w_half),
         ("Wall_Plain", w_plain), ("Wall_Plain_Half", w_plain_half),
         ("Pillar", w_pillar),
         ("Wall_Corner", w_corner), ("Wall_Corner_Inside", w_corner_inside),
         ("Wall_Broken", w_broken), ("Wall_Arch", w_arch),
         ("Wall_Door", w_door), ("Wall_Door_Double", w_door_double),
         ("Wall_Window", w_window), ("Wall_Window_Small", w_window_small),
         ("Wall_Window_Round", w_window_round)]


# --------------------------------------------------- interior wall pieces --
# The same wall, the same lattice, the same inserts, with the exterior masonry
# replaced by joinery so BOTH faces read as the inside of a room -- see the
# "interior partition walls" block at the top of the file. One piece here for
# every piece above, so a plan drawn with one family can be rebuilt with the
# other without moving anything.

def pilaster(mb, x0, x1, lap=0.0):
    """Panelled wood pilaster: the interior set's answer to the quoin post.

    Dado-height plinth block, panelled shaft, capital under the head beam. The
    panel layout is DERIVED FROM THE WIDTH -- one bay per PIL_W of column, a
    stile on every division, and an internal division carrying two stiles' worth.
    At the kit's column width (2 x PIL_W) that gives two bays and a double centre
    stile, so the free-standing `Pilaster` and the column a wall carries at its
    end are the SAME piece of joinery, built by the same call.

    ★ The plinth runs up to the CHAIR RAIL, not to the skirting. That is how a
    real pilaster is built -- the plinth block is dado height -- and it also
    keeps the sunk panel clear of the rail, which stands on the same P2 rung; two
    members at one projection put coplanar faces in the same place, which is the
    z-fight the ladder exists to prevent. Stiles and rails never overlap either:
    the stiles own the full shaft height and the rails run BETWEEN them, so the
    pilaster's front face is one plane with nothing competing for it."""
    wood, dark = M(WOOD), M(WOODD)
    yo0, yo1 = -HT - PIL_P, HT + PIL_P
    z0, z1 = RAIL_Z + lap, BEAM_Z - PIL_CAP
    sl(mb, x0, x1, yo0, yo1, 0.0, RAIL_Z + lap, dark)       # plinth block
    sl(mb, x0, x1, yo0, yo1, z1, BEAM_Z, dark)              # capital
    n = max(1, int(round((x1 - x0) / PIL_W)))
    step = (x1 - x0) / n
    for i in range(n + 1):
        xc = x0 + i * step
        sl(mb, xc if i == 0 else xc - PAN_STILE,
           xc + PAN_STILE if i < n else xc, yo0, yo1, z0, z1, wood)
    for i in range(n):
        a, b = x0 + i * step + PAN_STILE, x0 + (i + 1) * step - PAN_STILE
        sl(mb, a, b, yo0, yo1, z0, z0 + PAN_RAIL, wood)     # bottom rail
        sl(mb, a, b, yo0, yo1, z1 - PAN_RAIL, z1, wood)     # top rail
        # sunk panel: ONE rung shallower, which is the whole point of the ladder
        sl(mb, a, b, -HT - P2, HT + P2, z0 + PAN_RAIL, z1 - PAN_RAIL, wood)


def corner_post(mb, sgn=-1.0, arm=PIL_ARM, p=None, head=True):
    """The pilaster turning a corner -- ONE L-solid per member, never two butted
    arms (see `lpoly`), in the same sections a straight pilaster uses so a corner
    and the wall beside it read as one run of joinery.

    `sgn` < 0 wraps the convex corner at (-HT,-HT), > 0 the reflex corner at
    (+HT,+HT), exactly as `quoin_corner` / `quoin_inner` do.

    ★ `head` carries the post's own L straight through the head beam to the top
    of the wall, in place of the square block `_corner_beam` drops on the masonry
    corners. A square block on an L post is the same mismatch a 0.88 m block on a
    0.68 m column was: the top stops lining up with the body it sits on."""
    p = PIL_P if p is None else p
    wood, dark = M(WOOD), M(WOODD)
    tiers = [(0.0, RAIL_Z, dark, p),
             (RAIL_Z, BEAM_Z - PIL_CAP, wood, p),
             (BEAM_Z - PIL_CAP, BEAM_Z, dark, p)]
    if head:
        # flush: the interior corner's beam is one tier at P2, so the head has
        # the full P3 - P2 to itself and nothing runs behind it (see top_beam)
        tiers.append((BEAM_Z, H, dark, p))
    for z0, z1, m, pp in tiers:
        if sgn < 0:
            o, i_ = -HT - pp, -HT
            pts = [(o, o), (i_ + arm, o), (i_ + arm, i_), (i_, i_),
                   (i_, i_ + arm), (o, i_ + arm)]
        else:
            o, i_ = HT + pp, HT
            pts = [(i_, i_), (i_ + arm, i_), (i_ + arm, o), (o, o),
                   (o, i_ + arm), (i_, i_ + arm)]
        lpoly(mb, pts, z0, z1, m)


def arc_band(mb, cx, cz, r_in, r_out, a0, a1, y0, y1, mat, n=None):
    """One continuous curved member: an annulus sector swept through the wall.

    Facet count comes off ARC_S, the kit's one arc chord, so this band and the
    opening it follows are cut at the same resolution. The sector's ends are
    RADIAL, so the arc meets them square -- no arc ever runs tangent into a
    straight cut here, which is the wedge that clamps the whole piece's chamfer."""
    if n is None:
        n = max(4, int(round(abs(a1 - a0) / ARC_S)))
    pts = arc_pts(cx, cz, r_in, a0, a1, n) + arc_pts(cx, cz, r_out, a1, a0, n)
    poly(mb, _dedupe(pts), y0, y1, mat)


def int_ring(mb, o, proj=INT_RING_P, mat=None):
    """The interior wall's own arch band -- continuous, not voussoirs (see
    INT_RING_P). Like the stone ring it laps 0.05 INTO the hole, so the band and
    not the cut defines the opening and any tolerance in the cut disappears
    behind it.

    A closed ring is FOUR butted quarters rather than one overlapping sweep: two
    arcs of the same radius sampled from different start angles do not share
    facet boundaries, and a pair of nearly-coincident curved surfaces is the
    worst flicker in the book. Butted, the quarter's end caps are coincident with
    OPPOSITE normals -- each buried in the other's solid -- and the chamfer at the
    four joints reads as what it is, a built-up circular frame."""
    mat = M(WOOD) if mat is None else mat
    y0, y1 = -HT - proj, HT + proj
    if o["kind"] == "arch":
        arc_band(mb, o["cx"], o["zs"], o["hw"] - 0.05, o["hw"] + RING,
                 0.0, math.pi, y0, y1, mat)
    elif o["kind"] == "circle":
        for q in range(4):
            arc_band(mb, o["cx"], o["cz"], o["r"] - 0.05, o["r"] + RING,
                     q * math.pi / 2.0, (q + 1) * math.pi / 2.0, y0, y1, mat)


def int_stool(mb, o, top=None):
    """Wood stool under an opening, or -- with `top` given -- the flat head over
    one. Deliberately the same section as the stone sill (`stone_shelf`): ONE
    member, ONE section, whichever family of walls it lands in."""
    w = o["hw"] + CASE + SILL_LAP
    stone_shelf(mb, -w, w, o["z0"] if top is None else top, mat=M(WOOD))


def int_dress(mb, hw, opens, posts=True):
    """The interior vocabulary: head beam, wainscot on BOTH faces, and ONE whole
    pilaster standing at the module's -X end.

    ★★★ THE COLUMN IS NEVER SPLIT ACROSS TWO MODULES. The stone family puts half
    a quoin at each end and lets a butted pair read as one 0.68 m post, which
    works for masonry: the blocks are modelled, they alternate, and stone has no
    direction. Do the same in WOOD and the joint is obvious -- the grain runs
    along the boards, each module projects its UVs in its OWN local space, and
    the two halves meet with the figure jumping across the middle stile. It reads
    as two things butted together, which is the one thing a modular kit must
    never do at eye level.
    So the whole column lives on one side: 2 x PIL_W wide, its outer face flush
    with the module datum, and the heavy beam block over it likewise (2 x
    BEAM_END, the same 0.88 m a butted pair used to make). It is the SAME
    geometry as the free-standing `Pilaster` -- one mesh, one UV projection, one
    piece of timber.
    ★ The convention that falls out: a module dresses its -X end, so runs are
    built in +X / +Y away from a corner -- which is the direction corner wings
    already run. Every module boundary is then covered full height by the next
    module's column (floor to beam) and its block (beam to top), so the shell,
    ground, skirting, rail and beam all butt behind timber.
    ★ N modules carry N columns and make N+1 joints, so the joint at the FAR end
    of a run has none: cap it with a free-standing `Pilaster`, which straddles
    and is one mesh. That is a property of one-sided trim, not a bug to design
    around -- dressing both ends is what put a seam down the middle of every
    column, and having the corner piece dress a wing end only moves the problem,
    since which wing is the bare one depends on the plan's handedness."""
    top_beam(mb, -hw, hw, ends=False, one_tier=True)
    wainscot(mb, spans(hw, opens, 0.0, RAIL_Z))
    if posts:
        # lapped past the datum so BOTH arrises are chamfered -- see POST_LAP
        x0 = -hw - POST_LAP
        pilaster(mb, x0, x0 + 2.0 * PIL_W)
        # ★ The block is the COLUMN'S OWN width, not the masonry block's. Wider
        # (2 x BEAM_END) and 20 mm prouder, it overhung the shaft on one side
        # only -- both are anchored at the module datum -- and the top of every
        # column came out as an L instead of a square head.
        # ★★ Its projection is the shaft's plus ONE hairline, and that hairline
        # is load-bearing: authored dead flush, the head and the head beam's cap
        # share a plane, `deconflict()` hands it to the cap (much the larger
        # surface) and the block recedes half a millimetre BEHIND it -- so the
        # top 160 mm of every column rendered as light beam instead of dark
        # post. INSERT_EPS is wider than CLASH_GAP, so the two are simply
        # different planes and the column stays dark to the top of the wall.
        # Same rule the inserts live by: applied joinery stands over the wall's.
        beam_block(mb, x0, x0 + 2.0 * PIL_W, p=PIL_P)


def int_shell(mb, hw, opens):
    """Interior shell: both faces papered, and the reveals WOOD -- an interior
    opening is lined, not built out of masonry. Keeping stone off the edges is
    also what leaves the interior pieces with no BC_Stone slot at all."""
    shell(mb, hw, opens, m_e=M(WOOD))


def wi_straight(mb):
    int_shell(mb, HW, [])
    int_dress(mb, HW, [])


def wi_half(mb):
    int_shell(mb, W2 / 2.0, [])
    int_dress(mb, W2 / 2.0, [])


def wi_plain(mb):
    """4 m of partition with no end pilasters -- butt these in a run and drop
    `Pilaster` wherever you actually want a column. The damask runs through the
    butt joint (local UVs, 0.5 rep/m over a whole-metre module), so a run of
    these reads as one continuous papered wall."""
    int_shell(mb, HW, [])
    int_dress(mb, HW, [], posts=False)


def wi_plain_half(mb):
    int_shell(mb, W2 / 2.0, [])
    int_dress(mb, W2 / 2.0, [], posts=False)


def wi_pilaster(mb):
    """The panelled column on its own, 0.68 m wide -- the SAME column
    Wall_Int_Straight carries at its end, down to the stile widths and the beam
    block, just free-standing.

    Pivot is the column centre, and it belongs on a `Wall_Int_Plain` JOINT (2 m
    from a plain wall's own pivot), where it straddles the joint and hides the
    butt the way a Straight module's own column does. Interchangeable with
    `Pillar` on the same joint if you want one stone column in a papered room."""
    # ★ `lap`: dropped on a finished run, this column's plinth top and the
    # wall's chair rail both cap z = RAIL_Z from two different meshes -- 0.16 m2
    # of light rail flickering against dark plinth, right where you look down on
    # it. A hairline over, and the applied column simply stands on the rail.
    pilaster(mb, -PIL_W, PIL_W, lap=INSERT_EPS)
    # square on the shaft and one hairline proud, exactly as int_dress -- here it
    # also has to beat the cap of the wall this column is DROPPED ON, which is a
    # different mesh and so beyond anything deconflict() can arbitrate
    beam_block(mb, -PIL_W, PIL_W, p=PIL_P, z0=BEAM_Z - INSERT_EPS)


def wi_corner(mb):
    """Outer (convex) corner of a partition -- a chimney breast, a corridor
    turning. Wings run +X and +Y with the post on the convex side, so a run
    leaves the corner without a flip, same as `Wall_Corner`."""
    _corner_core(mb, outer_is_a=True, m_e=M(WOOD))
    corner_wainscot(mb, -1.0)
    corner_wainscot(mb, 1.0)
    _corner_beam(mb, block=False, one_tier=True)
    corner_post(mb, -1.0)


def wi_corner_inside(mb):
    """Inner (concave) corner: the post moves into the reflex notch, which is
    what a reflex corner of an L-shaped room means."""
    _corner_core(mb, outer_is_a=False, m_e=M(WOOD))
    corner_wainscot(mb, -1.0)
    corner_wainscot(mb, 1.0)
    _corner_beam(mb, block=False, one_tier=True)
    corner_post(mb, 1.0)


# Studs on 0.90 m centres and one noggin -- what an interior wall has where a
# stone wall has a bond. Rooted well outside the breach so they read as framing
# carried on past the damage, not as sticks dropped in the hole.
STUD_X = (-0.90, 0.0, 0.90)


def wi_broken(mb):
    """Partition smashed through: studs, a noggin and snapped lath in the
    breach, boards on the floor either side.

    The outline is the SAME ragged course-by-course cut as `Wall_Broken` -- the
    two damaged pieces have to look like the same event -- but what the hole
    exposes is framing, because that is what is actually inside a papered
    partition. Nothing here is stone.

    ★ The breach sits between the CHAIR RAIL and the head beam, not down at the
    plinth course the stone wall breaks from. Cut low, `spans()` takes the dado
    out under the hole and leaves a bare papered stub where the skirting and
    wainscot should still be -- which reads as missing trim, not as damage.
    Starting at the rail leaves the dado standing as the parapet you actually
    want to duck behind, and the rail's own top edge becomes the sill of the
    hole."""
    nc = max(1, int(round((BEAM_Z - RAIL_Z) / 0.44)))
    ch = (BEAM_Z - RAIL_Z) / nc
    opens = [op_rect((b - a) / 2.0, RAIL_Z + (i - 1) * ch, RAIL_Z + i * ch,
                     cx=(a + b) / 2.0) for i, a, b in BREACH]
    int_shell(mb, HW, opens)
    int_dress(mb, HW, opens)
    z_lo = min(o["z0"] for o in opens) - 0.40
    z_hi = max(o["z1"] for o in opens) + 0.40
    for x in STUD_X:
        sl(mb, x - 0.05, x + 0.05, -0.045, 0.045, z_lo, z_hi, M(WOODD))
    # ★ Noggins STAGGERED, one per bay. Run level across all three studs at
    # mid-height and the centre stud crosses it into a perfect plus sign, which
    # reads as a window mullion, not as framing.
    zm = (z_lo + z_hi) / 2.0
    for (a, b), dz in ((STUD_X[:2], 0.26), (STUD_X[1:], -0.38)):
        sl(mb, a - 0.05, b + 0.05, -0.045, 0.045,
           zm + dz - 0.06, zm + dz + 0.06, M(WOODD))
    # lath snapped off the studs and left hanging -- TILTED, because a level
    # board across a hole reads as a shelf someone fitted there, and each one
    # crosses a stud so it hangs off something instead of floating
    for x, z, ang in ((-0.75, 2.10, 24.0), (0.75, 2.86, -17.0),
                      (0.15, 1.52, 13.0)):
        for sgn in (-1.0, 1.0):
            mb.box((x, sgn * 0.10, z), (0.38, 0.07, 0.07), M(WOOD),
                   rot=(0.0, RAD(ang), 0.0))
    # debris: symmetric, because both sides of this wall are a room
    for sgn in (-1.0, 1.0):
        for i, (x, ln, wd) in enumerate(((-0.95, 0.42, 0.11),
                                         (0.35, 0.30, 0.09),
                                         (1.20, 0.24, 0.08))):
            y0c = sgn * (HT + P2 + 0.05 + 0.11 * i)
            y1c = y0c + sgn * ln
            sl(mb, x, x + wd + 0.06, min(y0c, y1c), max(y0c, y1c),
               0.0, 0.07, M(WOODD))


def wi_arch(mb):
    """Walk-through arch between two rooms: 2.20 m clear, springing at 1.90.

    Where the exterior arch lays a two-step stone apron, this gets a wood saddle
    over the same 0.10 m threshold -- one rung shallower than the architrave the
    insert brings, so `Arch_Door_Frame` still drops straight in."""
    o = spec(OP_A)
    int_shell(mb, HW, [o])
    int_dress(mb, HW, [o])
    int_ring(mb, o)
    w = o["hw"] + CASE + SILL_LAP
    stone_shelf(mb, -w, w, o["z0"] + 0.04, p=P1, mat=M(WOOD))


def wi_door(mb):
    o = spec(OP_D)
    int_shell(mb, HW, [o])
    int_dress(mb, HW, [o])
    int_ring(mb, o)


def wi_door_double(mb):
    o = spec(OP_DD)
    int_shell(mb, HW, [o])
    int_dress(mb, HW, [o])
    int_ring(mb, o)


def wi_window(mb):
    """Borrowed light: the tall window opening in a partition, with a wood stool
    where the outside wall has a stone sill. Takes `Window_Tall` and
    `Window_Boarded` unchanged."""
    o = spec(OP_W)
    int_shell(mb, HW, [o])
    int_dress(mb, HW, [o])
    int_ring(mb, o)
    int_stool(mb, o)


def wi_window_small(mb):
    """Hatch-sized light. Flat head and stool are the same block, which is the
    whole point of `stone_shelf` -- one section per member, either family."""
    o = spec(OP_WS)
    int_shell(mb, HW, [o])
    int_dress(mb, HW, [o])
    int_stool(mb, o, top=o["zs"] + SILL_H)
    int_stool(mb, o)


def wi_window_round(mb):
    """Interior oculus, wood ring. NOTE the `Window_Round` insert brings a STONE
    ring of its own at the prouder rung: fitted, it covers this one. Either
    override the BC_Stone slot on that insert for interior use, or leave the
    oculus bare and let the wall's own ring frame it."""
    o = spec(OP_R)
    int_shell(mb, HW, [o])
    int_dress(mb, HW, [])
    int_ring(mb, o)


WALLS_INT = [("Wall_Int_Straight", wi_straight), ("Wall_Int_Half", wi_half),
             ("Wall_Int_Plain", wi_plain),
             ("Wall_Int_Plain_Half", wi_plain_half),
             ("Pilaster", wi_pilaster),
             ("Wall_Int_Corner", wi_corner),
             ("Wall_Int_Corner_Inside", wi_corner_inside),
             ("Wall_Int_Broken", wi_broken), ("Wall_Int_Arch", wi_arch),
             ("Wall_Int_Door", wi_door),
             ("Wall_Int_Door_Double", wi_door_double),
             ("Wall_Int_Window", wi_window),
             ("Wall_Int_Window_Small", wi_window_small),
             ("Wall_Int_Window_Round", wi_window_round)]


# ------------------------------------------------------------ door pieces --
def ledged_leaf(mb, w, h, t, arch=False, mat=None, dark=None, iron=None,
                x0=0.0, ledges=(0.22, 0.55, 0.88)):
    """A ledged-and-braced plank leaf: vertical boards, horizontal ledges, iron
    straps. `x0` is the hinge edge, boards run to x0 + w.

    ★ The head radius is derived from the leaf's OWN half-width, never passed
    in. Feeding it the opening's radius makes the outer boards fall outside the
    arc, and they then drop to the springline in one step -- the leaf comes out
    looking like a ziggurat. r = w/2 is the only value for which the arc lands
    exactly on both stiles."""
    mat = M(WOODD) if mat is None else mat
    dark = M(WOOD) if dark is None else dark
    iron = M(IRON) if iron is None else iron
    n = max(5, int(round(w / PLANK_W)))
    step = w / n
    cx = x0 + w / 2.0
    r = w / 2.0
    zs = h - r
    for i in range(n):
        b0, b1 = x0 + i * step + 0.011, x0 + (i + 1) * step - 0.011
        top = h
        if arch:
            far = max(abs(b0 - cx), abs(b1 - cx))
            top = zs + math.sqrt(max(0.0, r ** 2 - far ** 2))
        sl(mb, b0, b1, -t / 2.0, t / 2.0, 0.02, top, mat)
    for fz in ledges:
        z = 0.10 + (h - 0.30) * fz
        sl(mb, x0 + 0.03, x0 + w - 0.03, t / 2.0 - 0.005, t / 2.0 + BOARD_T,
           z, z + BOARD_W, dark)
        for bx in (x0 + 0.10, x0 + w - 0.16):
            sl(mb, bx, bx + IRON_W / 2, -t / 2.0 - 0.022, t / 2.0 + BOARD_T + 0.02,
               z + BOARD_W / 2 - IRON_W / 2, z + BOARD_W / 2 + IRON_W / 2, iron)


def strap_hinge(mb, x0, z, length, t, sgn=1.0, iron=None):
    iron = M(IRON) if iron is None else iron
    sl(mb, x0, x0 + sgn * length, -t / 2.0 - 0.022, t / 2.0 + 0.022,
       z - IRON_W / 2, z + IRON_W / 2, iron)
    sl(mb, x0 - sgn * 0.05, x0 + sgn * 0.05, -t / 2.0 - 0.05, t / 2.0 + 0.05,
       z - 0.09, z + 0.09, iron)


def ring_pull(mb, cx, y, cz, r, iron=None, seg=14):
    iron = M(IRON) if iron is None else iron
    for i in range(seg):
        a0, a1 = TAU * i / seg, TAU * (i + 1) / seg
        pts = [(cx + (r - 0.03) * math.cos(a0), cz + (r - 0.03) * math.sin(a0)),
               (cx + (r - 0.03) * math.cos(a1), cz + (r - 0.03) * math.sin(a1)),
               (cx + (r + 0.03) * math.cos(a1), cz + (r + 0.03) * math.sin(a1)),
               (cx + (r + 0.03) * math.cos(a0), cz + (r + 0.03) * math.sin(a0))]
        poly(mb, pts, y - 0.03, y + 0.03, iron)
    sl(mb, cx - 0.07, cx + 0.07, y - 0.05, y + 0.05, cz + r - 0.02, cz + r + 0.14, iron)


def arch_frame(mb, o, case=CASE, proj=P2, mat=None, key=True, key_mat=None):
    """Timber/stone architrave following an arched opening, with a keystone.

    `key_mat` is the ONE stone member on a door frame, which is exactly why it is
    a parameter: dropped into an interior wall the frame has to be able to come
    in wood, or a partition finished on both faces sprouts three chalk-coloured
    blocks the moment you hang a door in it."""
    mat = M(WOOD) if mat is None else mat
    key_mat = M(STONE) if key_mat is None else key_mat
    hw, zs, r = o["hw"], o["zs"], o["r"]
    y0, y1 = -HT - proj, HT + proj
    for sgn in (-1.0, 1.0):
        x = sgn * (hw - INSERT_EPS)     # ★ laps the reveal -- see CASE_LAP note
        sl(mb, min(x, x + sgn * case), max(x, x + sgn * case), y0, y1,
           o["z0"], zs, mat)
    voussoirs(mb, 0.0, zs, r - 0.01, r + case, y0, y1, mat=mat, gap=0.012)
    if key:
        sl(mb, -CASE * 0.6, CASE * 0.6, y0 - 0.02, y1 + 0.02, zs + r - 0.04,
           zs + r + case + 0.08, key_mat)


def d_door_frame(mb, stone=None):
    o = spec(OP_D)
    arch_frame(mb, o, key_mat=stone)
    opening_plinths(mb, o, mat=stone)


def d_door_leaf(mb):
    """Origin ON THE HINGE: the leaf hangs at wall pivot +/- DOOR_HINGE and
    rotates about its own Z, nothing else."""
    o = spec(OP_D)
    w = 2 * DOOR_HINGE - 0.02
    ledged_leaf(mb, w, o["zs"] + o["r"] - 0.06, 0.09, arch=True, x0=-w + 0.01)
    strap_hinge(mb, 0.0, 0.55, w * 0.55, 0.09, sgn=-1.0)
    strap_hinge(mb, 0.0, 2.05, w * 0.55, 0.09, sgn=-1.0)
    sl(mb, -w + 0.10, -w + 0.30, -0.075, 0.075, 1.05, 1.22, M(IRON))
    sl(mb, -w + 0.02, -w + 0.20, -0.13, -0.05, 1.09, 1.17, M(IRON))


def d_double_frame(mb, stone=None):
    o = spec(OP_DD)
    arch_frame(mb, o, key_mat=stone)
    opening_plinths(mb, o, mat=stone)


def _double_leaf(mb, side):
    """One half of the pair, origin ON ITS HINGE at x = -/+ DD_HINGE.

    Local +/-X runs from the hinge toward the meeting stile at x = -/+ w, so the
    shared arch is a circle of radius w centred on the PAIR's centre-line, which
    in this leaf's own frame sits at x = -/+ w. Getting that centre wrong (using
    the leaf's own middle) is what makes the two halves meet in a peak instead
    of closing into one round head."""
    o = spec(OP_DD)
    w = DD_HINGE - 0.03
    h = o["zs"] + o["r"] - 0.08
    sgn = -1.0 if side == "L" else 1.0          # hinge is at -/+ DD_HINGE
    d = -sgn                                    # leaf body runs back toward 0
    r = w
    zs = h - r
    n = max(5, int(round(w / PLANK_W)))
    step = w / n
    for i in range(n):
        a, b = i * step + 0.012, (i + 1) * step - 0.012
        near = min(a, b)                        # distance from the hinge stile
        # x measured from the pair centre-line = w - (distance from hinge)
        far = w - near
        top = zs + math.sqrt(max(0.0, r ** 2 - far ** 2))
        p, q = d * a, d * b
        sl(mb, min(p, q), max(p, q), -0.05, 0.05, 0.02, top, M(WOODD))
    for fz in (0.24, 0.62):
        z = 0.22 + (h - 0.6) * fz
        p, q = d * 0.05, d * (w - 0.05)
        sl(mb, min(p, q), max(p, q), 0.045, 0.10, z, z + 0.17, M(WOOD))
    strap_hinge(mb, 0.0, 0.66, w * 0.62, 0.10, sgn=d)
    strap_hinge(mb, 0.0, h - 0.80, w * 0.62, 0.10, sgn=d)
    ring_pull(mb, d * (w - 0.30), -0.09, 1.30, 0.20)


def d_double_leaf_l(mb):
    _double_leaf(mb, "L")


def d_double_leaf_r(mb):
    _double_leaf(mb, "R")


def d_arch_frame(mb, stone=None):
    """Wood architrave + door stop for the Wall_Arch opening.

    ★ The STONE ring belongs to the wall, not to this piece. Emitting a second
    stone ring here at a slightly different radius gave two interleaved sets of
    voussoirs whose joints did not line up, and the arch read as noise. Using
    the shared `arch_frame()` instead also puts every door frame in the kit on
    the same architrave: wood inside the wall's stone."""
    o = spec(OP_A)
    arch_frame(mb, o, key_mat=stone)
    yp = HT + P2
    for sgn in (-1.0, 1.0):
        sl(mb, min(sgn * o["hw"], sgn * (o["hw"] - 0.07)),
           max(sgn * o["hw"], sgn * (o["hw"] - 0.07)),
           HT - 0.02, HT + 0.05, o["z0"], o["zs"] + o["r"] * 0.65, M(WOOD))


def d_arch_leaf(mb):
    o = spec(OP_A)
    w = 2 * (o["hw"] - 0.05)
    h = o["zs"] + o["r"] - 0.08
    ledged_leaf(mb, w, h, 0.10, arch=True, x0=-w + 0.02,
                ledges=(0.18, 0.50, 0.82))
    strap_hinge(mb, 0.0, 0.60, w * 0.5, 0.10, sgn=-1.0)
    strap_hinge(mb, 0.0, h - 0.55, w * 0.5, 0.10, sgn=-1.0)
    # escutcheon and the sheet's little cross ornament
    cx = -w / 2.0
    sl(mb, cx - 0.16, cx + 0.16, -0.095, 0.095, 1.02, 1.42, M(IRON))
    sl(mb, cx - 0.05, cx + 0.05, -0.10, 0.10, 1.10, 1.30, M(WOODD))
    for a, b, c, d in ((-0.13, 0.13, 1.86, 1.96), (-0.05, 0.05, 1.74, 2.08)):
        sl(mb, cx + a, cx + b, -0.10, 0.10, c, d, M(IRON))


def d_secret(mb):
    """Bookcase that hides a doorway. Origin is on its HINGE EDGE so it can be
    swung or spun about local Z; it is 1.84 m wide against a 1.40 m opening, so
    the case laps the jambs and the doorway never shows at the edges."""
    bw, bh, bd = 1.84, 2.90, 0.42
    x0 = -bw
    sl(mb, x0, 0.0, 0.0, bd, 0.0, 0.16, M(WOODD))                    # plinth
    sl(mb, x0, x0 + 0.13, 0.02, bd, 0.16, bh - 0.20, M(WOOD))        # stiles
    sl(mb, -0.13, 0.0, 0.02, bd, 0.16, bh - 0.20, M(WOOD))
    sl(mb, x0 + 0.86, x0 + 0.98, 0.02, bd, 0.16, bh - 0.20, M(WOOD))  # mullion
    sl(mb, x0, 0.0, bd - 0.06, bd, 0.16, bh - 0.20, M(WOODD))        # back
    sl(mb, x0 - 0.06, 0.06, 0.0, bd + 0.06, bh - 0.20, bh, M(WOOD))  # cornice
    for sgn, bx in ((1, x0 - 0.06), (1, -0.02)):
        sl(mb, bx, bx + 0.08, -0.02, bd + 0.02, bh - 0.30, bh + 0.02, M(WOODD))
    shelves = [0.16, 0.76, 1.36, 1.96, 2.56]
    for z in shelves[1:]:
        sl(mb, x0 + 0.04, -0.04, 0.03, bd - 0.04, z - 0.05, z, M(WOOD))
    books = [M(BOOK_A), M(BOOK_B), M(BOOK_C), M(WOODD)]
    seedv = 0
    for si in range(len(shelves) - 1):
        z0 = shelves[si]
        z1 = shelves[si + 1] - 0.05
        for bay in ((x0 + 0.15, x0 + 0.84), (x0 + 1.00, -0.16)):
            x = bay[0]
            while x < bay[1] - 0.05:
                seedv = (seedv * 1103515245 + 12345) & 0x7FFFFFFF
                r = seedv / float(0x7FFFFFFF)
                bwid = BEVEL_MIN + 0.055 * r
                bhh = (z1 - z0) * (0.62 + 0.30 * ((seedv >> 7) % 100) / 100.0)
                lean = ((seedv >> 11) % 7) == 0
                if x + bwid > bay[1]:
                    break
                m = books[(seedv >> 5) % len(books)]
                if lean:
                    mb.box((x + bwid / 2.0, 0.16, z0 + bhh / 2.0),
                           (bwid, 0.24, bhh), m, rot=(0.0, RAD(13), 0.0))
                else:
                    sl(mb, x, x + bwid, 0.06, 0.30, z0, z0 + bhh, m)
                x += bwid + 0.006
    # a candle-stub and a skull-ish blob so the shelf is not all spines
    sl(mb, x0 + 0.30, x0 + 0.40, 0.10, 0.20, 1.36, 1.62, M(STONE))
    sl(mb, x0 + 1.22, x0 + 1.44, 0.08, 0.30, 2.56, 2.76, M(STONE))


def d_barricaded(mb):
    """Frame plus a leaf nailed shut with crossed boards. One static mesh --
    nothing here is meant to open."""
    o = spec(OP_D)
    arch_frame(mb, o, key=False)
    w = 2 * o["hw"] - 0.06
    ledged_leaf(mb, w, o["zs"] + o["r"] - 0.10, 0.09, arch=True, x0=-w / 2.0)
    # ★ the boards sit at yb, well proud of the wall face at -HT. Centred on
    # y = -0.10 they were half-buried in the leaf and only their top edge showed,
    # which read as one thin batten instead of as a barricade.
    yb = -HT - P2 - BOARD_T / 2
    for z, ang in ((1.30, 33.0), (1.30, -33.0), (2.42, 9.0), (0.60, -7.0)):
        L = (2 * o["hw"] + 0.52) / math.cos(RAD(abs(ang)))
        mb.box((0.0, yb, z), (L, BOARD_T, BOARD_W), M(WOOD), rot=(0.0, RAD(ang), 0.0))
        for sgn in (-1.0, 1.0):
            bx = sgn * (o["hw"] - 0.06)
            bz = z - bx * math.tan(RAD(ang))
            sl(mb, bx - IRON_W / 2, bx + IRON_W / 2, yb - BOARD_T, yb + 0.02,
               bz - IRON_W / 2, bz + IRON_W / 2, M(IRON))
    sl(mb, -w / 2.0 - 0.04, -w / 2.0 + 0.16, -HT - 0.06, 0.05, 1.05, 1.25, M(IRON))


def d_trap_frame(mb):
    """Floor hatch surround. Pivot at the centre of a 2 x 2 m floor cell, top
    face at z = 0, so it drops into a floor tile without a Z nudge."""
    fx, fy, r = 1.00, 0.80, 0.22
    for x0, x1, y0, y1 in ((-fx, fx, -fy, -fy + r), (-fx, fx, fy - r, fy),
                           (-fx, -fx + r, -fy + r, fy - r),
                           (fx - r, fx, -fy + r, fy - r)):
        sl(mb, x0, x1, y0, y1, -0.20, 0.05, M(WOOD))
    # a rebate for the lid to sit on, not a slab across the hole -- the whole
    # point of the piece is that you can drop through it
    for x0, x1, y0, y1 in ((-fx + r, fx - r, -fy + r, -fy + r + 0.07),
                           (-fx + r, fx - r, fy - r - 0.07, fy - r),
                           (-fx + r, -fx + r + 0.07, -fy + r, fy - r),
                           (fx - r - 0.07, fx - r, -fy + r, fy - r)):
        sl(mb, x0, x1, y0, y1, -0.20, -0.12, M(WOODD))
    for sx, sy in ((-fx + 0.11, -fy + 0.11), (fx - 0.11, -fy + 0.11),
                   (-fx + 0.11, fy - 0.11), (fx - 0.11, fy - 0.11)):
        sl(mb, sx - 0.12, sx + 0.12, sy - 0.12, sy + 0.12, 0.01, 0.10, M(IRON))


def d_trap_leaf(mb):
    """Origin on the hinge edge (local -X side of the frame), lid lying flat."""
    lw, ly = 1.56, 1.14
    nb = max(3, int(round(ly / PLANK_W)))
    for i in range(nb):
        y0 = -ly / 2.0 + ly * i / nb + PLANK_G / 2
        y1 = -ly / 2.0 + ly * (i + 1) / nb - PLANK_G / 2
        sl(mb, 0.02, lw, y0, y1, -0.14, 0.0, M(WOODD))
    for x in (0.18, lw - 0.24):
        sl(mb, x, x + 0.16, -ly / 2.0 + 0.02, ly / 2.0 - 0.02, -0.15, -0.10, M(WOOD))
    for sy in (-ly / 2.0 + 0.22, ly / 2.0 - 0.22):
        sl(mb, 0.0, 0.56, sy - 0.065, sy + 0.065, -0.13, -0.02, M(IRON))
        sl(mb, -0.05, 0.07, sy - 0.10, sy + 0.10, -0.17, 0.03, M(IRON))
    sl(mb, lw - 0.34, lw - 0.02, -0.13, 0.13, -0.13, 0.02, M(IRON))
    # lifting handle: ring_pull() builds its ring standing in XZ, which is right
    # for a door and upside down on a lid, so this one is made by hand
    for hy in (-0.11, 0.11):
        sl(mb, lw - 0.28, lw - 0.20, hy - 0.035, hy + 0.035, 0.0, 0.11, M(IRON))
    sl(mb, lw - 0.30, lw - 0.18, -0.13, 0.13, 0.08, 0.15, M(IRON))


# ---------------------------------------------------- interior insert trim --
# ★ FOUR inserts carried the only stone in the door and window sets -- a door
# frame's keystone and its two jamb plinths, and the oculus ring. Dropped into a
# Wall_Int_* those chalk-coloured blocks are the only thing on the piece still
# saying "outside", and they sit at eye level exactly where you look. Each
# variant below is the SAME builder with its one stone member handed a wood
# material, so the two finishes can never drift apart: there is one door frame in
# this kit, in two colours of the same joinery. Leaves, glazing and boarding
# carry no stone and are shared unchanged.

def d_door_frame_int(mb):
    d_door_frame(mb, stone=M(WOODD))


def d_double_frame_int(mb):
    d_double_frame(mb, stone=M(WOODD))


def d_arch_frame_int(mb):
    d_arch_frame(mb, stone=M(WOODD))


DOORS = [("Door_Frame", d_door_frame), ("Door_Leaf", d_door_leaf),
         ("Double_Door_Frame", d_double_frame),
         ("Double_Door_Leaf_L", d_double_leaf_l),
         ("Double_Door_Leaf_R", d_double_leaf_r),
         ("Arch_Door_Frame", d_arch_frame), ("Arch_Door_Leaf", d_arch_leaf),
         ("Secret_Door", d_secret), ("Barricaded_Door", d_barricaded),
         ("Trapdoor_Frame", d_trap_frame), ("Trapdoor_Leaf", d_trap_leaf),
         ("Door_Frame_Int", d_door_frame_int),
         ("Double_Door_Frame_Int", d_double_frame_int),
         ("Arch_Door_Frame_Int", d_arch_frame_int)]


# ---------------------------------------------------------- window pieces --
def glazing_arch(mb, o, nv, nh, inset=0.0, bar=BAR, mat=None):
    """Glass pane following an arched opening, with muntins laid over it.

    ONE swept polygon, not a row of clipped column slabs. Columns were the first
    attempt and the bevel modifier chamfered every one of them, so the pane's
    arc and its sill came out finely serrated -- very visible, because the glass
    is the brightest thing on the piece."""
    mat = M(GLASS) if mat is None else mat
    hw, z0, zs, r = o["hw"] - inset, o["z0"] + inset, o["zs"], o["r"] - inset
    if r > 0.01:
        pts = [(-hw, z0), (hw, z0)] + arc_pts(0.0, zs, r, 0.0, math.pi, 18)
    else:
        pts = [(-hw, z0), (hw, z0), (hw, zs), (-hw, zs)]
    poly(mb, _dedupe(pts), -BEVEL_MIN / 2, BEVEL_MIN / 2, mat)
    for i in range(1, nv):
        x = -hw + 2 * hw * i / nv
        h2 = zs + (math.sqrt(max(0.0, r ** 2 - x ** 2)) if r > 0.01 else 0.0)
        sl(mb, x - bar / 2, x + bar / 2, -0.05, 0.05, z0, h2, M(WOODD))
    for i in range(1, nh):
        z = z0 + (zs - z0) * i / nh
        sl(mb, -hw, hw, -0.05, 0.05, z - bar / 2, z + bar / 2, M(WOODD))


def win_surround(mb, o, case=CASE, proj=P2, sill=False, mat=None):
    mat = M(WOODD) if mat is None else mat
    hw, z0, zs, r = o["hw"], o["z0"], o["zs"], o.get("r", 0.0)
    y0, y1 = -HT - proj, HT + proj
    for sgn in (-1.0, 1.0):
        x = sgn * (hw - INSERT_EPS)     # ★ laps the reveal -- see CASE_LAP note
        sl(mb, min(x, x + sgn * case), max(x, x + sgn * case), y0, y1, z0, zs, mat)
    if r > 0.0:
        voussoirs(mb, 0.0, zs, r - 0.01, r + case, y0, y1, mat=mat, gap=0.012)
        sl(mb, -CASE * 0.6, CASE * 0.6, y0 - 0.02, y1 + 0.02, zs + r - 0.03,
           zs + r + case + 0.06, mat)
    else:
        sl(mb, -hw - case, hw + case, y0, y1, zs - INSERT_EPS, zs + case, mat)
    if sill:
        sl(mb, -hw - case - 0.10, hw + case + 0.10, -HT - proj - 0.09,
           HT + proj + 0.09, z0 - 0.14, z0 + INSERT_EPS, mat)


def n_small(mb):
    """Square light under the sheet's heavy arched hood."""
    o = spec(OP_WS)
    glazing_arch(mb, o, 2, 2, inset=0.04)
    win_surround(mb, o)
    voussoirs(mb, 0.0, o["z1"] + CASE - 0.04, o["hw"] + CASE - 0.04,
              o["hw"] + CASE - 0.04 + RING * 0.8, -HT - P2, HT + P2,
              mat=M(WOODD), gap=0.012)


def n_tall(mb):
    o = spec(OP_W)
    glazing_arch(mb, o, 2, 4, inset=0.05)
    win_surround(mb, o)
    # Gothic tracery in the head: a central mullion, two lancet ribs and an
    # oculus. Built as thin voussoir rings -- a string of separate blobs along
    # the curve (the first attempt) reads as a dotted line, not as tracery.
    r, zs = o["r"] - 0.05, o["zs"]
    sl(mb, -BAR / 2, BAR / 2, -BAR, BAR, zs - 0.30, zs + r * 0.44, M(WOODD))
    for sgn in (-1.0, 1.0):
        voussoirs(mb, sgn * r * 0.42, zs, r * 0.55, r * 0.55 + BAR,
                  -BAR, BAR, mat=M(WOODD), n=7, gap=0.0)
    voussoirs(mb, 0.0, zs + r * 0.58, r * 0.21, r * 0.21 + BAR,
              -BAR, BAR, mat=M(WOODD), n=10, gap=0.0, a0=0.0, a1=TAU)


def n_boarded(mb):
    o = spec(OP_W)
    glazing_arch(mb, o, 2, 3, inset=0.05)
    win_surround(mb, o)
    for z, ang in ((1.45, 8.0), (2.05, -14.0), (2.55, 6.0), (2.98, -9.0)):
        L = (2 * o["hw"] + 0.52) / math.cos(RAD(abs(ang)))
        mb.box((0.0, -HT - P2 - BOARD_T / 2, z), (L, BOARD_T, BOARD_W), M(WOOD),
               rot=(0.0, RAD(ang), 0.0))
        for sgn in (-1.0, 1.0):
            bx = sgn * (o["hw"] - 0.04)
            bz = z + math.tan(RAD(ang)) * -bx
            sl(mb, bx - IRON_W / 2, bx + IRON_W / 2, -HT - P2 - BOARD_T,
               -HT - P2 + 0.02, bz - IRON_W / 2, bz + IRON_W / 2, M(IRON))


def n_round(mb, ring=None):
    o = spec(OP_R)
    r = o["r"]
    poly(mb, _dedupe(arc_pts(0.0, o["cz"], r - 0.05, 0.0, TAU, 28)),
         -BEVEL_MIN / 2, BEVEL_MIN / 2, M(GLASS))
    sl(mb, -r + 0.05, r - 0.05, -0.05, 0.05, o["cz"] - 0.03, o["cz"] + 0.03, M(WOODD))
    sl(mb, -0.03, 0.03, -0.05, 0.05, o["cz"] - r + 0.05, o["cz"] + r - 0.05, M(WOODD))
    voussoirs(mb, 0.0, o["cz"], r - 0.03, r + RING, -HT - P2, HT + P2,
              mat=ring, a0=0.0, a1=TAU)


def n_grate(mb):
    """Wood frame with corner brackets and an iron lattice -- the sheet's
    'secret grate'. Sized to the small-window opening."""
    o = spec(OP_WS)
    hw, z0, z1 = o["hw"], o["z0"], o["z1"]
    case, proj = CASE, P2
    y0, y1 = -HT - proj, HT + proj
    for sgn in (-1.0, 1.0):
        x = sgn * (hw - INSERT_EPS)      # ★ laps the reveal -- see CASE_LAP note
        sl(mb, min(x, sgn * (hw + case)), max(x, sgn * (hw + case)),
           y0, y1, z0 - case, z1 + case, M(WOOD))
    sl(mb, -hw - case, hw + case, y0, y1, z1 - INSERT_EPS, z1 + case, M(WOOD))
    sl(mb, -hw - case, hw + case, y0, y1, z0 - case, z0 + INSERT_EPS, M(WOOD))
    # corner braces INSIDE the frame corners. Centred on the corner they stick
    # out as free-floating diamonds instead of reading as brackets.
    for sx in (-1.0, 1.0):
        for zc in (z0 + 0.03, z1 - 0.03):
            mb.box((sx * (hw - 0.04), -HT - proj - 0.01, zc),
                   (0.30, 0.09, 0.30), M(WOODD), rot=(0.0, RAD(45), 0.0))
    nb = 5
    for i in range(nb):
        x = -hw + (2 * hw) * (i + 0.5) / nb
        sl(mb, x - IRON_W / 2, x + IRON_W / 2, -IRON_W, IRON_W, z0, z1, M(IRON))
    for i in range(nb):
        z = z0 + (z1 - z0) * (i + 0.5) / nb
        sl(mb, -hw, hw, -IRON_W / 2, IRON_W / 2,
           z - IRON_W / 2, z + IRON_W / 2, M(IRON))


def n_round_int(mb):
    """The oculus ring in wood -- see the interior insert note above DOORS."""
    n_round(mb, ring=M(WOODD))


WINDOWS = [("Window_Small", n_small), ("Window_Tall", n_tall),
           ("Window_Boarded", n_boarded), ("Window_Round", n_round),
           ("Secret_Grate", n_grate), ("Window_Round_Int", n_round_int)]


# ------------------------------------------------------------- materials ---
def _nt(m):
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out_ = nt.nodes.new("ShaderNodeOutputMaterial")
    out_.location = (600, 0)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.location = (300, 0)
    nt.links.new(b.outputs[0], out_.inputs[0])
    uv = nt.nodes.new("ShaderNodeTexCoord")
    uv.location = (-1200, 0)
    return nt, b, uv


def _mat(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    m.use_fake_user = True
    return m


def mat_flat(name, color, rough=0.62, emit=0.0):
    m = _mat(name)
    nt, b, uv = _nt(m)
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*color, 1.0)
        b.inputs["Emission Strength"].default_value = emit
    return m


def mat_paper(name, ground, motif):
    """Damask wallpaper: a 45-degree lattice of diamonds with a finer motif
    inside them, plus a grubby noise wash and a foot-of-the-wall darkening.

    Deliberately built on UV so it survives the 0.5 rep/m projection and runs
    unbroken across a module join."""
    m = _mat(name)
    nt, b, uv = _nt(m)
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.location = (-1000, 0)
    mp.inputs["Rotation"].default_value = (0.0, 0.0, RAD(45))
    mp.inputs["Scale"].default_value = (5.0, 5.0, 5.0)
    nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
    ck = nt.nodes.new("ShaderNodeTexChecker")
    ck.location = (-800, 120)
    ck.inputs["Scale"].default_value = 2.0
    nt.links.new(mp.outputs["Vector"], ck.inputs["Vector"])
    ck2 = nt.nodes.new("ShaderNodeTexChecker")
    ck2.location = (-800, -80)
    ck2.inputs["Scale"].default_value = 6.0
    nt.links.new(mp.outputs["Vector"], ck2.inputs["Vector"])
    mix1 = nt.nodes.new("ShaderNodeMix")
    mix1.data_type = "RGBA"
    mix1.blend_type = "MIX"
    mix1.location = (-560, 60)
    mix1.inputs[6].default_value = (*ground, 1.0)
    mix1.inputs[7].default_value = (*motif, 1.0)
    nt.links.new(ck.outputs["Fac"], mix1.inputs["Factor"])
    mix2 = nt.nodes.new("ShaderNodeMix")
    mix2.data_type = "RGBA"
    mix2.blend_type = "OVERLAY"
    mix2.location = (-360, 60)
    mix2.inputs["Factor"].default_value = 0.22
    nt.links.new(mix1.outputs[2], mix2.inputs[6])
    nt.links.new(ck2.outputs["Color"], mix2.inputs[7])
    ns = nt.nodes.new("ShaderNodeTexNoise")
    ns.location = (-800, -320)
    ns.inputs["Scale"].default_value = 3.2
    ns.inputs["Detail"].default_value = 6.0
    nt.links.new(uv.outputs["UV"], ns.inputs["Vector"])
    nr = nt.nodes.new("ShaderNodeValToRGB")
    nr.location = (-600, -320)
    nr.color_ramp.elements[0].position = 0.30
    nr.color_ramp.elements[0].color = (0.52, 0.46, 0.55, 1.0)
    nr.color_ramp.elements[1].position = 0.72
    nr.color_ramp.elements[1].color = (1.06, 1.04, 1.02, 1.0)
    nt.links.new(ns.outputs["Fac"], nr.inputs["Fac"])
    grime = nt.nodes.new("ShaderNodeMix")
    grime.data_type = "RGBA"
    grime.blend_type = "MULTIPLY"
    grime.location = (-160, 40)
    grime.inputs["Factor"].default_value = 0.65
    nt.links.new(mix2.outputs[2], grime.inputs[6])
    nt.links.new(nr.outputs["Color"], grime.inputs[7])
    nt.links.new(grime.outputs[2], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.80
    return m


def mat_stone(name, base, dark):
    """Ashlar: broad mottle plus a fine speckle, no pattern -- the blocks are
    modelled, so the material only has to carry grain."""
    m = _mat(name)
    nt, b, uv = _nt(m)
    ns = nt.nodes.new("ShaderNodeTexNoise")
    ns.location = (-900, 100)
    ns.inputs["Scale"].default_value = 2.4
    ns.inputs["Detail"].default_value = 8.0
    ns.inputs["Roughness"].default_value = 0.62
    nt.links.new(uv.outputs["UV"], ns.inputs["Vector"])
    rp = nt.nodes.new("ShaderNodeValToRGB")
    rp.location = (-680, 100)
    rp.color_ramp.elements[0].position = 0.34
    rp.color_ramp.elements[0].color = (*dark, 1.0)
    rp.color_ramp.elements[1].position = 0.70
    rp.color_ramp.elements[1].color = (*base, 1.0)
    nt.links.new(ns.outputs["Fac"], rp.inputs["Fac"])
    v = nt.nodes.new("ShaderNodeTexVoronoi")
    v.location = (-900, -200)
    v.feature = "F1"
    v.inputs["Scale"].default_value = 16.0
    nt.links.new(uv.outputs["UV"], v.inputs["Vector"])
    vr = nt.nodes.new("ShaderNodeValToRGB")
    vr.location = (-680, -200)
    vr.color_ramp.elements[0].position = 0.05
    vr.color_ramp.elements[0].color = (0.82, 0.80, 0.86, 1.0)
    vr.color_ramp.elements[1].position = 0.45
    vr.color_ramp.elements[1].color = (1.04, 1.03, 1.05, 1.0)
    nt.links.new(v.outputs["Distance"], vr.inputs["Fac"])
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.blend_type = "MULTIPLY"
    mx.location = (-360, 0)
    mx.inputs["Factor"].default_value = 0.55
    nt.links.new(rp.outputs["Color"], mx.inputs[6])
    nt.links.new(vr.outputs["Color"], mx.inputs[7])
    nt.links.new(mx.outputs[2], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.86
    return m


def mat_wood(name, base, dark, scale=26.0):
    """Plank grain: a stretched noise band across the boards."""
    m = _mat(name)
    nt, b, uv = _nt(m)
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.location = (-1000, 0)
    mp.inputs["Scale"].default_value = (1.0, scale, 1.0)
    nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
    ns = nt.nodes.new("ShaderNodeTexNoise")
    ns.location = (-800, 0)
    ns.inputs["Scale"].default_value = 3.0
    ns.inputs["Detail"].default_value = 6.0
    nt.links.new(mp.outputs["Vector"], ns.inputs["Vector"])
    rp = nt.nodes.new("ShaderNodeValToRGB")
    rp.location = (-560, 0)
    rp.color_ramp.elements[0].position = 0.36
    rp.color_ramp.elements[0].color = (*dark, 1.0)
    rp.color_ramp.elements[1].position = 0.66
    rp.color_ramp.elements[1].color = (*base, 1.0)
    nt.links.new(ns.outputs["Fac"], rp.inputs["Fac"])
    nt.links.new(rp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.74
    return m


def mat_glass(name, color):
    """Night glass: dark teal, a little transmissive, and lifted by its own
    emission so a window still glows in an unlit interior."""
    m = _mat(name)
    nt, b, uv = _nt(m)
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = 0.10
    b.inputs["Metallic"].default_value = 0.0
    if "Transmission Weight" in b.inputs:
        b.inputs["Transmission Weight"].default_value = 0.45
    b.inputs["Emission Color"].default_value = (*color, 1.0)
    b.inputs["Emission Strength"].default_value = 0.85
    m.use_backface_culling = False
    return m


def materials():
    mat_paper(PAPER, srgb(C_PAPER), srgb(C_PAPER2))
    mat_paper(PAPER_B, srgb(C_PAPER), srgb(C_PAPER2))
    mat_stone(STONE, srgb(C_STONE), srgb(C_STONE2))
    mat_wood(WOOD, srgb(C_WOOD), srgb(C_WOOD2))
    mat_wood(WOODD, srgb(C_WOOD_DK), srgb(0x33221C))
    mat_flat(IRON, srgb(C_IRON), rough=0.42)
    mat_glass(GLASS, srgb(C_GLASS))
    # Muted library colours, not the sheet's neon swatches -- those are for
    # signage. Full-chroma spines turn the bookcase into a toy.
    mat_flat(BOOK_A, srgb(0x3F6E38), rough=0.70)      # cloth green
    mat_flat(BOOK_B, srgb(0x8C3A31), rough=0.70)      # oxblood
    mat_flat(BOOK_C, srgb(0x2E6B76), rough=0.70)      # faded teal
    mat_flat(LABEL, srgb(0xE8E4F2), rough=0.6)
    mat_flat(STAGE, srgb(0x241C33), rough=0.9)


# ------------------------------------------------------------- catalogue ---
def label(coll, text, loc, size=0.26):
    cu = bpy.data.curves.new(PFX + "L_" + text, type="FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    cu.extrude = 0.008
    ob = bpy.data.objects.new(PFX + "L_" + text, cu)
    ob.location = Vector(loc)
    ob.rotation_euler = Euler((RAD(90), 0, 0), "XYZ")
    cu.materials.append(M(LABEL))
    coll.objects.link(ob)
    return ob


def ground_plane(coll, name, cx, cy, sx, sy, top=0.0):
    mb = MB(name, PFX)
    sl(mb, -sx / 2, sx / 2, -sy / 2, sy / 2, top - 0.4, top, M(STAGE))
    return out(mb, coll, (cx, cy, 0.0), bevel=0.0)


def dup(src, coll, loc, rot=0.0):
    ob = src.copy()
    ob.location = Vector(loc)
    ob.rotation_euler = Euler((0, 0, rot), "XYZ")
    coll.objects.link(ob)
    return ob


SEAM_X4 = [("x", -HW), ("x", HW)]
SEAM_X2 = [("x", -W2 / 2), ("x", W2 / 2)]
SEAM_Z = [("z", 0.0), ("z", H)]
SEAM_C = [("x", CWING), ("y", CWING)]


def seam_for(name):
    # ★ Matched on shape, not on a list of names: the interior family repeats
    # every shape in the kit, and a name list is exactly the kind of thing that
    # silently misses half of it (a Wall_Int_Half without SEAM_X2 gets its butt
    # edge chamfered and shows a hairline down every joint).
    if name in POSTS:
        return SEAM_Z
    if name.endswith("_Half"):
        return SEAM_X2 + SEAM_Z
    if "Corner" in name:
        return SEAM_C + SEAM_Z
    if name.startswith("Wall_"):
        return SEAM_X4 + SEAM_Z
    return None


# The free-standing columns: dropped ON a finished run, so they defer on the top
# datum (see `defer_top` in out()) instead of fighting the beam cap for it.
POSTS = ("Pillar", "Pilaster")

ROW_Y = {"Walls": 0.0, "WallsInt": -13.0, "Doors": 13.0, "Windows": 24.0}
ROW_TITLE = {"Walls": "WALLS", "WallsInt": "INTERIOR WALLS",
             "Doors": "DOORS", "Windows": "WINDOWS"}
STEP = 5.4

# Inserts shown fitted into their host wall, which is the whole point of sharing
# the pivot -- if a frame drifts, this row shows it immediately. ★ Module level so
# the row's cameras can be derived from its length: hardcoding the count is how a
# camera ends up pointing at whatever moved into its place. Every interior host
# takes the SAME insert as its exterior twin, which is what the last six rows
# check -- the openings are one set of constants for both families.
FITTED = [("Wall_Door", ["Door_Frame"], [("Door_Leaf", DOOR_HINGE, RAD(-28))]),
          ("Wall_Door_Double", ["Double_Door_Frame"],
           [("Double_Door_Leaf_L", -DD_HINGE, RAD(-24)),
            ("Double_Door_Leaf_R", DD_HINGE, RAD(24))]),
          ("Wall_Arch", ["Arch_Door_Frame"], [("Arch_Door_Leaf", OP_A["hw"] - 0.05,
                                               RAD(-34))]),
          ("Wall_Door", ["Barricaded_Door"], []),
          ("Wall_Door", ["Secret_Door"], []),
          ("Wall_Window", ["Window_Tall"], []),
          ("Wall_Window", ["Window_Boarded"], []),
          ("Wall_Window_Small", ["Window_Small"], []),
          ("Wall_Window_Small", ["Secret_Grate"], []),
          ("Wall_Window_Round", ["Window_Round"], []),
          ("Wall_Int_Door", ["Door_Frame_Int"],
           [("Door_Leaf", DOOR_HINGE, RAD(-28))]),
          ("Wall_Int_Door_Double", ["Double_Door_Frame_Int"],
           [("Double_Door_Leaf_L", -DD_HINGE, RAD(-24)),
            ("Double_Door_Leaf_R", DD_HINGE, RAD(24))]),
          ("Wall_Int_Arch", ["Arch_Door_Frame_Int"],
           [("Arch_Door_Leaf", OP_A["hw"] - 0.05, RAD(-34))]),
          ("Wall_Int_Door", ["Secret_Door"], []),
          ("Wall_Int_Window", ["Window_Tall"], []),
          ("Wall_Int_Window_Small", ["Window_Small"], []),
          ("Wall_Int_Window_Round", ["Window_Round_Int"], [])]
# Well clear of the catalogue: the row cameras stand 22 m in FRONT of the walls
# row, and at -22 the demo room swallowed them whole -- every "row" shot was
# really an interior of the demo.
DEMO_Y = -70.0


def build():
    BK.purge_coll(ROOT)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)
    materials()
    BK.MAT_UV_SCALE.clear()
    BK.MAT_UV_SCALE.update(UVS)

    scene = bpy.data.scenes.get(SCENE) or bpy.data.scenes.new(SCENE)
    bpy.context.window.scene = scene
    root = BK.ensure_coll(ROOT, scene.collection)
    c_w = BK.ensure_coll(PFX + "Walls", root)
    c_i = BK.ensure_coll(PFX + "Walls_Int", root)
    c_d = BK.ensure_coll(PFX + "Doors", root)
    c_n = BK.ensure_coll(PFX + "Windows", root)
    c_x = BK.ensure_coll(PFX + "Demo", root)
    c_f = BK.ensure_coll(PFX + "Fitted", root)
    c_l = BK.ensure_coll(PFX + "Preview", root)
    c_g = BK.ensure_coll(PFX + "Lighting", root)
    labs = {r: BK.ensure_coll(PFX + "Lab_" + r, c_l)
            for r in ("Walls", "WallsInt", "Doors", "Windows", "Fitted")}
    c_s = BK.ensure_coll(PFX + "Stage", c_l)

    ground_plane(c_s, "Stage", 26.0, 4.0, 120.0, 96.0)

    for coll, items, row in ((c_w, WALLS, "Walls"), (c_i, WALLS_INT, "WallsInt"),
                             (c_d, DOORS, "Doors"), (c_n, WINDOWS, "Windows")):
        y = ROW_Y[row]
        for i, (name, fn) in enumerate(items):
            mb = MB(name, PFX)
            fn(mb)
            ob = out(mb, coll, (i * STEP, y, 0.0), seam=seam_for(name),
                     insert=(row in ("Doors", "Windows") or name in POSTS),
                     defer_top=(name in POSTS))
            label(labs[row], name, (i * STEP, y - 2.7, 0.30), size=0.30)
        label(labs[row], ROW_TITLE[row], (-STEP - 0.4, y - 2.7, 0.90), size=0.52)

    K = bpy.data.objects
    for i, (wall, frames, leaves) in enumerate(FITTED):
        p = (i * STEP, ROW_Y["Windows"] + 9.0, 0.0)
        dup(K[PFX + wall], c_f, p)
        for f in frames:
            q = p
            if f == "Secret_Door":
                q = (p[0] + SECRET_HINGE, p[1] - HT - 0.24, p[2])
            dup(K[PFX + f], c_f, q)
        for nm, off, ang in leaves:
            dup(K[PFX + nm], c_f, (p[0] + off, p[1], p[2]), ang)
        label(labs["Fitted"], (frames[0] if frames else wall) + " in " + wall,
              (p[0], p[1] - 2.7, 0.30), size=0.26)
    label(labs["Fitted"], "FITTED", (-STEP - 0.4, ROW_Y["Windows"] + 6.3, 0.90),
          size=0.52)

    demo_room(c_x, (6.0, DEMO_Y))
    int_rooms(c_x, (0.0, DEMO_Y - 30.0))
    world_and_lights(scene, c_g)
    cd = bpy.data.cameras.new(PFX + "Cam")
    cam = bpy.data.objects.new(PFX + "Cam", cd)
    c_g.objects.link(cam)
    scene.camera = cam
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.eevee.taa_render_samples = 64
    try:
        scene.eevee.use_shadows = True
        scene.eevee.use_raytracing = True
    except Exception:
        pass
    aim(cam, *SHOTS["overview"])

    audit_bevel()
    audit_chamfer()
    audit_fit()
    tris = 0
    for c in (c_w, c_i, c_d, c_n):
        for o in c.objects:
            if o.type == "MESH":
                tris += len(o.data.polygons)
    return tris


def audit_bevel(report=True):
    """Find every island thinner than BEVEL_MIN in any axis.

    ★ The Bevel modifier runs with use_clamp_overlap, which is the right safety
    setting but the clamp is computed ONCE for the whole mesh: one member
    thinner than 2 x BEVEL_W quietly sharpens the chamfer on the ENTIRE piece,
    same number in the modifier, visibly sharper everything on screen.
    That is invisible in the code and obvious on the model, so it gets a build
    check rather than a comment. This per-island thickness floor catches most
    causes; audit_chamfer() measures the built RESULT and catches the rest
    (thin wedges inside big islands, e.g. an arc tangent to a cut line, which
    no bounding-box test can see). Run both after any new piece."""
    bad = []
    for cn in KIT_COLLS:
        for ob in bpy.data.collections[cn].objects:
            if ob.type != "MESH":
                continue
            me = ob.data
            bm = bmesh.new()
            bm.from_mesh(me)
            seen = set()
            for f in bm.faces:
                if f.index in seen:
                    continue
                stack, comp = [f], []
                seen.add(f.index)
                while stack:
                    g = stack.pop()
                    comp.append(g)
                    for e in g.edges:
                        for h in e.link_faces:
                            if h.index not in seen:
                                seen.add(h.index)
                                stack.append(h)
                vs = {v for g in comp for v in g.verts}
                dims = [max(v.co[i] for v in vs) - min(v.co[i] for v in vs)
                        for i in range(3)]
                if min(dims) < BEVEL_MIN - 1e-4:
                    mats = {me.materials[g.material_index].name for g in comp
                            if g.material_index < len(me.materials)}
                    bad.append((min(dims), ob.name, ",".join(sorted(mats))))
            bm.free()
    if report and bad:
        bad.sort()
        print("!! %d island(s) below the %.3f chamfer floor:" % (len(bad), BEVEL_MIN))
        for thin, who, mats in bad[:12]:
            print("   %.3f  %-26s %s" % (thin, who.replace(PFX, ""), mats))
    return bad


def audit_chamfer(report=True):
    """Measure the chamfer the Bevel modifier ACTUALLY produced on every piece.

    ★★ clamp_overlap computes ONE safe offset for the WHOLE mesh, so a single
    thin wedge anywhere silently sharpens every edge of the piece, and
    audit_bevel()'s island floor cannot see wedges inside big islands. The
    arch fillers used to run the arc tangent into the grid line: a 9-15 mm
    knife wedge at the crown, and Wall_Window measured 0.0066 strips ALL OVER
    (quoins, sill, voussoirs) against 0.0184 on Wall_Window_Small -- the
    'different bevels on the stone accents'. This audits the RESULT: median
    chamfer strip width per piece via the depsgraph, flagged when a piece
    falls off the kit norm. Zero output = every piece carries the same
    chamfer."""
    dg = bpy.context.evaluated_depsgraph_get()
    meds = {}
    for cn in KIT_COLLS:
        for ob in bpy.data.collections[cn].objects:
            if ob.type != "MESH" or not ob.modifiers.get("Bevel"):
                continue
            me = ob.evaluated_get(dg).to_mesh()
            ws = []
            for p in me.polygons:
                if len(p.vertices) != 4:
                    continue
                vs = [me.vertices[i].co for i in p.vertices]
                es = [(vs[i] - vs[(i + 1) % 4]).length for i in range(4)]
                a = (es[0] + es[2]) / 2.0
                b = (es[1] + es[3]) / 2.0
                w, ln = min(a, b), max(a, b)
                if w < 0.035 and ln > 2.5 * w:   # a chamfer strip, maybe clamped
                    ws.append(w)
            ob.evaluated_get(dg).to_mesh_clear()
            if ws:
                ws.sort()
                meds[ob.name] = ws[len(ws) // 2]
    norm = max(meds.values()) if meds else 0.0
    bad = sorted((m, n) for n, m in meds.items() if m < 0.93 * norm)
    if report and bad:
        print("!! %d piece(s) with a clamped chamfer (kit norm %.4f):"
              % (len(bad), norm))
        for m, n in bad:
            print("   %.4f  %s" % (m, n.replace(PFX, "")))
    return bad


def audit_fit(report=True, min_area=0.01):
    """Find coplanar clashes BETWEEN objects -- the class deconflict() cannot see.

    ★★ `deconflict()` only ever looks at one mesh, so it arbitrates a wall's own
    members and nothing else. Everything this kit assembles from two objects is
    invisible to it: an insert's casing against the host wall's opening REVEAL
    (0.30 m2 per jamb on every window wall, 0.80 on the small window's head), and
    a free-standing column against the run it is dropped on -- its plinth top
    against the chair rail it crosses, its block's soffit against the head beam.
    All of them flickered wood against wood at eye level. `lift_insert()` handles
    only the y rungs and the floor datum, which is why the rest needed CASE_LAP
    and the `lap` / `z0` arguments on `pilaster` / `beam_block`.

    The pass: for every pair of objects whose bounds touch, group world-space
    axis-aligned faces by plane and facing, and report different-material
    overlaps -- but only where BOTH faces are actually exposed. The exposure test
    is what makes it usable: a face buried under its own member (a column's
    capital under its own block) is coplanar with the neighbour's and will never
    render, and without the test those swamp the real findings."""
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    cache, bvhs, boxes = {}, {}, {}

    def prep(ob):
        if ob.name in cache:
            return
        me = ob.evaluated_get(dg).to_mesh()
        mw = ob.matrix_world
        rot = mw.to_3x3()
        vs = [mw @ v.co for v in me.vertices]
        tris, faces = [], []
        for p in me.polygons:
            idx = list(p.vertices)
            for i in range(1, len(idx) - 1):
                tris.append((idx[0], idx[i], idx[i + 1]))
            n = (rot @ p.normal).normalized()
            ax = max(range(3), key=lambda i: abs(n[i]))
            if abs(n[ax]) < 0.999:
                continue
            co = [vs[i][ax] for i in p.vertices]
            if max(co) - min(co) > 1e-5:
                continue
            o = [i for i in range(3) if i != ax]
            faces.append((ax, 1 if n[ax] > 0 else -1, sum(co) / len(co),
                          me.materials[p.material_index].name
                          if p.material_index < len(me.materials) else "?",
                          (min(vs[i][o[0]] for i in p.vertices),
                           max(vs[i][o[0]] for i in p.vertices),
                           min(vs[i][o[1]] for i in p.vertices),
                           max(vs[i][o[1]] for i in p.vertices)),
                          mw @ p.center, n))
        cache[ob.name] = faces
        bvhs[ob.name] = BVHTree.FromPolygons(vs, tris, all_triangles=True)
        ws = [mw @ Vector(c) for c in ob.bound_box]
        boxes[ob.name] = ([min(w[i] for w in ws) for i in range(3)],
                          [max(w[i] for w in ws) for i in range(3)])
        ob.evaluated_get(dg).to_mesh_clear()

    obs = []
    for cn in (PFX + "Fitted", PFX + "Demo"):
        c = bpy.data.collections.get(cn)
        if c is None:
            continue
        obs += [o for o in c.objects
                if o.type == "MESH" and "Floor" not in o.name
                and "Stage" not in o.name]
    for ob in obs:
        prep(ob)
    bad = []
    for i in range(len(obs)):
        for j in range(i + 1, len(obs)):
            a, b = obs[i], obs[j]
            la, ha = boxes[a.name]
            lb, hb = boxes[b.name]
            if any(la[k] > hb[k] + 0.02 or lb[k] > ha[k] + 0.02 for k in range(3)):
                continue
            for ax, sg, v, m1, r1, c1, n1 in cache[a.name]:
                for ax2, sg2, v2, m2, r2, c2, n2 in cache[b.name]:
                    if ax != ax2 or sg != sg2 or abs(v - v2) > 4e-4 or m1 == m2:
                        continue
                    w = min(r1[1], r2[1]) - max(r1[0], r2[0])
                    h = min(r1[3], r2[3]) - max(r1[2], r2[2])
                    if w <= 0 or h <= 0 or w * h < min_area:
                        continue
                    if any(bvhs[o.name].ray_cast(c + n * 0.0008, n, 8.0)[0]
                           is not None
                           for o, c, n in ((a, c1, n1), (a, c2, n2),
                                           (b, c1, n1), (b, c2, n2))):
                        continue                       # something covers it
                    bad.append((w * h, a.name, b.name, m1, m2, "xyz"[ax], v))
    if report and bad:
        bad.sort(reverse=True)
        print("!! %d exposed coplanar clash(es) BETWEEN objects:" % len(bad))
        for ar, an, bn, m1, m2, ax, v in bad[:10]:
            print("   %.3f m2  %s x %s  %s/%s  %s=%.3f"
                  % (ar, an.replace(PFX, ""), bn.replace(PFX, ""),
                     m1.replace(PFX, ""), m2.replace(PFX, ""), ax, v))
    return bad


def demo_room(coll, org):
    """A 12 x 8 m room off the kit, to prove the lattice: corners on the
    intersections, straight walls on the points between them."""
    K = bpy.data.objects
    ox, oy = org
    x0, x1 = ox - 6.0, ox + 6.0
    y0, y1 = oy - 4.0, oy + 4.0
    ground_plane(coll, "Demo_Floor", ox, oy, 20.0, 16.0, top=-0.02)
    for (cx, cy, rot) in ((x0, y0, 0.0), (x1, y0, RAD(90)),
                          (x1, y1, RAD(180)), (x0, y1, RAD(270))):
        dup(K[PFX + "Wall_Corner"], coll, (cx, cy, 0.0), rot)
    south = ["Wall_Door", "Wall_Window"]
    north = ["Wall_Window_Round", "Wall_Broken"]
    for i, nm in enumerate(south):
        dup(K[PFX + nm], coll, (x0 + 4.0 * i + 4.0, y0, 0.0), 0.0)
    for i, nm in enumerate(north):
        dup(K[PFX + nm], coll, (x1 - 4.0 * i - 4.0, y1, 0.0), RAD(180))
    dup(K[PFX + "Wall_Arch"], coll, (x1, y0 + 4.0, 0.0), RAD(90))
    dup(K[PFX + "Wall_Window_Small"], coll, (x0, y0 + 4.0, 0.0), RAD(270))
    # dress the openings
    dup(K[PFX + "Door_Frame"], coll, (x0 + 4.0, y0, 0.0), 0.0)
    dup(K[PFX + "Door_Leaf"], coll, (x0 + 4.0 + DOOR_HINGE, y0, 0.0), RAD(-72))
    dup(K[PFX + "Window_Tall"], coll, (x0 + 8.0, y0, 0.0), 0.0)
    dup(K[PFX + "Window_Round"], coll, (x1 - 4.0, y1, 0.0), RAD(180))
    dup(K[PFX + "Arch_Door_Frame"], coll, (x1, y0 + 4.0, 0.0), RAD(90))
    dup(K[PFX + "Window_Small"], coll, (x0, y0 + 4.0, 0.0), RAD(270))
    dup(K[PFX + "Secret_Door"], coll,
        (x0 + 2.0, y1 - HT - 0.24, 0.0), RAD(180))
    dup(K[PFX + "Trapdoor_Frame"], coll, (ox + 3.0, oy, 0.0), 0.0)
    dup(K[PFX + "Trapdoor_Leaf"], coll, (ox + 3.0 + TRAP_HINGE, oy, 0.0), 0.0)
    pillar_run(coll, (ox - 12.0, oy - 14.0))


def int_rooms(coll, org):
    """Two rooms sharing ONE partition -- the check that the interior set reads
    as a room finish from BOTH sides, which is the whole claim of the family.

    Shot from either side (demo_int / demo_int2). The run also mixes the two
    families on one lattice: a `Pillar` on the return wall's joint where the rest
    of the run carries `Pilaster`, which is only legible if the stone column and
    the panelled one really are the same width on the same rung."""
    K = bpy.data.objects
    ox, oy = org
    ground_plane(coll, "Int_Floor", ox + 6.0, oy + 6.0, 36.0, 32.0, top=-0.02)
    # the partition itself: 16 m across the middle, with the door and window a
    # character actually uses and the smashed module at the far end
    for i, nm in enumerate(("Wall_Int_Straight", "Wall_Int_Door",
                            "Wall_Int_Window", "Wall_Int_Broken")):
        dup(K[PFX + nm], coll, (ox + 4.0 * i, oy, 0.0), 0.0)
    dup(K[PFX + "Door_Frame_Int"], coll, (ox + 4.0, oy, 0.0), 0.0)
    dup(K[PFX + "Door_Leaf"], coll, (ox + 4.0 + DOOR_HINGE, oy, 0.0), RAD(-64))
    dup(K[PFX + "Window_Tall"], coll, (ox + 8.0, oy, 0.0), 0.0)
    # West return: corner on the lattice intersection, then Wall_Int_Plain with
    # Pilasters dropped on the JOINTS -- the interior half of the Plain + column
    # trick, so the columns land every 8 m instead of every 4.
    # ★ Columns go on Plain JOINTS only. Dropping one on a joint where a
    # Straight-family module already carries its own end post puts two identical
    # pilasters in the same 0.34 m of wall -- the same geometry twice over, which
    # is the one clash no amount of deconfliction can fix.
    # ★ And no `Pillar` in here, deliberately: the two families DO mix on one
    # lattice (same width, same rung, and the catalogue rows prove it), but a
    # lavender stone column in the middle of the plate that exists to show a room
    # papered on both sides just reads as a mistake.
    dup(K[PFX + "Wall_Int_Corner"], coll, (ox - 4.0, oy, 0.0), 0.0)
    for i in range(3):
        dup(K[PFX + "Wall_Int_Plain"], coll, (ox - 4.0, oy + 4.0 * i + 4.0, 0.0),
            RAD(90))
    for j in (2.0, 6.0, 10.0, 14.0):      # a Plain run needs one on EVERY joint
        dup(K[PFX + "Pilaster"], coll, (ox - 4.0, oy + j, 0.0), RAD(90))
    # east return: the walk-through arch a room away from the door, then the
    # oculus above the dado -- both Straight-family, so their joint reads as one
    # full column the way a butted pair is meant to
    dup(K[PFX + "Wall_Int_Corner"], coll, (ox + 16.0, oy, 0.0), RAD(90))
    dup(K[PFX + "Wall_Int_Arch"], coll, (ox + 16.0, oy + 4.0, 0.0), RAD(90))
    dup(K[PFX + "Arch_Door_Frame_Int"], coll, (ox + 16.0, oy + 4.0, 0.0), RAD(90))
    dup(K[PFX + "Wall_Int_Window_Round"], coll, (ox + 16.0, oy + 8.0, 0.0),
        RAD(90))
    dup(K[PFX + "Wall_Int_Half"], coll, (ox + 16.0, oy + 11.0, 0.0), RAD(90))
    # ★ Cap the FAR joint of each Straight-family run. N modules carry N columns
    # and make N+1 joints, so the last one -- here where the partition meets the
    # east corner's wing, and at the top of the east return -- has none until a
    # free-standing Pilaster straddles it.
    dup(K[PFX + "Pilaster"], coll, (ox + 14.0, oy, 0.0), 0.0)
    dup(K[PFX + "Pilaster"], coll, (ox + 16.0, oy + 12.0, 0.0), RAD(90))


def pillar_run(coll, org):
    """The point of Wall_Plain: one 32 m run showing pillars at three different
    spacings against the same wall. Walls sit on the 4 m lattice, pillars on the
    joints between them -- i.e. 2 m off a wall's own pivot."""
    K = bpy.data.objects
    ox, oy = org
    ground_plane(coll, "Run_Floor", ox + 14.0, oy, 40.0, 8.0, top=-0.02)
    for i in range(8):
        dup(K[PFX + "Wall_Plain"], coll, (ox + 4.0 * i, oy, 0.0), 0.0)
    # every 4 m (as Wall_Straight would), then every 8 m, then every 12 m
    for x in (-2.0, 2.0, 6.0, 14.0, 26.0, 30.0):
        dup(K[PFX + "Pillar"], coll, (ox + x, oy, 0.0), 0.0)


# --------------------------------------------------------------- lighting --
def world_and_lights(scene, c_lgt):
    w = bpy.data.worlds.get(PFX + "World") or bpy.data.worlds.new(PFX + "World")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (0.055, 0.045, 0.105, 1.0)
    bg.inputs[1].default_value = 1.6
    nt.links.new(bg.outputs[0], o.inputs[0])
    scene.world = w
    try:
        scene.view_settings.view_transform = "Khronos PBR Neutral"
    except TypeError:
        pass
    # Three SUNS, not area lights: the catalogue rows are 60 m long and any
    # point light falls off to nothing a third of the way down them. Colours
    # come off the sheet -- magenta key, cyan fill, acid-green rake -- because a
    # neutral rig turns the purple wallpaper grey.
    # A sun with euler (rx, 0, rz) travels along (-sin rx sin rz, sin rx cos rz,
    # -cos rx). The catalogue is shot down +Y, so the key needs cos(rz) > 0 or it
    # lights the backs of every piece and the row renders as silhouettes.
    rig = ((PFX + "Key", 3.6, (1.00, 0.74, 0.90), (RAD(50), 0.0, RAD(22))),
           (PFX + "Fill", 1.7, (0.55, 0.86, 1.00), (RAD(64), 0.0, RAD(330))),
           (PFX + "Rake", 1.3, (0.74, 1.00, 0.58), (RAD(74), 0.0, RAD(190))))
    for name, en, col, rot in rig:
        ld = bpy.data.lights.new(name, "SUN")
        ld.energy, ld.color, ld.angle = en, col, RAD(9.0)
        ob = bpy.data.objects.new(name, ld)
        ob.rotation_euler = Euler(rot, "XYZ")
        c_lgt.objects.link(ob)


def _row_shots(tag, y, n, per=4, dist=22.0, lens=35.0, z=2.15, tz=1.95):
    """Straight-on shots stepping `per` pieces at a time along a catalogue row.

    Framed from the row's own geometry rather than by hand: a piece added to the
    middle of a row shifts everything after it, and hand-placed cameras then
    quietly stop pointing at what their name says."""
    d = {}
    for k, i in enumerate(range(0, n, per)):
        lo, hi = i, min(n, i + per) - 1
        cx = (lo + hi) / 2.0 * STEP
        d["%s_%s" % (tag, "abcdef"[k])] = ((cx, y - dist, z), (cx, y, tz), lens)
    return d


DX, DY = 6.0, DEMO_Y
IX, IY = 0.0, DEMO_Y - 30.0          # the interior-partition demo's origin
SHOTS = {
    # pulled back when the interior row was added -- the plate is only useful if
    # it holds ALL of the rows, and a fourth one shifts the whole layout toward
    # the lens
    "overview":   ((84.0, -82.0, 64.0), (34.0, 5.0, 0.0), 40),
    "demo_hero":  ((DX - 19.0, DY - 22.0, 9.5), (DX, DY, 1.6), 34),
    "demo_close": ((DX - 5.0, DY - 13.0, 2.4), (DX - 2.0, DY - 4.0, 1.8), 34),
    "demo_in":    ((DX - 3.0, DY - 2.6, 1.70), (DX + 3.5, DY + 2.0, 1.90), 20),
    "demo_top":   ((DX, DY - 18.0, 22.0), (DX, DY, 0.0), 40),
    # the Wall_Plain + Pillar spacing demo, shot along its 32 m face
    "demo_run":   ((DX + 2.0, DY - 32.0, 2.6), (DX + 2.0, DY - 14.0, 2.0), 20),
    "demo_run2":  ((DX - 14.0, DY - 25.0, 3.2), (DX + 6.0, DY - 14.0, 1.9), 34),
    # ★ The interior partition from BOTH sides, which is the entire claim of the
    # Wall_Int_ family: one plate per room, and neither may show a stone face.
    "demo_int":   ((IX - 7.0, IY - 15.0, 3.6), (IX + 6.0, IY + 1.0, 1.9), 30),
    # ★ The far side is shot from INSIDE the north room, not from outside its
    # returns -- stand off and the return wall is simply in the way, which is what
    # made the first version of this plate a picture of a corner.
    "demo_int2":  ((IX + 8.5, IY + 13.0, 3.1), (IX + 6.0, IY - 0.5, 1.70), 24),
    "demo_int3":  ((IX + 3.0, IY - 5.4, 1.72), (IX + 5.0, IY + 6.0, 1.90), 22),
}


def _px(name, items=None):
    """x of a named catalogue piece. Close-ups are derived from the piece list,
    never hardcoded: adding a piece mid-row shifts everything after it, and a
    hardcoded camera then quietly points at whatever moved into its place."""
    for i, (n, _) in enumerate(items or WALLS):
        if n == name:
            return i * STEP
    return 0.0


# corners only read from a three-quarter: straight on they are just a wall
SHOTS["walls_corner"] = ((_px("Wall_Corner") - 5.6, -7.4, 3.4),
                         (_px("Wall_Corner") + 2.4, 0.6, 1.9), 42)
SHOTS["walls_broken"] = ((_px("Wall_Broken"), -9.5, 2.1),
                         (_px("Wall_Broken"), 0.0, 2.0), 45)
_IY = ROW_Y["WallsInt"]
SHOTS["wallsint_corner"] = ((_px("Wall_Int_Corner", WALLS_INT) - 5.6, _IY - 7.4, 3.4),
                            (_px("Wall_Int_Corner", WALLS_INT) + 2.4, _IY + 0.6,
                             1.9), 42)
SHOTS["wallsint_broken"] = ((_px("Wall_Int_Broken", WALLS_INT), _IY - 9.5, 2.1),
                            (_px("Wall_Int_Broken", WALLS_INT), _IY, 2.0), 45)
# the panelled pilaster IS the interior answer to the quoin post, so it gets the
# same close look the stone one never needed: read it against its own wall
SHOTS["wallsint_post"] = ((_px("Pilaster", WALLS_INT) - 2.2, _IY - 4.6, 2.2),
                          (_px("Pilaster", WALLS_INT) + 0.6, _IY, 1.8), 50)
# the trapdoor lies flat -- edge-on in a row plate it is a pencil line
_tx = (_px("Trapdoor_Frame", DOORS) + _px("Trapdoor_Leaf", DOORS)) / 2.0
SHOTS["doors_trap"] = ((_tx, ROW_Y["Doors"] - 8.6, 8.0),
                       (_tx, ROW_Y["Doors"], 0.0), 40)
SHOTS.update(_row_shots("walls", ROW_Y["Walls"], len(WALLS)))
SHOTS.update(_row_shots("wallsint", ROW_Y["WallsInt"], len(WALLS_INT)))
SHOTS.update(_row_shots("doors", ROW_Y["Doors"], len(DOORS), dist=17.0, lens=38.0,
                        z=1.75, tz=1.55))
SHOTS.update(_row_shots("windows", ROW_Y["Windows"], len(WINDOWS), dist=15.0,
                        lens=38.0, z=1.95, tz=1.85))
SHOTS.update(_row_shots("fitted", ROW_Y["Windows"] + 9.0, len(FITTED)))


def aim(cam, loc, tgt, lens):
    cam.data.lens = lens
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


# Which collections a shot should SEE. Rows sit only 11-13 m apart so the
# catalogue stays compact to work in, which means a row camera stands level with
# -- or inside -- its neighbours. Isolating the row is cheaper than spreading the
# layout over 100 m, and gives clean sheet-style plates either way.
ISO = [PFX + "Walls", PFX + "Walls_Int", PFX + "Doors", PFX + "Windows",
       PFX + "Fitted", PFX + "Demo", PFX + "Stage", PFX + "Lab_Walls",
       PFX + "Lab_WallsInt", PFX + "Lab_Doors",
       PFX + "Lab_Windows", PFX + "Lab_Fitted"]
_ST = PFX + "Stage"
ROW_COLL = {"walls": [PFX + "Walls", PFX + "Lab_Walls", _ST],
            "wallsint": [PFX + "Walls_Int", PFX + "Lab_WallsInt", _ST],
            "doors": [PFX + "Doors", PFX + "Lab_Doors", _ST],
            "windows": [PFX + "Windows", PFX + "Lab_Windows", _ST],
            "fitted": [PFX + "Fitted", PFX + "Lab_Fitted", _ST],
            "demo": [PFX + "Demo"]}


def _isolate(tag):
    show = ROW_COLL.get(tag)
    for cn in ISO:
        c = bpy.data.collections.get(cn)
        if c is not None:
            c.hide_render = show is not None and cn not in show


def render_shots(out_dir, names=None, res=(1600, 900), samples=64):
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.data.scenes[SCENE]
    cam = bpy.data.objects[PFX + "Cam"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.eevee.taa_render_samples = samples
    for n in (names or SHOTS):
        if n.startswith("piece:"):
            ob = bpy.data.objects[PFX + n.split(":", 1)[1]]
            cx, ht = ob.location.x, max(1.2, ob.dimensions.z)
            aim(cam, (cx, ob.location.y - ht * 2.1, ht * 0.55),
                (cx, ob.location.y, ht * 0.52), 45)
            _isolate(None)
        else:
            aim(cam, *SHOTS[n])
            _isolate(n.rsplit("_", 1)[0])
        scene.render.filepath = (out_dir.rstrip("/") + "/"
                                 + n.replace("piece:", "") + ".png")
        bpy.ops.render.render(write_still=True, scene=SCENE)
    _isolate(None)
    aim(cam, *SHOTS["overview"])


# ------------------------------------------------------------------ unity --
def export_fbx(out_dir):
    """One FBX per kit piece, exported AT THE ORIGIN so the Unity prefab pivot
    is the module pivot, bevel applied, Unity axis convention.

    bake_space_transform=True + FBX_SCALE_ALL are load-bearing: without them
    Blender leaves the Z-up -> Y-up conversion in the node transform, Unity drops
    it, and every piece imports lying on its back at 1/100 scale with an identity
    rotation. Verify orientation by measuring Renderer.bounds, never by reading
    the transform."""
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.data.scenes[SCENE]
    view = scene.view_layers[0]
    written = []
    for cn in KIT_COLLS:
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
            with bpy.context.temp_override(scene=scene, view_layer=view):
                bpy.ops.export_scene.fbx(
                    filepath=fp, use_selection=True, object_types={"MESH"},
                    use_mesh_modifiers=True, mesh_smooth_type="FACE",
                    apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL",
                    bake_space_transform=True, axis_forward="-Z", axis_up="Y",
                    path_mode="STRIP", use_triangles=False)
            ob.location = keep
            written.append(ob.name)
    write_readme(out_dir, written)
    return written


README = """# Bite Club -- Haunted House Modular Wall Kit

Generated by `BiteClubKitGen.py` (Blender 5.2) from the concept sheet. One FBX
per piece, each exported **at the origin** so the Unity prefab pivot is the
module pivot.

## The grid

| | |
|---|---|
| Module width | **4 m** (`Wall_Half` = 2 m) |
| Wall height | **4 m** |
| Wall thickness | **0.30 m** |
| Corner wings | **2 m** from the corner axis |

Everything lives on ONE 4 m lattice: **corners sit on lattice intersections,
straight walls on the lattice points between them**. A corner's wing covers the
first 2 m of each run, so a wall of N modules needs a span of 4N + 4 m between
two corners. Room sizes are therefore multiples of 4 m, minimum 8 x 8.

Snap increment in Unity: **4 m** (2 m if you use `Wall_Half`).

## Spacing the stone pillars out

`Wall_Straight` carries a stone quoin post at **both** ends, so a run of them
puts a column every 4 m. When you want them further apart:

1. build the run out of **`Wall_Plain`** (and `Wall_Plain_Half`), which is the
   same wall with no end posts -- field, wainscot and head beam run edge to
   edge;
2. drop **`Pillar`** wherever you actually want a column.

`Pillar` is 0.68 m wide -- exactly the column two butted `Wall_Straight` ends
make, and it emits the identical dark beam block on top -- so the two ways of
building a wall are indistinguishable. Its pivot is the column centre, and it
belongs on a wall **joint**: 2 m from a wall's own pivot along the run. With
walls at x = 0, 4, 8, 12 the joints are at x = 2, 6, 10.

The damask does not restart at a butt joint: UVs are projected in each piece's
local space at 0.5 repeats/m over a whole-metre module, so the pattern runs
straight through. A `Wall_Plain` run reads as one continuous wall.

%s

## Pivots and orientation

Every wall piece's origin is the **bottom centre of its module footprint, on the
wall centre-line**, with the exterior facing Blender -Y -> **Unity +Z** at yaw 0.
Corner pieces pivot on the corner axis with wings running +X and +Y and the
convex side facing -X / -Y.

> **Verify orientation by measuring `Renderer.bounds` on an instantiated
> prefab, never by reading the transform.** The FBX is exported with
> `bake_space_transform=True`, so the Z-up -> Y-up conversion is baked into the
> vertices and the object rotation reads (0,0,0) whether or not it worked.

Walking a rectangular plan, the four corners are the same mesh at 0 / 90 / 180 /
270 degrees; check the first one by eye and the rest follow.

## Inserts share their host wall's pivot

Doors and windows are **not** baked into the walls. Drop the insert at the
*identical transform* as its host wall and it fits:

| Host wall | Takes |
|---|---|
| `Wall_Door` | `Door_Frame`, `Barricaded_Door`, `Secret_Door` (offset, see below) |
| `Wall_Door_Double` | `Double_Door_Frame` |
| `Wall_Arch` | `Arch_Door_Frame` |
| `Wall_Window` | `Window_Tall`, `Window_Boarded` |
| `Wall_Window_Small` | `Window_Small`, `Secret_Grate` |
| `Wall_Window_Round` | `Window_Round` |

Every `Wall_Int_*` host takes the same inserts as its exterior twin -- the
openings are one set of constants for both families.

## Hinges

Anything that swings is its own mesh with its origin **on the hinge axis**.
Place it at the wall's transform plus this local-X offset, then rotate about
local Y (Unity) only:

| Leaf | Offset from the wall pivot |
|---|---|
| `Door_Leaf` | x = %+.2f |
| `Double_Door_Leaf_L` | x = %+.2f |
| `Double_Door_Leaf_R` | x = %+.2f |
| `Arch_Door_Leaf` | x = %+.2f |
| `Secret_Door` (bookcase) | x = %+.2f, z = %+.2f (stands clear of the wall face) |
| `Trapdoor_Leaf` | x = %+.2f from `Trapdoor_Frame` |

`Trapdoor_Frame` pivots at the centre of a 2 x 2 m floor cell with its top face
at y = 0, so it drops into a floor tile with no vertical nudge.

## Clear openings (what a character controller has to fit through)

| Opening | Clear width | Clear height |
|---|---|---|
| Door | %.2f m | %.2f m |
| Double door | %.2f m | %.2f m |
| Arch (walk-through) | %.2f m | %.2f m |

The arch has a two-step threshold apron totalling %.2f m -- inside a standard
`CharacterController` step offset, but check it if yours is tightened.

## Trim standard

Every trim member in the kit picks from one small set of constants -- nothing
has a bespoke number. That is what makes a beam, a quoin, an architrave, a sill
and a window bar read as the same carpentry where they meet.

The three projection rungs step by a uniform 0.05 m and are a strict
hierarchy: **stone stands proud of the joinery it dies into, and the joinery
stands proud of the field.** That is not decoration -- two members at the same
projection put coplanar faces in the same place, and a `Pillar` dropped on a
`Wall_Plain` run z-fights against the chair rail for exactly that reason.

## Datum deconfliction

The ladder keeps members apart on the wall FACE. It cannot help on the module
datums -- `z = 0`, `z = H`, `x = +/-HW` -- because the whole meaning of a datum
is that every member has to stop flush on it so modules butt on the lattice. So
the shell's top face, the head beam's cap and the block over the post all landed
on `z = H` together: coplanar, all facing +Z, three different materials, and the
depth buffer choosing between them per pixel. Every wall in the kit carried
1.20 m2 of that on its top, another 1.20 on its bottom and 0.24-1.78 on each end,
and every insert clashed with its host wall on the floor datum and on the P2
rung. Wall tops strobed stone/wood as the camera moved.

`deconflict()` now runs on every piece: it sweeps each plane, fuses faces that
share verts into one surface, and gives each plane ONE owner -- the largest
surface -- with everything that genuinely overlaps it receding by 0.5 mm rungs,
assigned by greedy colouring so nothing goes deeper than it must. The largest
surface at `x = +/-HW` is always the structural shell, so **the butt joint and
the snapping lattice stay bit-exact**; only applied trim ever moves, by a hairline
no eye resolves. `lift_insert()` does the same across objects for the inserts,
which cannot see their host wall: an insert stands a hairline PROUDER on the
wall-face rungs (applied joinery reads as over the wall's own) and lifts off the
floor datum. The kit measures zero coplanar exposed surfaces after this pass.

Two traps if you touch it. The pass must run AFTER `recalc_face_normals()` --
`sl()` and `extrude_poly()` disagree on winding, and reading `f.normal` before
the recalc splits one plane into two opposed groups and recedes half of them
upward, into the open. And `mark_bevel_weights()` excludes datum edges from
chamfering by testing them against the datum, so that exclusion is a BAND
(`SEAM_BAND`) wide enough to hold the recession ladder; leave it an exact plane
and receded trim ends start taking the full 24 mm chamfer, which is the V-notch
down every joint the exclusion exists to prevent.

The bottom rung is 0.08 and not lower **because of the chamfer**. The Bevel
modifier runs with `use_clamp_overlap`, and the clamp is **global per mesh**:
one member thinner than 2 x the bevel width silently shrinks the chamfer on
the ENTIRE piece -- the same number in the modifier, a visibly sharper piece
on screen. Nothing in the kit may be thinner than 0.048 m in any axis, and no
arc ever runs tangent into a straight cut (each arc stops one chord short and
runs flat, hidden behind its ring). `audit_bevel()` checks the thickness floor
and `audit_chamfer()` measures the chamfer every piece actually got; both run
on every build and print anything off the kit norm.

| | Value | Used by |
|---|---|---|
| Rung 1 -- field | %.2f m | ashlar relief, wainscot boards, wall-side arch rings |
| Rung 2 -- trim | %.2f m | skirting, chair rail, beam body, architraves, plinth |
| Rung 3 -- stone | %.2f m | quoins, posts, `Pillar`, beam cap, sills, keystones |
| Stone course | %.2f m | quoins, ashlar, plinths, spalled patches |
| Ashlar block | %.2f m | two courses long, so the bond half-laps |
| Mortar joint | %.2f m | every stone joint |
| Voussoir | %.2f m of **arc length** | every arch, so a stone in the little oculus is the same size as one over the double door |
| Board width | %.2f m | every plank run: wainscot, door leaves, trapdoor |
| Applied batten | %.2f x %.2f m | barricade boards, boarded window, door ledges |
| Iron stock | %.2f m | straps, ring stock, grate bars, bolts |
| Architrave | %.2f m | every opening |
| Sill / lintel / plinth | %.2f m tall, lapping %.2f m | ONE block: window sill, flat lintel, door plinth |
| Arch ring depth | %.2f m | every arch |
| **Chamfer** | **%.3f m, %d segments** | **every edge on every piece** |
| Minimum member | **%.3f m** | below this the chamfer is silently clamped |

The chamfer is weight-limited on every piece in the kit (module-boundary edges
excluded so butted modules never show a hairline), never angle-limited on some
and weight-limited on others -- so the rounding radius is identical kit-wide.

Three rules follow from that and are worth knowing before you author anything
new:

- **One member, one section.** Sills, flat lintels and door plinths are all
  `stone_shelf()` -- the same height, projection and lap. Written out by hand
  they had drifted to six different sections, which is why two window walls'
  trim did not match under an identical chamfer. Likewise the host wall owns the
  masonry (reveal, ring, sill) and the insert owns the joinery: an insert that
  brought its own sill put two of them inside each other.
- **A quoin step must never exceed the column it is stepping.** `quoin_col`
  clamps the inset to what the column can spare; unclamped, a 0.12 m jamb went
  to zero width on its short courses, those courses were dropped, and the jamb
  came out as a row of disconnected blocks floating beside the opening. The
  host walls carry no side jambs at all now -- an opening gets a stone reveal
  and a voussoir ring, and the insert that drops into it brings the architrave.

- **A stone course never steps in and out at a module boundary.** The long/short
  quoin alternation is an inset on the FIELD side only. Stepping on both sides
  put every other course exactly ON the boundary plane, where edges are excluded
  from the bevel -- so one post came out half sharp and half rounded, and butting
  two modules left a notch at every short course.
- **Corners are ONE solid, never two butted boxes.** Two boxes meeting at a
  corner each carry a bevelled edge at the joint, so the chamfer cuts a V-groove
  down the corner; the quoin then reads as loose bricks and the wainscot shows a
  slot at the corner cell. Every L-shaped member -- the corner core, each quoin
  course, the skirting, the chair rail, the head beam -- is swept from one
  L polygon.

The field trim (wainscot, plinth, ashlar) runs the FULL module width and the
posts ride over it, so `Wall_Straight` and `Wall_Plain` + `Pillar` emit
identical joinery. Verified by ray-casting both constructions on a 14 118-point
grid: they differ only on the three silhouette-tangent columns, which is
knife-edge sampling, not geometry.

## Materials

%d shared materials. Slot order is canonical on every piece, so **slot 0 is the
-Y (exterior) wall face and slot 1 the +Y (interior) face** on every wall
module: recolouring a room inside and out is two material overrides and no new
geometry. On the `Wall_Int_*` family both of those faces are room faces, so slot
0 and slot 1 are simply **the two rooms** -- paper them differently and one
partition serves a purple parlour on one side and a green one on the other. The
interior pieces carry **no `BC_Stone` slot at all**; their reveals are wood.

| Slot name | Use |
|---|---|
| `BC_Wall_A` | wall face toward -Y / Unity +Z |
| `BC_Wall_B` | wall face toward +Y / Unity -Z |
| `BC_Stone` | ashlar, quoins, voussoirs, reveals |
| `BC_Wood` | beams, rails, boards |
| `BC_WoodDark` | door leaves, muntins, skirting |
| `BC_Iron` | straps, rings, grate, crack shadow |
| `BC_Glass` | glazing (transparent) |
| `BC_Book_A/B/C` | bookcase spines |

The Blender materials are procedural node graphs and **FBX cannot carry them** --
imported cold, every piece arrives untextured. Either assign your own URP
materials by slot name, or bake the Blender materials to tiling maps first.
UV density is 0.5 repeats/m over whole-metre modules, so a baked 0..1 tile
continues across a module joint instead of restarting.

## Rebuilding

    blender -b BiteClubKit.blend --python BiteClubKitGen.py

then call `export_fbx("<dir>")` for the FBX set, or `render_shots("<dir>")` for
the catalogue plates.

## Pieces (%d)

%s
"""


README_INT = """## Interior walls -- `Wall_Int_*`, a room on BOTH faces

Fourteen partition modules, one for every shape in the exterior set, finished as
the inside of a room on **both** sides: damask field, skirting + plank wainscot
+ chair rail, wood head beam. They carry **no stone at all** -- no quoin post, no
voussoir ring, no plinth, no ashlar, no threshold steps -- because those are the
outside of a building and a partition has two insides. Use them anywhere both
faces are seen from a room: between two rooms, along a corridor, around a
stairwell, dividing a hall.

What replaces the stone quoin is a **panelled wood pilaster**, %.2f m wide on the
same projection rung as the quoin, so the two families sit on ONE lattice and
butt without a step.

### The column sits WHOLE at one end -- build runs in +X / +Y

The stone family puts half a quoin at each module end and lets a butted pair read
as one post. That works for masonry and **does not work for timber**: the grain
runs along the boards, each module projects its UVs in its own local space, and
two halves meet with the figure jumping down the middle of the column. So an
interior module carries **one whole pilaster at its -X end** (and the heavy beam
block above it), never two halves.

The convention that falls out: **a module dresses its -X end, so runs are built
in +X / +Y away from a corner** -- the direction corner wings already run. Walk a
room anticlockwise from each corner and every joint is covered, floor to ceiling,
by the next module's column and block: the shell, the board ground, the skirting,
the chair rail and the head beam all butt *behind* timber, and no butt joint in
the kit is left in the open. Run a wall the other way and the joint at the corner
end is bare -- flip the module, or cap it with a free-standing `Pilaster`.

`Wall_Int_Straight` therefore puts its column immediately AFTER each joint;
`Wall_Int_Plain` + `Pilaster` puts one centred ON the joint. Both give a 0.68 m
column at every joint and both hide the butt; they differ only by 0.34 m in where
the column lands, so pick one per run rather than mixing them in the same wall.

**Cap the far end of a run.** N modules carry N columns and make N+1 joints, so
whichever end you finish on has a bare joint -- drop a free-standing `Pilaster`
on it. It straddles the joint, it is one mesh, and it is the same column the
walls carry, so it closes the run exactly. A `Wall_Int_Plain` run wants one on
*every* joint. Budget one extra Pilaster per run and the room has no exposed butt
joint anywhere.

| Interior piece | Exterior twin | Notes |
|---|---|---|
| `Wall_Int_Straight` / `_Half` | `Wall_Straight` / `Wall_Half` | whole pilaster at the -X end |
| `Wall_Int_Plain` / `_Plain_Half` | `Wall_Plain` / `Wall_Plain_Half` | no end columns -- butt in runs |
| `Pilaster` | `Pillar` | free-standing column, %.2f m wide, drop on a JOINT |
| `Wall_Int_Corner` / `_Corner_Inside` | same | convex / reflex corner post |
| `Wall_Int_Broken` | `Wall_Broken` | studs, noggin and snapped lath in the breach |
| `Wall_Int_Arch` | `Wall_Arch` | wood saddle instead of the stone step apron |
| `Wall_Int_Door` / `_Door_Double` | same | wood arch band, continuous |
| `Wall_Int_Window` / `_Window_Small` | same | wood stool where the outside has a stone sill |
| `Wall_Int_Window_Round` | same | wood ring |

**The openings are identical**, so every insert fits either family unchanged:
`Wall_Int_Door` takes `Door_Frame`, `Barricaded_Door` and `Secret_Door`,
`Wall_Int_Arch` takes `Arch_Door_Frame`, `Wall_Int_Window` takes `Window_Tall`
and `Window_Boarded`, and so on down the table in the next section. The catalogue
ships a `BC_Fitted` row that shows exactly this.

One insert to watch: **`Window_Round` brings a stone ring of its own** at the
prouder rung, so fitted into `Wall_Int_Window_Round` it covers the wall's wood
ring with stone. Override its `BC_Stone` slot for interior use, or leave the
oculus bare and let the wall's own ring frame it.

Two things follow from the shared lattice and are worth knowing before you build
a run:

- **Columns go on `Plain` joints only.** Dropping a `Pilaster` (or a `Pillar`) on
  a joint where a Straight-family module already carries its own end post puts
  two identical columns in the same 0.34 m of wall. Same geometry twice over is
  the one clash no depth-buffer trick can fix.
- **Partitions are the same 0.30 m thick as the outside walls.** A real interior
  stud wall would be thinner, but the thickness is what every insert's reveal,
  architrave and glazing depth is cut against -- thinning it would fork the
  entire door and window set for no gameplay gain.
"""


def write_readme(out_dir, written):
    rows = {}
    for n in written:
        rows.setdefault(n.replace(PFX, "").split("_")[0], []).append(n)
    listing = "\n".join(
        "- `%s`" % n.replace(PFX, "") for n in written)
    mats = len([m for m in CANON if m not in (LABEL, STAGE)])
    txt = README % (
        README_INT % (2 * PIL_W, 2 * PIL_W),
        DOOR_HINGE, -DD_HINGE, DD_HINGE, OP_A["hw"] - 0.05,
        SECRET_HINGE, -(HT + 0.24), TRAP_HINGE,
        2 * OP_D["hw"], OP_D["zs"] + OP_D["r"],
        2 * OP_DD["hw"], OP_DD["zs"] + OP_DD["r"],
        2 * OP_A["hw"], OP_A["zs"] + OP_A["r"] - OP_A["z0"],
        OP_A["z0"],
        P1, P2, P3, COURSE, BLOCK, GAP, VOUSS, PLANK_W, BOARD_W, BOARD_T,
        IRON_W, CASE, SILL_H, SILL_LAP, RING, BEVEL_W, BEVEL_SEG, BEVEL_MIN,
        mats, len(written), listing)
    with open(os.path.join(out_dir, "README.md"), "w") as fh:
        fh.write(txt)


if not globals().get("BC_NOBUILD"):
    print("BiteClubKit quads:", build())
