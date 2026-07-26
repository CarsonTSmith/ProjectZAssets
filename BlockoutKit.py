"""
BlockoutKit.py -- small mesh-assembly kit shared by the blockout generators.

MB accumulates many primitives into ONE mesh with per-face material slots, then
world-planar projects UVs at a chosen density (1 unit/m by default, which is how
Wall.blend's materials are authored). Keeping a building as one object rather
than 800 keeps the outliner sane and the viewport fast.
"""

import bpy, bmesh, math
from mathutils import Vector, Matrix, Euler

# repeats per metre, per material name; chunky stone reads better shrunk
MAT_UV_SCALE = {}


def ensure_coll(name, parent):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    if c.name not in [ch.name for ch in parent.children]:
        parent.children.link(c)
    return c


def purge_coll(root_name):
    root = bpy.data.collections.get(root_name)
    if not root:
        return
    kids = [root] + list(root.children_recursive)
    for c in kids:
        for o in list(c.objects):
            bpy.data.objects.remove(o, do_unlink=True)
    for c in kids:
        bpy.data.collections.remove(c)


def uv_world_project(ob, scale, origin, overrides=None):
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers.active.data
    ox, oy, oz = origin
    co = [v.co for v in me.vertices]
    base = scale
    slot = [base * MAT_UV_SCALE.get(m.name, 1.0) if m else base
            for m in me.materials] or [base]
    for pi, p in enumerate(me.polygons):
        n = p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        ov = overrides[pi] if overrides and pi < len(overrides) else 0.0
        s = base * ov if ov else slot[min(p.material_index, len(slot) - 1)]
        for li in p.loop_indices:
            v = co[me.loops[li].vertex_index]
            wx, wy, wz = v.x + ox, v.y + oy, v.z + oz
            if ax == 0:
                u, w = wy, wz
            elif ax == 1:
                u, w = wx, wz
            else:
                u, w = wx, wy
            uvl[li].uv = (u * s, w * s)


class MB:
    def __init__(self, name, prefix=""):
        self.name = name
        self.prefix = prefix
        self.bm = bmesh.new()
        self.mats = []
        self.uvlay = self.bm.faces.layers.float.new("uvscale")

    # ---- internals ----
    def _mi(self, mat):
        for i, m in enumerate(self.mats):
            if m is mat:
                return i
        self.mats.append(mat)
        return len(self.mats) - 1

    def _tag(self, verts, mi, uvs):
        for f in {f for v in verts for f in v.link_faces}:
            f.material_index = mi
            f[self.uvlay] = uvs

    def _tagf(self, faces, mi, uvs):
        for f in faces:
            f.material_index = mi
            f[self.uvlay] = uvs

    # ---- primitives ----
    def box(self, center, size, mat, rot=None, uvs=0.0):
        mi = self._mi(mat)
        verts = bmesh.ops.create_cube(self.bm, size=1.0)["verts"]
        mtx = Matrix.Translation(Vector(center))
        if rot:
            mtx = mtx @ Euler(rot, "XYZ").to_matrix().to_4x4()
        mtx = mtx @ Matrix.Diagonal(Vector(size).to_4d())
        bmesh.ops.transform(self.bm, matrix=mtx, verts=verts)
        self._tag(verts, mi, uvs)

    def cyl(self, center, radius, height, mat, segments=24, radius_top=None,
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

    def beam(self, p0, p1, w, h, mat, uvs=0.0):
        """Box spanning two points -- railings, lamp arms, bunting cord."""
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        L = d.length
        if L < 1e-6:
            return
        rot = d.to_track_quat("Z", "Y").to_euler()
        self.box((p0 + p1) / 2.0, (w, h, L), mat, rot=rot, uvs=uvs)

    def sphere(self, center, radius, mat, segments=20, uvs=0.0):
        mi = self._mi(mat)
        verts = bmesh.ops.create_uvsphere(
            self.bm, u_segments=segments, v_segments=max(4, segments // 2),
            radius=radius)["verts"]
        bmesh.ops.transform(self.bm, matrix=Matrix.Translation(Vector(center)),
                            verts=verts)
        self._tag(verts, mi, uvs)

    def ring(self, center, r_in, r_out, height, mat, segments=64, uvs=0.0):
        mi = self._mi(mat)
        bm = self.bm
        cx, cy, cz = center
        zb, zt = cz - height / 2.0, cz + height / 2.0
        loops = {}
        for key, r, z in (("bi", r_in, zb), ("bo", r_out, zb),
                          ("ti", r_in, zt), ("to", r_out, zt)):
            loops[key] = [bm.verts.new((cx + r * math.cos(2 * math.pi * i / segments),
                                        cy + r * math.sin(2 * math.pi * i / segments), z))
                          for i in range(segments)]
        made = []
        for i in range(segments):
            j = (i + 1) % segments
            made.append(bm.faces.new((loops["ti"][i], loops["ti"][j], loops["to"][j], loops["to"][i])))
            made.append(bm.faces.new((loops["bo"][i], loops["bo"][j], loops["bi"][j], loops["bi"][i])))
            made.append(bm.faces.new((loops["to"][i], loops["to"][j], loops["bo"][j], loops["bo"][i])))
            made.append(bm.faces.new((loops["bi"][i], loops["bi"][j], loops["ti"][j], loops["ti"][i])))
        self._tagf(made, mi, uvs)

    def extrude_poly(self, pts, vec, mat, uvs=0.0):
        """Planar polygon `pts` swept by `vec`. The workhorse for roof slabs,
        gable ends, pediments and any wedge that is painful as a rotated box."""
        mi = self._mi(mat)
        bm = self.bm
        v = Vector(vec)
        top = [bm.verts.new(Vector(p)) for p in pts]
        bot = [bm.verts.new(Vector(p) + v) for p in pts]
        made = [bm.faces.new(top), bm.faces.new(list(reversed(bot)))]
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            made.append(bm.faces.new((top[i], top[j], bot[j], bot[i])))
        self._tagf(made, mi, uvs)

    def tri(self, p0, p1, p2, mat, uvs=0.0):
        mi = self._mi(mat)
        bm = self.bm
        f = bm.faces.new([bm.verts.new(Vector(p)) for p in (p0, p1, p2)])
        self._tagf([f], mi, uvs)

    def quad(self, pts, mat, uvs=0.0):
        mi = self._mi(mat)
        bm = self.bm
        f = bm.faces.new([bm.verts.new(Vector(p)) for p in pts])
        self._tagf([f], mi, uvs)

    # ---- output ----
    def finish(self, coll, origin=(0, 0, 0), bevel=0.03, uv_scale=1.0):
        origin = Vector(origin)
        bm = self.bm
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bmesh.ops.translate(bm, verts=bm.verts, vec=-origin)
        me = bpy.data.meshes.new(self.prefix + self.name)
        bm.faces.ensure_lookup_table()
        overrides = [f[self.uvlay] for f in bm.faces]     # to_mesh keeps face order
        bm.to_mesh(me)
        bm.free()
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(self.prefix + self.name, me)
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


# ---------------------------------------------------------------- materials --

def flat(name, color, roughness=0.55, emission=0.0):
    """Plain saturated shader -- the graphic style wants flat colour, not PBR."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1.0)
    b.inputs["Roughness"].default_value = roughness
    if emission and "Emission Color" in b.inputs:
        b.inputs["Emission Color"].default_value = (color[0], color[1], color[2], 1.0)
        b.inputs["Emission Strength"].default_value = emission
    out.location = (300, 0)
    nt.links.new(b.outputs[0], out.inputs[0])
    m.use_fake_user = True
    return m


def tint(src_name, new_name, color, roughness=None, force=True, grain=(0.80, 1.16)):
    """Copy a textured material and recolour it, keeping its grain and normal.

    The texture is reduced to a luminance signal, remapped to hover around 1.0,
    and used to MULTIPLY the target swatch. That takes hue *and* value from the
    swatch while the surface detail survives -- so eight saturated stucco
    variants cost one download. (A COLOR-blend mix looks like the obvious
    choice here and is wrong: it keeps the source's lightness, so every colour
    comes out as the same washed pastel no matter what swatch you feed it.)
    """
    if new_name in bpy.data.materials:
        if not force:
            return bpy.data.materials[new_name]
        bpy.data.materials.remove(bpy.data.materials[new_name])
    src = bpy.data.materials[src_name]
    m = src.copy()
    m.name = new_name
    m.use_fake_user = True
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return m
    bc = bsdf.inputs["Base Color"]
    if bc.is_linked:
        link = bc.links[0]
        src_socket = link.from_socket
        nt.links.remove(link)
        x, y = bsdf.location.x, bsdf.location.y
        bw = nt.nodes.new("ShaderNodeRGBToBW")
        bw.location = (x - 640, y + 200)
        nt.links.new(src_socket, bw.inputs[0])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.location = (x - 470, y + 200)
        mr.clamp = True
        for i, v in ((1, 0.30), (2, 1.00), (3, grain[0]), (4, grain[1])):
            mr.inputs[i].default_value = v
        nt.links.new(bw.outputs[0], mr.inputs[0])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.location = (x - 250, y + 200)
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs[6].default_value = (color[0], color[1], color[2], 1.0)   # A
        nt.links.new(mr.outputs[0], mix.inputs[7])                          # B
        nt.links.new(mix.outputs[2], bc)
    else:
        bc.default_value = (color[0], color[1], color[2], 1.0)
    if roughness is not None and not bsdf.inputs["Roughness"].is_linked:
        bsdf.inputs["Roughness"].default_value = roughness
    return m
