# ============================================================================
# Reactor facility executor -- data-driven low-poly sci-fi builder.
# Reads FACILITY_CATALOG (list) or FACILITY_CATALOG_PATH (json).
# Each module: {name, collection, at:[x,y,z]?, parts:[...]}.  Parts are LOCAL.
# Pure bmesh + data API. Adds EMISSIVE materials + transparency.
# ============================================================================
import bpy, bmesh, json, math
from mathutils import Matrix, Vector, Euler

BEVEL_W = 0.035
SMOOTH_ANGLE = math.radians(50)
SHARP_ANGLE = math.radians(35)
UV_SCALE = 0.4

# name -> (r,g,b, roughness, metallic)
PALETTE = {
    "M_Concrete":      (0.50, 0.50, 0.53, 0.92, 0.0),
    "M_Concrete_Dark": (0.27, 0.28, 0.31, 0.92, 0.0),
    "M_Metal_Panel":   (0.45, 0.47, 0.52, 0.45, 0.70),
    "M_Metal_Dark":    (0.17, 0.18, 0.21, 0.50, 0.80),
    "M_Steel":         (0.60, 0.62, 0.66, 0.50, 0.25),
    "M_Mesh_Silver":   (0.72, 0.74, 0.78, 0.40, 0.55),
    "M_Water":         (0.10, 0.34, 0.55, 0.06, 0.0),
    "M_Pipe":          (0.40, 0.42, 0.47, 0.40, 0.70),
    "M_Copper":        (0.55, 0.38, 0.22, 0.40, 0.80),
    "M_Rust":          (0.42, 0.27, 0.18, 0.85, 0.10),
    "M_Hazard_Yellow": (0.85, 0.66, 0.10, 0.55, 0.0),
    "M_Black":         (0.06, 0.06, 0.07, 0.70, 0.0),
    "M_Rubber":        (0.09, 0.09, 0.10, 0.90, 0.0),
    "M_Glass":         (0.30, 0.45, 0.55, 0.08, 0.0),
    # emissive (glow) -- base color carries the hue too
    "M_Emit_Cyan":     (0.20, 0.90, 1.00, 0.30, 0.0),
    "M_Emit_Green":    (0.35, 1.00, 0.45, 0.30, 0.0),
    "M_Emit_Red":      (1.00, 0.15, 0.10, 0.30, 0.0),
    "M_Emit_Warm":     (1.00, 0.86, 0.62, 0.30, 0.0),
    "M_Emit_Blue":     (0.25, 0.50, 1.00, 0.30, 0.0),
    "M_Screen":        (0.30, 0.80, 0.92, 0.20, 0.0),
}
FALLBACK_MAT = "M_Concrete"

# subtle interest on matte mats: name -> (mottle, bump)
MAT_FX = {
    "M_Concrete": (0.13, 0.06), "M_Concrete_Dark": (0.11, 0.05),
    "M_Metal_Panel": (0.07, 0.0), "M_Metal_Dark": (0.06, 0.0),
    "M_Steel": (0.06, 0.0), "M_Mesh_Silver": (0.05, 0.0), "M_Pipe": (0.06, 0.0), "M_Copper": (0.06, 0.0),
    "M_Rust": (0.14, 0.05), "M_Hazard_Yellow": (0.04, 0.0), "M_Rubber": (0.05, 0.0),
}
# emissive: name -> (r,g,b, strength)
EMISSIVE = {
    "M_Emit_Cyan": (0.20, 0.90, 1.00, 9.0),
    "M_Emit_Green": (0.35, 1.00, 0.45, 11.0),
    "M_Emit_Red": (1.00, 0.15, 0.10, 6.0),
    "M_Emit_Warm": (1.00, 0.86, 0.62, 6.0),
    "M_Emit_Blue": (0.25, 0.50, 1.00, 6.0),
    "M_Screen": (0.30, 0.80, 0.92, 5.0),
    "M_Water": (0.12, 0.45, 0.78, 0.4),
}
TRANSPARENT = {"M_Glass": 0.28, "M_Water": 0.2}

def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

def _lin3(r, g, b):
    return (srgb_to_lin(r), srgb_to_lin(g), srgb_to_lin(b))

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
        emit = EMISSIVE.get(name)

        if mottle > 0:
            tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-600, 100)
            noise = nt.nodes.new("ShaderNodeTexNoise"); noise.location = (-380, 100)
            noise.inputs["Scale"].default_value = 1.6
            noise.inputs["Detail"].default_value = 2.0
            nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
            ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.location = (-150, 100)
            dark = tuple(c * (1.0 - mottle) for c in base) + (1.0,)
            light = tuple(min(1.0, c * (1.0 + mottle * 0.45)) for c in base) + (1.0,)
            ramp.color_ramp.elements[0].position = 0.25; ramp.color_ramp.elements[0].color = dark
            ramp.color_ramp.elements[1].position = 0.75; ramp.color_ramp.elements[1].color = light
            nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        else:
            bsdf.inputs["Base Color"].default_value = base + (1.0,)

        if bump > 0:
            tc2 = nt.nodes.new("ShaderNodeTexCoord"); tc2.location = (-600, -300)
            bn = nt.nodes.new("ShaderNodeTexNoise"); bn.location = (-380, -300)
            bn.inputs["Scale"].default_value = 9.0
            nt.links.new(tc2.outputs["Object"], bn.inputs["Vector"])
            bnode = nt.nodes.new("ShaderNodeBump"); bnode.location = (0, -300)
            bnode.inputs["Strength"].default_value = bump
            bnode.inputs["Distance"].default_value = 0.02
            nt.links.new(bn.outputs["Fac"], bnode.inputs["Height"])
            nt.links.new(bnode.outputs["Normal"], bsdf.inputs["Normal"])

        if emit is not None:
            ec = _lin3(emit[0], emit[1], emit[2]) + (1.0,)
            for col_in in ("Emission Color", "Emission"):
                if col_in in bsdf.inputs:
                    bsdf.inputs[col_in].default_value = ec; break
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emit[3]

        if alpha is not None:
            bsdf.inputs["Alpha"].default_value = alpha
            m.blend_method = "BLEND"
            try: m.shadow_method = "HASHED"
            except Exception: pass
            m.show_transparent_back = False
        else:
            m.blend_method = "OPAQUE"
        m.diffuse_color = base + (1.0,)

def get_mat(name):
    if name not in PALETTE:
        name = FALLBACK_MAT
    return bpy.data.materials.get(name)

def ensure_collection(name, parent):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    if c.name not in [ch.name for ch in parent.children]:
        try: parent.children.link(c)
        except Exception: pass
    return c

def wipe_collection(col):
    if col is None: return
    for ob in list(col.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for ch in list(col.children):
        wipe_collection(ch); bpy.data.collections.remove(ch)

def build_part_bm(part):
    """Build ONE primitive in its own isolated bmesh (reliable per-part tracking +
    correct outward normals). Returns (bm, material_name) or (None, mat)."""
    p = part.get("p", "box")
    mat = part.get("m", FALLBACK_MAT)
    do_bevel = part.get("b", True)
    loc = Vector(part.get("l", [0, 0, 0]))
    rot = part.get("r", [0, 0, 0])
    bm = bmesh.new()

    if p == "box":
        s = part.get("s", [1, 1, 1])
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= s[0]; v.co.y *= s[1]; v.co.z *= s[2]
        mindim = min(abs(s[0]), abs(s[1]), abs(s[2]))
    elif p == "cyl":
        rad = part.get("rad", 0.5); h = part.get("h", 1.0); v = int(part.get("v", 16))
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=v,
                              radius1=rad, radius2=rad, depth=h)
        mindim = min(2 * rad, h); do_bevel = False
    elif p == "cone":
        rad = part.get("rad", 0.5); h = part.get("h", 1.0); v = int(part.get("v", 16))
        r2 = part.get("rad2", 0.0)
        bmesh.ops.create_cone(bm, cap_ends=part.get("cap", True), cap_tris=False, segments=v,
                              radius1=rad, radius2=r2, depth=h)
        mindim = min(2 * rad, h); do_bevel = False
    elif p == "sphere":
        rad = part.get("rad", 0.5); sub = int(part.get("sub", 2))
        try: bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=rad)
        except TypeError: bmesh.ops.create_icosphere(bm, subdivisions=sub, diameter=rad * 2)
        mindim = 2 * rad; do_bevel = False
    elif p == "wedge":
        s = part.get("s", [1, 1, 1])
        sx, sy, sz = s[0] / 2.0, s[1] / 2.0, s[2] / 2.0
        co = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, -sy, sz),
              (-sx, sy, -sz), (sx, sy, -sz), (sx, sy, sz)]
        vs = [bm.verts.new(c) for c in co]
        for f in [(0, 1, 2), (3, 5, 4), (0, 2, 5, 3), (0, 3, 4, 1), (1, 4, 5, 2)]:
            try: bm.faces.new([vs[i] for i in f])
            except ValueError: pass
        mindim = min(abs(s[0]), abs(s[1]), abs(s[2]))
    else:
        bm.free(); return None, mat

    if do_bevel:
        sharp = []
        for e in bm.edges:
            if len(e.link_faces) != 2: continue
            try:
                if e.calc_face_angle() > SHARP_ANGLE: sharp.append(e)
            except Exception: pass
        w = min(BEVEL_W, 0.45 * mindim)
        if sharp and w > 0.0005:
            bmesh.ops.bevel(bm, geom=sharp, offset=w, offset_type="OFFSET",
                            segments=1, profile=0.5, affect="EDGES", clamp_overlap=True)

    if any(rot):
        R = Euler((math.radians(rot[0]), math.radians(rot[1]), math.radians(rot[2])), "XYZ").to_matrix().to_4x4()
        bmesh.ops.transform(bm, matrix=R, verts=bm.verts)
    bmesh.ops.translate(bm, vec=loc, verts=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)  # isolated shell -> correct outward
    if part.get("flip"):  # inward-facing (dome ceiling, pool walls seen from inside)
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    return bm, mat

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

def build_module(mod, collection):
    name = mod["name"]
    master = bmesh.new()
    mats_order = []
    for part in mod.get("parts", []):
        pbm, mat = build_part_bm(part)
        if pbm is None: continue
        if mat not in PALETTE: mat = FALLBACK_MAT
        if mat not in mats_order: mats_order.append(mat)
        si = mats_order.index(mat)
        tmp = bpy.data.meshes.new("_ckpart_tmp")
        pbm.to_mesh(tmp); pbm.free()
        master.faces.ensure_lookup_table()
        before = len(master.faces)
        master.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
        master.faces.ensure_lookup_table()
        for f in master.faces[before:]:
            f.material_index = si
    me = bpy.data.meshes.new(name)
    master.to_mesh(me); master.free()
    for mname in mats_order: me.materials.append(get_mat(mname))
    for poly in me.polygons: poly.use_smooth = True
    try:
        me.use_auto_smooth = True; me.auto_smooth_angle = SMOOTH_ANGLE
    except Exception: pass
    box_uv(me); me.update()
    obj = bpy.data.objects.new(name, me)
    obj.location = (0.0, 0.0, 0.0); obj.rotation_euler = (0, 0, 0); obj.scale = (1, 1, 1)
    collection.objects.link(obj)
    return obj

def run(catalog, reset=True):
    ensure_materials()
    root = bpy.context.scene.collection
    fac = ensure_collection("ReactorFacility", root)
    if reset:
        wipe_collection(fac); fac = ensure_collection("ReactorFacility", root)
    cols = {}
    built = []; errors = []
    for mod in catalog:
        cname = mod.get("collection", "Structure")
        if cname not in cols: cols[cname] = ensure_collection(cname, fac)
        try:
            obj = build_module(mod, cols[cname])
            at = mod.get("at", [0, 0, 0])
            obj.location = (at[0], at[1], at[2])
            built.append(mod["name"])
        except Exception as e:
            errors.append(mod.get("name", "?") + ": " + repr(e))
    print("FACILITY_BUILT:", len(built))
    if errors:
        print("FACILITY_ERRORS:", len(errors))
        for e in errors[:30]: print("  ERR", e)
    return built, errors

_catalog = None
if "FACILITY_CATALOG" in globals():
    _catalog = FACILITY_CATALOG
elif "FACILITY_CATALOG_PATH" in globals():
    with open(FACILITY_CATALOG_PATH) as f:
        _catalog = json.load(f)
        if isinstance(_catalog, dict): _catalog = _catalog.get("modules", [])
if _catalog is not None:
    run(_catalog, reset=globals().get("FACILITY_RESET", True))
else:
    print("FACILITY: no catalog provided")
