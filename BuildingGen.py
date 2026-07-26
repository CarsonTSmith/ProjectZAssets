"""
BuildingGen.py -- one building, exterior + interior, in the Deceive Inc. idiom,
built ENTIRELY from the hand-picked material library already in Wall.blend.

A corner hotel: arcaded ground floor, double-height lobby with a north/east
mezzanine gallery, grand stair, reception. Coral stucco and white trim outside;
emerald walls, dark wainscot, deco checkerboard floor and an ornate red carpet
inside -- the palette the library was clearly bought for.

Openings are real holes, not glass decals stuck on solid walls: the wall is
emitted as storey bands, and each band is split analytically around its
openings. (Slicing walls into thin slabs and skipping the gaps is easier to
write but every slab keeps its own bevel, so the wall renders as corduroy.)

Lands in its own "Building" scene. Objects are split by role so the front wall,
roof and near lining can be hidden for a dollhouse render.

Run:  exec(open("/home/carson/Blender/ProjectZAssets/BuildingGen.py").read())
"""

import bpy, math, sys, importlib
from mathutils import Vector, Euler

sys.path.insert(0, "/home/carson/Blender/ProjectZAssets")
import BlockoutKit as BK
importlib.reload(BK)
MB = BK.MB

PFX = "BG_"
ROOT = "Building"
SCENE = "Building"

# ------------------------------------------------------------------ palette --
EXT_WALL  = "Orange plaster stucco wall"
EXT_BASE  = "White stone stylized"
TRIM      = "Stucco Plaster"
ROOFTILE  = "Square Floor Tile"
SHUTTER   = "Painted Plaster Wall.003"
SIGNCOL   = "Painted Plaster Wall.001"
AWN_A     = "Roll painted wall"
AWN_B     = "Painted Plaster Wall"
IRON      = "Stylized Metal Base"
GLASS     = "Glass.003"
GROUND    = "Industrial Grid Stone Pavement"
KERB      = "Stone bricks"

INT_FLOOR = "Generic Floor 09"
CARPET    = "Red Carpet.001"
WAINSCOT  = "Stylised Hard Wood"
INT_WALL  = "Painted Plaster Wall.002"
INT_CEIL  = "White Plaster"
FEATURE   = "Layered Hexagon Pattern"
MAHOG     = "Wood Floor Mahogany.001"
TEAK      = "Wood Floor Teak"
# the library has no gold, and every metal in it is grey -- the mustard plaster
# is the only warm option and reads as painted brass at trim scale
BRASS     = "Painted Plaster Wall.001"
STEEL     = "Smooth Metal"
PLANT     = "Stylized Clover Ground"

UVS = {
    # the casino carpet is a dark, low-contrast scan -- enlarge the motif or it
    # reads as flat red at any sane interior light level
    INT_FLOOR: 0.22, CARPET: 1.05, ROOFTILE: 0.30, EXT_WALL: 0.45,
    FEATURE: 0.22, EXT_BASE: 0.7, WAINSCOT: 0.55, MAHOG: 0.7, TEAK: 0.7,
    INT_WALL: 0.45, TRIM: 0.45, GROUND: 0.35, SHUTTER: 0.7, KERB: 0.8,
    AWN_A: 0.5, AWN_B: 0.5, SIGNCOL: 0.5, PLANT: 0.8, BRASS: 0.5,
}

# --------------------------------------------------------------- dimensions --
HW, HD = 7.0, 5.5
WT = 0.4
PLINTH = 0.70              # exterior plinth top == interior floor level
SPRING = 3.30              # arch springline (absolute)
ARCH_R = 1.35
ARCH_CROWN = SPRING + ARCH_R                      # 4.65
STRING = 5.00              # string course, clears the crown
WALL_TOP = 8.90
UP_SILL, UP_H = 5.85, 2.35                        # upper windows
GF_SILL, GF_H = 1.70, 2.60                        # ground windows (side walls)
CEIL = 7.60                # interior, relative to floor -> 8.30 absolute
MEZZ = 4.00                # mezzanine deck, relative -> 4.70 absolute
MEZZ_N, MEZZ_E = 1.60, 3.20
IX, IY = HW - WT, HD - WT
PW = (2 * HW - 3 * 2 * ARCH_R) / 4.0              # facade pier width
ARCH_U = [-HW + PW * (i + 1) + 2 * ARCH_R * i + ARCH_R for i in range(3)]
UP_U = (-5.05, -1.7, 1.7, 5.05)


def M(n):
    return bpy.data.materials[n]


def framer(mb, axis, fixed, inward):
    def place(u, w, du, dw, thick, mat, off=0.0, uvs=0.0):
        pos = fixed + inward * (thick / 2.0 + off)
        if axis == "X":
            mb.box((u, pos, w), (du, thick, dw), mat, uvs=uvs)
        else:
            mb.box((pos, u, w), (thick, du, dw), mat, uvs=uvs)
    return place


def band(place, a0, a1, z0, z1, opens, thick, mat, uvs=0.0):
    """One storey of wall, split analytically around its openings.
    `opens` = [(u_centre, half_width, z_bottom, z_top), ...]"""
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


def arch_head(place, uc, radius, spring, top, thick, mat, n=24):
    """Wall between a semicircular arc and the band above it."""
    for i in range(n):
        u0 = uc - radius + 2 * radius * i / n
        u1 = uc - radius + 2 * radius * (i + 1) / n
        um = (u0 + u1) / 2.0
        d = min(abs(um - uc), radius)
        h = spring + math.sqrt(max(0.0, radius ** 2 - d ** 2))
        if top - h > 0.02:
            place(um, (h + top) / 2.0, (u1 - u0) + 0.02, top - h, thick, mat)


def arch_ring(mb, axis, fixed, inward, uc, spring, radius, thick, ring_w, mat,
              segs=18, off=0.0):
    for i in range(segs):
        phi = math.pi * (i + 0.5) / segs
        du = (math.pi * radius / segs) * 1.12
        rr = radius + ring_w / 2.0
        u, w = uc + rr * math.cos(phi), spring + rr * math.sin(phi)
        pos = fixed + inward * (thick / 2.0 + off)
        if axis == "X":
            mb.box((u, pos, w), (du, thick, ring_w), mat, rot=(0, math.pi / 2 - phi, 0))
        else:
            mb.box((pos, u, w), (thick, du, ring_w), mat, rot=(phi - math.pi / 2, 0, 0))


def surround(place, uc, sill, ow, oh, proj=0.07):
    B = 0.17
    place(uc, sill - B / 2.0, ow + 2 * B, B, 0.18, M(TRIM), off=-proj)
    place(uc, sill + oh + B / 2.0, ow + 2 * B, B, 0.18, M(TRIM), off=-proj)
    for s in (-1, 1):
        place(uc + s * (ow + B) / 2.0, sill + oh / 2.0, B, oh, 0.18, M(TRIM), off=-proj)
    place(uc, sill - 0.17, ow + 0.8, 0.14, 0.34, M(TRIM), off=-0.18)
    place(uc, sill + oh + 0.34, ow + 0.9, 0.22, 0.38, M(TRIM), off=-0.20)


def sash(place, uc, sill, ow, oh):
    place(uc, sill + oh / 2.0, ow, oh, 0.07, M(GLASS), off=WT - 0.14)
    place(uc, sill + oh / 2.0, ow, 0.07, 0.11, M(TRIM), off=WT - 0.17)
    place(uc, sill + oh / 2.0, 0.07, oh, 0.11, M(TRIM), off=WT - 0.17)


def shutters(mb, axis, fixed, inward, uc, sill, ow, oh):
    lw = ow / 2.0 * 0.94
    for s in (-1, 1):
        cu = uc + s * (ow / 2.0 + lw / 2.0 + 0.06)
        pos = fixed - inward * 0.12
        def blk(u, w, du, dw, th):
            if axis == "X":
                mb.box((u, pos - inward * th / 2.0, w), (du, th, dw), M(SHUTTER))
            else:
                mb.box((pos - inward * th / 2.0, u, w), (th, du, dw), M(SHUTTER))
        wc = sill + oh / 2.0
        blk(cu, wc + oh / 2.0 - 0.07, lw, 0.14, 0.09)
        blk(cu, wc - oh / 2.0 + 0.07, lw, 0.14, 0.09)
        for e in (-1, 1):
            blk(cu + e * (lw / 2.0 - 0.05), wc, 0.10, oh, 0.09)
        for i in range(8):
            blk(cu, wc - oh / 2.0 + oh * (i + 0.5) / 8, lw - 0.17, oh / 8 * 0.58, 0.055)


def balcony(mb, axis, fixed, inward, place, uc, sill, ow):
    place(uc, sill - 0.34, ow + 1.2, 0.16, 1.0, M(TRIM), off=-0.84)
    pos = fixed - inward * 0.82
    for k in range(10):
        u = uc - (ow + 0.95) / 2.0 + (ow + 0.95) * k / 9.0
        if axis == "X":
            mb.box((u, pos, sill + 0.28), (0.05, 0.05, 0.88), M(IRON))
        else:
            mb.box((pos, u, sill + 0.28), (0.05, 0.05, 0.88), M(IRON))
    for zz in (sill + 0.71, sill - 0.16):
        if axis == "X":
            mb.box((uc, pos, zz), (ow + 1.0, 0.07, 0.07), M(IRON))
        else:
            mb.box((pos, uc, zz), (0.07, ow + 1.0, 0.07), M(IRON))


def cornice(place, mid, L):
    for ww, hh, dz in ((0.34, 0.22, 0.0), (0.62, 0.30, 0.26),
                       (0.88, 0.26, 0.55), (0.44, 0.5, 0.92)):
        place(mid, WALL_TOP - 0.55 + dz, L + ww, hh, WT + ww, M(TRIM), off=-ww / 2.0)

# ------------------------------------------------------------------- pieces --


def facade_front(coll):
    mb = MB("Facade_S", PFX)
    place = framer(mb, "X", -HD, 1)
    L = 2 * HW
    place(0, PLINTH / 2.0, L + 0.3, PLINTH, WT + 0.3, M(EXT_BASE), off=-0.15)
    # ground band: three open arches
    band(place, -HW, HW, PLINTH, SPRING,
         [(u, ARCH_R, PLINTH, SPRING) for u in ARCH_U], WT, M(EXT_WALL))
    for u in ARCH_U:
        arch_head(place, u, ARCH_R, SPRING, STRING, WT, M(EXT_WALL))
        arch_ring(mb, "X", -HD, 1, u, SPRING, ARCH_R, WT + 0.22, 0.36, M(TRIM), off=-0.11)
        mb.box((u, -HD - 0.17, ARCH_CROWN + 0.30), (0.46, WT + 0.34, 0.74), M(TRIM))
    for i in range(4):
        pc = -HW + PW / 2.0 + i * (PW + 2 * ARCH_R)
        place(pc, SPRING + 0.16, PW + 0.3, 0.3, WT + 0.2, M(TRIM), off=-0.1)  # impost
    place(0, STRING + 0.18, L + 0.44, 0.36, WT + 0.4, M(TRIM), off=-0.2)
    # upper band
    band(place, -HW, HW, STRING + 0.36, WALL_TOP,
         [(u, 0.7, UP_SILL, UP_SILL + UP_H) for u in UP_U], WT, M(EXT_WALL))
    for u in UP_U:
        sash(place, u, UP_SILL, 1.4, UP_H)
        surround(place, u, UP_SILL, 1.4, UP_H)
        shutters(mb, "X", -HD, 1, u, UP_SILL, 1.4, UP_H)
        balcony(mb, "X", -HD, 1, place, u, UP_SILL, 1.4)
    cornice(place, 0, L)
    # entrance doors in the centre arch
    uc = ARCH_U[1]
    for s in (-1, 1):
        place(uc + s * 0.64, PLINTH + 1.42, 1.24, 2.84, 0.11, M(MAHOG), off=WT - 0.24)
        place(uc + s * 0.64, PLINTH + 1.55, 0.88, 2.24, 0.07, M(GLASS), off=WT - 0.28)
        mb.box((uc + s * 0.16, -HD + WT - 0.30, PLINTH + 1.45), (0.05, 0.05, 0.5), M(BRASS))
    place(uc, PLINTH + 2.92, 2.7, 0.18, 0.22, M(TRIM), off=WT - 0.22)
    place(uc, SPRING + 0.55, 2.5, 1.3, 0.06, M(GLASS), off=WT - 0.20)
    for k in range(5):                                    # fanlight bars
        a = math.pi * (k + 1) / 6
        mb.box((uc + (ARCH_R - 0.25) * math.cos(a) / 2.0, -HD + WT - 0.22,
                SPRING + (ARCH_R - 0.25) * math.sin(a) / 2.0),
               (0.05, 0.08, ARCH_R - 0.25), M(TRIM), rot=(0, math.pi / 2 - a, 0))
    return mb.finish(coll, origin=(0, -HD, 0), bevel=0.035)


def shell(coll):
    mb = MB("Shell", PFX)
    for axis, fixed, inward, a0, a1, n in (
            ("Y",  HW, -1, -HD, HD, 3), ("Y", -HW, 1, -HD, HD, 3),
            ("X",  HD, -1, -HW, HW, 4)):
        place = framer(mb, axis, fixed, inward)
        L, mid = a1 - a0, (a0 + a1) / 2.0
        us = [a0 + L * (i + 0.5) / n for i in range(n)]
        place(mid, PLINTH / 2.0, L + 0.3, PLINTH, WT + 0.3, M(EXT_BASE), off=-0.15)
        band(place, a0, a1, PLINTH, STRING,
             [(u, 0.75, GF_SILL, GF_SILL + GF_H) for u in us], WT, M(EXT_WALL))
        place(mid, STRING + 0.18, L + 0.44, 0.36, WT + 0.4, M(TRIM), off=-0.2)
        band(place, a0, a1, STRING + 0.36, WALL_TOP,
             [(u, 0.7, UP_SILL, UP_SILL + UP_H) for u in us], WT, M(EXT_WALL))
        for u in us:
            sash(place, u, GF_SILL, 1.5, GF_H)
            surround(place, u, GF_SILL, 1.5, GF_H)
            sash(place, u, UP_SILL, 1.4, UP_H)
            surround(place, u, UP_SILL, 1.4, UP_H)
            shutters(mb, axis, fixed, inward, u, UP_SILL, 1.4, UP_H)
        cornice(place, mid, L)
    # quoins -- one block per course, alternating which face it reads on
    for sx in (-1, 1):
        for sy in (-1, 1):
            for k in range(15):
                z = PLINTH + 0.30 + k * 0.56
                if z > WALL_TOP - 1.0:
                    break
                if k % 2 == 0:
                    mb.box((sx * (HW - 0.55 + 0.07), sy * (HD + 0.07), z),
                           (1.10, WT + 0.14, 0.48), M(TRIM))
                else:
                    mb.box((sx * (HW + 0.07), sy * (HD - 0.55 + 0.07), z),
                           (WT + 0.14, 1.10, 0.48), M(TRIM))
    return mb.finish(coll, origin=(0, 0, 0), bevel=0.035)


def roof(coll):
    mb = MB("Roof", PFX)
    EO = 0.8
    ex, ey, ez = HW + EO, HD + EO, WALL_TOP
    rz = WALL_TOP + 2.4
    A, B, C, D = (-ex, -ey, ez), (ex, -ey, ez), (ex, ey, ez), (-ex, ey, ez)
    R0, R1 = (-1.6, 0, rz), (1.6, 0, rz)
    for pts in ((A, B, R1, R0), (B, C, R1), (C, D, R0, R1), (D, A, R0)):
        mb.extrude_poly(list(pts), (0, 0, -0.28), M(ROOFTILE))
    for s in (-1, 1):
        mb.box((0, s * ey, ez - 0.36), (2 * ex, 0.16, 0.36), M(TRIM))
        mb.box((s * ex, 0, ez - 0.36), (0.16, 2 * ey, 0.36), M(TRIM))
    ang = math.atan2(2.4, ey)
    n = int(2 * ex / 0.42)
    for i in range(n):
        x = -ex + 2 * ex * (i + 0.5) / n
        mb.cyl((x, -ey + 1.0, ez + 1.0 * math.tan(ang) + 0.06), 0.115, 2.2,
               M(ROOFTILE), segments=10, rot=(math.pi / 2 - ang, 0, 0))
    mb.box((0, 0, rz + 0.06), (3.6, 0.34, 0.3), M(ROOFTILE))
    for x in (-4.3, 4.3):
        mb.box((x, 2.7, ez + 1.8), (1.0, 1.0, 2.8), M(EXT_BASE))
        mb.box((x, 2.7, ez + 3.3), (1.28, 1.28, 0.3), M(TRIM))
    return mb.finish(coll, origin=(0, 0, 0), bevel=0.03)


def dressing(coll):
    mb = MB("Dressing", PFX)
    # Awnings go over the flanking shopfront windows, not the arcade -- a
    # colonnade shades itself, and hanging canvas over the arches buries the
    # best feature of the elevation.
    def awn(axis, fixed, inward, uc, half, ztop):
        n = 9
        for k in range(n):
            t0, t1 = uc - half + 2 * half * k / n, uc - half + 2 * half * (k + 1) / n
            m = M(AWN_A) if k % 2 == 0 else M(AWN_B)
            o, d = fixed - inward * 0.05, fixed - inward * 1.85
            if axis == "Y":
                pts = [(o, t0, ztop), (o, t1, ztop), (d, t1, ztop - 0.85), (d, t0, ztop - 0.85)]
            else:
                pts = [(t0, o, ztop), (t1, o, ztop), (t1, d, ztop - 0.85), (t0, d, ztop - 0.85)]
            mb.extrude_poly(pts, (0, 0, -0.09), m)
        e = fixed - inward * 1.88
        if axis == "Y":
            mb.box((e, uc, ztop - 0.98), (0.12, 2 * half, 0.32), M(AWN_B))
        else:
            mb.box((uc, e, ztop - 0.98), (2 * half, 0.12, 0.32), M(AWN_B))

    for i in range(3):
        u = -HD + 2 * HD * (i + 0.5) / 3
        awn("Y", -HW, 1, u, 1.25, GF_SILL + GF_H + 0.55)
        awn("Y", HW, -1, u, 1.25, GF_SILL + GF_H + 0.55)
    mb.beam((-3.4, -HD - 0.1, STRING + 1.0), (-3.4, -HD - 1.7, STRING + 1.0),
            0.09, 0.09, M(IRON))
    mb.beam((-3.4, -HD - 1.62, STRING + 1.0), (-3.4, -HD - 1.62, STRING + 0.3),
            0.06, 0.06, M(IRON))
    mb.box((-3.4, -HD - 1.62, STRING - 0.28), (2.2, 0.14, 1.15), M(SIGNCOL))
    mb.box((-3.4, -HD - 1.70, STRING - 0.28), (1.8, 0.06, 0.8), M(TRIM))
    for x in (-2.0, 2.0):
        mb.beam((x, -HD - 0.05, ARCH_CROWN + 0.5), (x, -HD - 0.5, ARCH_CROWN + 0.62),
                0.07, 0.07, M(IRON))
        mb.cyl((x, -HD - 0.5, ARCH_CROWN + 0.22), 0.26, 0.55, M(IRON), segments=6,
               radius_top=0.13)
        mb.cyl((x, -HD - 0.5, ARCH_CROWN + 0.25), 0.20, 0.42, M(GLASS), segments=6)
    for k in range(3):
        mb.box((0, -HD - 0.42 - k * 0.44, PLINTH - 0.13 - k * 0.24),
               (5.4 + k * 0.55, 1.0 + k * 0.9, 0.26), M(EXT_BASE))
    mb.box((0, 0, -0.12), (150, 150, 0.24), M(GROUND))
    mb.box((0, -HD - 11.0, 0.06), (150, 0.4, 0.3), M(KERB))
    return mb.finish(coll, origin=(0, 0, 0), bevel=0.025)

# ----------------------------------------------------------------- interior --
# built with z=0 at the finished floor; the object is lifted to PLINTH on finish


def interior(coll):
    mb = MB("Interior", PFX)
    cut = MB("Interior_Cut", PFX)
    WH = 1.25
    up_sill = UP_SILL - PLINTH
    gf_sill = GF_SILL - PLINTH

    mb.box((0, 0, -0.16), (2 * IX, 2 * IY, 0.32), M(INT_FLOOR))
    cut.box((0, 0, CEIL + 0.18), (2 * IX, 2 * IY, 0.36), M(INT_CEIL))
    mb.box((0, -1.2, 0.025), (3.2, 2 * IY - 2.4, 0.05), M(CARPET))

    def lining(target, axis, fixed, inward, a0, a1, opens_low, opens_high):
        place = framer(target, axis, fixed, inward)
        L, mid = a1 - a0, (a0 + a1) / 2.0
        band(place, a0, a1, 0, WH, opens_low, 0.09, M(WAINSCOT))
        band(place, a0, a1, WH, WH + 0.13, opens_low, 0.17, M(TRIM))
        band(place, a0, a1, WH + 0.13, CEIL, opens_low + opens_high, 0.07, M(INT_WALL))
        for ww, hh, dz in ((0.16, 0.2, 0.0), (0.3, 0.26, 0.2)):
            place(mid, CEIL - 0.2 - dz, L, hh, ww, M(TRIM))
        return place

    up = [(u, 0.72, up_sill, up_sill + UP_H) for u in UP_U]
    upY = [(u, 0.72, up_sill, up_sill + UP_H)
           for u in (-HD + 2 * HD * (i + 0.5) / 3 for i in range(3))]
    gfY = [(u, 0.78, gf_sill, gf_sill + GF_H)
           for u in (-HD + 2 * HD * (i + 0.5) / 3 for i in range(3))]
    upN = [(u, 0.72, up_sill, up_sill + UP_H)
           for u in (-HW + 2 * HW * (i + 0.5) / 4 for i in range(4))]
    gfN = [(u, 0.78, gf_sill, gf_sill + GF_H)
           for u in (-HW + 2 * HW * (i + 0.5) / 4 for i in range(4))]

    # south lining: the three arches carry through, so the loggia is a real hole
    ps = framer(cut, "X", -IY, 1)
    # An arch opening must read as full-height to `band`, otherwise band's
    # "wall above the opening" segment plugs the arch head with solid wall.
    # arch_head fills the spandrel above the curve instead.
    arches_open = [(u, ARCH_R, -1.0, 1e6) for u in ARCH_U]
    band(ps, -IX, IX, 0, WH, arches_open, 0.09, M(WAINSCOT))
    band(ps, -IX, IX, WH, WH + 0.13, arches_open, 0.17, M(TRIM))
    band(ps, -IX, IX, WH + 0.13, CEIL, arches_open + up, 0.07, M(INT_WALL))
    for u in ARCH_U:
        arch_head(ps, u, ARCH_R, SPRING - PLINTH, CEIL, 0.07, M(INT_WALL))
        arch_ring(cut, "X", -IY, 1, u, SPRING - PLINTH, ARCH_R, 0.2, 0.3, M(TRIM), off=-0.06)
    for ww, hh, dz in ((0.16, 0.2, 0.0), (0.3, 0.26, 0.2)):
        ps(0, CEIL - 0.2 - dz, 2 * IX, hh, ww, M(TRIM))

    lining(mb, "X", IY, -1, -IX, IX, gfN, upN)
    lining(mb, "Y", -IX, 1, -IY, IY, gfY, upY)
    lining(mb, "Y", IX, -1, -IY, IY, gfY, upY)

    # feature wall behind reception
    mb.box((0, IY - 0.09, MEZZ / 2.0), (7.0, 0.1, MEZZ - 0.3), M(FEATURE))
    mb.box((0, IY - 0.16, MEZZ - 0.18), (7.3, 0.26, 0.26), M(TRIM))

    # mezzanine: north strip + east strip
    mb.box((0, (MEZZ_N + IY) / 2.0, MEZZ - 0.18), (2 * IX, IY - MEZZ_N, 0.36), M(TEAK))
    mb.box(((MEZZ_E + IX) / 2.0, (MEZZ_N - IY) / 2.0, MEZZ - 0.18),
           (IX - MEZZ_E, IY + MEZZ_N, 0.36), M(TEAK))
    mb.box((0, MEZZ_N + 0.1, MEZZ - 0.38), (2 * IX, 0.34, 0.32), M(TRIM))
    mb.box((MEZZ_E + 0.1, (MEZZ_N - IY) / 2.0, MEZZ - 0.38),
           (0.34, IY + MEZZ_N, 0.32), M(TRIM))

    for (cx, cy) in ((-IX + 1.0, MEZZ_N), (0.0, MEZZ_N), (MEZZ_E, MEZZ_N),
                     (MEZZ_E, -1.6), (MEZZ_E, -IY + 1.0)):
        mb.box((cx, cy, 0.22), (0.82, 0.82, 0.44), M(TRIM))
        mb.cyl((cx, cy, MEZZ / 2.0 + 0.2), 0.28, MEZZ - 0.5, M(TRIM), segments=20,
               radius_top=0.24)
        mb.box((cx, cy, MEZZ - 0.44), (0.74, 0.74, 0.3), M(TRIM))
    for (cx, cy) in ((-IX + 1.0, MEZZ_N), (0.0, MEZZ_N), (MEZZ_E, MEZZ_N)):
        mb.cyl((cx, cy, (MEZZ + CEIL) / 2.0), 0.22, CEIL - MEZZ - 0.45, M(TRIM),
               segments=16)

    def rail(p0, p1):
        p0, p1 = Vector(p0), Vector(p1)
        n = max(2, int((p1 - p0).length / 0.30))
        mb.beam(p0 + Vector((0, 0, 0.07)), p1 + Vector((0, 0, 0.07)), 0.13, 0.13, M(MAHOG))
        mb.beam(p0 + Vector((0, 0, 1.02)), p1 + Vector((0, 0, 1.02)), 0.20, 0.14, M(MAHOG))
        for k in range(1, n):
            q = p0.lerp(p1, k / n)
            mb.cyl((q.x, q.y, q.z + 0.55), 0.034, 0.9, M(IRON), segments=8)
    rail((-IX, MEZZ_N + 0.28, MEZZ), (MEZZ_E, MEZZ_N + 0.28, MEZZ))
    rail((MEZZ_E + 0.28, MEZZ_N + 0.28, MEZZ), (MEZZ_E + 0.28, -IY, MEZZ))

    # doors off the gallery
    for u in (-4.2, 4.2):
        mb.box((u, IY - 0.14, MEZZ + 1.15), (1.15, 0.12, 2.3), M(MAHOG))
        mb.box((u, IY - 0.22, MEZZ + 1.15), (1.4, 0.14, 2.55), M(TRIM))

    # grand stair up the west wall
    STEPS, RISE = 14, MEZZ / 14.0
    y0, run = -4.3, 5.9
    for k in range(STEPS):
        y = y0 + run * (k + 0.5) / STEPS
        mb.box((-IX + 1.05, y, RISE * (k + 0.5)), (2.1, run / STEPS + 0.04, RISE), M(MAHOG))
        mb.box((-IX + 1.05, y, RISE * (k + 1) - 0.02), (2.16, run / STEPS * 0.8, 0.06),
               M(CARPET))
        mb.cyl((-IX + 2.1, y, RISE * (k + 0.5) + 0.52), 0.034, 1.0, M(IRON), segments=8)
    mb.beam((-IX + 2.1, y0, 0.98), (-IX + 2.1, y0 + run, MEZZ + 0.98), 0.16, 0.16, M(MAHOG))
    return (mb.finish(coll, origin=(0, 0, PLINTH), bevel=0.02),
            cut.finish(coll, origin=(0, 0, PLINTH), bevel=0.02))


def furniture(coll):
    mb = MB("Furniture", PFX)
    mb.box((0, IY - 1.9, 0.55), (5.0, 1.0, 1.10), M(MAHOG))
    mb.box((0, IY - 1.9, 1.14), (5.4, 1.25, 0.1), M(BRASS))
    mb.box((0, IY - 1.45, 0.42), (4.4, 0.14, 0.84), M(BRASS))
    for x in (-1.9, 1.9):
        mb.cyl((x, IY - 2.35, 1.45), 0.06, 0.6, M(BRASS), segments=10)
        mb.cyl((x, IY - 2.35, 1.86), 0.30, 0.28, M(AWN_B), segments=14, radius_top=0.19)
    for (cx, cy) in ((-3.9, -2.4), (-1.5, -3.6)):
        mb.box((cx, cy, 0.22), (1.15, 1.1, 0.44), M(CARPET))
        mb.box((cx, cy, 0.46), (1.05, 1.0, 0.16), M(AWN_A))
        mb.box((cx, cy + 0.48, 0.75), (1.1, 0.18, 0.66), M(AWN_A))
        for sx in (-1, 1):
            mb.box((cx + sx * 0.52, cy, 0.62), (0.14, 1.0, 0.36), M(MAHOG))
    mb.cyl((-2.7, -3.1, 0.26), 0.60, 0.09, M(MAHOG), segments=20)
    mb.cyl((-2.7, -3.1, 0.13), 0.12, 0.26, M(BRASS), segments=10)
    mb.box((IX - 1.2, -2.2, 0.58), (1.6, 4.6, 1.16), M(MAHOG))
    mb.box((IX - 1.2, -2.2, 1.20), (1.85, 4.9, 0.1), M(STEEL))
    for k in range(9):
        mb.cyl((IX - 0.55, -4.2 + k * 0.48, 1.45), 0.06, 0.4, M(GLASS), segments=8)
    for k in range(3):
        mb.cyl((IX - 2.7, -3.4 + k * 1.2, 0.36), 0.18, 0.72, M(BRASS), segments=10)
        mb.cyl((IX - 2.7, -3.4 + k * 1.2, 0.78), 0.27, 0.12, M(AWN_A), segments=14)
    for sx in (-1, 1):
        x = sx * 4.4
        mb.cyl((x, -IY + 1.1, 0.34), 0.44, 0.68, M(TRIM), segments=16)
        mb.cyl((x, -IY + 1.1, 0.70), 0.48, 0.1, M(BRASS), segments=16)
        mb.cyl((x, -IY + 1.1, 0.95), 0.09, 0.4, M(MAHOG), segments=8)
        mb.sphere((x, -IY + 1.1, 1.42), 0.56, M(PLANT), segments=18)
        mb.sphere((x, -IY + 1.1, 2.10), 0.42, M(PLANT), segments=16)
    cx, cy, cz = -0.6, -1.6, CEIL - 0.1
    mb.cyl((cx, cy, cz - 0.6), 0.05, 1.2, M(BRASS), segments=8)
    mb.cyl((cx, cy, cz - 1.35), 0.95, 0.16, M(BRASS), segments=20)
    mb.cyl((cx, cy, cz - 1.52), 0.55, 0.32, M(BRASS), segments=16, radius_top=0.82)
    for i in range(10):
        a = 2 * math.pi * i / 10
        px, py = cx + 1.05 * math.cos(a), cy + 1.05 * math.sin(a)
        mb.beam((cx, cy, cz - 1.3), (px, py, cz - 1.58), 0.05, 0.05, M(BRASS))
        mb.cyl((px, py, cz - 1.78), 0.13, 0.34, M(AWN_B), segments=8, radius_top=0.07)
    return mb.finish(coll, origin=(0, 0, PLINTH), bevel=0.02)

# ------------------------------------------------------------------- build ---


def build():
    BK.purge_coll(ROOT)
    BK.MAT_UV_SCALE.clear()
    BK.MAT_UV_SCALE.update(UVS)
    scene = bpy.data.scenes.get(SCENE) or bpy.data.scenes.new(SCENE)
    root = BK.ensure_coll(ROOT, scene.collection)
    c_ext = BK.ensure_coll(PFX + "Exterior", root)
    c_int = BK.ensure_coll(PFX + "Interior", root)
    c_lgt = BK.ensure_coll(PFX + "Lighting", root)

    facade_front(c_ext)
    shell(c_ext)
    roof(c_ext)
    dressing(c_ext)
    interior(c_int)
    furniture(c_int)

    w = bpy.data.worlds.get(PFX + "Sky") or bpy.data.worlds.new(PFX + "Sky")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    ids = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
    sky.sky_type = "MULTIPLE_SCATTERING" if "MULTIPLE_SCATTERING" in ids else "NISHITA"
    sky.sun_elevation = math.radians(30)
    sky.sun_rotation = math.radians(198)
    for p, v in (("sun_intensity", 0.12), ("air_density", 0.9),
                 ("dust_density", 0.3), ("sun_disc", False)):
        if hasattr(sky, p):
            setattr(sky, p, v)
    bg.inputs[1].default_value = 0.28
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    scene.world = w
    try:
        scene.view_settings.view_transform = "Khronos PBR Neutral"
    except TypeError:
        pass

    # low sun from the front so it rakes through the arches; an interior only
    # reads if the daylight has somewhere to land
    sd = bpy.data.lights.new(PFX + "Sun", "SUN")
    sd.energy, sd.angle = 4.2, math.radians(1.5)
    sd.color = (1.0, 0.95, 0.86)
    sun = bpy.data.objects.new(PFX + "Sun", sd)
    sun.rotation_euler = Euler((math.radians(58), 0, math.radians(198)), "XYZ")
    c_lgt.objects.link(sun)

    def lamp(name, kind, loc, energy, size=1.0, color=(1.0, 0.86, 0.68), rot=None):
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
        return ob

    Z = PLINTH
    lamp("Chandelier", "POINT", (-0.6, -1.6, Z + CEIL - 1.8), 1100, 0.7)
    lamp("Fill", "AREA", (0, -1.0, Z + CEIL - 0.4), 500, 8.0, (1.0, 0.93, 0.84),
         rot=(math.pi, 0, 0))
    lamp("Reception", "AREA", (0, IY - 2.4, Z + MEZZ - 0.5), 300, 4.5,
         rot=(math.pi, 0, 0))
    lamp("Bar", "POINT", (IX - 1.7, -2.2, Z + 2.4), 220, 0.5, (1.0, 0.78, 0.55))
    lamp("Stair", "POINT", (-IX + 1.7, -1.2, Z + 2.8), 180, 0.5)
    lamp("FloorWash", "AREA", (0, -1.5, Z + 3.2), 340, 7.0, (1.0, 0.9, 0.8),
         rot=(math.pi, 0, 0))
    lamp("Gallery", "AREA", (0, MEZZ_N + 1.6, Z + CEIL - 0.6), 220, 6.0,
         rot=(math.pi, 0, 0))

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
    aim(cam, *SHOTS["ext"])
    return sum(len(o.data.polygons) for c in (c_ext, c_int) for o in c.objects
               if o.type == "MESH")


SHOTS = {
    "ext":       ((-15.5, -18.0, 5.2), (0.5, -3.0, 5.0), 35),
    "ext_front": ((0.0, -23.0, 6.5), (0.0, -3.0, 5.5), 40),
    "door":      ((0.0, -13.0, 1.75), (0.0, 4.0, 3.4), 30),
    "lobby":     ((1.6, -4.4, 1.68), (-2.5, 3.8, 2.4), 24),
    "lobby2":    ((4.6, 1.2, 6.05), (-3.4, -4.6, 1.4), 22),
    "cutaway":   ((15.0, -17.5, 12.0), (-0.5, 0.5, 3.0), 34),
}
CUTAWAY_HIDE = (PFX + "Facade_S", PFX + "Roof", PFX + "Dressing", PFX + "Interior_Cut")


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
    aim(cam, *SHOTS["ext"])


if True:
    print("Building tris:", build())
