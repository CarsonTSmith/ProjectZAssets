"""
CarsonBuildingGen.py -- "Hotel Girafa": one building in the Deceive Inc. idiom,
built from NOTHING BUT the six materials the user hand-picked into the `Carson`
collection of Wall.blend.

    Terracotta Wall Blocks (Rounded Edge)  -> ground storey, arcade piers, roofs
    White plaster                          -> every piece of trim, and the
                                              tint() source for the coloured walls
    PZ_M_Stone                             -> plinth, kerbs, lamp posts
    Stone tiles                            -> street paving + rotunda floor
    Stylized Wooden Planks                 -> shutters, doors, balustrades, joinery
    Giraffe Skin Material                  -> awnings, parasols, the lobby rug

The only material NOT from that set is a flat pale-blue glass, because the six
contain no glazing and a facade of blind windows reads as a wall.

Massing: an L of two wings hinged on a round corner rotunda -- a five-arch
arcade at street level, teal drum above it, stepped terracotta dome and lantern
on top. The wings are coral stucco over a brick ground floor, with white
surrounds, wooden louvred shutters and balconies.

Run:  exec(open("/home/carson/Blender/ProjectZAssets/CarsonBuildingGen.py").read())
"""

import bpy, math, sys, importlib
from mathutils import Vector, Euler

sys.path.insert(0, "/home/carson/Blender/ProjectZAssets")
import BlockoutKit as BK
importlib.reload(BK)
MB = BK.MB

PFX = "CB_"
ROOT = "CarsonBuilding"
SCENE = "CarsonBuilding"

TAU = math.tau
RAD = math.radians


def srgb(h):
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f((h >> 16) & 255), f((h >> 8) & 255), f(h & 255))


# ------------------------------------------------------------------ palette --
BRICK = "Terracotta Wall Blocks (Rounded Edge)"
WHITE = "White plaster"
SAND  = "PZ_M_Stone"
TILE  = "Stone tiles"
WOOD  = "Stylized Wooden Planks"

CORAL = PFX + "Coral"       # tinted White plaster -- wing upper storeys
TEAL  = PFX + "Teal"        # tinted White plaster -- the drum
OCHRE = PFX + "Ochre"       # tinted White plaster -- signboards, bunting
ROSE  = PFX + "Rose"        # tinted White plaster -- bunting, parasol trim
LEAF  = PFX + "Leaf"        # tinted White plaster -- topiary
HIDE  = PFX + "Hide"        # Giraffe Skin, respaced
PANTILE = PFX + "Pantile"   # tinted brick -- raw brick roofs read near-black
GLASS = PFX + "Glass"

# repeats per metre; a 2 k texture at 0.4 repeats/m tiles every 2.5 m
UVS = {
    BRICK: 0.80, WHITE: 0.40, SAND: 0.42, TILE: 0.24, WOOD: 0.60,
    CORAL: 0.40, TEAL: 0.40, OCHRE: 0.45, ROSE: 0.45, LEAF: 0.50,
    PANTILE: 0.80, GLASS: 0.30,
}
ROOF_UV = 1.25          # brick courses shrunk until they read as pantiles

# --------------------------------------------------------------- dimensions --
R      = 5.20           # drum outer radius
WT     = 0.50           # wall thickness
WD     = 3.90           # wing half-depth
XE     = 17.00          # east end of the east wing
YN     = 13.00          # north end of the north wing

PLINTH = 0.80
SPRING = 3.30           # arcade springline
STRING = 5.45           # string course
UP_SILL, UP_H = 6.35, 2.55
WALL_TOP = 10.30        # wing eaves
DRUM_TOP = 11.40
GF_SILL, GF_H = 1.55, 2.55      # shopfront openings
FLOOR2 = 6.20           # rotunda gallery deck

TAN = math.sqrt(R * R - WD * WD)                 # 3.44: wing/drum tangent point
A0 = math.atan2(WD, -TAN)                        # 138.6 deg, west wing corner
A1 = math.atan2(-WD, TAN) + TAU                  # 311.4 deg, south wing corner
NBAY = 5
PIER_A = RAD(11.0)
ARCH_A = (A1 - A0 - (NBAY + 1) * PIER_A) / NBAY
ARCH_U = [A0 + PIER_A * (i + 1) + ARCH_A * (i + 0.5) for i in range(NBAY)]
ARCH_R = ARCH_A / 2.0 * (R - WT / 2.0)           # arch radius in metres


def M(n):
    return bpy.data.materials[n]


# ------------------------------------------------------------ arc machinery --
# The drum needs the same "wall split analytically around its openings" trick the
# straight walls get, but in polar coordinates. Every piece is a closed solid
# (an annular-sector prism) rather than a shell, so the bevel modifier has real
# geometry to work on; neighbouring sectors overlap a hair so no seam opens up.

def arc_slice(mb, r_in, r_out, a0, a1, z0, z1, mat, n=1, uvs=0.0):
    pad = RAD(0.15)
    for i in range(n):
        b0 = a0 + (a1 - a0) * i / n - pad
        b1 = a0 + (a1 - a0) * (i + 1) / n + pad
        pts = [(r_in * math.cos(b0), r_in * math.sin(b0), z0),
               (r_out * math.cos(b0), r_out * math.sin(b0), z0),
               (r_out * math.cos(b1), r_out * math.sin(b1), z0),
               (r_in * math.cos(b1), r_in * math.sin(b1), z0)]
        mb.extrude_poly(pts, (0, 0, z1 - z0), mat, uvs=uvs)


def arc_band(mb, r_in, r_out, a0, a1, z0, z1, opens, mat, step=RAD(5.0), uvs=0.0):
    """One storey of drum wall. `opens` = [(a_centre, a_half, z_bot, z_top), ...]"""
    def seg(b0, b1, w0, w1):
        if b1 - b0 > 1e-4 and w1 - w0 > 0.01:
            arc_slice(mb, r_in, r_out, b0, b1, w0, w1, mat,
                      n=max(1, int((b1 - b0) / step)), uvs=uvs)
    ops = sorted([o for o in opens if o[0] + o[1] > a0 and o[0] - o[1] < a1],
                 key=lambda o: o[0])
    cur = a0
    for ac, ah, zb, zt in ops:
        l, r = max(a0, ac - ah), min(a1, ac + ah)
        seg(cur, l, z0, z1)
        seg(l, r, z0, min(zb, z1))
        seg(l, r, max(zt, z0), z1)
        cur = max(cur, r)
    seg(cur, a1, z0, z1)


def arc_arch_head(mb, r_in, r_out, ac, ah, spring, top, mat, n=18):
    """Spandrel between a semicircular arch and the band above it."""
    rm = (r_in + r_out) / 2.0
    rad = ah * rm
    for i in range(n):
        b0 = ac - ah + 2 * ah * i / n
        b1 = ac - ah + 2 * ah * (i + 1) / n
        d = min(abs(((b0 + b1) / 2.0 - ac) * rm), rad)
        h = spring + math.sqrt(max(0.0, rad * rad - d * d))
        if top - h > 0.02:
            arc_slice(mb, r_in, r_out, b0, b1, h, top, mat)


def arc_arch_ring(mb, rb, ac, ah, spring, thick, ring_w, mat, segs=16):
    """White archivolt following an arch in the drum's tangent plane."""
    rm = rb
    rad = ah * rm
    for i in range(segs):
        phi = math.pi * (i + 0.5) / segs
        du = (math.pi * rad / segs) * 1.14
        rr = rad + ring_w / 2.0
        u, w = rr * math.cos(phi), spring + rr * math.sin(phi)
        p = (rm * math.cos(ac) - u * math.sin(ac),
             rm * math.sin(ac) + u * math.cos(ac), w)
        mb.box(p, (du, thick, ring_w), mat,
               rot=(0, math.pi / 2 - phi, ac + math.pi / 2))


def at(a, r, z):
    return (r * math.cos(a), r * math.sin(a), z)


def tangent_box(mb, ac, r, z, du, thick, dz, mat, uvs=0.0):
    """Box sitting on the drum, its length running along the tangent."""
    mb.box(at(ac, r, z), (du, thick, dz), mat, rot=(0, 0, ac + math.pi / 2), uvs=uvs)


# -------------------------------------------------- straight-wall machinery --

def framer(mb, axis, fixed, inward):
    def place(u, w, du, dw, thick, mat, off=0.0, uvs=0.0):
        pos = fixed + inward * (thick / 2.0 + off)
        if axis == "X":
            mb.box((u, pos, w), (du, thick, dw), mat, uvs=uvs)
        else:
            mb.box((pos, u, w), (thick, du, dw), mat, uvs=uvs)
    return place


def band(place, a0, a1, z0, z1, opens, thick, mat, uvs=0.0):
    ops = sorted([o for o in opens if o[0] - o[1] < a1 and o[0] + o[1] > a0],
                 key=lambda o: o[0])
    cur = a0
    for uc, hw, zb, zt in ops:
        l, r = max(a0, uc - hw), min(a1, uc + hw)
        if l - cur > 0.01:
            place((cur + l) / 2.0, (z0 + z1) / 2.0, l - cur, z1 - z0, thick, mat, uvs=uvs)
        if zb - z0 > 0.01:
            place((l + r) / 2.0, (z0 + zb) / 2.0, r - l, zb - z0, thick, mat, uvs=uvs)
        if z1 - zt > 0.01:
            place((l + r) / 2.0, (zt + z1) / 2.0, r - l, z1 - zt, thick, mat, uvs=uvs)
        cur = max(cur, r)
    if a1 - cur > 0.01:
        place((cur + a1) / 2.0, (z0 + z1) / 2.0, a1 - cur, z1 - z0, thick, mat, uvs=uvs)


def surround(place, uc, sill, ow, oh, proj=0.07):
    B = 0.16
    place(uc, sill - B / 2.0, ow + 2 * B, B, 0.18, M(WHITE), off=-proj)
    place(uc, sill + oh + B / 2.0, ow + 2 * B, B, 0.18, M(WHITE), off=-proj)
    for s in (-1, 1):
        place(uc + s * (ow + B) / 2.0, sill + oh / 2.0, B, oh, 0.18, M(WHITE), off=-proj)
    place(uc, sill - 0.16, ow + 0.75, 0.14, 0.32, M(WHITE), off=-0.17)
    place(uc, sill + oh + 0.33, ow + 0.88, 0.22, 0.36, M(WHITE), off=-0.19)


def sash(place, uc, sill, ow, oh, thick=WT):
    place(uc, sill + oh / 2.0, ow, oh, 0.07, M(GLASS), off=thick - 0.15)
    place(uc, sill + oh / 2.0, ow, 0.07, 0.11, M(WHITE), off=thick - 0.18)
    place(uc, sill + oh / 2.0, 0.07, oh, 0.11, M(WHITE), off=thick - 0.18)


def shutters(mb, axis, fixed, inward, uc, sill, ow, oh):
    lw = ow / 2.0 * 0.94
    for s in (-1, 1):
        cu = uc + s * (ow / 2.0 + lw / 2.0 + 0.06)
        pos = fixed - inward * 0.12

        def blk(u, w, du, dw, th):
            if axis == "X":
                mb.box((u, pos - inward * th / 2.0, w), (du, th, dw), M(WOOD))
            else:
                mb.box((pos - inward * th / 2.0, u, w), (th, du, dw), M(WOOD))
        wc = sill + oh / 2.0
        blk(cu, wc + oh / 2.0 - 0.07, lw, 0.14, 0.09)
        blk(cu, wc - oh / 2.0 + 0.07, lw, 0.14, 0.09)
        for e in (-1, 1):
            blk(cu + e * (lw / 2.0 - 0.05), wc, 0.10, oh, 0.09)
        for i in range(8):
            blk(cu, wc - oh / 2.0 + oh * (i + 0.5) / 8, lw - 0.17, oh / 8 * 0.58, 0.055)


def balusters(mb, p0, p1, top, mat_rail=None):
    """Turned wooden balustrade between two points."""
    p0, p1 = Vector(p0), Vector(p1)
    L = (p1 - p0).length
    n = max(2, int(L / 0.26))
    rail = mat_rail or M(WOOD)
    mb.beam(p0 + Vector((0, 0, top)), p1 + Vector((0, 0, top)), 0.20, 0.13, M(WHITE))
    mb.beam(p0 + Vector((0, 0, 0.06)), p1 + Vector((0, 0, 0.06)), 0.20, 0.12, M(WHITE))
    for k in range(1, n):
        q = p0.lerp(p1, k / n)
        mb.cyl((q.x, q.y, q.z + top / 2.0), 0.052, top - 0.12, rail, segments=8,
               radius_top=0.052)
        mb.cyl((q.x, q.y, q.z + top * 0.42), 0.082, top * 0.34, rail, segments=8)


def balcony(mb, axis, fixed, inward, place, uc, sill, ow):
    place(uc, sill - 0.32, ow + 1.15, 0.16, 1.05, M(WHITE), off=-0.86)
    for s in (-1, 1):
        place(uc + s * (ow + 1.0) / 2.0, sill - 0.52, 0.34, 0.34, 0.7, M(WHITE), off=-0.55)
    d = 0.80
    if axis == "X":
        y = fixed - inward * d
        a = (uc - (ow + 1.05) / 2.0, y, sill - 0.22)
        b = (uc + (ow + 1.05) / 2.0, y, sill - 0.22)
        s0 = (a[0], fixed, a[2])
        s1 = (b[0], fixed, b[2])
    else:
        x = fixed - inward * d
        a = (x, uc - (ow + 1.05) / 2.0, sill - 0.22)
        b = (x, uc + (ow + 1.05) / 2.0, sill - 0.22)
        s0 = (fixed, a[1], a[2])
        s1 = (fixed, b[1], b[2])
    balusters(mb, a, b, 0.92)
    balusters(mb, s0, a, 0.92)
    balusters(mb, b, s1, 0.92)


def cornice(place, mid, L, top=WALL_TOP):
    for ww, hh, dz in ((0.30, 0.22, 0.0), (0.58, 0.30, 0.25),
                       (0.86, 0.26, 0.54), (0.42, 0.52, 0.90)):
        place(mid, top - 0.55 + dz, L + ww, hh, WT + ww, M(WHITE), off=-ww / 2.0)


# -------------------------------------------------------------------- drum ---

def drum(coll):
    mb = MB("Drum", PFX)
    r_in, r_out = R - WT, R
    rm = R - WT / 2.0

    # plinth + brick ground storey, five open arches on the exposed arc
    mb.ring((0, 0, PLINTH / 2.0), r_in - 0.2, R + 0.16, PLINTH, M(SAND), segments=72)
    opens = [(u, ARCH_A / 2.0, PLINTH, 1e6) for u in ARCH_U]
    arc_band(mb, r_in, r_out, A0, A1, PLINTH, STRING, opens, M(BRICK))
    arc_band(mb, r_in, r_out, A1, A0 + TAU, PLINTH, STRING, [], M(BRICK))
    for u in ARCH_U:
        arc_arch_head(mb, r_in, r_out, u, ARCH_A / 2.0, SPRING, STRING, M(BRICK))
        arc_arch_ring(mb, rm, u, ARCH_A / 2.0, SPRING, WT + 0.26, 0.34, M(WHITE))
        tangent_box(mb, u, R + 0.10, SPRING + ARCH_R + 0.34, 0.42, WT + 0.30, 0.68, M(WHITE))
        # impost blocks either side of the arch
        for s in (-1, 1):
            tangent_box(mb, u + s * (ARCH_A / 2.0 + PIER_A / 2.0), R + 0.06,
                        SPRING + 0.15, PIER_A * rm + 0.24, WT + 0.22, 0.28, M(WHITE))

    # string course, teal upper storey, balcony
    mb.ring((0, 0, STRING + 0.19), r_in - 0.1, R + 0.26, 0.38, M(WHITE), segments=72)
    ups = [(u, RAD(6.4), UP_SILL, UP_SILL + UP_H + 0.3) for u in ARCH_U]
    arc_band(mb, r_in, r_out, A0, A1, STRING + 0.38, DRUM_TOP - 0.95, ups, M(TEAL))
    arc_band(mb, r_in, r_out, A1, A0 + TAU, STRING + 0.38, DRUM_TOP - 0.95, [], M(TEAL))
    for u in ARCH_U:
        hw = RAD(6.4) * rm
        tangent_box(mb, u, R - 0.07, UP_SILL + (UP_H + 0.3) / 2.0,
                    2 * hw, 0.10, UP_H + 0.3, M(GLASS))
        for s in (-1, 1):
            tangent_box(mb, u + s * RAD(7.0), R + 0.02, UP_SILL + (UP_H + 0.3) / 2.0,
                        0.30, WT + 0.14, UP_H + 0.75, M(WHITE))
        tangent_box(mb, u, R + 0.02, UP_SILL + UP_H + 0.46, 2 * hw + 0.72, WT + 0.14,
                    0.26, M(WHITE))
        tangent_box(mb, u, R + 0.02, UP_SILL - 0.16, 2 * hw + 0.86, WT + 0.30, 0.20, M(WHITE))

    # wrap-around balcony on the exposed arc
    mb.ring((0, 0, UP_SILL - 0.42), R - 0.1, R + 0.95, 0.20, M(WHITE), segments=72)
    n = 46
    for i in range(n):
        a = A0 + (A1 - A0) * i / n
        b = A0 + (A1 - A0) * (i + 1) / n
        balusters(mb, at(a, R + 0.78, UP_SILL - 0.32), at(b, R + 0.78, UP_SILL - 0.32), 0.90)

    # cornice + parapet + stepped terracotta dome + lantern
    for rr, hh, dz in ((R + 0.20, 0.24, 0.0), (R + 0.46, 0.30, 0.26),
                       (R + 0.72, 0.26, 0.55), (R + 0.30, 0.44, 0.90)):
        mb.ring((0, 0, DRUM_TOP - 0.85 + dz), r_in - 0.05, rr, hh, M(WHITE), segments=72)
    dz0 = DRUM_TOP + 0.20
    STEPS, DR, DH = 11, R - 0.35, 4.30
    for i in range(STEPS):
        t0 = math.pi / 2 * i / STEPS
        t1 = math.pi / 2 * (i + 1) / STEPS
        mb.cyl((0, 0, dz0 + DH * math.sin(t0) + (DH * (math.sin(t1) - math.sin(t0))) / 2.0),
               DR * math.cos(t0), DH * (math.sin(t1) - math.sin(t0)) + 0.06,
               M(PANTILE), segments=48, radius_top=DR * math.cos(t1), uvs=ROOF_UV)
    lz = dz0 + DH
    mb.cyl((0, 0, lz + 0.18), 1.00, 0.36, M(WHITE), segments=32)
    mb.cyl((0, 0, lz + 1.10), 0.72, 1.55, M(WHITE), segments=16)
    for i in range(8):
        a = TAU * i / 8
        mb.box((0.60 * math.cos(a), 0.60 * math.sin(a), lz + 1.10), (0.13, 0.13, 1.5),
               M(WOOD), rot=(0, 0, a))
    mb.cyl((0, 0, lz + 2.00), 0.90, 0.24, M(WHITE), segments=32)
    mb.cyl((0, 0, lz + 2.72), 0.86, 1.25, M(PANTILE), segments=24, radius_top=0.06,
           uvs=ROOF_UV)
    mb.sphere((0, 0, lz + 3.50), 0.20, M(WHITE), segments=14)
    return mb.finish(coll, origin=(0, 0, 0), bevel=0.035, uv_scale=1.0)


# ------------------------------------------------------------------- wings ---
# Each wing: brick ground storey with shopfronts, coral upper storey with
# shuttered windows and balconies, hipped terracotta roof.

WINGS = (
    # name, axis, outer fixed, inward, a0, a1, bays, roof-extent
    ("E", "X", -WD, 1, TAN, XE, 4),
    ("N", "Y", -WD, 1, TAN, YN, 3),
)


def wing_facade(mb, axis, fixed, inward, a0, a1, nbay):
    place = framer(mb, axis, fixed, inward)
    L, mid = a1 - a0, (a0 + a1) / 2.0
    us = [a0 + L * (i + 0.5) / nbay for i in range(nbay)]
    place(mid, PLINTH / 2.0, L + 0.3, PLINTH, WT + 0.30, M(SAND), off=-0.15)
    band(place, a0, a1, PLINTH, STRING,
         [(u, 1.20, GF_SILL, GF_SILL + GF_H) for u in us], WT, M(BRICK))
    place(mid, STRING + 0.19, L + 0.42, 0.38, WT + 0.38, M(WHITE), off=-0.19)
    band(place, a0, a1, STRING + 0.38, WALL_TOP,
         [(u, 0.70, UP_SILL, UP_SILL + UP_H) for u in us], WT, M(CORAL))
    for u in us:
        # shopfront: wooden frame, glass, stall riser
        place(u, GF_SILL + GF_H / 2.0, 2.40, GF_H, 0.09, M(GLASS), off=WT - 0.16)
        place(u, GF_SILL + GF_H / 2.0, 2.52, 0.13, 0.16, M(WOOD), off=WT - 0.20)
        for s in (-1, 1):
            place(u + s * 1.20, GF_SILL + GF_H / 2.0, 0.14, GF_H + 0.2, 0.18,
                  M(WOOD), off=WT - 0.22)
            place(u + s * 0.40, GF_SILL + GF_H / 2.0, 0.08, GF_H, 0.12,
                  M(WOOD), off=WT - 0.20)
        place(u, GF_SILL - 0.22, 2.70, 0.30, 0.26, M(WHITE), off=-0.13)
        place(u, GF_SILL + GF_H + 0.30, 2.80, 0.28, 0.30, M(WHITE), off=-0.15)
        # upper window
        sash(place, u, UP_SILL, 1.40, UP_H)
        surround(place, u, UP_SILL, 1.40, UP_H)
    cornice(place, mid, L)
    return us, place


def wing(coll, name, axis, fixed, inward, a0, a1, nbay):
    mb = MB("Wing_" + name, PFX)
    us, place = wing_facade(mb, axis, fixed, inward, a0, a1, nbay)
    for u in us:
        shutters(mb, axis, fixed, inward, u, UP_SILL, 1.40, UP_H)
        balcony(mb, axis, fixed, inward, place, u, UP_SILL, 1.40)

    # inner (courtyard) elevation and the far end wall -- plainer, but the
    # plinth/string/cornice have to carry round or the corners read unfinished
    far = a1
    inner = framer(mb, axis, -fixed, -1)
    L, mid = a1 - a0, (a0 + a1) / 2.0
    inner(mid, PLINTH / 2.0, L + 0.3, PLINTH, WT + 0.30, M(SAND), off=-0.15)
    iu = [a0 + L * (i + 0.5) / nbay for i in range(nbay)]
    band(inner, a0, a1, PLINTH, STRING,
         [(u, 0.75, GF_SILL, GF_SILL + GF_H) for u in iu], WT, M(BRICK))
    inner(mid, STRING + 0.19, L + 0.42, 0.38, WT + 0.38, M(WHITE), off=-0.19)
    band(inner, a0, a1, STRING + 0.38, WALL_TOP,
         [(u, 0.70, UP_SILL, UP_SILL + UP_H) for u in iu], WT, M(CORAL))
    for u in iu:
        sash(inner, u, GF_SILL, 1.50, GF_H)
        surround(inner, u, GF_SILL, 1.50, GF_H)
        sash(inner, u, UP_SILL, 1.40, UP_H)
        surround(inner, u, UP_SILL, 1.40, UP_H)
        shutters(mb, axis, -fixed, -1, u, UP_SILL, 1.40, UP_H)
    cornice(inner, mid, L)

    end = framer(mb, "Y" if axis == "X" else "X", far, -1)
    end(0, PLINTH / 2.0, 2 * WD + 0.3, PLINTH, WT + 0.30, M(SAND), off=-0.15)
    eu = (-WD / 2.0, WD / 2.0)
    band(end, -WD, WD, PLINTH, STRING,
         [(u, 0.75, GF_SILL, GF_SILL + GF_H) for u in eu], WT, M(BRICK))
    end(0, STRING + 0.19, 2 * WD + 0.42, 0.38, WT + 0.38, M(WHITE), off=-0.19)
    band(end, -WD, WD, STRING + 0.38, WALL_TOP,
         [(u, 0.70, UP_SILL, UP_SILL + UP_H) for u in eu], WT, M(CORAL))
    for u in eu:
        sash(end, u, GF_SILL, 1.50, GF_H)
        surround(end, u, GF_SILL, 1.50, GF_H)
        sash(end, u, UP_SILL, 1.40, UP_H)
        surround(end, u, UP_SILL, 1.40, UP_H)
        shutters(mb, "Y" if axis == "X" else "X", far, -1, u, UP_SILL, 1.40, UP_H)
    cornice(end, 0, 2 * WD)

    # quoins on the free corner
    for k in range(18):
        z = PLINTH + 0.32 + k * 0.56
        if z > WALL_TOP - 1.1:
            break
        for sy in (-1, 1):
            if axis == "X":
                if k % 2 == 0:
                    mb.box((far - 0.55, sy * (WD + 0.06), z), (1.10, WT + 0.12, 0.46), M(WHITE))
                else:
                    mb.box((far + 0.06, sy * (WD - 0.55), z), (WT + 0.12, 1.10, 0.46), M(WHITE))
            else:
                if k % 2 == 0:
                    mb.box((sy * (WD + 0.06), far - 0.55, z), (WT + 0.12, 1.10, 0.46), M(WHITE))
                else:
                    mb.box((sy * (WD - 0.55), far + 0.06, z), (1.10, WT + 0.12, 0.46), M(WHITE))
    return mb.finish(coll, origin=(0, 0, 0), bevel=0.035)


def wing_roof(coll, name, axis, a0, a1):
    mb = MB("Roof_" + name, PFX)
    EO = 0.85
    ez, rz = WALL_TOP, WALL_TOP + 2.55
    lo, hi = a0 - 0.4, a1 + EO
    w = WD + EO
    inset = w                                      # 45 deg hips
    if axis == "X":
        A, B, C, D = (lo, -w, ez), (hi, -w, ez), (hi, w, ez), (lo, w, ez)
        R0, R1 = (lo, 0, rz), (hi - inset, 0, rz)
    else:
        A, B, C, D = (-w, lo, ez), (-w, hi, ez), (w, hi, ez), (w, lo, ez)
        R0, R1 = (0, lo, rz), (0, hi - inset, rz)
    for pts in ((A, B, R1, R0), (B, C, R1), (C, D, R0, R1), (D, A, R0)):
        mb.extrude_poly(list(pts), (0, 0, -0.30), M(PANTILE), uvs=ROOF_UV)
    # eaves fascia + ridge cap
    if axis == "X":
        for s in (-1, 1):
            mb.box(((lo + hi) / 2.0, s * w, ez - 0.34), (hi - lo, 0.18, 0.40), M(WHITE))
        mb.box((hi, 0, ez - 0.34), (0.18, 2 * w, 0.40), M(WHITE))
        mb.box(((R0[0] + R1[0]) / 2.0, 0, rz + 0.06), (R1[0] - R0[0], 0.36, 0.30),
               M(PANTILE), uvs=ROOF_UV)
        cx = hi - 3.2
        mb.box((cx, 1.9, ez + 1.5), (1.05, 1.05, 2.9), M(BRICK), uvs=0.85)
        mb.box((cx, 1.9, ez + 3.05), (1.34, 1.34, 0.30), M(WHITE))
    else:
        for s in (-1, 1):
            mb.box((s * w, (lo + hi) / 2.0, ez - 0.34), (0.18, hi - lo, 0.40), M(WHITE))
        mb.box((0, hi, ez - 0.34), (2 * w, 0.18, 0.40), M(WHITE))
        mb.box((0, (R0[1] + R1[1]) / 2.0, rz + 0.06), (0.36, R1[1] - R0[1], 0.30),
               M(PANTILE), uvs=ROOF_UV)
        cy = hi - 3.2
        mb.box((1.9, cy, ez + 1.5), (1.05, 1.05, 2.9), M(BRICK), uvs=0.85)
        mb.box((1.9, cy, ez + 3.05), (1.34, 1.34, 0.30), M(WHITE))
    return mb.finish(coll, origin=(0, 0, 0), bevel=0.03)


# ---------------------------------------------------------------- dressing ---

def dressing(coll):
    mb = MB("Dressing", PFX)

    def awning(axis, fixed, inward, uc, half, ztop, drop=0.90, proj=1.75):
        n = 9
        for k in range(n):
            t0 = uc - half + 2 * half * k / n
            t1 = uc - half + 2 * half * (k + 1) / n
            m = M(HIDE) if k % 2 == 0 else M(TEAL)
            o, d = fixed - inward * 0.05, fixed - inward * proj
            if axis == "X":
                pts = [(t0, o, ztop), (t1, o, ztop), (t1, d, ztop - drop), (t0, d, ztop - drop)]
            else:
                pts = [(o, t0, ztop), (o, t1, ztop), (d, t1, ztop - drop), (d, t0, ztop - drop)]
            mb.extrude_poly(pts, (0, 0, -0.09), m)
        e = fixed - inward * (proj + 0.03)
        if axis == "X":
            mb.box((uc, e, ztop - drop - 0.16), (2 * half, 0.13, 0.30), M(WHITE))
        else:
            mb.box((e, uc, ztop - drop - 0.16), (0.13, 2 * half, 0.30), M(WHITE))

    for _n, axis, fixed, inward, a0, a1, nbay in WINGS:
        L = a1 - a0
        for i in range(nbay):
            u = a0 + L * (i + 0.5) / nbay
            awning(axis, fixed, inward, u, 1.45, GF_SILL + GF_H + 0.60)

    # hanging shop sign on each wing
    for _n, axis, fixed, inward, a0, a1, nbay in WINGS:
        u = a0 + (a1 - a0) * 0.30
        if axis == "X":
            p0, p1 = (u, fixed - 0.05, STRING - 0.55), (u, fixed - 1.55, STRING - 0.55)
            mb.beam(p0, p1, 0.10, 0.10, M(WOOD))
            mb.beam((u, fixed - 1.48, STRING - 0.55), (u, fixed - 1.48, STRING - 1.05),
                    0.06, 0.06, M(WOOD))
            mb.box((u, fixed - 1.48, STRING - 1.60), (2.10, 0.13, 1.05), M(OCHRE))
            mb.box((u, fixed - 1.56, STRING - 1.60), (1.72, 0.05, 0.72), M(WHITE))
        else:
            p0, p1 = (fixed - 0.05, u, STRING - 0.55), (fixed - 1.55, u, STRING - 0.55)
            mb.beam(p0, p1, 0.10, 0.10, M(WOOD))
            mb.beam((fixed - 1.48, u, STRING - 0.55), (fixed - 1.48, u, STRING - 1.05),
                    0.06, 0.06, M(WOOD))
            mb.box((fixed - 1.48, u, STRING - 1.60), (0.13, 2.10, 1.05), M(OCHRE))
            mb.box((fixed - 1.56, u, STRING - 1.60), (0.05, 1.72, 0.72), M(WHITE))

    # Curved steps, but only across the exposed arc -- a full ring would run the
    # podium straight through both wings' plinths.
    for k, (r0, r1, top) in enumerate(((R + 0.16, R + 0.82, 0.54),
                                       (R + 0.82, R + 1.50, 0.27))):
        arc_slice(mb, r0, r1, A0 - RAD(4), A1 + RAD(4), 0.0, top, M(SAND),
                  n=70)

    # paving, kerb, planters, lamps, cafe sets
    mb.box((0, 0, -0.14), (400, 400, 0.28), M(TILE))

    def lamp_post(x, y):
        mb.box((x, y, 0.26), (0.52, 0.52, 0.52), M(SAND))
        mb.cyl((x, y, 2.20), 0.10, 3.40, M(SAND), segments=12, radius_top=0.075)
        mb.cyl((x, y, 3.98), 0.22, 0.16, M(WHITE), segments=12)
        mb.cyl((x, y, 4.36), 0.19, 0.62, M(GLASS), segments=6, radius_top=0.14)
        mb.cyl((x, y, 4.76), 0.17, 0.22, M(WOOD), segments=6, radius_top=0.04)
        return (x, y, 4.16)

    def planter(x, y):
        mb.box((x, y, 0.34), (1.10, 1.10, 0.68), M(BRICK))
        mb.box((x, y, 0.72), (1.26, 1.26, 0.14), M(WHITE))
        mb.sphere((x, y, 1.45), 0.72, M(LEAF), segments=16)
        mb.sphere((x, y, 2.25), 0.52, M(LEAF), segments=14)

    def cafe(x, y, a=0.0):
        mb.cyl((x, y, 0.36), 0.06, 0.72, M(WOOD), segments=8)
        mb.cyl((x, y, 0.74), 0.62, 0.07, M(WOOD), segments=20)
        for i in range(3):
            b = a + TAU * i / 3
            cx, cy = x + 1.05 * math.cos(b), y + 1.05 * math.sin(b)
            mb.box((cx, cy, 0.22), (0.44, 0.44, 0.06), M(WOOD), rot=(0, 0, b))
            for s in (-1, 1):
                mb.box((cx + 0.18 * math.cos(b + s * 1.2), cy + 0.18 * math.sin(b + s * 1.2), 0.11),
                       (0.06, 0.06, 0.22), M(WOOD))
            mb.box((cx - 0.20 * math.cos(b), cy - 0.20 * math.sin(b), 0.44),
                   (0.08, 0.42, 0.50), M(WOOD), rot=(0, 0, b))

    def parasol(x, y):
        mb.cyl((x, y, 1.15), 0.055, 2.30, M(WOOD), segments=8)
        n = 8
        for i in range(n):
            b0, b1 = TAU * i / n, TAU * (i + 1) / n
            m = M(HIDE) if i % 2 == 0 else M(WHITE)
            mb.tri((x, y, 2.55),
                   (x + 1.45 * math.cos(b0), y + 1.45 * math.sin(b0), 2.05),
                   (x + 1.45 * math.cos(b1), y + 1.45 * math.sin(b1), 2.05), m)
            mb.tri((x, y, 2.48),
                   (x + 1.45 * math.cos(b1), y + 1.45 * math.sin(b1), 1.98),
                   (x + 1.45 * math.cos(b0), y + 1.45 * math.sin(b0), 1.98), m)
        mb.sphere((x, y, 2.62), 0.10, M(WOOD), segments=10)

    lp = []
    lp.append(lamp_post(-7.6, -6.4))
    lp.append(lamp_post(9.0, -7.2))
    lp.append(lamp_post(-8.4, 9.5))
    for a in (RAD(196), RAD(254)):
        planter(*at(a, R + 2.9, 0)[:2])
    planter(6.6, -6.2)
    planter(-6.4, 6.0)
    cafe(-9.2, -3.4, 0.4)
    cafe(11.2, -6.6, 1.1)
    parasol(-9.2, -3.4)
    parasol(11.2, -6.6)

    # Papel-picado bunting. Both ends have to sit OUTSIDE the two wing walls or
    # the string is drawn straight through the building: anchor on the drum's
    # exposed arc at r > R, below the wing eaves, and run to a lamp post on the
    # same side of that wall.
    def bunting(p0, p1, sag, cols):
        p0, p1 = Vector(p0), Vector(p1)
        d = (p1 - p0)
        nrm = Vector((-d.y, d.x, 0.0))
        nrm = nrm.normalized() * 0.21 if nrm.length > 1e-5 else Vector((0.21, 0, 0))
        n = 15
        prev = None
        for i in range(n + 1):
            t = i / n
            q = p0.lerp(p1, t)
            q.z -= sag * math.sin(math.pi * t)
            if prev is not None:
                mb.beam(prev, q, 0.035, 0.035, M(WOOD))
                mid = (prev + q) / 2.0
                m = cols[i % len(cols)]
                a, b = mid - nrm, mid + nrm
                tip = Vector((mid.x, mid.y, mid.z - 0.58))
                mb.tri((a.x, a.y, a.z - 0.02), (b.x, b.y, b.z - 0.02), tip, m)
                mb.tri((b.x, b.y, b.z - 0.05), (a.x, a.y, a.z - 0.05),
                       (tip.x, tip.y, tip.z - 0.03), m)
            prev = q
    cols = [M(OCHRE), M(ROSE), M(TEAL), M(WHITE)]
    AZ = UP_SILL - 0.05          # just above the balcony rail, not floating on the drum
    bunting(lp[0], at(RAD(236), R + 1.25, AZ), 1.3, cols)
    bunting(at(RAD(214), R + 1.25, AZ), lp[2], 1.3, cols)
    bunting(lp[1], at(RAD(288), R + 1.25, AZ), 1.4, cols)
    return mb.finish(coll, origin=(0, 0, 0), bevel=0.022)


# --------------------------------------------------------------- interior ---

def interior(coll):
    mb = MB("Interior", PFX)
    cut = MB("Interior_Cut", PFX)
    r_in = R - WT

    # floor: stone-tile border, wood-plank centre, giraffe rug -- three of the six
    # in one shot. Each layer sits PROUD of the one under it; matching tops here
    # buries the rug and z-fights the planks.
    mb.cyl((0, 0, PLINTH - 0.15), r_in, 0.30, M(TILE), segments=72)
    mb.cyl((0, 0, PLINTH + 0.012), 3.55, 0.03, M(WOOD), segments=64)
    mb.cyl((0, 0, PLINTH + 0.038), 2.30, 0.03, M(HIDE), segments=56)

    # back wall of the rotunda (the arc the wings hide) + reception
    arc_band(mb, r_in - 0.10, r_in, A1, A0 + TAU, PLINTH, PLINTH + 1.25, [], M(WOOD))
    arc_band(mb, r_in - 0.16, r_in, A1, A0 + TAU, PLINTH + 1.25, PLINTH + 1.42, [], M(WHITE))
    arc_band(mb, r_in - 0.10, r_in, A1, A0 + TAU, PLINTH + 1.42, FLOOR2 + 3.6, [], M(CORAL))
    bc = RAD(30)
    tangent_box(mb, bc, r_in - 0.9, PLINTH + 1.5, 5.4, 0.16, 3.0, M(TILE))
    tangent_box(mb, bc, r_in - 0.82, PLINTH + 3.1, 5.9, 0.30, 0.26, M(WHITE))
    tangent_box(mb, bc, r_in - 1.9, PLINTH + 0.56, 4.6, 1.0, 1.12, M(WOOD))
    tangent_box(mb, bc, r_in - 1.9, PLINTH + 1.16, 5.0, 1.22, 0.10, M(WHITE))

    # gallery ring on wooden joists, carried on white columns
    mb.ring((0, 0, FLOOR2 - 0.18), 3.30, r_in, 0.36, M(WOOD), segments=64)
    mb.ring((0, 0, FLOOR2 - 0.38), 3.20, 3.52, 0.34, M(WHITE), segments=64)
    n = 40
    for i in range(n):
        a = TAU * i / n
        b = TAU * (i + 1) / n
        balusters(mb, at(a, 3.44, FLOOR2), at(b, 3.44, FLOOR2), 0.95)
    for i in range(8):
        a = TAU * i / 8 + RAD(22)
        mb.box(at(a, 3.44, PLINTH + 0.22), (0.80, 0.80, 0.44), M(WHITE), rot=(0, 0, a))
        mb.cyl(at(a, 3.44, PLINTH + (FLOOR2 - PLINTH) / 2.0 + 0.2), 0.27,
               FLOOR2 - PLINTH - 0.55, M(WHITE), segments=18, radius_top=0.23)
        mb.cyl(at(a, 3.44, FLOOR2 - 0.60), 0.34, 0.30, M(WHITE), segments=18)

    # curved stair up the north-east of the drum
    S, sa0, sa1 = 20, RAD(78), RAD(196)
    rise = (FLOOR2 - PLINTH) / S
    prev = None
    for k in range(S):
        a = sa0 + (sa1 - sa0) * (k + 0.5) / S
        da = (sa1 - sa0) / S
        # each step is solid from the floor to its own tread, not a slab floating
        # at tread height -- open risers on a curved flight read as loose blocks
        arc_slice(mb, 3.62, r_in - 0.12, a - da / 2.0, a + da / 2.0,
                  PLINTH, PLINTH + rise * (k + 1), M(WHITE))
        arc_slice(mb, 3.58, r_in - 0.08, a - da / 2.0, a + da / 2.0,
                  PLINTH + rise * (k + 1) - 0.06, PLINTH + rise * (k + 1), M(WOOD))
        arc_slice(mb, 3.72, r_in - 0.22, a - da / 2.0, a + da / 2.0,
                  PLINTH + rise * (k + 1), PLINTH + rise * (k + 1) + 0.018, M(HIDE))
        # one baluster per tread with a single continuous ramped handrail; a full
        # balusters() call per step gives every step its own level rail, which
        # reads as a stack of loose blocks rather than a flight
        top = PLINTH + rise * (k + 1)
        mb.cyl(at(a, 3.68, top + 0.46), 0.045, 0.92, M(WOOD), segments=8)
        mb.cyl(at(a, 3.68, top + 0.36), 0.075, 0.30, M(WOOD), segments=8)
        cur = at(a, 3.68, top + 0.97)
        if k:
            mb.beam(prev, cur, 0.16, 0.11, M(WOOD))
        prev = cur
    mb.beam(prev, at(sa1, 3.68, FLOOR2 + 0.97), 0.16, 0.11, M(WOOD))

    # coffered ceiling disc, hidden for the cutaway shot
    cut.cyl((0, 0, FLOOR2 + 4.05), r_in, 0.40, M(WHITE), segments=72)
    for i in range(10):
        cut.ring((0, 0, FLOOR2 + 3.80), r_in - 0.55 * (i + 1), r_in - 0.55 * i - 0.10,
                 0.12 + 0.03 * i, M(WHITE), segments=48)

    # chandelier
    cz = FLOOR2 + 3.5
    mb.cyl((0, 0, cz - 0.7), 0.05, 1.4, M(WHITE), segments=8)
    mb.cyl((0, 0, cz - 1.55), 1.05, 0.16, M(WOOD), segments=24)
    mb.cyl((0, 0, cz - 1.78), 0.62, 0.34, M(WOOD), segments=20, radius_top=0.92)
    for i in range(12):
        a = TAU * i / 12
        p = at(a, 1.16, cz - 1.60)
        mb.beam((0, 0, cz - 1.40), p, 0.05, 0.05, M(WOOD))
        mb.cyl((p[0], p[1], cz - 1.92), 0.145, 0.36, M(WHITE), segments=8, radius_top=0.08)
    return (mb.finish(coll, origin=(0, 0, 0), bevel=0.022),
            cut.finish(coll, origin=(0, 0, 0), bevel=0.022))


# ------------------------------------------------------------------- build ---

def materials():
    W = WHITE
    BK.tint(W, CORAL, srgb(0xE0704A), roughness=0.62)
    BK.tint(W, TEAL,  srgb(0x1E6E67), roughness=0.60)
    BK.tint(W, OCHRE, srgb(0xE0A03A), roughness=0.58)
    BK.tint(W, ROSE,  srgb(0xD8577F), roughness=0.58)
    BK.tint(W, LEAF,  srgb(0x3E7A44), roughness=0.72)
    BK.flat(GLASS, srgb(0xBBD9E8), roughness=0.10)
    # the giraffe pattern rides on Object coordinates, so its spot size follows
    # the object's local space, not the UVs -- give it its own copy respaced to
    # ~0.45 m cells, which is the size that reads as pattern on an awning
    src = bpy.data.materials["Giraffe Skin Material"]
    if HIDE in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials[HIDE])
    m = src.copy()
    m.name = HIDE
    m.use_fake_user = True
    # Object coordinates, NOT Generated: Generated normalises over the object's
    # bounding box, and these objects are one 90 m mesh apiece, so the spots get
    # stretched to a flat wash. Object space is local metres, so 0.45 here means
    # the voronoi's 5 cells/unit lands at ~2.2 cells/m -- 45 cm spots.
    for nd in m.node_tree.nodes:
        if nd.bl_idname == "ShaderNodeMapping":
            nd.inputs["Scale"].default_value = (0.62, 0.62, 0.62)
    BK.tint(BRICK, PANTILE, srgb(0xC96B3C), roughness=0.66)


def world_and_lights(scene, c_lgt):
    w = bpy.data.worlds.get(PFX + "Sky") or bpy.data.worlds.new(PFX + "Sky")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    ids = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
    sky.sky_type = "MULTIPLE_SCATTERING" if "MULTIPLE_SCATTERING" in ids else "NISHITA"
    sky.sun_elevation = RAD(32)
    sky.sun_rotation = RAD(226)
    for p, v in (("sun_intensity", 0.12), ("air_density", 0.85),
                 ("dust_density", 0.35), ("sun_disc", False)):
        if hasattr(sky, p):
            setattr(sky, p, v)
    bg.inputs[1].default_value = 0.30
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    scene.world = w
    try:
        scene.view_settings.view_transform = "Khronos PBR Neutral"
    except TypeError:
        pass

    sd = bpy.data.lights.new(PFX + "Sun", "SUN")
    sd.energy, sd.angle = 4.4, RAD(1.6)
    sd.color = (1.0, 0.95, 0.86)
    sun = bpy.data.objects.new(PFX + "Sun", sd)
    sun.rotation_euler = Euler((RAD(56), 0, RAD(226)), "XYZ")
    c_lgt.objects.link(sun)

    def lamp(name, kind, loc, energy, size=1.0, color=(1.0, 0.87, 0.70), rot=None):
        ld = bpy.data.lights.new(PFX + name, kind)
        ld.energy, ld.color = energy, color
        if kind == "AREA":
            ld.size = size
        else:
            ld.shadow_soft_size = size
        ob = bpy.data.objects.new(PFX + name, ld)
        ob.location = loc
        if rot:
            ob.rotation_euler = rot
        c_lgt.objects.link(ob)
    lamp("Chandelier", "POINT", (0, 0, FLOOR2 + 1.8), 1700, 0.8)
    lamp("LobbyFill", "AREA", (0, 0, FLOOR2 + 3.2), 700, 8.0, rot=(math.pi, 0, 0))
    lamp("Reception", "AREA", at(RAD(30), 3.2, FLOOR2 - 1.0), 500, 4.0, rot=(math.pi, 0, 0))
    lamp("FloorWash", "AREA", (0, 0, PLINTH + 3.0), 700, 7.0, (1.0, 0.90, 0.80),
         rot=(math.pi, 0, 0))
    # kept well inside the arcade: an area light sitting in the arch itself
    # blows out the soffit and the archivolt before it lights anything
    for i, a in enumerate((RAD(200), RAD(225), RAD(250))):
        lamp("Arcade%d" % i, "AREA", at(a, 2.6, SPRING - 0.35), 150, 2.5,
             rot=(math.pi, 0, 0))


def build():
    BK.purge_coll(ROOT)
    materials()
    BK.MAT_UV_SCALE.clear()
    BK.MAT_UV_SCALE.update(UVS)
    scene = bpy.data.scenes.get(SCENE) or bpy.data.scenes.new(SCENE)
    root = BK.ensure_coll(ROOT, scene.collection)
    c_ext = BK.ensure_coll(PFX + "Exterior", root)
    c_int = BK.ensure_coll(PFX + "Interior", root)
    c_lgt = BK.ensure_coll(PFX + "Lighting", root)

    drum(c_ext)
    for name, axis, fixed, inward, a0, a1, nbay in WINGS:
        wing(c_ext, name, axis, fixed, inward, a0, a1, nbay)
        wing_roof(c_ext, name, axis, a0, a1)
    dressing(c_ext)
    interior(c_int)

    world_and_lights(scene, c_lgt)
    cd = bpy.data.cameras.new(PFX + "Cam")
    cam = bpy.data.objects.new(PFX + "Cam", cd)
    c_lgt.objects.link(cam)
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.eevee.taa_render_samples = 96
    scene.eevee.use_shadows = True
    try:
        scene.eevee.use_raytracing = True
        scene.eevee.ray_tracing_options.use_denoise = True
    except Exception:
        pass
    aim(cam, *SHOTS["hero"])
    return sum(len(o.data.polygons) for c in (c_ext, c_int) for o in c.objects
               if o.type == "MESH")


SHOTS = {
    "hero":    ((-19.0, -21.0, 6.4), (0.0, 0.0, 6.6), 38),
    "corner":  ((-11.0, -14.5, 1.72), (0.0, 0.0, 6.2), 26),
    "wing":    ((-24.0, -9.0, 4.0), (6.0, -3.5, 5.5), 45),
    "arcade":  ((-6.6, -7.4, 1.70), (0.5, 0.6, 2.4), 26),
    "lobby":   ((-3.0, -3.4, 1.68), (1.6, 1.8, 3.2), 22),
    "cutaway": ((-27.0, -29.0, 22.0), (0.5, 0.5, 3.0), 42),
    "up":      ((-2.0, -2.4, 1.60), (0.6, 0.7, 12.0), 20),
}
CUTAWAY_HIDE = (PFX + "Interior_Cut",)


def aim(cam, loc, tgt, lens):
    cam.data.lens = lens
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def render_shots(out_dir, names=None, res=(1600, 900), samples=96, prefix=""):
    scene = bpy.data.scenes[SCENE]
    cam = bpy.data.objects[PFX + "Cam"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.eevee.taa_render_samples = samples
    for n in (names or SHOTS):
        cut = (n == "cutaway")
        for nm in CUTAWAY_HIDE:
            o = bpy.data.objects.get(nm)
            if o:
                o.hide_render = cut
        aim(cam, *SHOTS[n])
        scene.render.filepath = out_dir.rstrip("/") + "/" + prefix + n + ".png"
        bpy.ops.render.render(write_still=True, scene=SCENE)
        print("shot", n)
    for nm in CUTAWAY_HIDE:
        o = bpy.data.objects.get(nm)
        if o:
            o.hide_render = False
    aim(cam, *SHOTS["hero"])


if True:
    print("CarsonBuilding tris:", build())
