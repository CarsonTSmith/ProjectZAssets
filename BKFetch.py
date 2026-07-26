"""
BKFetch.py -- pull materials from BlenderKit straight into the open .blend.

The BlenderKit add-on's operators are not registered in this session, so this
talks to the web API directly using the key stored in the add-on preferences,
caches the .blend under the add-on's own global_dir, and appends the material.

    import BKFetch; BKFetch.fetch("Terracotta Roof TIles", "PZ_RoofTile")
"""

import bpy, json, os, urllib.request, urllib.parse

API = "https://www.blenderkit.com/api/v1"
UA = "Mozilla/5.0 (X11; Linux x86_64) BlenderKit/Blender"


def _prefs():
    return bpy.context.preferences.addons["blenderkit"].preferences


def _get(url):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + _prefs().api_key,
        "Accept": "application/json", "User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode())


def search(query, asset_type="material", n=10):
    return _get(API + "/search/?" + urllib.parse.urlencode(
        {"query": "%s asset_type:%s" % (query, asset_type), "page_size": n}))["results"]


def _cache_dir():
    d = os.path.join(getattr(_prefs(), "global_dir", os.path.expanduser("~/blenderkit_data")),
                     "materials")
    os.makedirs(d, exist_ok=True)
    return d


def download(asset, res="resolution_2K"):
    """Returns a local .blend path for the asset dict, downloading if needed."""
    files = {f["fileType"]: f for f in asset["files"]}
    f = files.get(res) or files.get("resolution_1K") or files.get("blend")
    local = os.path.join(_cache_dir(), "%s_%s.blend" % (asset["assetBaseId"][:8], f["fileType"]))
    if os.path.exists(local) and os.path.getsize(local) > 1024:
        return local
    scene_uuid = bpy.context.scene.get("uuid", "00000000-0000-0000-0000-000000000000")
    url = _get(f["downloadUrl"] + "?scene_uuid=" + scene_uuid)["filePath"]
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r, open(local, "wb") as out:
        out.write(r.read())
    return local


def fetch(query, rename=None, res="resolution_2K", pick=0, base_id=None):
    """Search, download and append a material. Returns the material datablock.

    Pass base_id to pin an exact asset -- name searches are ambiguous (several
    unrelated materials are literally called "Paint").
    """
    if rename and rename in bpy.data.materials:
        return bpy.data.materials[rename]
    hits = search("asset_base_id:" + base_id) if base_id else search(query)
    if not hits:
        raise LookupError("no BlenderKit hit for " + query)
    exact = [h for h in hits if query and h["name"].lower() == query.lower()]
    asset = (exact or hits)[pick]
    path = download(asset, res)
    before = set(bpy.data.materials.keys())
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.materials = list(src.materials)
    new = [bpy.data.materials[n] for n in bpy.data.materials.keys() if n not in before]
    if not new:
        raise RuntimeError("no material appended from " + path)
    mat = max(new, key=lambda m: len(m.node_tree.nodes) if m.node_tree else 0)
    for m in new:
        if m is not mat:
            bpy.data.materials.remove(m)
    if rename:
        mat.name = rename
    mat.use_fake_user = True
    print("BKFetch:", asset["name"], "->", mat.name)
    return mat
