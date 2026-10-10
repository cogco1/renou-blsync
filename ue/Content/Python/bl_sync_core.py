"""人偶之心 · Blender→UE 实时预览 2026-10-09 (user: "脚本Blender做没问题，但需要在UE预览效果，这样快速迭代").
UE side of the live link. Works on a batch that ct_placements.py already built (one HISM per part per era on the actors
INST_<name>_<era>) and changes it in place: no re-import, no re-build, no level save. Imported once, kept in sys.modules,
so the state survives between lk_session requests.

The Blender side writes one override file per batch (schema renou-overrides/1, written atomically: tmp + rename). It is
CUMULATIVE: everything that differs from the base placements table, so applying it is idempotent and an editor restart only
needs attach + one apply.
  {"schema": "renou-overrides/1", "batch": "area_04_03", "base_sha256": "<sha256 of the base placements json>",
   "rev": 12, "written": <unix time>,
   "instances": {"<id>": {"pos": [x, y, z], "quat_wxyz": [w, x, y, z], "scale": s | [sx, sy, sz],
                          "part": "<part>"            (optional: swap the mesh)
                          "deleted": true             (optional: hide it)
                          "era": "both", "src": "..." (only for new ids: copies made in Blender)}},
   "meshes": {"<part>": {"glb": "/abs/<part>.glb", "sha256": "..."}}   (optional: changed or new part geometry)}
Coordinates as renou-placements/1: Blender metres, Z up -> UE cm (x, -y, z) x 100, quat_wxyz -> Quat(x, -y, z, -w).
Hidden = scale 1e-4 at the same place (the slot is kept, indices never shift).
Save guard (视效 10-09): while the preview differs from the table, the level files that hold the batch's HISMs are made
read-only on disk, so nobody can save preview changes into the batch layer (a rebuild of that layer is blocked too);
they get their write permission back as soon as the preview equals the table again (reset / empty override) or on detach.
The list is kept in Saved/BlSync/guard.json, so detach also works after an editor restart.
Ownership (user 10-09, as D5 LiveSync): Blender owns which part, where, rotation, scale and the part's geometry; UE owns
materials, lights, post, vegetation, water, cameras. A sync never changes a UE-owned thing: when a part's mesh is replaced
or an instance lands in a new HISM, every material slot keeps the material UE already shows for that slot name (component
override or the batch's MI_C_ by ct_placements' rules); only slots UE has never seen fall back to the GLB's material."""
import hashlib, json, math, os, re, runpy, time, traceback
from pathlib import Path
import unreal

EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
UES = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
EAL = unreal.EditorAssetLibrary
PROJ = Path(unreal.Paths.project_dir()).resolve()
CTRL = PROJ / "Saved" / "BlSync"
CTRL.mkdir(parents=True, exist_ok=True)
HIDE = 1e-4
TOL = 1e-4          # metres / quaternion units: below this two states count as equal

S = {"batches": {}, "watch": None}
GUARD = CTRL / "guard.json"
LIVE_ROOT = "/Game/_LivePreview"        # single-part re-imports (in memory; if someone saves them they stay in this folder)   # name -> Batch; watch = {"path", "sig", "handle", "next", "interval"}


_MI = {}


def _norm(name):                                   # = lk_kit.norm
    return re.sub(r"[^0-9a-z]", "", name.lower())


def _stem(k):                                      # = ct_placements.stem
    return re.sub(r"[._]?\d{1,3}$", "", k)


def read_rules(f):
    """ct_unmapped.py's RULES list ([regex, MI name], ...) read with ast - the script itself is not run (it would scan
    the open level). 视效's make_slot_mi_table.py reads it the same way."""
    import ast
    tree = ast.parse(Path(f).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "RULES" for t in node.targets):
            v = node.value
            if isinstance(v, ast.BoolOp):                    # RULES = REQ.get("rules") or [ ... ]
                v = v.values[-1]
            return [tuple(x) for x in ast.literal_eval(v)]
    return []


def mi_for_slot(slot):
    """the tuned MI_C_* ct_placements would give this slot name (same maps and ct_unmapped rules), or None."""
    if "mm" not in _MI:
        mm = {}
        mats = EAL.list_assets("/Game/City2/Materials", recursive=False, include_folder=False) \
            if EAL.does_directory_exist("/Game/City2/Materials") else []
        for p in mats:
            n = p.split("/")[-1].split(".")[0]
            if n.startswith("MI_C_"):
                mm[_norm(n[5:])] = p.split(".")[0]
        st = {}
        for key in sorted(mm):
            st.setdefault(_stem(key), mm[key])
        f = Path(unreal.Paths.project_content_dir()) / "Python" / "ct_unmapped.py"
        rules = read_rules(f) if mm and f.exists() else []
        _MI.update(mm=mm, st=st, rules=rules)
    k = _norm(slot)
    p = _MI["mm"].get(k) or _MI["mm"].get(k[:52]) or _MI["st"].get(_stem(k)) or _MI["st"].get(_stem(k[:52]))
    if not p:
        hit = next((mi for rx, mi in _MI["rules"] if re.search(rx, slot.lower())), None)
        if hit:
            p = f"/Game/Terrain/Materials/{hit}" if hit.startswith("MI_CT_") else f"/Game/City2/Materials/{hit}"
    return unreal.load_asset(p) if p and EAL.does_asset_exist(p) else None


SLOT_TABLE_GLOB = "/workspace/guest/look-ue-20261008/live/handoff/slot_to_mi_v*.json"   # 视效 maintains it
PLACEHOLDER = "/Engine/EngineDebugMaterials/M_GeoInsp_Zebra.M_GeoInsp_Zebra"         # loud: a slot nobody mapped yet
GENERIC_SLOT = re.compile(r"^material(_0)?([._ ]\d+)?$")   # = ct_placements 10-09: keep when the import has a texture


def load_slot_table(path=None):
    """视效's slot -> MI table (highest version unless a path is given): {raw name: entry} plus {norm: entry}."""
    import glob
    if not path:
        files = sorted(glob.glob(SLOT_TABLE_GLOB), key=lambda f: int(re.search(r"_v(\d+)\.json$", f).group(1)))
        path = files[-1] if files else None
    if not path:
        return None, {}, {}
    slots = json.loads(Path(path).read_text(encoding="utf-8"))["slots"]
    return path, slots, {v.get("norm") or _norm(k): v for k, v in slots.items()}


def slot_names(mesh):
    return [str(m.get_editor_property("material_slot_name")) for m in mesh.get_editor_property("static_materials")]


def log(msg):
    unreal.log("[BLSYNC] " + str(msg))


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_state(d):
    """(part, era, pos, quat, scale3, deleted) from a placements / override record."""
    if d is None:
        return None
    s = d.get("scale", 1.0)
    s = [float(s)] * 3 if not isinstance(s, (list, tuple)) else [float(v) for v in s]
    if d.get("quat_wxyz"):
        q = [float(v) for v in d["quat_wxyz"]]
    else:
        h = math.radians(float(d.get("yaw_deg") or 0.0)) / 2
        q = [math.cos(h), 0.0, 0.0, math.sin(h)]
    n = math.sqrt(sum(v * v for v in q)) or 1.0      # table quaternions carry 7 decimals: make them unit
    q = [v / n for v in q]
    for c in q:                                      # q and -q are the same rotation: first clearly non-zero
        if abs(c) > 1e-6:                            # component positive (w alone is not enough when w = 0, #31)
            if c < 0:
                q = [-v for v in q]
            break
    return {"part": d["part"], "era": d.get("era", "both"), "pos": [float(v) for v in d["pos"]], "quat": q,
            "scale": s, "deleted": bool(d.get("deleted"))}


def same(a, b):
    if a is None or b is None:
        return a is b
    if a["part"] != b["part"] or a["deleted"] != b["deleted"] or a["era"] != b["era"]:
        return False
    if abs(sum(x * y for x, y in zip(a["quat"], b["quat"]))) < 1.0 - 1e-9:     # rotations compared as rotations
        return False
    return all(abs(x - y) < TOL for k in ("pos", "scale") for x, y in zip(a[k], b[k]))


def ue_xf(st, hidden=False):
    w, x, y, z = st["quat"]
    rot = unreal.Quat(x, -y, z, -w).rotator()
    s = [HIDE] * 3 if hidden else st["scale"]
    p = st["pos"]
    return unreal.Transform(location=unreal.Vector(p[0] * 100.0, -p[1] * 100.0, p[2] * 100.0), rotation=rot,
                            scale=unreal.Vector(*s))


def xf_err(t, st):
    """largest location error in cm between a UE transform and a state (rotation via a 10 m test point)."""
    want = ue_xf(st)
    e = (t.translation - want.translation).length()
    probe = unreal.Vector(1000.0, 1000.0, 1000.0)
    e2 = (t.transform_location(probe) - want.transform_location(probe)).length()
    return max(e, e2)


def glb_materials(glb):
    """{material name: has a texture} from a GLB's JSON chunk only (the names = the slot names UE gives the mesh,
    before sanitising)."""
    import struct
    with open(glb, "rb") as fh:
        magic, _v, _n = struct.unpack("<4sII", fh.read(12))
        if magic != b"glTF":
            return {}
        clen, _t = struct.unpack("<II", fh.read(8))
        g = json.loads(fh.read(clen))
    out = {}
    for m in g.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        out[m.get("name", "")] = bool(pbr.get("baseColorTexture") or pbr.get("metallicRoughnessTexture")
                                      or m.get("normalTexture") or m.get("emissiveTexture"))
    return out


def glb_material_names(glb):
    return list(glb_materials(glb))


_ASYNC = {}         # folder -> async import record (module level: one import per folder, whichever batch asked first)
ASYNC_MAX = 3       # imports running at the same time; the rest wait in "queued"
ASYNC_TIMEOUT = 900.0


def interchange_mesh(glb, folder, preview=True, materials=False, on_done=None):
    """import one part GLB as plain Nanite static mesh(es) into folder, replacing assets of the same name in place.
    preview (issue #11, 视效 agreed 10-09): no distance field and no collision - a preview mesh only shows position and
    volume; Lumen soft shadows / GI on it are a little worse until the formal ct_placements rebuild.
    materials=False (issue #11): the GLB's own materials are not imported - making their instances and compiling their
    shaders was 15 of the 17 s in the live editor (0.1 s without); UE gives every slot its own material anyway. Only
    needed when a slot must keep the GLB material (KEEP_GLB) and UE has no material for that slot name yet.
    on_done (issue #28): asynchronous import, returns at once; on_done(objects) runs on the game thread when the assets
    exist. Test editor 10-09, one 250 m tower: the synchronous import held the game thread 4.95 s, the asynchronous one
    took 6 s with the longest gap between two editor ticks 0.35 s."""
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    params = unreal.ImportAssetParameters()
    params.set_editor_property("is_automated", True)
    params.set_editor_property("replace_existing", True)
    base = "DefaultGLTFAssetsPipeline"
    pipe = unreal.SystemLibrary.duplicate_object(unreal.load_object(None, f"/Interchange/Pipelines/{base}.{base}"), mgr)
    mp = pipe.get_editor_property("mesh_pipeline")
    opts = [("build_nanite", True), ("generate_lightmap_u_vs", False), ("collision", False)]
    if preview:
        opts.append(("distance_field_resolution_scale", 0.0))
    for k, v in opts:
        try:
            mp.set_editor_property(k, v)
        except Exception:
            log(f"mesh pipeline has no property {k}")
    if not materials:
        pipe.get_editor_property("material_pipeline").set_editor_property("import_materials", False)
    params.set_editor_property("override_pipelines", [
        unreal.SoftObjectPath(pipe.get_path_name()),
        unreal.SoftObjectPath("/Interchange/Pipelines/DefaultGLTFPipeline.DefaultGLTFPipeline")])
    if on_done is None:
        return mgr.import_asset(folder, mgr.create_source_data(str(glb)), params)
    d = params.get_editor_property("on_assets_import_done")
    d.bind_callable(on_done)
    params.set_editor_property("on_assets_import_done", d)
    _ASYNC.setdefault(folder, {})["keep"] = (params, pipe, on_done)     # alive until the callback has run
    return mgr.scripted_import_asset_async(folder, mgr.create_source_data(str(glb)), params)


def _start_import(rec):
    def done(objs):                                 # exactly one parameter: UE checks the callable's signature
        rec["state"] = "done"
        rec["done_t"] = time.time()
        rec["objs"] = [o.get_path_name() for o in (objs or [])]
    rec["state"], rec["start_t"] = "running", time.time()
    try:
        ok = interchange_mesh(rec["glb"], rec["folder"], materials=rec["need_mats"], on_done=done)
    except Exception as exc:
        ok, rec["error"] = False, f"{type(exc).__name__}: {exc}"
    if not ok:
        rec["state"], rec["done_t"] = "failed", time.time()
        rec.setdefault("error", "Interchange did not start the import")


def _pump_imports():
    """start queued imports while fewer than ASYNC_MAX run (only those an attached batch still waits for); time out the
    ones that never report back."""
    now = time.time()
    for r in _ASYNC.values():
        if r.get("state") == "running" and now - r["start_t"] > ASYNC_TIMEOUT:
            r["state"], r["done_t"], r["error"] = "failed", now, f"no answer from Interchange after {ASYNC_TIMEOUT:.0f} s"
    wanted = {i["folder"] for b in S["batches"].values() for i in getattr(b, "pending", {}).values()}
    for folder in [f for f, r in _ASYNC.items() if r.get("state") == "queued" and f not in wanted]:
        del _ASYNC[folder]                          # nobody waits for it any more (dropped from the file, detached)
    for r in sorted((r for r in _ASYNC.values() if r.get("state") == "queued"), key=lambda r: r["queued_t"]):
        if sum(1 for x in _ASYNC.values() if x.get("state") == "running") >= ASYNC_MAX:
            break
        _start_import(r)


class MeshPending(Exception):
    """the instance's part is still being imported (#28): it is placed when the mesh is there."""


class Batch:
    def __init__(self, req):
        t0 = time.time()
        self.placements = Path(req["placements"])
        self.data = json.loads(self.placements.read_text(encoding="utf-8-sig"))
        assert self.data.get("schema") == "renou-placements/1", self.data.get("schema")
        assert self.data.get("coord") == "blender_zup_m", self.data.get("coord")
        self.base_sha = sha_file(self.placements)
        self.name = req["name"]
        self.dest = req.get("dest", f"/Game/Inst/{self.name}")
        self.prefer = req.get("prefer", ["NEAR", "MID", "FAR"])
        self.slot_table_path, self.slot_table, self.slot_table_norm = load_slot_table(req.get("slot_table"))
        _MI.clear()                                 # MI_C_ list and ct_unmapped RULES are read again
        self.unmapped = set()                       # slots that got the placeholder (receipt: 视效 adds a table row)
        self.meshes = {}
        for p in EAL.list_assets(f"{self.dest}/parts", recursive=True, include_folder=False):
            a = unreal.load_asset(p)
            if isinstance(a, unreal.StaticMesh):
                self.meshes[a.get_name().lower()] = a
        self.hosts, self.comps = {}, {}             # era -> actor; (era, mesh path) -> HISM
        for a in EAS.get_all_level_actors():
            tags = [str(t) for t in a.tags]
            if f"INST_{self.name}" not in tags or "CITY_INST_GROUND" in tags or "CITY_INST_FAR" in tags:
                continue
            era = a.get_actor_label().rsplit("_", 1)[-1]
            self.hosts[era] = a
            for c in a.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
                m = c.get_editor_property("static_mesh")
                if m:
                    self.comps[(era, m.get_path_name())] = c
        assert self.hosts, f"no INST_{self.name}_* actors in the open level: build the batch with ct_placements first"
        self.level_files = sorted({level_file(a) for a in self.hosts.values()} - {None})
        # same grouping as ct_placements step 2: per (era, mesh) in table order -> instance index in that HISM
        self.base, self.home, counter, skipped = {}, {}, {}, 0
        for inst in self.data.get("instances", []):
            st = norm_state(inst)
            m = self.mesh_for(inst["part"], inst.get("lods"))
            if m is None:
                skipped += 1
                continue
            key = (st["era"], m.get_path_name())
            idx = counter.get(key, 0)
            counter[key] = idx + 1
            self.base[inst["id"]] = st
            self.home[inst["id"]] = (key, idx)
        self.slot = dict(self.home)                 # id -> (comp key, index) where it lives now
        self.orig_count = {k: c.get_instance_count() for k, c in self.comps.items()}
        self.free = {}                              # comp key -> indices we added and hid again (reusable)
        self.applied = {}                           # id -> normalised override last applied
        self.rev = None
        self.mesh_sha = {}
        self.keypath = {}                           # live mesh path -> the batch mesh path its HISMs are keyed by
        self.mesh_orig = {}                         # part -> the batch's own mesh (to switch back on reset)
        self.pending, self.last_ov = {}, None       # #28: part -> async import it waits for; the last override applied
        self.sync_import = bool(req.get("sync_import"))
        # verify the mapping against what is really in the level. Instances someone changed in UE (视效 10-09: preview-only
        # hiding of the buildings 建模's north slope replaces, moved 10 km down) are not an error: they are listed as
        # changed_in_ue and left alone - bl_sync only ever touches what an override names. A level that does not match
        # the table at all (most instances off, an index past the end, a missing HISM) still refuses to attach.
        worst, bad, missing_comp, changed = 0.0, 0, 0, []
        for iid, (key, idx) in self.home.items():
            c = self.comps.get(key)
            if c is None:
                missing_comp += 1
                continue
            if idx >= c.get_instance_count():
                bad += 1
                continue
            e = xf_err(c.get_instance_transform(idx, True), self.base[iid])
            if e > 1.0:
                changed.append(iid)
            else:
                worst = max(worst, e)
        self.foreign = set(changed)                 # changed in UE by someone else when attached
        self.report = {"batch": self.data.get("batch"), "instances": len(self.base), "skipped_no_mesh": skipped,
                       "hism": len(self.comps), "verify_bad": bad, "verify_worst_cm": round(worst, 3),
                       "changed_in_ue": len(changed), "changed_in_ue_ids": sorted(changed)[:20],
                       "missing_comp": missing_comp, "slot_table": self.slot_table_path, "seconds": round(time.time() - t0, 2)}
        too_many = len(changed) > (0 if req.get("strict") else 0.9 * max(1, len(self.home)))
        assert bad == 0 and missing_comp == 0 and not too_many, f"level does not match the placements table: {self.report}"

    def mesh_for(self, part, lods=None, fallback=False):
        # identical to ct_placements.mesh_for for the base table; fallback (overrides only) also tries the NEAR mesh
        for lod in [x for x in self.prefer if x in (lods or ["NEAR"])] + (["NEAR"] if fallback else []):
            m = self.meshes.get((part if lod == "NEAR" else f"{part}_{lod}").lower())
            if m:
                return m
        return None

    def ue_material(self, slot):
        """(material, how) for a slot that has no same-name slot on the replaced mesh. Order (视效's rule, 10-09):
        1. 视效's slot table: MI_C_* ("table"), or KEEP_GLB = the import's own material (None, "keep"). Entries marked
           "keep_if_textured" (the generic Material_0 / Material_0.00N names: every Meshy model has its own) keep the
           import's material when the incoming GLB material has a texture ("keep_textured"); every other entry wins
           even over a texture (F5_*, C__Harbor_*: the formal import maps them to MI_C_ too);
        2. slot not in the table: a generic name (GENERIC_SLOT: Material, Material_0, Material_0.001 ...) with a texture
           keeps its own material, the same rule ct_placements uses since 10-09 ("keep_textured"); otherwise the formal
           import's own mi_path - MI_C_<norm> (cut to 52), then without the trailing number, then ct_unmapped's RULES
           ("rule", 视效 10-09: most new names map this way, exactly as the formal rebuild); then the material UE already
           shows for this slot name in the batch ("ue");
        3. otherwise a loud placeholder, listed in the receipt ("placeholder")."""
        if not hasattr(self, "_slotmat"):
            self._slotmat = {}
            for c in self.comps.values():
                m = c.get_editor_property("static_mesh")
                for i, n in enumerate(slot_names(m) if m else []):
                    self._slotmat.setdefault(_norm(n), c.get_material(i))
        k = _norm(slot)
        textured = k in getattr(self, "textured_now", set())
        e = self.slot_table.get(slot) or self.slot_table_norm.get(k)
        if e is not None:
            if e.get("mi") == "KEEP_GLB":
                return None, "keep"
            if textured and e.get("keep_if_textured"):
                return None, "keep_textured"
            p = e["mi"]
            if EAL.does_asset_exist(p.split(".")[0]):
                return unreal.load_asset(p), "table"
        if textured and GENERIC_SLOT.match(slot.lower()):
            return None, "keep_textured"
        m = mi_for_slot(slot)
        if m is not None:
            return m, "rule"
        m = self._slotmat.get(k)
        if m is not None:
            return m, "ue"
        if self.slot_table_path:
            self.unmapped.add(slot)
            return unreal.load_asset(PLACEHOLDER), "placeholder"
        return None, "keep"

    def needs_glb_materials(self, names, old_mesh):
        """True when some slot of the new mesh would end on "keep" (KEEP_GLB) with nothing in UE to show for it."""
        old = {_norm(n) for n in slot_names(old_mesh)} if old_mesh else set()
        for n in names:
            k = _norm(n)
            if k in old:
                continue
            m, how = self.ue_material(n)
            if how in ("keep", "keep_textured"):
                return True
        self.unmapped -= {n for n in names}         # ue_material() above only looked; the real assignment reports again
        return False

    def carry_materials(self, comp, old_mesh, new_mesh):
        """switch comp to new_mesh; a slot with the same name as on the old mesh keeps exactly the material UE showed
        there ("carried"); other slots go through ue_material(). Returns {slot: [material or "glb", how]}."""
        before = {_norm(n): comp.get_material(i) for i, n in enumerate(slot_names(old_mesh))} if old_mesh else {}
        self.textured_now = getattr(self, "textured_by_mesh", {}).get(new_mesh.get_path_name(), set())
        comp.set_static_mesh(new_mesh)
        rep = {}
        for j, n in enumerate(slot_names(new_mesh)):
            m = before.get(_norm(n))
            how = "carried"
            if m is None:
                m, how = self.ue_material(n)
            if m is not None:
                comp.set_material(j, m)
            rep[n] = [m.get_path_name() if m else "glb", how]
        return rep

    def comp_for(self, era, mesh):
        path = mesh.get_path_name()
        key = (era, self.keypath.get(path, path))
        if key in self.comps:
            return key
        host = self.hosts.get(era)
        if host is None:                            # new era host, same tags as ct_placements, in the batch's own level
            any_host = next(iter(self.hosts.values()))
            ELU, LES = unreal.EditorLevelUtils, unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            cur = LES.get_current_level()           # VFX's current level comes back right after the spawn
            ELU.make_level_current(any_host.get_outer())
            try:
                host = EAS.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
            finally:
                ELU.make_level_current(cur)
            host.set_actor_label(f"INST_{self.name}_{era}")
            host.set_folder_path(f"City_Inst/{self.name}")
            tg = ["CITY_INST", f"INST_{self.name}"] + ([f"CITY_ERA_{era}"] if era in ("past", "present") else [])
            host.set_editor_property("tags", [unreal.Name(x) for x in tg])
            self.hosts[era] = host
        sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
        BL = unreal.SubobjectDataBlueprintFunctionLibrary
        root = sub.k2_gather_subobject_data_for_instance(host)[0]
        handle, _ = sub.add_new_subobject(unreal.AddNewSubobjectParams(
            parent_handle=root, new_class=unreal.HierarchicalInstancedStaticMeshComponent, blueprint_context=None))
        comp = BL.get_object(BL.get_data(handle))
        self.last_slots = self.carry_materials(comp, None, mesh)
        self.comps[key] = comp
        return key

    def revert_meshes(self, keep, out):
        """parts no longer listed in the override's "meshes": HISMs back to the batch's own mesh."""
        for part in [p for p in self.mesh_sha if p not in keep]:
            live, orig = self.meshes.get(part.lower()), self.mesh_orig.get(part)
            if orig is not None and live is not None:
                lp = live.get_path_name()
                for c in self.comps.values():
                    m = c.get_editor_property("static_mesh")
                    if m and m.get_path_name() == lp:
                        self.carry_materials(c, m, orig)
                self.meshes[part.lower()] = orig
            else:
                self.meshes.pop(part.lower(), None)
            del self.mesh_sha[part]
            out.setdefault("meshes_reverted", []).append(part)

    def update_meshes(self, meshes, out):
        """changed or new part geometry: import the part GLB into its own folder /parts_live/<part>_<sha8>, then point
        every HISM that shows the part at the new mesh (instances, indices and material overrides stay). The batch's
        original asset is left as it is; HISM keys keep the original mesh path (keypath alias).
        #28: a GLB that is not imported yet is imported asynchronously, so the editor keeps running (19 new towers held
        the live editor 135 s before). Until its mesh is there a changed part keeps showing its old mesh and the
        instances of a new part wait ("waiting_mesh" in counts); the receipt lists the part in "pending_meshes" and says
        "complete": false. finish_imports() (control tick) switches the HISMs and applies the file again, which writes
        the complete receipt. sync_import (attach option, tests) imports in place as before."""
        meshes = meshes or {}
        for part in [p for p in self.pending if p not in meshes]:
            del self.pending[part]                  # left the file before its import finished
        for part, info in meshes.items():
            glb = Path(info["glb"])
            want = info.get("sha256")
            if want and self.mesh_sha.get(part) == want:
                continue
            if want and self.pending.get(part, {}).get("sha") == want:
                out.setdefault("pending_meshes", []).append(part)
                continue
            got = sha_file(glb)
            if want and got != want:
                out.setdefault("errors", []).append(f"mesh {part}: sha {got[:12]} != {want[:12]} (file still being written?)")
                continue
            gm = glb_materials(glb)
            textured = {_norm(n) for n, tex in gm.items() if tex}
            self.textured_now = textured
            need_mats = self.needs_glb_materials(list(gm), self.meshes.get(part.lower()))
            # R3: preview assets apart, never in a batch folder. One folder per part, GLB content and material choice,
            # shared by every batch: the north slope (10-10) sent the same part to three batches, imported three times
            folder = f"{LIVE_ROOT}/_parts/{part}_{got[:8]}{'_m' if need_mats else ''}"
            job = {"folder": folder, "sha": got, "textured": textured, "need_mats": need_mats}
            rec = _ASYNC.get(folder)
            if rec is not None and rec["state"] == "failed":
                if time.time() - rec["done_t"] < 60:
                    out.setdefault("errors", []).append(f"mesh {part}: import failed: {rec.get('error')}")
                    continue
                rec = None                          # try again, at most once a minute
                del _ASYNC[folder]
            if rec is None:
                t = time.time()
                if EAL.does_directory_exist(folder) and any(
                        isinstance(unreal.load_asset(p), unreal.StaticMesh)
                        for p in EAL.list_assets(folder, recursive=True, include_folder=False)):
                    self.finish_mesh(part, job, out, {"start_t": t})       # imported earlier (reset, re-attach)
                    continue
                if self.sync_import:
                    interchange_mesh(glb, folder, materials=need_mats)
                    self.finish_mesh(part, job, out, {"start_t": t})
                    continue
                rec = _ASYNC[folder] = {"state": "queued", "queued_t": t, "glb": str(glb), "folder": folder,
                                        "need_mats": need_mats, "part": part}
            if rec["state"] == "done":
                self.finish_mesh(part, job, out, rec)
                continue
            self.pending[part] = job
            out.setdefault("pending_meshes", []).append(part)
        _pump_imports()

    def finish_imports(self):
        """#28, control tick: parts whose import has finished get their mesh, then the last override is applied again
        (instances that waited appear) -> the receipt to write, or None when nothing finished."""
        ready = [p for p, j in self.pending.items() if _ASYNC.get(j["folder"], {}).get("state") in ("done", "failed")]
        if not ready or self.last_ov is None:
            return None
        out = {}
        for part in ready:
            job = self.pending.pop(part)
            rec = _ASYNC[job["folder"]]
            rec.pop("keep", None)
            if rec["state"] == "done":
                self.finish_mesh(part, job, out, rec)
            # failed: apply() below reports it once (update_meshes sees the failed record)
        res = self.apply(self.last_ov)
        res["meshes"] = out.get("meshes", []) + res.get("meshes", [])
        if out.get("errors"):
            res["errors"] = out["errors"] + res.get("errors", [])
        return res

    def finish_mesh(self, part, job, out, timing):
        """the imported mesh in job["folder"] becomes the part's mesh: every HISM that showed the part switches to it."""
        found = [unreal.load_asset(p) for p in EAL.list_assets(job["folder"], recursive=True, include_folder=False)]
        sms = [a for a in found if isinstance(a, unreal.StaticMesh)]
        new = next((a for a in sms if a.get_name().lower() == part.lower()), sms[0] if len(sms) == 1 else None)
        if new is None:
            out.setdefault("errors", []).append(f"mesh {part}: {len(sms)} static meshes in {job['folder']}, none named {part}")
            return
        textured, need_mats, got = job["textured"], job["need_mats"], job["sha"]
        if not hasattr(self, "textured_by_mesh"):
            self.textured_by_mesh = {}
        self.textured_by_mesh[new.get_path_name()] = textured
        old = self.meshes.get(part.lower())
        if old is not None and part not in self.mesh_orig:
            self.mesh_orig[part] = old
        swapped, slots = 0, None
        if old:
            op = old.get_path_name()
            for c in self.comps.values():
                m = c.get_editor_property("static_mesh")
                if m and m.get_path_name() == op:
                    slots = self.carry_materials(c, m, new)
                    swapped += 1
            self.keypath[new.get_path_name()] = self.keypath.get(op, op)
        self.meshes[part.lower()] = new
        self.mesh_sha[part] = got
        tri = new.get_num_triangles(0) if hasattr(new, "get_num_triangles") else None
        row = {"part": part, "new_part": old is None, "hism_switched": swapped, "glb_materials": need_mats,
               "slots": slots if old else None, "asset": new.get_path_name(), "triangles": tri}
        if timing.get("done_t"):                    # asynchronous: time in the queue and in Interchange
            row.update(queued_s=round(timing["start_t"] - timing["queued_t"], 2),
                       import_s=round(timing["done_t"] - timing["start_t"], 2))
        else:
            row["seconds"] = round(time.time() - timing["start_t"], 2)
        out.setdefault("meshes", []).append(row)

    def key_for(self, st):
        """the HISM (comps key) an instance in state st belongs in, created if needed."""
        mesh = self.mesh_for(st["part"], fallback=True)
        if mesh is None:
            if any(p.lower() == st["part"].lower() for p in self.pending):
                raise MeshPending(st["part"])
            raise KeyError(f"part {st['part']} has no mesh in {self.dest}/parts (send it in 'meshes')")
        return self.comp_for(st["era"], mesh)

    def trim(self):
        """back at the table: drop what the preview added, so a later save holds nothing of it - instances appended to a
        HISM (only the tail, earlier indices never move) and HISMs the preview created. Returns what was removed."""
        out = {}
        for key, c in list(self.comps.items()):
            n0 = self.orig_count.get(key)
            if n0 is None:                          # a HISM made by the preview (new part / era / slot)
                c.clear_instances()
                try:
                    c.destroy_component(c)
                except Exception:
                    pass
                del self.comps[key]
                out["hism_removed"] = out.get("hism_removed", 0) + 1
                continue
            n = c.get_instance_count()
            if n > n0:
                c.remove_instances(list(range(n0, n)))
                out["instances_removed"] = out.get("instances_removed", 0) + n - n0
        self.free, self.slot = {}, dict(self.home)
        self.unmapped = set()                       # nothing of the preview is shown any more
        if hasattr(self, "slot_comp"):
            self.slot_comp = {k: v for k, v in self.slot_comp.items() if v in self.comps}
        return out

    def place(self, iid, st):
        """move instance iid to state st (None = remove an added one, deleted = hide)."""
        cur = self.slot.get(iid)
        if st is None or st["deleted"]:
            if cur:
                key, idx = cur
                self.comps[key].update_instance_transform(idx, ue_xf(self.base.get(iid) or self.applied[iid], True), True, True, True)
                if cur != self.home.get(iid):
                    self.free.setdefault(key, []).append(idx)
                    del self.slot[iid]
            return "hidden"
        key = self.key_for(st)
        if cur and cur[0] == key:
            self.comps[key].update_instance_transform(cur[1], ue_xf(st), True, True, True)
            return "moved"
        if cur:                                     # part swap: hide the old slot
            okey, oidx = cur
            self.comps[okey].update_instance_transform(oidx, ue_xf(st, True), True, True, True)
            if cur != self.home.get(iid):
                self.free.setdefault(okey, []).append(oidx)
        home = self.home.get(iid)
        if home and home[0] == key:
            idx = home[1]
            self.comps[key].update_instance_transform(idx, ue_xf(st), True, True, True)
        elif self.free.get(key):
            idx = self.free[key].pop()
            self.comps[key].update_instance_transform(idx, ue_xf(st), True, True, True)
        else:
            idx = self.comps[key].add_instance(ue_xf(st), True)
        self.slot[iid] = (key, idx)
        return "swapped" if cur else "added"

    def apply(self, ov):
        t0 = time.time()
        out = {"rev": ov.get("rev"), "written": ov.get("written")}
        if ov.get("base_sha256") and self.base_sha and ov["base_sha256"] != self.base_sha:
            raise ValueError(f"override base {ov['base_sha256'][:12]} != loaded table {self.base_sha[:12]}")
        self.last_ov = ov
        self.revert_meshes(set(ov.get("meshes") or {}), out)
        self.update_meshes(ov.get("meshes"), out)
        new = {}
        for iid, d in (ov.get("instances") or {}).items():
            b = self.base.get(iid)
            merged = dict({"part": b["part"], "era": b["era"], "pos": b["pos"], "quat_wxyz": b["quat"], "scale": b["scale"]} if b else {}, **d)
            new[iid] = norm_state(merged)
        counts, touched, waiting = {}, [], set()
        for iid in set(self.applied) | set(new):
            want = new.get(iid) or self.base.get(iid)   # dropped from the file: back to the table (or gone if it was new)
            have = self.applied.get(iid) or self.base.get(iid)
            if same(want, have) and (want is None or iid in self.slot or want["deleted"]):
                continue
            try:
                r = self.place(iid, want)
                counts[r] = counts.get(r, 0) + 1
                if r in ("moved", "added", "swapped"):
                    touched.append(iid)
                foreign = getattr(self, "foreign", None)
                if foreign and iid in foreign:      # the override wins over a change made in UE: say so
                    foreign.discard(iid)
                    out.setdefault("overrode_ue_changes", []).append(iid)
            except MeshPending:                     # #28: placed by finish_imports() once its mesh is imported
                waiting.add(iid)
                counts["waiting_mesh"] = counts.get("waiting_mesh", 0) + 1
            except Exception as exc:
                out.setdefault("errors", []).append(f"{iid}: {exc}")
        # a waiting instance still shows what it showed before, so that is what counts as applied
        prev = self.applied
        self.applied = {k: v for k, v in new.items() if k not in waiting}
        self.applied.update({k: prev[k] for k in waiting if k in prev})
        self.rev = ov.get("rev")
        if not self.applied and not self.mesh_sha:
            trimmed = self.trim()
            if trimmed:
                out["trimmed"] = trimmed
        out["save_guard"] = reguard()
        if touched and not S.get("suspended"):
            c = conflicts(self, touched)
            if c:
                out["conflicts"] = c
        if self.unmapped:
            out["unmapped_slots"] = sorted(self.unmapped)
        out.update(counts=counts, overrides=len(new), seconds=round(time.time() - t0, 3),
                   complete=not self.pending)       # false: meshes still importing, a complete receipt follows
        return out


def level_file(actor):
    """the .umap on disk that holds this actor (persistent level or streamed sublevel), or None."""
    try:
        world_path = actor.get_outer().get_outer().get_path_name().split(".")[0]      # /Game/Inst/x/L_x
    except Exception:
        return None
    if not world_path.startswith("/Game/"):
        return None
    f = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())) / (world_path[6:] + ".umap")
    return str(f.resolve()) if f.exists() else None


def _guard_state():
    try:
        return json.loads(GUARD.read_text(encoding="utf-8"))
    except Exception:
        return {}


def guard(files, on):
    """make the files read-only (on) or give back the mode they had before (off). Returns the files now guarded."""
    st = _guard_state()
    for f in files:
        if on and f not in st:
            mode = os.stat(f).st_mode & 0o7777
            st[f] = mode
            os.chmod(f, mode & ~0o222)
        elif not on and f in st:
            os.chmod(f, st.pop(f))
    GUARD.write_text(json.dumps(st, indent=1), encoding="utf-8")
    return sorted(k for k in st if k in files)


def reguard():
    """level files read-only exactly while some attached batch in them differs from its table (and not suspended)."""
    want, every = set(), set()
    for b in S["batches"].values():
        every |= set(b.level_files)
        if (b.applied or b.mesh_sha) and not S.get("suspended"):
            want |= set(b.level_files)
    guard(sorted(want), True)
    guard(sorted((every | set(_guard_state())) - want), False)
    return sorted(want)


class VegBatch(Batch):
    """engineering's vegetation placements (renou-placements/1; src = an abstract slot such as tree_broadleaf_A; no parts
    GLB) on the VEG_<veg>_<era> actors ct_vegplace builds (one HISM per era and slot). The build may have cropped the
    file to discs, or instances may have been cleared since (lk_vegclear), so instances are found by position.
    REQUEST {"kind": "veg", "placements": "/abs/veg_<region>_<era>_placements.json", "veg": "S02" (VEG_<veg>_*)}
    Override files use the table's batch name (veg_peninsula_present ...); "part" of a new instance = its slot.
    The slot -> mesh mapping stays with UE: Blender never sends vegetation meshes ("meshes" is ignored here)."""

    def __init__(self, req):
        t0 = time.time()
        self.placements = Path(req["placements"])
        self.data = json.loads(self.placements.read_text(encoding="utf-8-sig"))
        assert self.data.get("schema") == "renou-placements/1", self.data.get("schema")
        assert self.data.get("coord") == "blender_zup_m", self.data.get("coord")
        self.base_sha = sha_file(self.placements)
        self.veg = req["veg"]
        self.name = req.get("name") or self.data["batch"]
        self.dest = f"{LIVE_ROOT}/{self.name}"
        self.prefer = ["NEAR"]
        self.slot_table_path, self.slot_table, self.slot_table_norm = None, {}, {}
        self.unmapped = set()
        self.hosts, self.comps = {}, {}
        for a in EAS.get_all_level_actors():
            if f"VEG_{self.veg}" in [str(t) for t in a.tags]:
                self.hosts[a.get_actor_label().rsplit("_", 1)[-1]] = a
                for c in a.get_components_by_class(unreal.HierarchicalInstancedStaticMeshComponent):
                    self.comps[c.get_path_name()] = c
        assert self.hosts, f"no VEG_{self.veg}_* actors in the open level"
        index = {}
        for key, c in self.comps.items():
            for i in range(c.get_instance_count()):
                t = c.get_instance_transform(i, True).translation
                index[(round(t.x), round(t.y), round(t.z))] = (key, i)
        default_era = self.data.get("era", "both")
        self.base, self.home, votes = {}, {}, {}
        missing, bad, worst, checked = 0, 0, 0.0, 0
        near = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)]
        for n, inst in enumerate(self.data.get("instances", [])):
            st = norm_state(dict(inst, part=inst["src"], era=inst.get("era") or default_era))
            self.base[inst["id"]] = st
            x, y, z = st["pos"]
            k = (round(x * 100), round(-y * 100), round(z * 100))
            hit = index.get(k)
            if hit is None:
                hit = next((index[(k[0] + a, k[1] + b, k[2] + c)] for a, b, c in near
                            if (k[0] + a, k[1] + b, k[2] + c) in index), None)
            if hit is None:
                missing += 1                        # cropped away or cleared in UE: nothing of it is shown
                continue
            self.home[inst["id"]] = hit
            v = votes.setdefault((st["era"], st["part"]), {})
            v[hit[0]] = v.get(hit[0], 0) + 1
            if n % 25 == 0:                         # full transform check on a sample
                e = xf_err(self.comps[hit[0]].get_instance_transform(hit[1], True), st)
                worst, bad, checked = max(worst, e), bad + (e > 1.0), checked + 1
        self.slot_comp = {es: max(v, key=v.get) for es, v in votes.items()}
        self.meshes = {}
        for (era, slot), key in self.slot_comp.items():
            self.meshes.setdefault(slot.lower(), self.comps[key].get_editor_property("static_mesh"))
        self.slot = dict(self.home)
        self.orig_count = {k: c.get_instance_count() for k, c in self.comps.items()}
        self.free, self.applied, self.rev, self.mesh_sha, self.keypath, self.mesh_orig = {}, {}, None, {}, {}, {}
        self.pending, self.last_ov = {}, None
        self.level_files = sorted({level_file(a) for a in self.hosts.values()} - {None})
        self.report = {"batch": self.data.get("batch"), "kind": "veg", "veg": self.veg, "instances": len(self.base),
                       "matched": len(self.home), "not_in_level": missing, "hism": len(self.comps),
                       "slots": {f"{e}/{sl}": self.comps[k].get_editor_property("static_mesh").get_name()
                                 for (e, sl), k in sorted(self.slot_comp.items())},
                       "verify_checked": checked, "verify_bad": bad, "verify_worst_cm": round(worst, 3),
                       "level_files": self.level_files, "seconds": round(time.time() - t0, 2)}
        assert bad == 0, f"vegetation in the level does not match the table: {self.report}"

    def mesh_for(self, part, lods=None, fallback=False):
        return self.meshes.get(part.lower())

    def key_for(self, st):
        key = self.slot_comp.get((st["era"], st["part"]))
        if key is not None:
            return key
        mesh = self.mesh_for(st["part"])
        if mesh is None:
            raise KeyError(f"slot {st['part']} has no mesh in UE yet (UE maps slots to meshes in ct_vegplace)")
        before = set(self.comps)
        key = self.comp_for(st["era"], mesh)        # new HISM on VEG_<veg>_<era>, cull distances as ct_vegplace
        if key not in before:
            lo, hi = (250, 400) if st["part"].startswith("shrub") else (1200, 1800)
            self.comps[key].set_editor_property("instance_start_cull_distance", int(lo * 100))
            self.comps[key].set_editor_property("instance_end_cull_distance", int(hi * 100))
        self.slot_comp[(st["era"], st["part"])] = key
        return key

    def update_meshes(self, meshes, out):
        if meshes:
            out.setdefault("errors", []).append("vegetation batches take no meshes (slot -> mesh is UE's)")

    def revert_meshes(self, keep, out):
        pass


_NOT_HAND = ("CITY_INST", "CITY_VEG", "CITY_IMPORT", "CITY_ERA_")
_NOT_HAND_CLS = ("Landscape", "WorldSettings", "Brush", "Light", "SkyLight", "DirectionalLight", "SkyAtmosphere",
                 "ExponentialHeightFog", "PostProcessVolume", "VolumetricCloud", "CineCameraActor", "CameraActor",
                 "WaterBody", "WaterZone", "InstancedFoliageActor", "LevelBounds", "NavigationData", "PlayerStart")


def _hand_candidates():
    """actors nobody syncs (props, decals, hand-placed meshes) with their world AABB, cached for 60 s."""
    c = S.get("hand")
    if c and time.monotonic() - c["t"] < 60:
        return c["rows"]
    hosts = {a.get_path_name() for b in S["batches"].values() for a in b.hosts.values()}
    rows = []
    for a in EAS.get_all_level_actors():
        if a.get_path_name() in hosts:
            continue
        if any(str(t).startswith(_NOT_HAND) for t in a.tags):
            continue
        cls = a.get_class().get_name()
        if cls.startswith(_NOT_HAND_CLS) or not (a.get_components_by_class(unreal.StaticMeshComponent)
                                                 or a.get_components_by_class(unreal.DecalComponent)):
            continue
        o, e = a.get_actor_bounds(False)
        if max(e.x, e.y, e.z) > 50000:             # > 1 km across: a landscape-like actor, not a hand-placed piece
            continue
        rows.append((a, (o.x - e.x, o.y - e.y, o.z - e.z), (o.x + e.x, o.y + e.y, o.z + e.z)))
    S["hand"] = {"t": time.monotonic(), "rows": rows}
    return rows


def conflicts(b, ids, limit=50):
    """#16: hand-placed actors whose bounds overlap an instance that was just moved / added / swapped (report only)."""
    out = []
    rows = _hand_candidates()
    for iid in ids:
        key_idx = b.slot.get(iid)
        if not key_idx:
            continue
        comp = b.comps[key_idx[0]]
        mesh = comp.get_editor_property("static_mesh")
        if mesh is None:
            continue
        bb = mesh.get_bounding_box()
        t = comp.get_instance_transform(key_idx[1], True)
        pts = [t.transform_location(unreal.Vector(x, y, z)) for x in (bb.min.x, bb.max.x)
               for y in (bb.min.y, bb.max.y) for z in (bb.min.z, bb.max.z)]
        lo = (min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))
        hi = (max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))
        for a, alo, ahi in rows:
            ov = [min(hi[i], ahi[i]) - max(lo[i], alo[i]) for i in range(3)]
            if min(ov) > 0:
                out.append({"inst": iid, "actor": a.get_actor_label(),
                            "level": a.get_outer().get_outer().get_path_name().split(".")[0],
                            "overlap_m": [round(v / 100, 1) for v in ov]})
                if len(out) >= limit:
                    return out
    return out


class GroundBatch(Batch):
    """#18: ground tiles (scene-imported actors <tile>_LOD0 in a ground layer such as /Game/Inst/ground_core, tagged
    INST_<name> and CITY_INST_GROUND) are no HISM instances: a tile changes as a whole. The override's "meshes" maps
    tile ids (the actor label without _LOD<n>, e.g. CITY_T_3_-2) to one-tile GLBs; the tile's StaticMeshComponent is
    switched in place, every slot keeps UE's material by the usual rule (terrain slots keep MI_CT_Terrain). No
    instances, so positions never change; a tile that leaves "meshes" gets its release mesh back.
    REQUEST {"kind": "ground", "name": "ground_core", "batch": "ground_core" (override files' batch name)}"""

    def __init__(self, req):
        t0 = time.time()
        self.name = req["name"]
        self.data = {"batch": req.get("batch", self.name), "instances": []}
        self.placements, self.base_sha = None, None
        self.dest = f"{LIVE_ROOT}/{self.name}"
        self.prefer = ["NEAR"]
        self.slot_table_path, self.slot_table, self.slot_table_norm = load_slot_table(req.get("slot_table"))
        self.unmapped = set()
        self.tiles, self.hosts = {}, {}
        for a in EAS.get_all_level_actors():
            if f"INST_{self.name}" not in [str(t) for t in a.tags]:
                continue
            for c in a.get_components_by_class(unreal.StaticMeshComponent):
                m = c.get_editor_property("static_mesh")
                if m is not None:
                    tid = re.sub(r"_LOD\d+$", "", a.get_actor_label())
                    self.tiles[tid] = (a, c, m)
                    self.hosts[tid] = a
        assert self.tiles, f"no INST_{self.name} ground actors in the open level"
        self.comps, self.base, self.home, self.slot, self.free, self.applied = {}, {}, {}, {}, {}, {}
        self.rev, self.mesh_sha, self.keypath, self.mesh_orig, self.orig_count = None, {}, {}, {}, {}
        self.pending, self.last_ov = {}, None      # ground tiles are still imported in place (one tile at a time)
        self.meshes = {}
        self.level_files = sorted({level_file(a) for a, _c, _m in self.tiles.values()} - {None})
        self.report = {"batch": self.data["batch"], "kind": "ground", "tiles": len(self.tiles),
                       "level_files": self.level_files, "seconds": round(time.time() - t0, 2)}

    def update_meshes(self, meshes, out):
        for tid, info in (meshes or {}).items():
            if tid not in self.tiles:
                out.setdefault("errors", []).append(f"tile {tid}: no such ground actor in {self.name}")
                continue
            glb = Path(info["glb"])
            want = info.get("sha256")
            if want and self.mesh_sha.get(tid) == want:
                continue
            got = sha_file(glb)
            if want and got != want:
                out.setdefault("errors", []).append(f"tile {tid}: sha {got[:12]} != {want[:12]} (file still being written?)")
                continue
            t = time.time()
            a, comp, orig = self.tiles[tid]
            cur = comp.get_editor_property("static_mesh")
            folder = f"{LIVE_ROOT}/{self.name}/{tid}_{got[:8]}"
            gm = glb_materials(glb)
            textured = {_norm(n) for n, tex in gm.items() if tex}
            self.textured_now = textured
            need = self.needs_glb_materials(list(gm), cur)
            found = []
            if EAL.does_directory_exist(folder):
                found = [unreal.load_asset(p) for p in EAL.list_assets(folder, recursive=True, include_folder=False)]
            if not any(isinstance(x, unreal.StaticMesh) for x in found):
                interchange_mesh(glb, folder, materials=need)
                found = [unreal.load_asset(p) for p in EAL.list_assets(folder, recursive=True, include_folder=False)]
            sms = [x for x in found if isinstance(x, unreal.StaticMesh)]
            if len(sms) != 1:
                out.setdefault("errors", []).append(f"tile {tid}: {len(sms)} static meshes in {glb.name}, need exactly 1 (LOD0 only)")
                continue
            if not hasattr(self, "textured_by_mesh"):
                self.textured_by_mesh = {}
            self.textured_by_mesh[sms[0].get_path_name()] = textured
            slots = self.carry_materials(comp, cur, sms[0])
            self.mesh_sha[tid] = got
            out.setdefault("meshes", []).append({"tile": tid, "glb_materials": need, "slots": slots,
                                                  "triangles": sms[0].get_num_triangles(0), "seconds": round(time.time() - t, 2)})

    def revert_meshes(self, keep, out):
        for tid in [k for k in self.mesh_sha if k not in keep]:
            a, comp, orig = self.tiles[tid]
            self.carry_materials(comp, comp.get_editor_property("static_mesh"), orig)
            del self.mesh_sha[tid]
            out.setdefault("meshes_reverted", []).append(tid)


def remap(name=None):
    """视效 extended the slot table or the rules: every slot that shows the placeholder is resolved again (table, then
    the formal mi_path, then UE's material by name). Nothing else changes; no import, no flicker."""
    out = {}
    ph = PLACEHOLDER.split(".")[0]
    for n, b in S["batches"].items():
        if name and n != name:
            continue
        b.slot_table_path, b.slot_table, b.slot_table_norm = load_slot_table()
        _MI.clear()
        b.unmapped = set()
        comps = list(b.comps.values()) + [c for _a, c, _m in getattr(b, "tiles", {}).values()]
        fixed = 0
        for c in comps:
            mesh = c.get_editor_property("static_mesh")
            if mesh is None:
                continue
            b.textured_now = getattr(b, "textured_by_mesh", {}).get(mesh.get_path_name(), set())
            for j, slot in enumerate(slot_names(mesh)):
                cur = c.get_material(j)
                if cur is None or cur.get_path_name().split(".")[0] != ph:
                    continue
                m, how = b.ue_material(slot)
                if m is None and how in ("keep", "keep_textured"):
                    m = mesh.get_material(j)
                if m is not None and m.get_path_name().split(".")[0] != ph:
                    c.set_material(j, m)
                    fixed += 1
        out[n] = {"slots_fixed": fixed, "still_unmapped": sorted(b.unmapped), "slot_table": b.slot_table_path}
    return out


def suspend():
    """before UE saves: every preview goes back to its table for a moment (files writable). Nothing is lost - override
    files are cumulative and resume() simply reads them again."""
    S["suspended"] = True
    out = {n: b.apply({"rev": "suspended", "instances": {}, "meshes": {}}) for n, b in S["batches"].items()}
    out["save_guard"] = reguard()
    return out


def resume():
    S["suspended"] = False
    if S.get("watch"):
        S["watch"]["sig"] = {}                      # next tick applies every watched file again
    return {"resumed": True, "watching": (S.get("watch") or {}).get("paths")}


SESSION = CTRL / "session.json"


def _session():
    try:
        return json.loads(SESSION.read_text(encoding="utf-8"))
    except Exception:
        return {"attach": [], "watch": None}


def _save_session(sess):
    SESSION.with_suffix(".tmp").write_text(json.dumps(sess, ensure_ascii=False, indent=1), encoding="utf-8")
    SESSION.with_suffix(".tmp").replace(SESSION)


def restore():
    """after an editor restart: attach every batch of the session file again and watch its files (the override files
    are cumulative, so the preview comes back as it was). Batches that fail are reported and kept in the file."""
    sess, out = _session(), {"attached": {}, "failed": {}, "already": []}
    for req in sess.get("attach", []):
        key = req.get("name") or req.get("placements")
        if key in S["batches"]:                 # restore twice (视效's start script + a manual one): keep what runs
            out["already"].append(key)
            continue
        try:
            out["attached"][key] = attach(req, remember=False)
        except Exception as exc:
            out["failed"][key] = str(exc)[:300]
    w = sess.get("watch")
    if w and w.get("paths"):
        out["watch"] = watch(w["paths"], w.get("interval", 0.2), remember=False)
    return out


def attach(req, remember=True):
    """a batch that is attached already is reset first and replaced: a second Batch object over a layer the first one
    changed would take the preview's added instances for table rows (and never trim them)."""
    kinds = {"veg": VegBatch, "ground": GroundBatch}
    again = req.get("name") in S["batches"]
    if again:
        reset(req["name"])
        del S["batches"][req["name"]]
    b = kinds.get(req.get("kind"), Batch)(req)
    if again and S.get("watch"):
        S["watch"]["sig"] = {}                      # the watched files are applied again to the new object
    if remember:
        sess = _session()
        keep = {k: v for k, v in req.items() if k not in ("id", "script", "action")}
        sess["attach"] = [r for r in sess.get("attach", []) if (r.get("name") or r.get("placements")) != b.name] + [keep]
        _save_session(sess)
    S["batches"][b.name] = b
    log(f"attached {b.name}: {b.report}")
    return b.report


ARCHIVE_KEEP = 50    # = renou_blsync_lib.ARCHIVE_KEEP


def replace_risk(old, new):
    """= renou_blsync_lib.replace_risk (user 10-10): why replacing override document old by new could lose work."""
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


def _archive_dirs(path):
    return [Path(path).parent / "archive", CTRL / "archive"]     # the second when the first is not writable


def snapshot_raw(path, raw, reason):
    """keep the bytes of the override file bl_sync applied last, before a version that shrinks or replaces it is applied
    (whoever wrote it: the add-on keeps its own copies, scripts may not). Same naming and rotation as
    renou_blsync_lib.snapshot_file: archive/<stem>__<yyyymmdd-hhmmss-mmm>__rev<rev>__<reason>.json, a copy identical to
    the newest one is not made again, the newest ARCHIVE_KEEP stay. Returns the snapshot path or None."""
    p = Path(path)
    for d in _archive_dirs(path):
        try:
            d.mkdir(parents=True, exist_ok=True)
            olds = sorted(d.glob(f"{p.stem}__*.json"))
            if olds and olds[-1].read_bytes() == raw:
                return str(olds[-1])
            try:
                rev = json.loads(raw.decode("utf-8-sig")).get("rev")
            except Exception:
                rev = "unreadable"
            t = time.time()
            stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + f"-{int(t * 1000) % 1000:03d}"
            why = re.sub(r"[^0-9A-Za-z_-]+", "-", str(reason))[:40]
            snap = d / f"{p.stem}__{stamp}__rev{rev}__{why}.json"
            snap.with_suffix(".tmp").write_bytes(raw)
            snap.with_suffix(".tmp").replace(snap)
            for old in sorted(d.glob(f"{p.stem}__*.json"))[:-ARCHIVE_KEEP]:
                old.unlink()
            return str(snap)
        except OSError:
            continue
    return None


def latest_snapshot(path):
    p, best = Path(path), None
    for d in _archive_dirs(path):
        fs = sorted(d.glob(f"{p.stem}__*.json")) if d.exists() else []
        if fs and (best is None or fs[-1].name > best.name):
            best = fs[-1]
    return str(best) if best else None


def apply_file(path, name=None):
    raw = Path(path).read_bytes()
    ov = json.loads(raw.decode("utf-8-sig"))
    assert ov.get("schema") == "renou-overrides/1", ov.get("schema")
    b = S["batches"].get(name) if name else next((x for x in S["batches"].values() if x.data.get("batch") == ov.get("batch")), None)
    assert b is not None, f"batch {ov.get('batch')} not attached"
    prev, why = getattr(b, "file_prev", None), None
    if prev and prev[0] == str(path):
        why = replace_risk(prev[2], ov)
        if why:
            snapshot_raw(path, prev[1], why)
    out = b.apply(ov)
    b.file_prev = (str(path), raw, ov)
    if why:
        out["snapshot_made"] = why
    return _receipt(b, out)


def _receipt(b, out):
    if getattr(b, "file_prev", None):
        out["snapshot"] = latest_snapshot(b.file_prev[0])     # user 10-10: the receipt names the newest copy
    out["applied_at"] = time.time()
    if out.get("written"):
        out["latency_s"] = round(out["applied_at"] - float(out["written"]), 3)
    body = json.dumps(out, ensure_ascii=False)
    (CTRL / "status.tmp").write_text(body, encoding="utf-8")
    (CTRL / "status.tmp").replace(CTRL / "status.json")      # the last receipt of any batch (kept for old readers)
    one = CTRL / f"status_{b.data.get('batch') or b.name}.json"   # one receipt per batch: two writers never mix receipts
    one.with_suffix(".tmp").write_text(body, encoding="utf-8")
    one.with_suffix(".tmp").replace(one)
    return out


def _imports_tick():
    """#28: start queued imports; the first batch with a finished import switches its meshes and writes its receipt
    (one batch per tick)."""
    if not _ASYNC or S.get("suspended"):
        return
    _pump_imports()
    for b in list(S["batches"].values()):
        if not b.pending:
            continue
        S["busy"] = True
        try:
            out = b.finish_imports()
            if out is not None:
                _receipt(b, out)
                log(f"meshes in for {b.name} rev {out.get('rev')}: {[m.get('part') for m in out.get('meshes', [])]} "
                    f"{out.get('counts')} pending {out.get('pending_meshes')}")
                return
        except Exception:
            err = traceback.format_exc()
            unreal.log_error("[BLSYNC] " + err)
            b.pending.clear()                       # never retry a broken finish every tick; the next file change does
        finally:
            S["busy"] = False


def _sig(path):
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _watch_tick(dt):
    w = S["watch"]
    if not w or S.get("suspended") or S.get("busy") or time.monotonic() < w["next"]:
        return                                   # never inside another apply / control request (imports pump ticks)
    w["next"] = time.monotonic() + w["interval"]
    for path in w["paths"]:
        sig = _sig(path)
        if sig is None or w["sig"].get(path) == sig:
            continue
        S["busy"] = True
        try:
            out = apply_file(path)
            log(f"applied {Path(path).name} rev {out.get('rev')}: {out.get('counts')} in {out.get('seconds')} s")
        except Exception:
            err = traceback.format_exc()
            unreal.log_error("[BLSYNC] " + err)
            (CTRL / "status.json").write_text(json.dumps({"error": err, "file": path, "t": time.time()}), encoding="utf-8")
        finally:
            S["busy"] = False
        # the file read is the one applied; if it changed meanwhile, the next tick sees a new signature and applies it
        w["sig"][path] = sig
        return                                   # one file per tick: the editor gets a frame between applies


def watch(paths, interval=0.2, remember=True):
    unwatch(remember=False)
    if remember:
        sess = _session()
        sess["watch"] = {"paths": [str(p) for p in paths], "interval": float(interval)}
        _save_session(sess)
    S["watch"] = {"paths": [str(p) for p in paths], "sig": {}, "next": 0.0, "interval": float(interval)}
    S["watch"]["handle"] = unreal.register_slate_post_tick_callback(_watch_tick)
    return {"watching": S["watch"]["paths"], "interval": interval}


def unwatch(remember=True):
    if remember:
        sess = _session()
        sess["watch"] = None
        _save_session(sess)
    w = S.get("watch")
    if w and w.get("handle"):
        unreal.unregister_slate_post_tick_callback(w["handle"])
    S["watch"] = None
    return {"watching": []}


def reset(name):
    """everything back to the base table (an empty override): positions, parts and live meshes; files writable again."""
    b = S["batches"][name]
    return b.apply({"rev": "reset", "instances": {}, "meshes": {}})


def reapply(name=None):
    """every instance the last override names is placed again, even if bl_sync thinks it already shows that state -
    for after another tool moved instances of a batch layer in UE (视效 10-09: lk_ns_hide restore brought back two
    buildings the override deletes). Instances the override does not name are not touched. Writes the receipt."""
    out = {}
    for n, b in S["batches"].items():
        if (name and n != name) or b.last_ov is None:
            continue
        keep = b.applied
        b.applied = {}                              # nothing counts as shown: apply() places every listed instance
        try:
            out[n] = _receipt(b, b.apply(b.last_ov))
        except Exception:
            b.applied = keep
            raise
    return out


def detach(name=None, forget=True):
    """stop watching, reset every attached batch (or one), give all guarded files their mode back, forget the batch
    (also in the session file: a later restore will not bring it back). forget=False (code reload): the session file
    is kept, so restore() right after brings everything back."""
    if forget:
        sess = _session()
        sess["attach"] = [r for r in sess.get("attach", []) if name and (r.get("name") or r.get("placements")) != name]
        if not name:
            sess["watch"] = None
        _save_session(sess)
    if not name:
        unwatch(remember=False)                   # one batch: the others keep being watched
    out = {}
    for n in ([name] if name else list(S["batches"])):
        if n in S["batches"]:
            out[n] = reset(n)
            del S["batches"][n]
    if name:
        out["save_guard"] = reguard()             # only what the remaining batches still need
        return out
    left = _guard_state()
    guard(list(left), False)                      # also files guarded by an earlier editor session
    S["suspended"] = False
    out["unguarded"] = sorted(left)
    return out


def _txt(v):
    """stable text of a value (UE structs print their memory address with str())."""
    try:
        return v.export_text()
    except Exception:
        return repr(round(v, 6)) if isinstance(v, float) else str(v)


def fingerprint():
    """R2 check: what UE owns, before and after a sync must be identical. Counts and key values of lights, sky, fog,
    post, clouds, water, foliage / grass, cameras, plus a hash of the materials on every HISM slot NOT touched by bl_sync."""
    out, rows = {}, []
    keys = {"DirectionalLight": ("DirectionalLightComponent", ["intensity", "light_color", "temperature"]),
            "SkyLight": ("SkyLightComponent", ["intensity"]), "SkyAtmosphere": ("SkyAtmosphereComponent", ["mie_scattering_scale"]),
            "ExponentialHeightFog": ("ExponentialHeightFogComponent", ["fog_density", "fog_height_falloff"]),
            "PostProcessVolume": (None, ["blend_weight"]), "VolumetricCloud": ("VolumetricCloudComponent", ["layer_bottom_altitude"]),
            "CineCameraActor": (None, []), "InstancedFoliageActor": (None, []), "WaterBody": (None, []), "Landscape": (None, [])}
    touched = set()
    for b in S["batches"].values():
        touched |= {c.get_path_name() for c in b.comps.values()}
    nmat = 0
    for a in EAS.get_all_level_actors():
        cls = a.get_class().get_name()
        k = next((x for x in keys if cls.startswith(x)), None)
        if k is not None:
            out[k] = out.get(k, 0) + 1
            comp_name, props = keys[k]
            obj = a.get_component_by_class(getattr(unreal, comp_name)) if comp_name else a
            vals = []
            for pr in props:
                try:
                    vals.append(_txt(obj.get_editor_property(pr)))
                except Exception:
                    pass
            t = a.get_actor_transform()
            rows.append(f"{a.get_path_name()}|{_txt(t.translation)}|{_txt(t.rotation.rotator())}|{vals}")
        for c in a.get_components_by_class(unreal.StaticMeshComponent):
            if c.get_path_name() in touched:
                continue
            mats = [(c.get_material(i).get_path_name() if c.get_material(i) else "-") for i in range(c.get_num_materials())]
            rows.append(f"{c.get_path_name()}|{mats}")
            nmat += len(mats)
    rows.sort()
    out["other_mesh_slots"] = nmat
    out["sha"] = hashlib.sha256(chr(10).join(rows).encode()).hexdigest()[:16]
    out["rows"] = {r.split("|")[0].rsplit(".", 1)[-1]: hashlib.sha256(r.encode()).hexdigest()[:8] for r in rows}
    return out


def materials(name, ids):
    """per instance: the mesh UE shows and the material on every slot (acceptance: same before / after a sync)."""
    b = S["batches"][name]
    out = {}
    for iid in ids:
        key, idx = b.slot[iid]
        c = b.comps[key]
        m = c.get_editor_property("static_mesh")
        out[iid] = {"mesh": m.get_name(), "slots": {n: (c.get_material(i).get_path_name() if c.get_material(i) else None)
                                                   for i, n in enumerate(slot_names(m))}}
    return out


def where(name, iid):
    """world bounds centre (Blender metres) and yaw of one instance as UE shows it now."""
    b = S["batches"][name]
    key, idx = b.slot[iid]
    comp = b.comps[key]
    t = comp.get_instance_transform(idx, True)
    c = t.transform_location(comp.get_editor_property("static_mesh").get_bounds().origin)
    return {"centre_m": [round(c.x / 100, 3), round(-c.y / 100, 3), round(c.z / 100, 3)],
            "yaw_ue": round(t.rotation.rotator().yaw, 3), "scale": [round(v, 4) for v in (t.scale3d.x, t.scale3d.y, t.scale3d.z)]}


# ---------------------------------------------------------------- control channel (own file, not 视效's lk_session)
ACTIONS = ("attach", "apply", "watch", "unwatch", "reset", "detach", "status", "restore", "suspend", "resume", "remap",
           "where", "materials", "fingerprint", "reapply")


def dispatch(req):
    """one request (the same JSON bl_sync.py takes) -> report. Used by bl_sync.py and by the control channel. While it
    runs, the watch tick and the control tick stay out (an import inside would otherwise let them run nested)."""
    was = S.get("busy")
    S["busy"] = True
    try:
        return _dispatch(req)
    finally:
        S["busy"] = was


def _dispatch(req):
    act = req.get("action", "status")
    if act == "attach":
        return attach(req)
    if act == "apply":
        return apply_file(req["overrides"], req.get("name"))
    if act == "watch":
        p = req["overrides"]
        return watch(p if isinstance(p, list) else [p], req.get("interval", 0.2))
    if act == "unwatch":
        return unwatch()
    if act == "reset":
        return reset(req["name"])
    if act == "detach":
        return detach(req.get("name"))
    if act == "restore":
        return restore()
    if act == "suspend":
        return suspend()
    if act == "resume":
        return resume()
    if act == "remap":
        return remap(req.get("name"))
    if act == "where":
        return where(req["name"], req["inst"])
    if act == "materials":
        return materials(req["name"], req["inst"])
    if act == "fingerprint":
        return fingerprint()
    if act == "reapply":
        return reapply(req.get("name"))
    return {"batches": {k: {"rev": b.rev, "overrides": len(b.applied), "instances": len(b.base),
                            "pending_meshes": sorted(b.pending)} for k, b in S["batches"].items()},
            "imports": {r.get("part", f): r.get("state") for f, r in _ASYNC.items() if r.get("state") != "done"},
            "watch": (S["watch"] or {}).get("paths"), "suspended": bool(S.get("suspended")), "session": _session()}


CREQ, CRES = CTRL / "request.json", CTRL / "result.json"
_CTL = {"sig": None, "last": None, "next": 0.0}


def _ctl_tick(dt):
    """Saved/BlSync/request.json -> result.json, 4 times a second, independent of 视效's channel."""
    if S.get("busy") or time.monotonic() < _CTL["next"]:
        return
    _CTL["next"] = time.monotonic() + 0.25
    _imports_tick()
    try:
        st = os.stat(CREQ)
    except FileNotFoundError:
        return
    sig = (st.st_mtime_ns, st.st_size)
    if sig == _CTL["sig"]:
        return
    _CTL["sig"] = sig
    try:
        req = json.loads(CREQ.read_text(encoding="utf-8-sig"))
    except Exception:
        return
    if not req.get("id") or req.get("id") == _CTL["last"]:
        return
    _CTL["last"] = req["id"]
    t0 = time.time()
    try:
        res = {"id": req["id"], "status": "done", "action": req.get("action"), "report": dispatch(req)}
    except Exception:
        res = {"id": req["id"], "status": "error", "action": req.get("action"), "error": traceback.format_exc()[-2000:]}
    res["seconds"] = round(time.time() - t0, 3)
    CRES.with_suffix(".tmp").write_text(json.dumps(res, ensure_ascii=False, default=str), encoding="utf-8")
    CRES.with_suffix(".tmp").replace(CRES)


def _start_ctl():
    import builtins
    old = getattr(builtins, "_blsync_ctl_handle", None)   # a reloaded module must not leave the old tick running
    if old is not None:
        try:
            unreal.unregister_slate_post_tick_callback(old)
        except Exception:
            pass
    try:                                                  # a request left from an earlier editor session is not run
        _CTL["last"] = json.loads(CREQ.read_text(encoding="utf-8-sig")).get("id")
        _CTL["sig"] = (os.stat(CREQ).st_mtime_ns, os.stat(CREQ).st_size)
    except Exception:
        pass
    builtins._blsync_ctl_handle = unreal.register_slate_post_tick_callback(_ctl_tick)


_start_ctl()
