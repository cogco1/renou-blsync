"""人偶之心 · Blender→UE 实时预览 2026-10-09: small Blender library for scripted edits that show up live in UE (until the
interactive add-on exists). Use inside Blender 5.2 (headless or on the Selkies desktop):

    import sys; sys.path.insert(0, "/workspace/jobs/look-blsync-20261009-01/lib")
    import renou_blsync_lib as rb
    B = rb.Batch("/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_placements.json",
                 out="/workspace/jobs/look-blsync-20261009-01/data/area_04_03_overrides.json",
                 parts_glb="/workspace/shared/eng-inst/u20b_r1/area_04_03/area_04_03_parts.glb")   # parts_glb optional
    hub = B.group("V10_TWR_000_BLD_HubTower_C1Empire")          # src before " | ", or a building_id
    tw = B.group("V10_CBDFILL_BLK_001")
    B.rotate(tw, 15.0)                                           # about the group's own centre (needs parts_glb)
    B.move(tw, (20.0, -5.0, 0.0))
    r = B.publish("CBD radial v1")                               # writes the override file, waits for UE's receipt
    B.write_back("/workspace/jobs/<your job>/out")                 # when the user has approved: new placements version

Override file = renou-overrides/1, CUMULATIVE (everything that differs from the table), written atomically. One writer per
batch file at a time. Coordinates: Blender world, metres, Z up; quaternions wxyz. CBD fill blocks and many other parts are
baked in world space (pos 0,0,0): turning such a building in place needs its centre, so load the parts GLB (parts_glb) or
pass centre= explicitly."""
import hashlib, json, math, os, re, subprocess, time
from pathlib import Path
import bpy
from mathutils import Matrix, Quaternion, Vector

STATUS_DEFAULT = "/workspace/guest/look-ue-20261008/HarborLookMS/Saved/BlSync/status.json"   # 视效's live editor (R4)


def glb_part_bounds(path):
    """{part: (min, max)} in Blender coordinates, read from the GLB's JSON chunk only (POSITION accessor min/max; nodes
    carry no transform by the placements interface v1). Fast even for a 400 MB parts GLB: no mesh is imported."""
    import struct
    with open(path, "rb") as fh:
        magic, _ver, _len = struct.unpack("<4sII", fh.read(12))
        assert magic == b"glTF", path
        clen, ctype = struct.unpack("<II", fh.read(8))
        g = json.loads(fh.read(clen))
    acc, meshes, out = g["accessors"], g.get("meshes", []), {}
    for node in g.get("nodes", []):
        if "mesh" not in node or "name" not in node:
            continue
        lo, hi = [1e30] * 3, [-1e30] * 3
        for prim in meshes[node["mesh"]]["primitives"]:
            a = acc[prim["attributes"]["POSITION"]]
            for i in range(3):
                lo[i], hi[i] = min(lo[i], a["min"][i]), max(hi[i], a["max"][i])
        # glTF Y up -> Blender Z up: (x, y, z) -> (x, -z, y)
        out[node["name"]] = (Vector((lo[0], -hi[2], lo[1])), Vector((hi[0], -lo[2], hi[1])))
    return out


ARCHIVE_KEEP = 50    # snapshots kept per override file (user 10-10: at least 20)


def archive_dir(out):
    """where the snapshots of an override file go: archive/ next to it (bl_sync in UE uses the same folder)."""
    return Path(out).parent / "archive"


def replace_risk(old, new):
    """why writing override document `new` over `old` could lose work, or None. User 10-10, after an edit got lost when
    a window was reopened: cleared, instances or meshes leaving the file, most of it rewritten, the revision going back
    or another table version all keep a copy of the old file first. bl_sync_core.replace_risk() is the same rule."""
    if not old:
        return None
    oi, ni = old.get("instances") or {}, new.get("instances") or {}
    if oi and not ni:
        return "cleared"
    if old.get("base_sha256") and new.get("base_sha256") and old["base_sha256"] != new["base_sha256"]:
        return "base-changed"
    try:
        if float(new.get("rev")) < float(old.get("rev")):
            return "rev-back"
    except (TypeError, ValueError):
        pass
    gone = set(oi) - set(ni)
    if gone:
        return f"dropped{len(gone)}"
    gm = set(old.get("meshes") or {}) - set(new.get("meshes") or {})
    if gm:
        return f"meshes-dropped{len(gm)}"
    common = set(oi) & set(ni)
    if len(common) >= 10 and sum(oi[k] != ni[k] for k in common) > len(common) / 2:
        return "rewritten"
    return None


def snapshot_bytes(out, raw, reason, archive=None, keep=ARCHIVE_KEEP):
    """keep `raw` (an override document's bytes) in archive/ as <stem>__<yyyymmdd-hhmmss-mmm>__rev<rev>__<reason>__
    <sha8>.json; <stem> is the override file's. Ash 10-10: the content's SHA in the name and an exclusive create, so two
    different contents never share a name, and the copy is read back before it counts. Same as the newest snapshot:
    not made again. The newest `keep` stay. Raises OSError when it cannot be kept - callers then change nothing."""
    p = Path(out)
    d = Path(archive) if archive else archive_dir(p)
    d.mkdir(parents=True, exist_ok=True)
    olds = sorted(d.glob(f"{p.stem}__*.json"))
    if olds and olds[-1].read_bytes() == raw:
        return olds[-1]
    try:
        rev = json.loads(raw.decode("utf-8-sig")).get("rev")
    except Exception:
        rev = "unreadable"
    t = time.time()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + f"-{int(t * 1000) % 1000:03d}"
    why = re.sub(r"[^0-9A-Za-z_-]+", "-", str(reason or "replaced"))[:40]
    snap = d / f"{p.stem}__{stamp}__rev{rev}__{why}__{hashlib.sha256(raw).hexdigest()[:8]}.json"
    if snap.exists():
        if snap.read_bytes() == raw:
            return snap
        raise OSError(f"{snap.name} exists with other bytes")
    with open(snap, "xb") as fh:         # exclusive: never replaces an existing snapshot
        fh.write(raw)
    if snap.read_bytes() != raw:
        raise OSError(f"{snap.name}: read back differs")
    for old in sorted(d.glob(f"{p.stem}__*.json"))[:-keep]:
        old.unlink()                     # rotation of the tool's own copies (the newest `keep` stay)
    return snap


def snapshot_file(path, reason, archive=None, keep=ARCHIVE_KEEP):
    """copy an override file into archive/ before something replaces it (see snapshot_bytes). None: no file to keep."""
    p = Path(path)
    if not p.exists():
        return None
    return snapshot_bytes(p, p.read_bytes(), reason, archive, keep)


def list_snapshots(out, archive=None, limit=20):
    """newest first: [{"path", "time", "rev", "reason", "instances", "meshes"}] for one override file."""
    p = Path(out)
    d = Path(archive) if archive else archive_dir(p)
    rows = []
    for f in sorted(d.glob(f"{p.stem}__*.json"), reverse=True)[:limit]:
        parts = f.stem.split("__")
        row = {"path": str(f), "time": parts[1] if len(parts) > 1 else "", "rev": parts[2][3:] if len(parts) > 2 else "",
               "reason": parts[3] if len(parts) > 3 else "", "instances": None, "meshes": None}
        try:
            doc = json.loads(f.read_text(encoding="utf-8-sig"))
            row.update(instances=len(doc.get("instances") or {}), meshes=len(doc.get("meshes") or {}))
        except Exception:
            pass
        rows.append(row)
    return rows


def mat_of(rec):
    q = Quaternion(rec["quat_wxyz"]) if rec.get("quat_wxyz") else Quaternion((0, 0, 1), math.radians(rec.get("yaw_deg", 0.0)))
    s = rec.get("scale", 1.0)
    s = Vector(s) if isinstance(s, (list, tuple)) else Vector((s, s, s))
    return Matrix.LocRotScale(Vector(rec["pos"]), q, s)


def canon(q):
    """q and -q are the same rotation: make the first clearly non-zero component (w, x, y, z) positive. "w < 0" alone
    is not enough - a 180 deg turn about a horizontal axis has w = 0 and its sign is then decided by x / y / z (#31)."""
    for c in (q.w, q.x, q.y, q.z):
        if abs(c) > 1e-6:
            if c < 0:
                q.negate()
            break
    return q


ROT_TOL = 1e-5      # radians (0.00057 deg, 1 mm at 100 m). Blender 5.2.2, 10,000 random rotations: a float32 matrix round
                    # trip differs by at most 7.4e-7 rad, 7-decimal table quaternions by 1.8e-7; a 0.01 deg edit is 1.7e-4


def rotation_angle(a, b):
    """angle in radians between the rotations of two quaternions (wxyz, any sign, any length), in double precision.
    The chord |a - s b| (s = sign of a.b) is 2 sin(angle / 4): no cancellation near 1, unlike 1 - |a.b|."""
    a, b = [float(x) for x in a], [float(x) for x in b]
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    a, b = [x / na for x in a], [x / nb for x in b]
    s = 1.0 if sum(x * y for x, y in zip(a, b)) >= 0.0 else -1.0
    chord = math.sqrt(sum((x - s * y) ** 2 for x, y in zip(a, b)))
    return 4.0 * math.asin(min(1.0, chord / 2.0))


def same_rotation(a, b, tol=ROT_TOL):
    """True when two quaternions are the same rotation within tol radians, whatever their signs (#31). Ash 10-10: the
    float32 |a.b| > 1 - 1e-9 test called 190 of 10,000 identical rotations different."""
    return rotation_angle(a, b) <= tol


def decompose(m):
    loc, q, s = m.decompose()
    return loc, canon(q), s


def mesh_sig(me):
    """SHA-256 of a mesh's vertex positions, polygon vertex indices and material slot names: tells a real geometry edit
    from a mere 'geometry updated' depsgraph tag (entering edit mode, selection)."""
    import numpy as np
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    lv = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", lv)
    h = hashlib.sha256(co.tobytes())
    h.update(lv.tobytes())
    h.update("|".join(m.name if m else "" for m in me.materials).encode("utf-8"))
    return h.hexdigest()


def alive(o):
    """False for a Python handle whose Blender object has been deleted."""
    try:
        o.name
        return True
    except ReferenceError:
        return False


def _slot_names_only(glb, names, part):
    """Replace temporary material names in a locally exported GLB, keeping only slot names.
    The export uses fresh, untextured placeholder materials, never the source shaders."""
    import struct
    raw = glb.read_bytes()
    magic, version, length, size, kind = struct.unpack("<4sIIII", raw[:20])
    if magic != b"glTF" or version != 2 or length != len(raw) or kind != 0x4e4f534a:
        raise ValueError("unexpected GLB header")
    doc = json.loads(raw[20:20 + size])
    if doc.get("images") or doc.get("textures"):
        raise ValueError("slot-only export unexpectedly contains textures")
    if "materials" in doc:
        doc["materials"] = [{"name": names[m["name"]]} for m in doc["materials"]]
    if len(doc.get("meshes", [])) != 1:
        raise ValueError("slot-only export must contain exactly one mesh")
    doc["meshes"][0]["name"] = part
    chunk = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    chunk += b" " * (-len(chunk) % 4)
    tail = raw[20 + size:]
    glb.write_bytes(struct.pack("<4sIIII", magic, version, 20 + len(chunk) + len(tail), len(chunk), kind) + chunk + tail)


class Batch:
    def __init__(self, placements, out, parts_glb=None, status=STATUS_DEFAULT, only_src=None, remote=None, load_meshes=True,
                 track_edits=False, archive=None):
        """only_src: optional regex on src; instances not matching are not loaded (they stay as in the table).
        remote (R7, Blender on a laptop): "myserver:/workspace/jobs/look-blsync-20261009-01/data" - out / meshes are written
        locally, then pushed with the system's own scp/ssh (keys already set up; nothing stored here); the receipt is read
        back over ssh. placements / parts_glb are local copies of the release files.
        track_edits (the add-on sets it): remember a signature of every part mesh, so export_part_if_changed() only exports
        parts whose geometry really changed.
        archive: where snapshots of the override file go (default archive/ next to it). A Batch starts from the table; to
        go on from the file already in `out` (or from a snapshot) call load_overrides()."""
        self.remote = remote
        self._pushed = set()                 # (part, sha256) already copied to the server (remote mode)
        self._sig = {}                       # part -> mesh signature at load / last export (track_edits)
        self._slot_only_parts = set()        # new independent parts: geometry and slot names, never source shaders
        self.bounds = {}                     # part -> (min, max) from the GLB header when load_meshes=False
        self.placements, self.out, self.status = Path(placements), Path(out), Path(status)
        raw = self.placements.read_bytes()
        self.base_sha = hashlib.sha256(raw).hexdigest()
        self.data = json.loads(raw.decode("utf-8-sig"))
        assert self.data.get("schema") == "renou-placements/1" and self.data.get("coord") == "blender_zup_m"
        self.base = {i["id"]: i for i in self.data["instances"]}
        self.batch = self.data["batch"]
        self.col = bpy.data.collections.new("BLSYNC|" + self.batch)
        bpy.context.scene.collection.children.link(self.col)
        meshes = {}
        if parts_glb and not load_meshes:
            self.bounds = glb_part_bounds(parts_glb)
        elif parts_glb:
            names = set(glb_part_bounds(parts_glb))      # the GLB's own node names = part ids
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=str(parts_glb))
            lib = bpy.data.collections.new("BLSYNC_PARTS|" + self.batch)
            bpy.context.scene.collection.children.link(lib)
            for o in set(bpy.data.objects) - before:
                if o.type == "MESH":
                    # a second load in the same Blender (the add-on attaching again) gets PBOX_D.001: key by the node name
                    base = re.sub(r"\.\d{3,}$", "", o.name)
                    meshes[o.name if o.name in names or base not in names else base] = o.data
                for c in list(o.users_collection):
                    c.objects.unlink(o)
                lib.objects.link(o)
            lib.hide_viewport = lib.hide_render = True
        self.meshes = meshes
        if track_edits:
            self._sig = {p: mesh_sig(me) for p, me in meshes.items()}
        rx = re.compile(only_src) if only_src else None
        self.obj = {}
        for iid, rec in self.base.items():
            if rx and not rx.search(rec.get("src", "")):
                continue
            self._spawn(iid)
        self.added = 0
        self.mesh_out = {}                   # part -> {"glb", "sha256"}: geometry sent to UE in this session
        self.rev = int(time.time())          # monotonic across restarts of the script
        self.archive = Path(archive) if archive else archive_dir(self.out)
        self.last_snapshot = None
        self._orig_mesh = {}                 # table part -> its release mesh, while a loaded document replaces it
        on_disk = self.read_out()
        if on_disk:                          # never number below the file already there (rev-back = a snapshot)
            try:
                self.rev = max(self.rev, int(float(on_disk.get("rev"))))
            except (TypeError, ValueError):
                pass
        bpy.context.view_layer.update()

    def read_out(self):
        """the override document now in self.out (None: no file or unreadable)."""
        try:
            return json.loads(self.out.read_text(encoding="utf-8-sig"))
        except Exception:
            return None

    def snapshots(self, limit=20):
        return list_snapshots(self.out, self.archive, limit)

    def snapshot(self, reason):
        """keep a copy of the current override file in archive/ (see snapshot_file)."""
        snap = snapshot_file(self.out, reason, self.archive)
        if snap:
            self.last_snapshot = str(snap)
        return snap

    def _spawn(self, iid):
        """(re)create the object of a table instance: a mesh when the parts GLB is loaded, else an Empty."""
        rec = self.base[iid]
        o = bpy.data.objects.new(iid, self.meshes.get(rec["part"]))
        o["blsync_id"], o["blsync_part"] = iid, rec["part"]
        o["blsync_era"], o["blsync_src"] = rec.get("era", "both"), rec.get("src", "")
        o.matrix_world = mat_of(rec)
        self.col.objects.link(o)
        self.obj[iid] = o
        return o

    def batch_of(self, iid):
        """True when an id belongs to this batch (table ids and the <batch>_bl… ids made here)."""
        return iid in self.base or str(iid).startswith(self.batch + "_bl")

    # ---- selection helpers
    def group(self, key):
        """objects whose building_id == key, or whose src (part before ' | ') == key."""
        out = [o for iid, o in self.obj.items()
               if self.base[iid].get("building_id") == key or self.base[iid].get("src", "").split(" | ")[0].strip() == key]
        assert out, f"no instances for {key!r} in {self.batch}"
        return out

    def srcs(self, pattern=""):
        """sorted list of building keys (src before ' | ') matching a regex, with instance counts."""
        c = {}
        for iid in self.obj:
            k = self.base[iid].get("src", "").split(" | ")[0].strip()
            if re.search(pattern, k):
                c[k] = c.get(k, 0) + 1
        return sorted(c.items())

    def centre(self, objs, base=True):
        """centre of the group's world bounding box; base=True: at its lowest z (turn about the footprint)."""
        pts = []
        for o in objs:
            if o.type == "MESH":
                pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
            elif o.get("blsync_part") in self.bounds:
                lo, hi = self.bounds[o["blsync_part"]]
                pts += [o.matrix_world @ Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
            else:
                pts.append(o.matrix_world.translation.copy())
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        c = (lo + hi) / 2
        if base:
            c.z = lo.z
        return c

    # ---- edits (all in Blender world space)
    def move(self, objs, d):
        M = Matrix.Translation(Vector(d))
        for o in objs:
            o.matrix_world = M @ o.matrix_world

    def rotate(self, objs, deg, centre=None):
        """turn a group about the vertical axis through centre (default: its own footprint centre). CCW seen from above."""
        if centre is None:
            known = any(o.type == "MESH" or o.get("blsync_part") in self.bounds for o in objs)
            assert known, "world-baked parts need parts_glb (or centre=) to find the centre"
            centre = self.centre(objs)
        c = Vector(centre)
        M = Matrix.Translation(c) @ Matrix.Rotation(math.radians(deg), 4, "Z") @ Matrix.Translation(-c)
        for o in objs:
            o.matrix_world = M @ o.matrix_world

    def set_part(self, objs, part):
        for o in objs:
            o["blsync_part"] = part
            if part in self.meshes and o.type == "MESH":
                o.data = self.meshes[part]

    def new_part(self, src_part, name):
        """a new part = a copy of an existing part's mesh under a new id (edit it, then export_part + set_part)."""
        assert src_part in self.meshes, "new_part needs parts_glb"
        me = self.meshes[src_part].copy()
        me.name = name
        self.meshes[name] = me
        if src_part in self._slot_only_parts:
            self._slot_only_parts.add(name)
        return me

    def add_object(self, obj, part, era="both", src=""):
        """Register a mesh object as a new part + instance; return the new instance (main thread, object mode).
        Copy local mesh data and world TRS separately, leaving the source object, its parent and shaders unchanged.
        New part ids are P + 12 hexadecimal digits. Modifiers are not applied; shear cannot be represented by TRS."""
        if not isinstance(part, str) or re.fullmatch(r"P[0-9a-fA-F]{12}", part) is None:
            raise ValueError("part must be P followed by 12 hexadecimal digits")
        known = set(self.meshes) | set(self.mesh_out) | {rec["part"] for rec in self.base.values()}
        if part.lower() in {name.lower() for name in known}:
            raise ValueError(f"part {part} already exists")
        if not isinstance(obj, bpy.types.Object) or obj.type != "MESH":
            raise TypeError("add_object needs a Blender mesh object")
        if obj.mode != "OBJECT":
            raise ValueError("leave edit mode before adding an object")
        bpy.context.view_layer.update()
        world = obj.matrix_world.copy()
        loc, quat, scale = world.decompose()
        trs = Matrix.LocRotScale(loc, quat, scale)
        if max(abs(world[i][j] - trs[i][j]) for i in range(4) for j in range(4)) > 1e-5:
            raise ValueError("world transform has shear; placements support translation, rotation and scale only")
        me = obj.data.copy()
        me.name = part
        for i, slot in enumerate(obj.material_slots):
            me.materials[i] = slot.material    # respect object-linked slots as well as mesh-linked slots
        new = bpy.data.objects.new(part, me)
        new.matrix_world = world
        new["blsync_part"], new["blsync_era"], new["blsync_src"] = part, era, src
        self.adopt(new)
        self.col.objects.link(new)
        self.meshes[part] = me
        self._slot_only_parts.add(part)
        try:
            self.export_part(part)
        except Exception:
            self.meshes.pop(part, None)
            self.mesh_out.pop(part, None)
            self._sig.pop(part, None)
            self._slot_only_parts.discard(part)
            bpy.data.objects.remove(new, do_unlink=True)
            bpy.data.meshes.remove(me)
            raise
        return new

    def export_part(self, part, out_dir=None):
        """export ONE part's current mesh as <out>/meshes/<part>_<sha8>.glb (identity transform, glTF Y-up like the release);
        the next publish() lists it under "meshes" and UE swaps the mesh in place, keeping UE's materials per slot name."""
        me = self.meshes[part]
        d = Path(out_dir) if out_dir else self.out.parent / "meshes"
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"{part}.tmp.glb"
        export_mesh, placeholders, names = me, [], {}
        if part in self._slot_only_parts:
            export_mesh = me.copy()
            for i, material in enumerate(me.materials):
                placeholder = bpy.data.materials.new("BLSYNC_SLOT")
                placeholders.append(placeholder)
                names[placeholder.name] = material.name if material else ""
                export_mesh.materials[i] = placeholder
        selected, active = list(bpy.context.selected_objects), bpy.context.view_layer.objects.active
        tmpo = bpy.data.objects.new(part, export_mesh)
        bpy.context.scene.collection.objects.link(tmpo)
        try:
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            tmpo.select_set(True)
            bpy.context.view_layer.objects.active = tmpo
            bpy.ops.export_scene.gltf(filepath=str(tmp), export_format="GLB", use_selection=True, export_apply=False,
                                      export_yup=True, export_animations=False, export_cameras=False, export_lights=False)
            if part in self._slot_only_parts:
                _slot_names_only(tmp, names, part)
        finally:
            bpy.data.objects.remove(tmpo, do_unlink=True)
            if export_mesh != me:
                bpy.data.meshes.remove(export_mesh)
            for material in placeholders:
                bpy.data.materials.remove(material)
            for o in selected:
                if alive(o):
                    o.select_set(True)
            bpy.context.view_layer.objects.active = active if active is not None and alive(active) else None
        sha = hashlib.sha256(tmp.read_bytes()).hexdigest()
        glb = d / f"{part}_{sha[:8]}.glb"
        os.replace(tmp, glb)
        self.mesh_out[part] = {"glb": str(glb), "sha256": sha}
        if self._sig:
            self._sig[part] = mesh_sig(me)
        return self.mesh_out[part]

    def export_part_if_changed(self, part):
        """export_part() only when the mesh differs from the load / last export (needs track_edits=True for the baseline;
        without one it always exports). Returns the mesh entry, or None when nothing changed. Object mode only."""
        if part not in self.meshes:
            return None
        if part in self._sig and mesh_sig(self.meshes[part]) == self._sig[part]:
            return None
        return self.export_part(part)

    def adopt(self, o):
        """give an object a new id of this batch (a Shift+D copy carries its source's blsync_id along)."""
        self.added += 1
        iid = f"{self.batch}_bl{int(time.time()) % 100000:05d}{self.added:03d}"
        o["blsync_id"] = iid
        o.name = iid
        return iid

    def fix_duplicates(self):
        """the registered object keeps its id; every other object in the collection holding the same id gets a new one.
        Returns the new ids."""
        owner, fixed = {}, []
        for o in self.col.objects:
            iid = o.get("blsync_id")
            if not iid:
                continue
            reg = self.obj.get(iid)
            registered_elsewhere = reg is not None and alive(reg) and reg != o and reg.name in self.col.objects
            if registered_elsewhere or iid in owner:
                fixed.append(self.adopt(o))
            else:
                owner[iid] = o
        return fixed

    def delete(self, objs):
        for o in objs:
            o["blsync_deleted"] = True
            o.hide_viewport = o.hide_render = True

    def copy(self, objs, d=(0, 0, 0)):
        new = []
        for o in objs:
            self.added += 1
            n = o.copy()
            iid = f"{self.batch}_bl{int(time.time()) % 100000:05d}{self.added:03d}"
            n.name = iid
            n["blsync_id"] = iid
            n.matrix_world = Matrix.Translation(Vector(d)) @ o.matrix_world
            self.col.objects.link(n)
            new.append(n)
        return new

    def reset(self, objs=None):
        if objs is None:
            self.mesh_out = {}               # back to the release geometry too
            for part, me in self._orig_mesh.items():     # meshes a loaded document had replaced
                self.meshes[part] = me
            self._orig_mesh.clear()
            for iid, o in list(self.obj.items()):
                if not alive(o) or o.name not in self.col.objects:     # deleted by hand (X) in Blender: bring it back
                    self._spawn(iid)
        for o in (objs or list(self.col.objects)):
            iid = o.get("blsync_id")
            if iid in self.base and objs is None and self.obj.get(iid) != o:
                bpy.data.objects.remove(o)    # an unfixed Shift+D copy still carrying a table id
                continue
            if iid in self.base:
                o.matrix_world = mat_of(self.base[iid])
                o["blsync_part"] = self.base[iid]["part"]
                if o.type == "MESH" and self.base[iid]["part"] in self.meshes:
                    o.data = self.meshes[self.base[iid]["part"]]
                if "blsync_deleted" in o:
                    del o["blsync_deleted"]
                o.hide_viewport = o.hide_render = False
            elif iid:
                bpy.data.objects.remove(o)

    def _local_glb(self, path):
        """a document's GLB on this machine: the path as written, else the same file name in <out>/meshes (remote mode
        writes server paths into the document; the local copy keeps the name)."""
        p = Path(path)
        if p.exists():
            return p
        alt = self.out.parent / "meshes" / p.name
        return alt if alt.exists() else None

    def _import_part_mesh(self, glb, part):
        """the single mesh of a part GLB (as export_part writes them), as a Blender mesh named after the part."""
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(glb))
        new = [o for o in bpy.data.objects if o not in before]
        meshes = [o.data for o in new if o.type == "MESH"]
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
        if len(meshes) != 1:
            raise ValueError(f"{glb}: {len(meshes)} meshes, a part GLB has exactly one")
        meshes[0].name = part
        return meshes[0]

    def load_overrides(self, src):
        """put the scene into the state an override document describes - a snapshot from archive/, or the file already
        in `out` when the add-on attaches again (user 10-10: reopening a window must not start from an empty file).
        Everything goes back to the table first, then each listed instance is placed as listed; part meshes come from
        the document's GLBs. Ash 10-10, all or nothing: the document, every GLB (present - as written or in <out>/meshes -,
        its SHA-256 equal to the document's, importable) and every instance entry (its transform computed, finite) are
        checked BEFORE the scene changes; anything wrong raises and leaves the scene as it was. After that only plain
        assignments are made. Returns {"instances", "meshes", "missing_meshes": []}. Main thread."""
        doc = src if isinstance(src, dict) else json.loads(Path(src).read_text(encoding="utf-8-sig"))
        if doc.get("schema") != "renou-overrides/1" or doc.get("batch") != self.batch:
            raise ValueError(f"not an override document of {self.batch}: {doc.get('schema')} / {doc.get('batch')}")
        if doc.get("base_sha256") and doc["base_sha256"] != self.base_sha:
            raise ValueError("the document was made against another version of the placements table")
        staged = {}
        try:
            for part, m in (doc.get("meshes") or {}).items():
                glb = self._local_glb(m["glb"])
                if glb is None:
                    raise FileNotFoundError(f"mesh {part}: {m['glb']} not found (nor in {self.out.parent / 'meshes'})")
                got = hashlib.sha256(glb.read_bytes()).hexdigest()
                if m.get("sha256") and got != m["sha256"]:
                    raise ValueError(f"mesh {part}: {glb.name} has SHA-256 {got[:12]}, the document says {m['sha256'][:12]}")
                staged[part] = (glb, got, self._import_part_mesh(glb, part + "__staged"))
            plan = self._plan_instances(doc.get("instances") or {})
        except Exception:
            for _glb, _got, me in staged.values():
                bpy.data.meshes.remove(me)
            raise
        # from here on nothing reads a file: the scene changes as a whole
        self.reset()
        table_parts = {r["part"] for r in self.base.values()}
        for part, (glb, got, me) in staged.items():
            me.name = part
            if part in self.meshes and part not in self._orig_mesh:
                self._orig_mesh[part] = self.meshes[part]
            self.meshes[part] = me
            if part not in table_parts:
                self._slot_only_parts.add(part)          # new parts export slot names only, as add_object made them
            self.mesh_out[part] = {"glb": str(glb), "sha256": got}
            if self._sig:
                self._sig[part] = mesh_sig(me)
        for o in self.col.objects:                       # table objects of a replaced part show the loaded mesh
            if o.type == "MESH" and o.get("blsync_part") in self.mesh_out and o.get("blsync_part") in self.meshes:
                o.data = self.meshes[o["blsync_part"]]
        for iid, kind, part, M, e in plan:
            if kind == "new":
                o = bpy.data.objects.new(iid, self.meshes.get(part))
                o["blsync_id"], o["blsync_part"] = iid, part
                o["blsync_era"], o["blsync_src"] = str(e.get("era", "both")), str(e.get("src", ""))
                o.matrix_world = M
                self.col.objects.link(o)
                continue
            o = self.obj.get(iid)
            if o is None or not alive(o) or o.name not in self.col.objects:
                o = self._spawn(iid)
            if kind == "delete":
                self.delete([o])
                continue
            if part != self.base[iid]["part"]:
                self.set_part([o], part)
            o.matrix_world = M
        try:
            self.rev = max(self.rev, int(float(doc.get("rev"))))
        except (TypeError, ValueError):
            pass
        bpy.context.view_layer.update()
        return {"instances": len(doc.get("instances") or {}), "meshes": len(doc.get("meshes") or {}),
                "missing_meshes": []}

    def _plan_instances(self, entries):
        """every entry of a document checked, its object kind, part and world matrix computed - before load_overrides()
        changes anything (Ash 10-10: a bad value in a late entry used to fail after the reset). Raises ValueError."""
        plan = []
        for iid, e in entries.items():
            try:
                if not isinstance(iid, str) or not isinstance(e, dict):
                    raise ValueError("entry is not an object")
                rec = self.base.get(iid)
                if e.get("deleted"):
                    if rec is not None:
                        plan.append((iid, "delete", None, None, e))
                    continue                         # a new instance marked deleted: nothing to show
                part = e.get("part") if e.get("part") is not None else (rec or {}).get("part")
                if not isinstance(part, str) or not part:
                    raise ValueError("no part")
                M = mat_of(dict(rec, **e) if rec is not None else e)
                if not all(math.isfinite(v) for row in M for v in row):
                    raise ValueError("transform is not finite")
                plan.append((iid, "table" if rec is not None else "new", part, M, e))
            except Exception as exc:
                raise ValueError(f"instance {iid}: {type(exc).__name__}: {exc}") from exc
        return plan

    def snapshot_scene(self, reason="scene"):
        """keep the scene's current state (unpublished edits included) in archive/ as an override document - before a
        restore replaces it (Ash 10-10: the file on disk may not hold the newest edits). Part meshes edited but not yet
        exported are exported first (Ash 10-10: otherwise a restore loses unpublished geometry): with track_edits every part
        whose mesh changed since load / last export, without it the parts already sent (they may have been edited
        since). Object mode only (edit-mode changes are not in the mesh yet)."""
        if bpy.context.mode != "OBJECT":
            raise RuntimeError("leave edit mode first: edits made there are not in the mesh yet")
        for part in list(self.meshes if self._sig else self.mesh_out):
            if self._sig:
                self.export_part_if_changed(part)
            else:
                self.export_part(part)
        doc = {"schema": "renou-overrides/1", "batch": self.batch, "base_sha256": self.base_sha, "rev": self.rev,
               "label": f"scene before {reason} (unpublished edits included)", "written": time.time(),
               "instances": self.overrides(),
               "meshes": {p: {"glb": m["glb"], "sha256": m["sha256"]} for p, m in self.mesh_out.items()}}
        snap = snapshot_bytes(self.out, json.dumps(doc, ensure_ascii=False).encode("utf-8"), reason, self.archive)
        self.last_snapshot = str(snap)
        return snap

    # ---- output
    def overrides(self):
        inst = {}
        bpy.context.view_layer.update()
        for o in self.col.objects:
            iid = o.get("blsync_id")
            if not iid:
                continue
            if o.get("blsync_deleted"):
                if iid in self.base:
                    inst[iid] = {"deleted": True}
                continue
            loc, q, s = decompose(o.matrix_world)
            e = {"pos": [round(v, 5) for v in loc], "quat_wxyz": [round(v, 7) for v in q], "scale": [round(v, 6) for v in s]}
            rec = self.base.get(iid)
            if rec is None:
                inst[iid] = dict(e, part=o["blsync_part"], era=o["blsync_era"], src=o["blsync_src"])
                continue
            bl, bq, bs = decompose(mat_of(rec))
            moved = (loc - bl).length > 1e-4 or not same_rotation(bq, q) or (s - bs).length > 1e-5
            if o["blsync_part"] != rec["part"]:
                e["part"] = o["blsync_part"]
            elif not moved:
                continue
            inst[iid] = e
        # loaded table instances whose object was deleted outright (X in Blender, not delete()) are deletions too
        seen = {o.get("blsync_id") for o in self.col.objects}
        for iid in self.obj:
            if iid in self.base and iid not in seen:
                inst[iid] = {"deleted": True}
        return inst

    def publish(self, label="", wait=30.0):
        """write the cumulative override file; wait for UE's receipt (status.json with the same rev) up to `wait` s.
        = build() + deliver() + wait_receipt(); the add-on calls build() on Blender's main thread and the other two on a
        worker thread, so pushing to the server never freezes the UI."""
        ov = self.build(label)
        res = self.deliver(ov)
        res["ue"] = self.wait_receipt(ov, wait)
        return res

    def build(self, label=""):
        """main thread only (reads bpy): the next override document; "meshes" holds local GLB paths."""
        inst = self.overrides()
        self.rev += 1
        return {"schema": "renou-overrides/1", "batch": self.batch, "base_sha256": self.base_sha, "rev": self.rev,
                "label": label, "written": time.time(), "instances": inst,
                "meshes": {p: {"glb": m["glb"], "sha256": m["sha256"]} for p, m in self.mesh_out.items()}}

    def deliver(self, ov):
        """any thread (no bpy): remote mode copies new meshes and points "meshes" at the server paths; then the file is
        written atomically (locally, and pushed to the server in remote mode)."""
        self.out.parent.mkdir(parents=True, exist_ok=True)
        if self.remote:
            ov["meshes"] = self._push_meshes(ov["meshes"])
            ov["written"] = time.time()
        if self.out.exists():                # user 10-10: nothing that shrinks or replaces the file without a copy first
            old = self.read_out()
            why = replace_risk(old, ov) if old is not None else "unreadable"
            if why:
                self.snapshot(why)
        tmp = self.out.with_suffix(".tmp")
        tmp.write_text(json.dumps(ov, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.out)
        res = {"rev": ov["rev"], "overrides": len(ov["instances"]), "ue": None, "snapshot": self.last_snapshot}
        if self.remote:
            res["push_s"] = self._push_file(self.out)
        return res

    def wait_receipt(self, ov, wait=30.0, complete=False):
        """any thread: UE's receipt for this rev (or an error newer than the file), or None after `wait` s.
        bl_sync writes one receipt per batch (status_<batch>.json) besides the shared status.json: the batch's own
        file is read first, so two writers on two batches never pick up each other's receipt.
        New meshes are imported in the background (#28): the first receipt for a rev can say "complete": false and list
        "pending_meshes" (positions are already applied, instances of new parts wait); another receipt for the same rev
        follows when the meshes are in. complete=True waits for that one."""
        t0 = time.time()
        while wait and time.time() - t0 < wait:
            for own, text in self._read_statuses():
                try:
                    st = json.loads(text)
                except Exception:
                    continue
                if not self.receipt_is_mine(st, own):
                    continue
                if st.get("error"):
                    if st.get("t", 0) > ov["written"]:
                        return st
                    continue
                if st.get("rev") == ov["rev"] and (not complete or st.get("complete", True)):
                    return st
            time.sleep(0.5 if self.remote else 0.05)
        return None

    def receipt_is_mine(self, st, own):
        """Ash 10-10: a rev alone is no identity (two batches started in the same second share it). A receipt that
        names its batch must name this one; one that names none (bl_sync before 10-10) is believed only from the
        batch's own status_<batch>.json, never from the shared status.json."""
        b = st.get("batch")
        if b is not None:
            return b == self.batch
        return own

    # ---- R7: laptop -> server with the system's scp / ssh
    def _split(self):
        host, path = self.remote.split(":", 1)
        return host, path.rstrip("/")

    def _push_file(self, local):
        """atomic on the server: stream into <name>.tmp, then mv (one ssh connection)."""
        t = time.time()
        host, path = self._split()
        dst = f"{path}/{Path(local).name}"
        with open(local, "rb") as fh:
            subprocess.run(["ssh", host, f"cat > '{dst}.tmp' && mv '{dst}.tmp' '{dst}'"], stdin=fh, check=True)
        return round(time.time() - t, 2)

    def _push_meshes(self, meshes):
        host, path = self._split()
        out = {}
        for part, m in meshes.items():
            rpath = f"{path}/meshes/{Path(m['glb']).name}"
            if (part, m["sha256"]) not in self._pushed:
                subprocess.run(["ssh", host, f"mkdir -p '{path}/meshes'"], check=True)
                subprocess.run(["scp", "-q", m["glb"], f"{host}:{rpath}"], check=True)
                self._pushed.add((part, m["sha256"]))
            out[part] = {"glb": rpath, "sha256": m["sha256"]}
        return out

    def _status_paths(self):
        own = self.status.with_name(f"status_{self.batch}.json")
        return [own, self.status] if self.status.name == "status.json" else [self.status]

    def _read_statuses(self):
        """[(own, text)] of the receipt files, the batch's own first (own = status_<batch>.json); missing files are
        skipped."""
        own_name = f"status_{self.batch}.json"
        if not self.remote:
            out = []
            for p in self._status_paths():
                try:
                    out.append((p.name == own_name, p.read_text(encoding="utf-8")))
                except OSError:
                    pass
            return out
        host, _ = self._split()
        out = []
        for p in self._status_paths():           # one plain `cat` per file (a missing file just fails)
            r = subprocess.run(["ssh", host, f"cat '{p.as_posix()}'"], capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and r.stdout.strip():
                out.append((p.name == own_name, r.stdout))
        return out

    def _read_status(self):
        if not self.remote:
            return self.status.read_text(encoding="utf-8")
        host, _ = self._split()
        return subprocess.run(["ssh", host, f"cat '{self.status.as_posix()}'"], capture_output=True, text=True, timeout=15).stdout

    def write_back(self, out_dir):
        """new placements version (never overwrites): <batch>_placements_v<NNN>.json + <batch>_changes_v<NNN>.md."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        n = 1
        while (out_dir / f"{self.batch}_placements_v{n:03d}.json").exists():
            n += 1
        inst = self.overrides()
        rows, log = [], {"moved": [], "swapped": [], "deleted": [], "added": []}
        for rec in self.data["instances"]:
            e = inst.get(rec["id"])
            if e is None:
                rows.append(rec)
                continue
            if e.get("deleted"):
                log["deleted"].append(rec)
                continue
            r = dict(rec)
            q = Quaternion(e["quat_wxyz"])
            r.update(pos=e["pos"], quat_wxyz=e["quat_wxyz"], yaw_deg=round(math.degrees(q.to_euler("XYZ").z), 3),
                     scale=e["scale"][0] if max(e["scale"]) - min(e["scale"]) < 1e-6 else e["scale"])
            if "part" in e and e["part"] != rec["part"]:
                r["part"], r["lods"] = e["part"], ["NEAR"]
                log["swapped"].append(r)
            else:
                log["moved"].append(r)
            rows.append(r)
        for iid, e in inst.items():
            if iid in self.base or e.get("deleted"):
                continue
            src_rec = next((x for x in self.data["instances"] if x.get("src") == e.get("src")), {})
            q = Quaternion(e["quat_wxyz"])
            r = {"id": iid, "part": e["part"], "lods": ["NEAR"], "pos": e["pos"], "quat_wxyz": e["quat_wxyz"],
                 "yaw_deg": round(math.degrees(q.to_euler("XYZ").z), 3),
                 "scale": e["scale"][0] if max(e["scale"]) - min(e["scale"]) < 1e-6 else e["scale"],
                 "district": src_rec.get("district", self.batch), "zone": src_rec.get("zone", ""), "era": e.get("era", "both"),
                 "building_id": src_rec.get("building_id", ""), "src": e.get("src", "")}
            rows.append(r)
            log["added"].append(r)
        new = dict(self.data, instances=rows, count=len(rows),
                   source=f"{self.data.get('source', '')} + blsync write_back v{n:03d} of {self.placements.name} ({self.base_sha[:12]})")
        pj = out_dir / f"{self.batch}_placements_v{n:03d}.json"
        pj.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
        md = [f"# {self.batch} 摆放改动 v{n:03d}", "", f"原表 {self.placements} (SHA-256 {self.base_sha})", "",
              "注意：零件库 GLB 和 parts_sha256 沿用原表；改了网格的零件、新零件要由工程一并发布进零件库。", ""]
        md.append(f"## 改了网格或新增的零件：{len(self.mesh_out)}")
        md += [f"- {k}  {v['glb']}  sha256 {v['sha256']}" for k, v in sorted(self.mesh_out.items())]
        md.append("")
        for k, title in (("moved", "挪位/转向"), ("swapped", "换件"), ("added", "新增"), ("deleted", "删除")):
            md.append(f"## {title}：{len(log[k])}")
            md += [f"- {r['id']}  {r.get('src', '')}  pos {r.get('pos')}" for r in log[k]]
            md.append("")
        (out_dir / f"{self.batch}_changes_v{n:03d}.md").write_text("\n".join(md), encoding="utf-8")
        return {"placements": str(pj), "meshes": sorted(self.mesh_out), **{k: len(v) for k, v in log.items()}}
