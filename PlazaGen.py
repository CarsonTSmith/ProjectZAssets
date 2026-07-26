"""
PlazaGen.py -- a colonial plaza in the Deceive Inc. graphic style.

Builds into its OWN Blender scene ("Plaza") with its own world, sun and camera,
so it can be lit for bright spy-caper daylight without disturbing the
StreetPreview scene in the same file.

Style targets, read off the reference: saturated pastel stucco, heavy white
trim on every edge, ground-floor arcades, louvered shutters, clay barrel-tile
roofs, a central bandstand, papel-picado bunting overhead, striped awnings and
parasols. Flat clean materials with hard bevels -- no grime.

Textures come from BlenderKit (see BKFetch.py); the eight wall colours are one
downloaded stucco recoloured eight ways so the surface grain stays consistent.

Run:  exec(open("/home/carson/Blender/ProjectZAssets/PlazaGen.py").read())
"""

import bpy, bmesh, math, sys, importlib
from mathutils import Vector, Euler

sys.path.insert(0, "/home/carson/Blender/ProjectZAssets")
import BlockoutKit as BK
importlib.reload(BK)
MB = BK.MB

PFX = "PZ_"
ROOT = "Plaza"
SCENE = "Plaza"

# ------------------------------------------------------------------ palette --

def srgb(h):
    """#RRGGBB -> linear RGB. Feeding sRGB values straight into Blender makes
    every pastel read muddy, which kills this style immediately."""
    h = h.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


WALL_COLORS = [
    ("Terracotta", "#D4694A"), ("Cream", "#F2E2C2"), ("Mint", "#9FD6B4"),
    ("Mustard", "#EFB43C"), ("Rose", "#E9A398"), ("Teal", "#2E8F9B"),
    ("Sage", "#A9C48A"), ("Coral", "#EE7B52"),
]
BUNTING = ["#FF7A2F", "#FF4E8A", "#FFC93C", "#3FC1C9", "#F5F0E6"]

# --------------------------------------------------------------- dimensions --

PLAZA_HALF = 23.0        # paved square half-width
WALK = 3.5               # sidewalk between plaza edge and the facades
FACE = PLAZA_HALF + WALK # facades sit here
GF = 4.9                 # ground storey (arcade height)
FL = 3.7                 # upper storey
PLINTH = 0.55
WT = 0.5                 # wall thickness


def M(n):
    return bpy.data.materials[n]


def build_materials():
    m = {}
    for name, hexc in WALL_COLORS:
        m[name] = BK.tint("PZ_Stucco", PFX + "W_" + name, srgb(hexc), roughness=0.72)
    m["trim"] = BK.tint("PZ_Trim", PFX + "M_Trim", srgb("#FAF3E6"), roughness=0.62)
    m["stone"] = BK.tint("PZ_Trim", PFX + "M_Stone", srgb("#E4D8C2"), roughness=0.7)
    m["roof"] = BK.tint("PZ_RoofTile", PFX + "M_Roof", srgb("#C4643C"))
    m["shutterA"] = BK.tint("PZ_Wood", PFX + "M_ShutterGreen", srgb("#2F6B4F"), roughness=0.5)
    m["shutterB"] = BK.tint("PZ_Wood", PFX + "M_ShutterTeal", srgb("#24707A"), roughness=0.5)
    m["door"] = BK.tint("PZ_Wood", PFX + "M_Door", srgb("#8C4A2F"), roughness=0.45)
    m["patina"] = BK.tint("PZ_Wood", PFX + "M_Patina", srgb("#5FB496"), roughness=0.55)
    m["iron"] = BK.tint("PZ_Iron", PFX + "M_Iron", srgb("#23232A"), roughness=0.45)
    m["paving"] = BK.tint("PZ_Paving", PFX + "M_Paving", srgb("#C3AE8A"), roughness=0.8)
    m["paving2"] = BK.tint("PZ_Paving", PFX + "M_PavingDark", srgb("#8E7350"), roughness=0.8)
    m["glass"] = BK.flat(PFX + "M_Glass", srgb("#1E3038"), roughness=0.08)
    m["ground"] = BK.flat(PFX + "M_Ground", srgb("#C8B394"), roughness=0.9)
    m["white"] = BK.flat(PFX + "M_White", srgb("#FBF6EC"), roughness=0.6)
    m["leaf"] = BK.flat(PFX + "M_Leaf", srgb("#4E8F4A"), roughness=0.8)
    m["leaf2"] = BK.flat(PFX + "M_Leaf2", srgb("#6DA85C"), roughness=0.8)
    m["lamp"] = BK.flat(PFX + "M_LampGlow", srgb("#FFE6B0"), roughness=0.4, emission=3.0)
    for i, c in enumerate(BUNTING):
        m["b%d" % i] = BK.flat(PFX + "M_Flag%d" % i, srgb(c), roughness=0.75)
    BK.MAT_UV_SCALE.update({
        PFX + "M_Paving": 0.5, PFX + "M_PavingDark": 0.5,
        PFX + "M_Roof": 1.6, PFX + "M_Stone": 0.8,
    })
    return m

# ------------------------------------------------------------ wall plumbing --
# Facades are axis-aligned, so every piece is placed in a wall-local (u, w)
# frame: u runs along the facade, w is height. `inward` points into the building.


def framer(mb, axis, fixed, inward):
    def place(u, w, du, dw, thick, mat, off=0.0, uvs=0.0):
        pos = fixed + inward * (thick / 2.0 + off)
        if axis == "X":
            mb.box((u, pos, w), (du, thick, dw), mat, uvs=uvs)
        else:
            mb.box((pos, u, w), (thick, du, dw), mat, uvs=uvs)
    return place


def arch_ring(mb, axis, fixed, inward, uc, spring, radius, thick, ring_w, mat,
              segs=15, off=0.0):
    """Voussoir ring. Each stone is rotated tangentially -- stepping unrotated
    boxes around the arc reads as a staircase at any sane segment count."""
    for i in range(segs):
        phi = math.pi * (i + 0.5) / segs
        du = (math.pi * radius / segs) * 1.12
        rr = radius + ring_w / 2.0
        u = uc + rr * math.cos(phi)
        w = spring + rr * math.sin(phi)
        pos = fixed + inward * (thick / 2.0 + off)
        if axis == "X":
            mb.box((u, pos, w), (du, thick, ring_w), mat, rot=(0, math.pi / 2 - phi, 0))
        else:
            mb.box((pos, u, w), (thick, du, ring_w), mat, rot=(phi - math.pi / 2, 0, 0))


def arch_spandrel(mb, place, uc, half, spring, radius, top, thick, mat, n=20):
    """Wall above a round-headed opening, as vertical slabs following the arc."""
    for i in range(n):
        u0 = uc - half + 2 * half * i / n
        u1 = uc - half + 2 * half * (i + 1) / n
        um = (u0 + u1) / 2.0
        d = abs(um - uc)
        h = spring + (math.sqrt(max(0.0, radius ** 2 - d ** 2)) if d < radius else 0.0)
        if top - h > 0.02:
            place(um, (h + top) / 2.0, (u1 - u0) + 0.02, top - h, thick, mat)


def shutters(mb, axis, fixed, inward, uc, wc, ow, oh, mat, slats=7):
    """Two louvered leaves folded flat against the wall beside the opening."""
    lw = ow / 2.0 * 0.92
    for s in (-1, 1):
        cu = uc + s * (ow / 2.0 + lw / 2.0 + 0.04)
        pos = fixed - inward * 0.09
        def blk(u, w, du, dw, th, m):
            if axis == "X":
                mb.box((u, pos - inward * th / 2.0, w), (du, th, dw), m)
            else:
                mb.box((pos - inward * th / 2.0, u, w), (th, du, dw), m)
        blk(cu, wc + oh / 2.0 - 0.06, lw, 0.12, 0.09, mat)      # top rail
        blk(cu, wc - oh / 2.0 + 0.06, lw, 0.12, 0.09, mat)      # bottom rail
        for e in (-1, 1):
            blk(cu + e * (lw / 2.0 - 0.05), wc, 0.10, oh, 0.09, mat)
        for i in range(slats):
            z = wc - oh / 2.0 + oh * (i + 0.5) / slats
            blk(cu, z, lw - 0.16, oh / slats * 0.62, 0.055, mat)


def window(mb, axis, fixed, inward, place, uc, sill, ow, oh, wall, mats,
           balcony=False, shutter_mat=None):
    trim, iron, glass = mats["trim"], mats["iron"], mats["glass"]
    wc = sill + oh / 2.0
    place(uc, wc, ow, oh, 0.1, glass, off=WT - 0.14)             # glazing
    B = 0.16
    place(uc, sill - B / 2.0, ow + 2 * B, B, 0.16, trim, off=-0.06)
    place(uc, sill + oh + B / 2.0, ow + 2 * B, B, 0.16, trim, off=-0.06)
    for s in (-1, 1):
        place(uc + s * (ow + B) / 2.0, wc, B, oh, 0.16, trim, off=-0.06)
    place(uc, sill - 0.16, ow + 0.75, 0.14, 0.30, trim, off=-0.16)   # sill
    place(uc, sill + oh + 0.30, ow + 0.85, 0.20, 0.34, trim, off=-0.18)  # hood
    if shutter_mat:
        shutters(mb, axis, fixed, inward, uc, wc, ow, oh, shutter_mat)
    if balcony:
        place(uc, sill - 0.30, ow + 1.15, 0.16, 0.95, trim, off=-0.80)
        pos = fixed - inward * 0.78
        for k in range(9):
            u = uc - (ow + 0.9) / 2.0 + (ow + 0.9) * k / 8.0
            if axis == "X":
                mb.box((u, pos, sill + 0.28), (0.055, 0.055, 0.85), iron)
            else:
                mb.box((pos, u, sill + 0.28), (0.055, 0.055, 0.85), iron)
        for zz in (sill + 0.70, sill - 0.14):
            if axis == "X":
                mb.box((uc, pos, zz), (ow + 0.95, 0.07, 0.07), iron)
            else:
                mb.box((pos, uc, zz), (0.07, ow + 0.95, 0.07), iron)


def gable_roof(mb, axis, fixed, inward, a0, a1, depth, top, mats):
    """Ridge parallel to the facade, tiled slopes, overhanging eaves, and a row
    of barrel tiles at the front eave where the eye actually lands."""
    tile, trim = mats["roof"], mats["trim"]
    EO, RISE, TH = 0.95, 2.0, 0.26
    s = inward
    f = fixed - s * EO
    r = fixed + s * depth / 2.0
    b = fixed + s * (depth + EO)
    u0, u1 = a0 - EO, a1 + EO
    zl, zh = top - 0.06, top + RISE

    def P(u, v, z):
        return (u, v, z) if axis == "X" else (v, u, z)

    mb.extrude_poly([P(u0, f, zl), P(u1, f, zl), P(u1, r, zh), P(u0, r, zh)],
                    (0, 0, -TH), tile)
    mb.extrude_poly([P(u0, r, zh), P(u1, r, zh), P(u1, b, zl), P(u0, b, zl)],
                    (0, 0, -TH), tile)
    gv = (0.14, 0, 0) if axis == "X" else (0, 0.14, 0)
    for u, sgn in ((u0, -1), (u1, 1)):
        mb.extrude_poly([P(u, f, zl - TH), P(u, r, zh - TH), P(u, b, zl - TH)],
                        tuple(g * sgn for g in gv), trim)
    # fascia board along the front eave
    if axis == "X":
        mb.box(((u0 + u1) / 2.0, f, zl - TH - 0.1), (u1 - u0, 0.16, 0.3), trim)
    else:
        mb.box((f, (u0 + u1) / 2.0, zl - TH - 0.1), (0.16, u1 - u0, 0.3), trim)
    # barrel tiles running up the front slope
    ang = math.atan2(RISE, depth / 2.0 + EO)
    n = max(2, int((u1 - u0) / 0.38))
    for i in range(n):
        u = u0 + (u1 - u0) * (i + 0.5) / n
        c = P(u, f + s * 0.9, zl + 0.9 * math.tan(ang) + 0.08)
        rot = (ang - math.pi / 2, 0, 0) if s > 0 else (math.pi / 2 - ang, 0, 0)
        if axis == "Y":
            rot = (0, math.pi / 2 - ang, 0) if s > 0 else (0, ang - math.pi / 2, 0)
        mb.cyl(c, 0.115, 2.0, tile, segments=10, rot=rot)

# ---------------------------------------------------------------- buildings --


def colonial_building(name, coll, axis, fixed, inward, a0, a1, depth, floors,
                      wall, mats, arcade=True, shutter_mat=None, prefix=PFX):
    mb = MB("Bldg_" + name, prefix)
    place = framer(mb, axis, fixed, inward)
    trim, stone = mats["trim"], mats["stone"]
    L = a1 - a0
    mid = (a0 + a1) / 2.0
    top = PLINTH + GF + (floors - 1) * FL

    place(mid, PLINTH / 2.0, L + 0.3, PLINTH, WT + 0.3, stone, off=-0.15)

    # ---- ground storey -------------------------------------------------
    if arcade:
        PW, SPRING = 1.25, 3.15
        n = max(2, int(round((L - PW) / 3.9)))
        ow = (L - PW * (n + 1)) / n
        rad = ow / 2.0
        for i in range(n + 1):
            pc = a0 + i * (PW + ow) + PW / 2.0
            place(pc, PLINTH + (SPRING + rad) / 2.0, PW, SPRING + rad, WT, wall)
            place(pc, PLINTH + SPRING + rad + 0.14, PW + 0.24, 0.28, WT + 0.16,
                  trim, off=-0.08)                                  # impost block
        for i in range(n):
            uc = a0 + PW * (i + 1) + ow * i + ow / 2.0
            arch_spandrel(mb, place, uc, rad + 0.02, PLINTH + SPRING, rad,
                          PLINTH + GF, WT, wall)
            arch_ring(mb, axis, fixed, inward, uc, PLINTH + SPRING, rad, WT + 0.18,
                      0.34, trim, off=-0.09)
            # shop front set back inside the arcade
            back = fixed + inward * 3.0
            bp = framer(mb, axis, back, inward)
            bp(uc, PLINTH + 1.55, ow - 0.25, 3.1, 0.12, mats["glass"], off=-0.06)
            bp(uc, PLINTH + 3.2, ow + 0.3, 0.28, 0.3, trim, off=-0.1)
    else:
        n = max(1, int(round(L / 5.2)))
        bw = L / n
        for i in range(n):
            uc = a0 + bw * (i + 0.5)
            place(uc, PLINTH + 1.75, bw - 1.1, 3.3, 0.12, mats["glass"], off=WT - 0.16)
            place(uc, PLINTH + 3.55, bw - 0.8, 0.3, 0.34, trim, off=-0.12)
            for s in (-1, 1):
                place(uc + s * (bw - 1.1) / 2.0, PLINTH + 1.75, 0.22, 3.3, 0.2,
                      trim, off=-0.08)
            place(uc, PLINTH + GF - 0.55, bw, 1.1, WT, wall)
        for i in range(n + 1):
            place(a0 + bw * i, PLINTH + GF / 2.0, 0.55, GF, WT, wall)

    # ---- string course, upper storeys, cornice -------------------------
    place(mid, PLINTH + GF + 0.16, L + 0.4, 0.32, WT + 0.34, trim, off=-0.17)
    nw = max(2, int(round(L / 3.4)))
    for fl in range(1, floors):
        z0 = PLINTH + GF + (fl - 1) * FL
        place(mid, z0 + FL / 2.0, L, FL, WT, wall)
        for i in range(nw):
            uc = a0 + L * (i + 0.5) / nw
            window(mb, axis, fixed, inward, place, uc, z0 + 0.95, 1.35, 2.35,
                   wall, mats, balcony=(fl == 1), shutter_mat=shutter_mat)
        if fl < floors - 1:
            place(mid, z0 + FL - 0.12, L + 0.3, 0.24, WT + 0.26, trim, off=-0.13)
    for k, (ww, hh) in enumerate(((0.5, 0.26), (0.78, 0.3), (0.4, 0.22))):
        place(mid, top - 0.4 + k * 0.3, L + ww, hh, WT + ww, trim, off=-ww / 2.0)

    # ---- flanks, back, roof --------------------------------------------
    fl_len = depth
    for side, u in ((-1, a0), (1, a1)):
        if axis == "X":
            mb.box((u - side * WT / 2.0, fixed + inward * fl_len / 2.0, top / 2.0),
                   (WT, fl_len, top), wall)
        else:
            mb.box((fixed + inward * fl_len / 2.0, u - side * WT / 2.0, top / 2.0),
                   (fl_len, WT, top), wall)
    if axis == "X":
        mb.box((mid, fixed + inward * (depth - WT / 2.0), top / 2.0), (L, WT, top), wall)
    else:
        mb.box((fixed + inward * (depth - WT / 2.0), mid, top / 2.0), (WT, L, top), wall)

    # Carry the plinth/string/cornice around the flanks. The plaza corners are
    # left open as street mouths, so the flanks are on camera and a bare
    # coloured slab there kills the whole facade language.
    for u, outw in ((a0, -1), (a1, 1)):
        def band(zc, dz, proj, mat):
            if axis == "X":
                mb.box((u + outw * proj / 2.0, fixed + inward * depth / 2.0, zc),
                       (proj, depth, dz), mat)
            else:
                mb.box((fixed + inward * depth / 2.0, u + outw * proj / 2.0, zc),
                       (depth, proj, dz), mat)
        band(PLINTH / 2.0, PLINTH, 0.34, stone)
        band(PLINTH + GF + 0.16, 0.32, 0.30, trim)
        for fl in range(1, floors - 1):
            band(PLINTH + GF + fl * FL - 0.12, 0.24, 0.24, trim)
        for k, (ww, hh) in enumerate(((0.5, 0.26), (0.78, 0.3), (0.4, 0.22))):
            band(top - 0.4 + k * 0.3, hh, 0.26 + ww * 0.45, trim)

    gable_roof(mb, axis, fixed, inward, a0, a1, depth, top, mats)

    o = (mid, fixed + inward * depth / 2.0, 0) if axis == "X" else \
        (fixed + inward * depth / 2.0, mid, 0)
    return mb.finish(coll, origin=o, bevel=0.035)

# -------------------------------------------------------------------- props --


def bandstand(coll, mats, prefix=PFX):
    """The plaza's hero prop: octagonal kiosco with a patina copper roof."""
    mb = MB("Bandstand", prefix)
    trim, iron, pat, stone = mats["trim"], mats["iron"], mats["patina"], mats["stone"]
    for i, (r, z) in enumerate(((8.0, 0.16), (7.4, 0.44), (6.8, 0.72))):
        mb.cyl((0, 0, z), r, 0.30, stone, segments=8, rot=(0, 0, math.pi / 8))
    DECK = 0.95
    mb.cyl((0, 0, DECK - 0.14), 6.5, 0.34, stone, segments=8, rot=(0, 0, math.pi / 8))
    R, N = 5.5, 8
    CH = 4.3
    for i in range(N):
        a = 2 * math.pi * i / N + math.pi / 8
        x, y = R * math.cos(a), R * math.sin(a)
        mb.box((x, y, DECK + 0.16), (0.62, 0.62, 0.32), trim, rot=(0, 0, a))
        mb.cyl((x, y, DECK + CH / 2.0), 0.23, CH, trim, segments=16, radius_top=0.20)
        mb.box((x, y, DECK + CH - 0.1), (0.58, 0.58, 0.34), trim, rot=(0, 0, a))
        # railing to the next column, left open at the front bay
        a2 = 2 * math.pi * (i + 1) / N + math.pi / 8
        if i in (0, 7):
            continue
        p0 = Vector((R * math.cos(a), R * math.sin(a), DECK))
        p1 = Vector((R * math.cos(a2), R * math.sin(a2), DECK))
        mb.beam(p0 + Vector((0, 0, 0.12)), p1 + Vector((0, 0, 0.12)), 0.14, 0.14, trim)
        mb.beam(p0 + Vector((0, 0, 1.05)), p1 + Vector((0, 0, 1.05)), 0.20, 0.16, trim)
        for k in range(1, 8):
            t = k / 8.0
            q = p0.lerp(p1, t)
            mb.cyl((q.x, q.y, DECK + 0.58), 0.055, 0.95, iron, segments=8)
    mb.cyl((0, 0, DECK + CH + 0.35), 6.3, 0.45, trim, segments=8, rot=(0, 0, math.pi / 8))
    mb.cyl((0, 0, DECK + CH + 0.62), 6.0, 0.12, mats["white"], segments=8,
           rot=(0, 0, math.pi / 8))
    mb.cyl((0, 0, DECK + CH + 2.4), 6.7, 3.3, pat, segments=8, radius_top=0.55,
           rot=(0, 0, math.pi / 8))
    mb.cyl((0, 0, DECK + CH + 4.15), 0.32, 0.5, pat, segments=8)
    mb.sphere((0, 0, DECK + CH + 4.6), 0.34, pat, segments=16)
    mb.cyl((0, 0, DECK + CH + 5.15), 0.07, 0.8, iron, segments=8)
    return mb.finish(coll, origin=(0, 0, 0), bevel=0.03)


def lamp_post(mb, x, y, mats, banner=None):
    iron, glow = mats["iron"], mats["lamp"]
    mb.cyl((x, y, 0.20), 0.42, 0.40, iron, segments=12)
    mb.cyl((x, y, 0.55), 0.30, 0.36, iron, segments=12)
    mb.cyl((x, y, 2.6), 0.13, 4.2, iron, segments=12, radius_top=0.10)
    mb.cyl((x, y, 4.75), 0.22, 0.22, iron, segments=12)
    for a in (0.0, math.pi * 2 / 3, math.pi * 4 / 3):
        dx, dy = 1.05 * math.cos(a), 1.05 * math.sin(a)
        mb.beam((x, y, 4.85), (x + dx, y + dy, 5.20), 0.075, 0.075, iron)
        mb.cyl((x + dx, y + dy, 5.42), 0.21, 0.44, iron, segments=6, radius_top=0.11)
        mb.cyl((x + dx, y + dy, 5.16), 0.17, 0.22, glow, segments=6)
    mb.cyl((x, y, 5.95), 0.10, 0.45, iron, segments=8, radius_top=0.02)
    if banner is not None:
        for s in (-1, 1):
            mb.beam((x, y, 3.9), (x + s * 0.55, y, 3.9), 0.06, 0.06, iron)
            mb.box((x + s * 0.62, y, 3.2), (0.62, 0.04, 1.5), banner)


def bunting_line(mb, p0, p1, sag, mats, n=24):
    cols = [mats["b%d" % i] for i in range(len(BUNTING))]
    def pt(t):
        return Vector((p0[0] + (p1[0] - p0[0]) * t,
                       p0[1] + (p1[1] - p0[1]) * t,
                       p0[2] + (p1[2] - p0[2]) * t - sag * 4 * t * (1 - t)))
    for i in range(n):
        a, b = pt(i / n), pt((i + 1) / n)
        mb.beam(a, b, 0.022, 0.022, mats["iron"])
        m = (a + b) / 2.0
        d = (b - a).normalized()
        w = 0.30
        mb.tri(m - d * w, m + d * w, m - Vector((0, 0, 0.62)), cols[i % len(cols)])


def parasol(mb, x, y, mats, col, r=1.7, h=2.35):
    mb.cyl((x, y, h / 2.0), 0.055, h, mats["iron"], segments=8)
    for i in range(8):
        a0 = 2 * math.pi * i / 8
        a1 = 2 * math.pi * (i + 1) / 8
        m = col if i % 2 == 0 else mats["white"]
        mb.tri((x, y, h + 0.42),
               (x + r * math.cos(a0), y + r * math.sin(a0), h - 0.12),
               (x + r * math.cos(a1), y + r * math.sin(a1), h - 0.12), m)
    mb.cyl((x, y, h + 0.52), 0.05, 0.3, mats["iron"], segments=6)


def cafe_set(mb, x, y, mats, col):
    iron, white = mats["iron"], mats["white"]
    mb.cyl((x, y, 0.36), 0.06, 0.72, iron, segments=8)
    mb.cyl((x, y, 0.05), 0.35, 0.06, iron, segments=12)
    mb.cyl((x, y, 0.75), 0.62, 0.07, white, segments=20)
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.6
        cx, cy = x + 1.15 * math.cos(a), y + 1.15 * math.sin(a)
        mb.box((cx, cy, 0.44), (0.44, 0.44, 0.06), col, rot=(0, 0, -a))
        mb.box((cx + 0.20 * math.cos(a), cy + 0.20 * math.sin(a), 0.70),
               (0.42, 0.08, 0.48), col, rot=(0, 0, -a))
        for k in (-1, 1):
            for j in (-1, 1):
                mb.cyl((cx + k * 0.16, cy + j * 0.16, 0.21), 0.03, 0.42, iron, segments=6)


def planter(mb, x, y, mats, kind=0):
    stone, leaf = mats["stone"], mats["leaf"]
    mb.box((x, y, 0.34), (1.5, 1.5, 0.68), stone)
    mb.box((x, y, 0.72), (1.62, 1.62, 0.16), mats["trim"])
    if kind == 0:
        mb.cyl((x, y, 1.0), 0.16, 0.6, mats["door"], segments=8)
        for i, (rr, zz) in enumerate(((0.75, 1.65), (0.58, 2.35))):
            mb.sphere((x, y, zz), rr, leaf if i == 0 else mats["leaf2"], segments=16)
    else:
        mb.cyl((x, y, 1.9), 0.75, 2.4, mats["leaf2"], segments=10, radius_top=0.05)


def palm(mb, x, y, mats, h=6.0):
    trunk, leaf = mats["door"], mats["leaf"]
    seg = 7
    for i in range(seg):
        t = i / seg
        r = 0.30 - 0.12 * t
        mb.cyl((x + 0.28 * math.sin(t * 2.2), y, h * (i + 0.5) / seg),
               r, h / seg * 1.08, trunk, segments=10)
    tipx = x + 0.28 * math.sin(2.2)
    # Fronds as tapered, drooping, *extruded* strips. Single flat triangles turn
    # edge-on into slivers and the whole crown reads as a green asterisk.
    for i in range(11):
        a = 2 * math.pi * i / 11 + 0.2
        ca, sa = math.cos(a), math.sin(a)
        L, droop = 3.2 + 0.5 * (i % 3), 2.1 + 0.5 * (i % 2)
        seg = 4
        for k in range(seg):
            t0, t1 = k / seg, (k + 1) / seg
            def cs(t):
                w = 0.34 * (1.0 - 0.82 * t) + 0.02
                px, py = tipx + ca * L * t, y + sa * L * t
                pz = h + 0.35 - droop * t * t
                return ((px - sa * w, py + ca * w, pz), (px + sa * w, py - ca * w, pz))
            l0, r0 = cs(t0)
            l1, r1 = cs(t1)
            mb.extrude_poly([l0, r0, r1, l1], (0, 0, -0.07),
                            leaf if i % 2 else mats["leaf2"])


def market_stall(mb, x, y, rot, mats, col):
    iron, white = mats["iron"], mats["white"]
    c, s = math.cos(rot), math.sin(rot)
    def R(u, v):
        return (x + u * c - v * s, y + u * s + v * c)
    for u, v in ((-1.7, -0.9), (1.7, -0.9), (-1.7, 0.9), (1.7, 0.9)):
        px, py = R(u, v)
        mb.cyl((px, py, 1.15), 0.055, 2.3, iron, segments=6)
    px, py = R(0, 0)
    mb.box((px, py, 0.85), (3.6, 1.9, 0.1), white, rot=(0, 0, rot))
    # ridged canopy built from explicit corners -- stacking a tilt and a yaw
    # into one XYZ euler skews the strips into a flat plank
    n = 8
    for i in range(n):
        u0, u1 = -1.9 + 3.8 * i / n, -1.9 + 3.8 * (i + 1) / n
        m = col if i % 2 else white
        for v0, z0, v1, z1 in ((-1.2, 2.2, 0.0, 2.75), (0.0, 2.75, 1.2, 2.2)):
            q0, q1 = R(u0, v0), R(u1, v0)
            q2, q3 = R(u1, v1), R(u0, v1)
            mb.extrude_poly([(q0[0], q0[1], z0), (q1[0], q1[1], z0),
                             (q2[0], q2[1], z1), (q3[0], q3[1], z1)], (0, 0, -0.08), m)
    for i in range(9):
        u = -1.7 + 3.4 * i / 8
        qx, qy = R(u, -0.55)
        mb.sphere((qx, qy, 1.05), 0.22, mats["b%d" % (i % 4)], segments=10)


def awning(mb, axis, fixed, inward, uc, half, z, mats, col, drop=2.3):
    """Striped shop awning -- alternating geometry strips, not a texture, which
    is what gives the reference its crisp graphic edge."""
    n = 9
    for i in range(n):
        t0 = -half + 2 * half * i / n
        t1 = -half + 2 * half * (i + 1) / n
        m = col if i % 2 == 0 else mats["white"]
        if axis == "X":
            mb.extrude_poly([(uc + t0, fixed - inward * 0.05, z),
                             (uc + t1, fixed - inward * 0.05, z),
                             (uc + t1, fixed - inward * drop, z - 0.95),
                             (uc + t0, fixed - inward * drop, z - 0.95)],
                            (0, 0, -0.09), m)
        else:
            mb.extrude_poly([(fixed - inward * 0.05, uc + t0, z),
                             (fixed - inward * 0.05, uc + t1, z),
                             (fixed - inward * drop, uc + t1, z - 0.95),
                             (fixed - inward * drop, uc + t0, z - 0.95)],
                            (0, 0, -0.09), m)

# -------------------------------------------------------------------- build --


def build():
    BK.purge_coll(ROOT)
    mats = build_materials()
    scene = bpy.data.scenes.get(SCENE) or bpy.data.scenes.new(SCENE)
    root = BK.ensure_coll(ROOT, scene.collection)
    c_grd = BK.ensure_coll(PFX + "Ground", root)
    c_bld = BK.ensure_coll(PFX + "Buildings", root)
    c_prp = BK.ensure_coll(PFX + "Props", root)
    c_lgt = BK.ensure_coll(PFX + "Lighting", root)

    # ---- ground, paving ------------------------------------------------
    g = MB("Ground", PFX)
    g.box((0, 0, -0.4), (300, 300, 0.8), mats["ground"])
    g.finish(c_grd, bevel=0.0)

    p = MB("Paving", PFX)
    H = PLAZA_HALF
    p.box((0, 0, 0.06), (2 * H, 2 * H, 0.12), mats["paving"])
    for s in (-1, 1):                                   # dark border frame
        p.box((s * (H - 1.6), 0, 0.135), (2.4, 2 * H, 0.13), mats["paving2"])
        p.box((0, s * (H - 1.6), 0.135), (2 * H - 4.8, 2.4, 0.13), mats["paving2"])
    for k in range(1, 7):                               # joint bands, both ways
        for s in (-1, 1):
            o = s * k * 6.0 - 3.0
            if abs(o) < H - 3.2:
                p.box((o, 0, 0.132), (0.3, 2 * H - 6.4, 0.13), mats["paving2"])
                p.box((0, o, 0.132), (2 * H - 6.4, 0.3, 0.13), mats["paving2"])
    p.ring((0, 0, 0.145), 9.4, 10.4, 0.15, mats["paving2"], segments=72)
    p.cyl((0, 0, 0.145), 9.4, 0.15, mats["paving"], segments=72)
    p.ring((0, 0, 0.16), 6.9, 7.4, 0.16, mats["paving2"], segments=64)
    # sidewalk + curb around the square
    for s in (-1, 1):
        p.box((s * (H + WALK / 2.0), 0, 0.14), (WALK, 2 * (H + WALK), 0.28), mats["stone"])
        p.box((0, s * (H + WALK / 2.0), 0.14), (2 * (H + WALK), WALK, 0.28), mats["stone"])
        p.box((s * H, 0, 0.17), (0.34, 2 * H, 0.34), mats["paving2"])
        p.box((0, s * H, 0.17), (2 * H, 0.34, 0.34), mats["paving2"])
    p.finish(c_grd, bevel=0.02)

    # ---- the four building rows ----------------------------------------
    W = {n: mats[n] for n, _ in WALL_COLORS}
    rows = [
        ("N1", "X",  FACE,  1, -22.5, -7.5, 15, 2, "Terracotta", True,  "shutterA"),
        ("N2", "X",  FACE,  1,  -7.0,  7.0, 16, 3, "Cream",      True,  "shutterB"),
        ("N3", "X",  FACE,  1,   7.5, 22.5, 15, 2, "Mint",       True,  "shutterA"),
        ("S1", "X", -FACE, -1, -22.5, -7.5, 15, 2, "Mustard",    False, "shutterA"),
        ("S2", "X", -FACE, -1,  -7.0,  8.0, 16, 3, "Rose",       True,  "shutterB"),
        ("S3", "X", -FACE, -1,   8.5, 22.5, 14, 2, "Teal",       False, "shutterA"),
        ("E1", "Y",  FACE,  1, -20.0, -2.0, 15, 2, "Coral",      False, "shutterB"),
        ("E2", "Y",  FACE,  1,   2.0, 20.0, 16, 3, "Sage",       True,  "shutterA"),
        ("W1", "Y", -FACE, -1, -20.0, -1.0, 16, 3, "Cream",      True,  "shutterA"),
        ("W2", "Y", -FACE, -1,   1.5, 20.0, 15, 2, "Mustard",    False, "shutterB"),
    ]
    for nm, ax, fx, iw, a0, a1, dp, fls, col, arc, sh in rows:
        colonial_building(nm, c_bld, ax, fx, iw, a0, a1, dp, fls, W[col], mats,
                          arcade=arc, shutter_mat=mats[sh])

    # awnings on the non-arcaded shopfronts
    aw = MB("Awnings", PFX)
    for nm, ax, fx, iw, a0, a1, dp, fls, col, arc, sh in rows:
        if arc:
            continue
        n = max(1, int(round((a1 - a0) / 5.2)))
        bw = (a1 - a0) / n
        for i in range(n):
            uc = a0 + bw * (i + 0.5)
            awning(aw, ax, fx, iw, uc, bw / 2.0 - 0.35, PLINTH + 4.05, mats,
                   mats["b%d" % (i % 4)])
    aw.finish(c_prp, bevel=0.015)

    bandstand(c_prp, mats)

    # ---- street furniture ----------------------------------------------
    f = MB("Furniture", PFX)
    lamps = []
    for s in (-1, 1):
        for t in (-1, 1):
            lamps.append((s * 15.5, t * 15.5))
    for i, (x, y) in enumerate(lamps):
        lamp_post(f, x, y, mats, banner=mats["b%d" % (i % 4)])
    for x, y in ((-19.5, -19.5), (19.5, -19.5), (-19.5, 19.5), (19.5, 19.5)):
        lamp_post(f, x, y, mats)
    for i, (x, y) in enumerate(((-13.5, -12.5), (-14, 3), (14, -3), (13.5, 12.5),
                                (-6.5, 16.5), (7.5, -13.0))):
        parasol(f, x, y, mats, mats["b%d" % (i % 4)])
        cafe_set(f, x, y, mats, mats["white"])
    for i, (x, y) in enumerate(((-20.5, -4), (-20.5, 8), (20.5, -8), (20.5, 4),
                                (-4, -20.5), (8, -20.5), (-8, 20.5), (4, 20.5))):
        planter(f, x, y, mats, kind=i % 2)
    for x, y in ((-21.5, -14.5), (21.5, 14.5)):
        palm(f, x, y, mats)
    market_stall(f, -17.0, -6.5, math.pi / 2 + 0.25, mats, mats["b0"])
    market_stall(f, 17.0, 6.5, -math.pi / 2 + 0.25, mats, mats["b1"])
    market_stall(f, 5.0, -18.5, 0.1, mats, mats["b2"])
    f.finish(c_prp, bevel=0.02)

    # ---- bunting strung across the square ------------------------------
    b = MB("Bunting", PFX)
    Z = 8.4
    for k in range(4):
        o = -12 + 8 * k
        bunting_line(b, (-FACE + 1.0, o, Z), (FACE - 1.0, o + 3.0, Z), 3.0, mats)
    for k in range(3):
        o = -9 + 9 * k
        bunting_line(b, (o, -FACE + 1.0, Z + 1.2), (o + 2.0, FACE - 1.0, Z + 1.2), 3.2, mats)
    b.finish(c_prp, bevel=0.0)

    # ---- sun, sky, camera ----------------------------------------------
    w = bpy.data.worlds.get(PFX + "Sky") or bpy.data.worlds.new(PFX + "Sky")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    ids = [i.identifier for i in sky.bl_rna.properties["sky_type"].enum_items]
    sky.sky_type = "MULTIPLE_SCATTERING" if "MULTIPLE_SCATTERING" in ids else "NISHITA"
    sky.sun_elevation = math.radians(58)
    sky.sun_rotation = math.radians(35)
    for prop, val in (("sun_intensity", 0.12), ("air_density", 0.9),
                      ("dust_density", 0.3), ("sun_disc", False)):
        if hasattr(sky, prop):
            setattr(sky, prop, val)
    bg.inputs[1].default_value = 0.24
    nt.links.new(sky.outputs[0], bg.inputs[0])
    nt.links.new(bg.outputs[0], out.inputs[0])
    scene.world = w

    # AgX rolls saturation out of exactly the bright pastels this style is made
    # of; Khronos PBR Neutral keeps them. Scene-local, so StreetPreview is
    # untouched.
    try:
        scene.view_settings.view_transform = "Khronos PBR Neutral"
    except TypeError:
        pass

    sd = bpy.data.lights.new(PFX + "Sun", "SUN")
    sd.energy = 3.4
    sd.angle = math.radians(1.6)
    sd.color = (1.0, 0.96, 0.90)
    sun = bpy.data.objects.new(PFX + "Sun", sd)
    sun.rotation_euler = Euler((math.radians(34), 0, math.radians(35)), "XYZ")
    c_lgt.objects.link(sun)

    cd = bpy.data.cameras.new(PFX + "Cam")
    cam = bpy.data.objects.new(PFX + "Cam", cd)
    c_lgt.objects.link(cam)
    scene.camera = cam

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.eevee.taa_render_samples = 64
    scene.eevee.use_shadows = True
    try:
        scene.eevee.use_raytracing = True
        scene.eevee.ray_tracing_options.use_denoise = True
    except Exception:
        pass
    aim(cam, *SHOTS["hero"])

    n_tris = sum(len(o.data.polygons) for c in (c_grd, c_bld, c_prp)
                 for o in c.objects if o.type == "MESH")
    return len(list(root.children_recursive)), n_tris


SHOTS = {
    "hero":   ((-11.0, -18.5, 1.70), (2.0, 3.0, 5.0), 30),
    "arcade": ((-13.5, 24.2, 1.72), (9.0, -12.0, 4.5), 26),
    "kiosco": ((-9.0, -12.5, 2.4), (0.0, 0.0, 5.2), 42),
    "corner": ((-38.0, -39.0, 11.0), (1.0, 1.0, 4.5), 32),
    "aerial": ((-46.0, -50.0, 40.0), (0.0, 0.0, 5.0), 42),
}


def aim(cam, loc, tgt, lens):
    cam.data.lens = lens
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def render_shots(out_dir, names=None, res=(1600, 900), samples=64, prefix=""):
    scene = bpy.data.scenes[SCENE]
    cam = bpy.data.objects[PFX + "Cam"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.eevee.taa_render_samples = samples
    for n in (names or SHOTS):
        aim(cam, *SHOTS[n])
        scene.render.filepath = out_dir.rstrip("/") + "/" + prefix + n + ".png"
        bpy.ops.render.render(write_still=True, scene=SCENE)
        print("shot", n)
    aim(cam, *SHOTS["hero"])


if True:
    print("Plaza built:", build())
