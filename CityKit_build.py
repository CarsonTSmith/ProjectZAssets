# ============================================================================
# CityKit executor -- turns module DATA into finished low-poly kit objects.
# Reads catalog from globals: CITYKIT_CATALOG (list) or CITYKIT_CATALOG_PATH (json file).
# Pure bmesh + data API (NO bpy.ops for geometry/join) -> robust under MCP.
# ============================================================================
import bpy, bmesh, json, math, os
from mathutils import Matrix, Vector, Euler

BEVEL_W      = 0.04
SMOOTH_ANGLE = math.radians(50)
SHARP_ANGLE  = math.radians(35)   # edges sharper than this get beveled
UV_SCALE     = 0.5

# --- material palette: name -> (r,g,b, roughness, metallic) ----------------
PALETTE = {
    "M_Concrete":      (0.62, 0.62, 0.60, 0.90, 0.0),
    "M_Concrete_Dark": (0.40, 0.40, 0.42, 0.90, 0.0),
    "M_Brick":         (0.55, 0.27, 0.20, 0.95, 0.0),
    "M_Plaster":       (0.85, 0.80, 0.70, 0.90, 0.0),
    "M_Plaster_Warm":  (0.80, 0.62, 0.45, 0.90, 0.0),
    "M_Trim_White":    (0.92, 0.92, 0.90, 0.60, 0.0),
    "M_Wood":          (0.45, 0.30, 0.18, 0.80, 0.0),
    "M_Glass":         (0.30, 0.55, 0.65, 0.10, 0.0),
    "M_Glass_Clear":   (0.55, 0.78, 0.85, 0.06, 0.0),
    "M_Metal_Dark":    (0.22, 0.23, 0.25, 0.50, 0.85),
    "M_Metal_Galv":    (0.65, 0.67, 0.70, 0.40, 0.85),
    "M_Roof":          (0.28, 0.28, 0.30, 0.95, 0.0),
    "M_Rubber":        (0.10, 0.10, 0.11, 0.90, 0.0),
    "M_Accent_Red":    (0.75, 0.18, 0.16, 0.70, 0.0),
    "M_Accent_Teal":   (0.10, 0.55, 0.55, 0.70, 0.0),
    "M_Accent_Yellow": (0.85, 0.65, 0.12, 0.70, 0.0),
    "M_Accent_Blue":   (0.18, 0.35, 0.62, 0.70, 0.0),
    "M_Sign_White":    (0.95, 0.95, 0.95, 0.50, 0.0),
    "M_Plastic_Grey":  (0.50, 0.50, 0.52, 0.60, 0.0),
    # light painted facade colors (for colored wall variants)
    "M_Facade_Red":    (0.85, 0.45, 0.42, 0.90, 0.0),
    "M_Facade_Blue":   (0.45, 0.60, 0.80, 0.90, 0.0),
    "M_Facade_Yellow": (0.92, 0.82, 0.45, 0.90, 0.0),
    "M_Facade_Green":  (0.56, 0.76, 0.53, 0.90, 0.0),
    "M_Facade_Orange": (0.93, 0.66, 0.42, 0.90, 0.0),
    "M_Facade_Purple": (0.67, 0.56, 0.80, 0.90, 0.0),
}
FALLBACK_MAT = "M_Concrete"

def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def _lin3(r, g, b):
    return (srgb_to_lin(r), srgb_to_lin(g), srgb_to_lin(b))

# Subtle "interest": name -> (mottle_amplitude, bump_strength). Very low amplitude
# keeps the clean flat low-poly look; matte surfaces get a touch of life.
MAT_FX = {
    "M_Concrete":      (0.12, 0.06),
    "M_Concrete_Dark": (0.12, 0.06),
    "M_Brick":         (0.14, 0.06),
    "M_Plaster":       (0.09, 0.05),
    "M_Plaster_Warm":  (0.10, 0.05),
    "M_Roof":          (0.12, 0.07),
    "M_Wood":          (0.12, 0.04),
    "M_Metal_Dark":    (0.07, 0.0),
    "M_Metal_Galv":    (0.07, 0.0),
    "M_Rubber":        (0.05, 0.0),
    "M_Plastic_Grey":  (0.06, 0.0),
    "M_Trim_White":    (0.04, 0.0),
    "M_Accent_Red":    (0.05, 0.0),
    "M_Accent_Teal":   (0.05, 0.0),
    "M_Accent_Yellow": (0.05, 0.0),
    "M_Accent_Blue":   (0.05, 0.0),
    "M_Facade_Red":    (0.08, 0.04),
    "M_Facade_Blue":   (0.08, 0.04),
    "M_Facade_Yellow": (0.08, 0.04),
    "M_Facade_Green":  (0.08, 0.04),
    "M_Facade_Orange": (0.08, 0.04),
    "M_Facade_Purple": (0.08, 0.04),
}
# alpha-blended (see-through) materials: name -> alpha
TRANSPARENT = {"M_Glass_Clear": 0.20}

def ensure_materials():
    for name, (r, g, b, rough, metal) in PALETTE.items():
        m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (300, 0)
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        base = _lin3(r, g, b)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        mottle, bump = MAT_FX.get(name, (0.0, 0.0))
        alpha = TRANSPARENT.get(name)

        if mottle > 0:
            tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-600, 100)
            noise = nt.nodes.new("ShaderNodeTexNoise"); noise.location = (-380, 100)
            noise.inputs["Scale"].default_value = 1.6
            noise.inputs["Detail"].default_value = 2.0
            try: noise.inputs["Roughness"].default_value = 0.6
            except Exception: pass
            nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
            ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.location = (-150, 100)
            dark = tuple(c * (1.0 - mottle) for c in base) + (1.0,)
            light = tuple(min(1.0, c * (1.0 + mottle * 0.45)) for c in base) + (1.0,)
            ramp.color_ramp.elements[0].position = 0.25
            ramp.color_ramp.elements[0].color = dark
            ramp.color_ramp.elements[1].position = 0.75
            ramp.color_ramp.elements[1].color = light
            nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        else:
            bsdf.inputs["Base Color"].default_value = base + (1.0,)

        if bump > 0:
            tc2 = nt.nodes.new("ShaderNodeTexCoord"); tc2.location = (-600, -300)
            bn = nt.nodes.new("ShaderNodeTexNoise"); bn.location = (-380, -300)
            bn.inputs["Scale"].default_value = 9.0
            bn.inputs["Detail"].default_value = 2.0
            nt.links.new(tc2.outputs["Object"], bn.inputs["Vector"])
            bnode = nt.nodes.new("ShaderNodeBump"); bnode.location = (0, -300)
            bnode.inputs["Strength"].default_value = bump
            bnode.inputs["Distance"].default_value = 0.02
            nt.links.new(bn.outputs["Fac"], bnode.inputs["Height"])
            nt.links.new(bnode.outputs["Normal"], bsdf.inputs["Normal"])

        if alpha is not None:
            bsdf.inputs["Alpha"].default_value = alpha
            m.blend_method = "BLEND"
            try: m.shadow_method = "HASHED"
            except Exception: pass
            try: m.use_screen_space_refraction = False
            except Exception: pass
            m.show_transparent_back = False
        else:
            m.blend_method = "OPAQUE"
        m.diffuse_color = base + (1.0,)

def get_mat(name):
    if name not in PALETTE:
        name = FALLBACK_MAT
    return bpy.data.materials.get(name)

# --- collections -----------------------------------------------------------
def ensure_collection(name, parent):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    if c.name not in [ch.name for ch in parent.children]:
        try:
            parent.children.link(c)
        except Exception:
            pass
    return c

def wipe_collection(col):
    if col is None:
        return
    for ob in list(col.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for ch in list(col.children):
        wipe_collection(ch)
        bpy.data.collections.remove(ch)

# --- geometry helpers (all add into a shared bmesh) ------------------------
def _new_elems(bm, pre_v, pre_f):
    nv = [v for v in bm.verts if v not in pre_v]
    nf = [f for f in bm.faces if f not in pre_f]
    return nv, nf

def add_part(bm, part):
    """Add one primitive into bm, return (new_faces, material_name)."""
    p = part.get("p", "box")
    mat = part.get("m", FALLBACK_MAT)
    do_bevel = part.get("b", True)
    loc = Vector(part.get("l", [0, 0, 0]))
    rot = part.get("r", [0, 0, 0])

    pre_v = set(bm.verts)
    pre_f = set(bm.faces)

    if p == "box":
        s = part.get("s", [1, 1, 1])
        bmesh.ops.create_cube(bm, size=1.0)
        nv = [v for v in bm.verts if v not in pre_v]
        for v in nv:
            v.co.x *= s[0]; v.co.y *= s[1]; v.co.z *= s[2]
        mindim = min(abs(s[0]), abs(s[1]), abs(s[2]))
    elif p == "cyl":
        rad = part.get("rad", 0.5); h = part.get("h", 1.0); v = int(part.get("v", 12))
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=v,
                              radius1=rad, radius2=rad, depth=h)
        mindim = min(2 * rad, h)
        do_bevel = False  # cylinders rounded via auto-smooth, not bevel
    elif p == "cone":
        rad = part.get("rad", 0.5); h = part.get("h", 1.0); v = int(part.get("v", 12))
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=v,
                              radius1=rad, radius2=0.0, depth=h)
        mindim = min(2 * rad, h)
        do_bevel = False
    elif p == "sphere":
        rad = part.get("rad", 0.5); sub = int(part.get("sub", 1))
        try:
            bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=rad)
        except TypeError:
            bmesh.ops.create_icosphere(bm, subdivisions=sub, diameter=rad * 2)
        mindim = 2 * rad
        do_bevel = False
    elif p == "wedge":
        s = part.get("s", [1, 1, 1])
        sx, sy, sz = s[0] / 2.0, s[1] / 2.0, s[2] / 2.0
        co = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, -sy, sz),
              (-sx, sy, -sz), (sx, sy, -sz), (sx, sy, sz)]
        vs = [bm.verts.new(c) for c in co]
        faces = [(0, 1, 2), (3, 5, 4), (0, 2, 5, 3), (0, 3, 4, 1), (1, 4, 5, 2)]
        for f in faces:
            try:
                bm.faces.new([vs[i] for i in f])
            except ValueError:
                pass
        mindim = min(abs(s[0]), abs(s[1]), abs(s[2]))
    else:
        return [], mat

    # bevel sharp edges of just this part
    if do_bevel:
        nv, _ = _new_elems(bm, pre_v, pre_f)
        new_edges = set()
        for v in nv:
            for e in v.link_edges:
                new_edges.add(e)
        sharp = []
        for e in new_edges:
            if len(e.link_faces) != 2:
                continue
            try:
                if e.calc_face_angle() > SHARP_ANGLE:
                    sharp.append(e)
            except Exception:
                pass
        w = min(BEVEL_W, 0.45 * mindim)
        if sharp and w > 0.0005:
            bmesh.ops.bevel(bm, geom=sharp, offset=w, offset_type="OFFSET",
                            segments=1, profile=0.5, affect="EDGES", clamp_overlap=True)

    # rotate + translate the part's new verts into place
    nv, nf = _new_elems(bm, pre_v, pre_f)
    if any(rot):
        R = Euler((math.radians(rot[0]), math.radians(rot[1]), math.radians(rot[2])), "XYZ").to_matrix().to_4x4()
        bmesh.ops.transform(bm, matrix=R, verts=nv)
    bmesh.ops.translate(bm, vec=loc, verts=nv)
    return nf, mat

# --- UV: deterministic box projection (no ops) -----------------------------
def box_uv(me, scale=UV_SCALE):
    uvl = me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")
    uvd = uvl.data
    for poly in me.polygons:
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        a, b = (1, 2) if ax == 0 else (0, 2) if ax == 1 else (0, 1)
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uvd[li].uv = (co[a] * scale, co[b] * scale)

# --- build one module ------------------------------------------------------
def build_module(mod, collection):
    name = mod["name"]
    bm = bmesh.new()
    mats_order = []           # material names in slot order
    face_mat = []             # (face, mat_name) pairs

    for part in mod.get("parts", []):
        nf, mat = add_part(bm, part)
        if mat not in PALETTE:
            mat = FALLBACK_MAT
        if mat not in mats_order:
            mats_order.append(mat)
        for f in nf:
            face_mat.append((f, mat))

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    idx = {m: i for i, m in enumerate(mats_order)}
    for f, mat in face_mat:
        if f.is_valid:
            f.material_index = idx[mat]

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()

    for mname in mats_order:
        me.materials.append(get_mat(mname))

    for poly in me.polygons:
        poly.use_smooth = True
    try:
        me.use_auto_smooth = True
        me.auto_smooth_angle = SMOOTH_ANGLE
    except Exception:
        pass
    box_uv(me)
    me.update()

    obj = bpy.data.objects.new(name, me)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    collection.objects.link(obj)
    return obj

# --- text label (font curve, no ops) ---------------------------------------
def make_label(text, loc, col, size=0.32):
    cu = bpy.data.curves.new(text + "_lbl", type="FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new(text + "_lbl", cu)
    ob.location = loc
    ob.rotation_euler = (math.radians(90), 0, 0)
    m = bpy.data.materials.get("M_Concrete_Dark")
    if m:
        ob.data.materials.append(m)
    col.objects.link(ob)
    return ob

# --- main ------------------------------------------------------------------
def run(catalog, reset=True):
    ensure_materials()
    root = bpy.context.scene.collection
    kit = ensure_collection("CityKit", root)
    if reset:
        wipe_collection(kit)
        kit = ensure_collection("CityKit", root)
    order = ["Structure", "BuildingParts", "Details"]
    cols = {n: ensure_collection(n, kit) for n in order}
    labels = ensure_collection("_Showroom_Labels", kit)

    by_col = {n: [] for n in order}
    for mod in catalog:
        c = mod.get("collection", "Structure")
        if c not in by_col:
            c = "Structure"
        by_col[c].append(mod)

    SPACING_X = 6.0
    ROW_GAP   = 8.0
    PER_ROW   = 8
    SECTION_GAP = 6.0
    built = []
    errors = []
    y_cursor = 0.0
    for cname in order:
        mods = sorted(by_col[cname], key=lambda m: m["name"])
        if not mods:
            continue
        make_label("== " + cname.upper() + " ==", (-SPACING_X, y_cursor + 3.0, 0.0), labels, size=0.9)
        y_cursor -= 3.0
        for i, mod in enumerate(mods):
            col_i = i % PER_ROW
            row_i = i // PER_ROW
            x = col_i * SPACING_X
            y = y_cursor - row_i * ROW_GAP
            try:
                obj = build_module(mod, cols[cname])
                obj.location = (x, y, 0.0)
                make_label(mod["name"], (x, y - 2.6, 0.0), labels)
                built.append(mod["name"])
            except Exception as e:
                errors.append(mod.get("name", "?") + ": " + repr(e))
        rows = (len(mods) + PER_ROW - 1) // PER_ROW
        y_cursor -= rows * ROW_GAP + SECTION_GAP

    print("CITYKIT_BUILT:", len(built))
    if errors:
        print("CITYKIT_ERRORS:", len(errors))
        for e in errors[:30]:
            print("  ERR", e)
    return built, errors

# entry
_catalog = None
if "CITYKIT_CATALOG" in globals():
    _catalog = CITYKIT_CATALOG
elif "CITYKIT_CATALOG_PATH" in globals():
    with open(CITYKIT_CATALOG_PATH) as f:
        _catalog = json.load(f)
        if isinstance(_catalog, dict):
            _catalog = _catalog.get("modules", [])

if _catalog is not None:
    _reset = globals().get("CITYKIT_RESET", True)
    run(_catalog, reset=_reset)
else:
    print("CITYKIT: no catalog provided")
