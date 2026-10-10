"""renou_blsync_lib against the mock UE receiver: no UE, no team assets.
    blender -b --factory-startup --python-exit-code 1 --python tests/test_lib_mock.py -- build
Builds the synthetic fixture (tests/make_fixture.py), starts tests/mock_ue_receiver.py with Blender's own Python, then
drives the library the way an engineering script would. Prints PASS/FAIL per check; exit code 0 = everything passed."""
import hashlib, json, os, shlex, shutil, struct, subprocess, sys, time, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "blender"))
sys.path.insert(0, str(ROOT / "tests"))
from fake_ssh import FakeSSH
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
build = Path(argv[0] if argv else ROOT / "build").resolve()
fx, out = build / "fixture", build / f"run_{int(time.time())}"
subprocess.run([sys.executable, str(ROOT / "tests" / "make_fixture.py"), str(fx)], check=True)
out.mkdir(parents=True, exist_ok=True)
P, G = fx / "test_01_placements.json", fx / "test_01_parts.glb"
OV, ST = out / "test_01_overrides.json", out / "status.json"
mock = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mock_ue_receiver.py"),
                         "--placements", str(P), "--overrides", str(OV), "--status", str(ST)])

import renou_blsync_lib as rb                      # noqa: E402  (needs bpy, so only inside Blender)
import bpy                                       # noqa: E402
from mathutils import Matrix, Quaternion, Vector   # noqa: E402

fails = []


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {info}" if info != "" else ""))
    if not cond:
        fails.append(name)


def list_snaps(ov):
    return sorted((ov.parent / "archive").glob(ov.stem + "__*.json"))


def receipt_ok(r):
    ue = r.get("ue") or {}
    return ue.get("rev") == r["rev"] and not ue.get("errors")


try:
    # fast mode: Empties only, part bounds read from the GLB header
    Bf = rb.Batch(P, out=out / "fast_overrides.json", parts_glb=G, status=ST, load_meshes=False)
    check("fast mode baseline: no overrides, also for the w = 0 row (#31)", Bf.overrides() == {}, list(Bf.overrides())[:3])
    c = Bf.centre(Bf.group("BLK_BAKED"), base=False)
    check("fast mode: world-baked block centre from the GLB header", (c - Vector((110, 60, 20))).length < 1e-3, tuple(c))

    # #28: UE answers a rev twice when new meshes import in the background (complete false, then true)
    pdir = out / "pending_receipts"
    pdir.mkdir()
    Bf.status = pdir / "status.json"
    own = pdir / f"status_{Bf.batch}.json"
    doc = {"rev": 7, "written": time.time()}
    own.write_text(json.dumps({"rev": 7, "complete": False, "pending_meshes": ["P_NEW"]}), encoding="utf-8")
    first = Bf.wait_receipt(doc, wait=1)
    check("#28: the first receipt (meshes still importing) is returned by default",
          first and first.get("pending_meshes") == ["P_NEW"], first)
    check("#28: complete=True does not take the incomplete receipt", Bf.wait_receipt(doc, wait=0.3, complete=True) is None)
    import threading
    threading.Timer(0.3, lambda: own.write_text(json.dumps({"rev": 7, "complete": True, "meshes": [{"part": "P_NEW"}]}),
                                                encoding="utf-8")).start()
    done = Bf.wait_receipt(doc, wait=5, complete=True)
    check("#28: complete=True returns the receipt written when the meshes are in", done and done.get("complete") is True, done)
    own.write_text(json.dumps({"rev": 8}), encoding="utf-8")
    check("#28: receipts without the field (older bl_sync) count as complete",
          Bf.wait_receipt({"rev": 8, "written": time.time()}, wait=1, complete=True) is not None)

    # full mode
    B = rb.Batch(P, out=OV, parts_glb=G, status=ST)
    r = B.publish("baseline", wait=10)
    check("baseline: no overrides", r["overrides"] == 0, r["overrides"])
    check("baseline: receipt from the receiver", receipt_ok(r), r.get("ue"))

    b1 = B.group("BLD_01")
    B.move(b1, (5.0, 0.0, 0.0))
    r = B.publish("move BLD_01 5 m east", wait=10)
    check("move: 4 overrides", r["overrides"] == 4, r["overrides"])
    check("move: receipt counts 4 moved", receipt_ok(r) and (r["ue"].get("counts") or {}).get("moved") == 4, r.get("ue"))

    blk = B.group("BLK_BAKED")
    c0 = B.centre(blk, base=False)
    B.rotate(blk, 15.0)
    c1 = B.centre(blk, base=False)
    check("rotate: world-baked block turns about its own centre", (c0 - c1).length < 1e-3, (tuple(c0), tuple(c1)))

    B.delete(B.group("BLD_02")[:1])
    new = B.copy(B.group("BLD_03")[:1], (0.0, 30.0, 0.0))
    B.set_part(B.group("BLD_04")[:1], "PBOX_C")
    B.meshes["PBOX_D"].transform(Matrix.Diagonal((1.0, 1.0, 1.3, 1.0)))
    B.export_part("PBOX_D")
    r = B.publish("delete + copy + swap + mesh", wait=10)
    check("mixed: receipt without errors", receipt_ok(r), r.get("ue"))
    ov = json.loads(OV.read_text(encoding="utf-8"))
    check("mixed: a deleted entry", any(e.get("deleted") for e in ov["instances"].values()))
    e_new = ov["instances"].get(new[0]["blsync_id"], {})
    check("mixed: the copy carries part, era, src", all(k in e_new for k in ("part", "era", "src")), e_new)
    check("mixed: swapped part listed", any(e.get("part") == "PBOX_C" for e in ov["instances"].values()))
    m = ov.get("meshes", {}).get("PBOX_D", {})
    check("mixed: edited mesh listed with its SHA-256", len(m.get("sha256", "")) == 64 and Path(m.get("glb", "")).exists(), m)

    B.move(b1, (-5.0, 0.0, 0.0))
    r = B.publish("move BLD_01 back", wait=10)
    ov = json.loads(OV.read_text(encoding="utf-8"))
    check("cumulative: instances moved back leave the file", not any(o["blsync_id"] in ov["instances"] for o in b1))
    check("cumulative: receipt", receipt_ok(r), r.get("ue"))

    wb = B.write_back(out / "write_back")
    tab = json.loads(Path(wb["placements"]).read_text(encoding="utf-8"))
    base = json.loads(P.read_text(encoding="utf-8"))
    check("write_back: count = base - 1 deleted + 1 added", tab["count"] == base["count"], (tab["count"], base["count"]))
    touched = set(ov["instances"])
    same = all(row == next(b for b in base["instances"] if b["id"] == row["id"])
               for row in tab["instances"] if row["id"] not in touched and not row["id"].startswith("test_01_bl"))
    check("write_back: untouched rows identical to the table", same)
    check("write_back: the original table is not overwritten", Path(wb["placements"]) != P)

    B.reset()
    r = B.publish("reset", wait=10)
    check("reset: back to the table, no overrides", r["overrides"] == 0 and receipt_ok(r), r["overrides"])

    # Independent objects keep local geometry separate from their world TRS,
    # including a parented source and non-uniform scale (issues #2 and #19).
    bpy.ops.mesh.primitive_cube_add(size=2)
    source = bpy.context.object
    source.name = "synthetic independent source"
    parent = bpy.data.objects.new("synthetic parent", None)
    bpy.context.scene.collection.objects.link(parent)
    parent.matrix_world = Matrix.LocRotScale(Vector((3, 4, 5)), Quaternion((0, 0, 1), 0.3), Vector((2, 2, 2)))
    source.parent = parent
    source.matrix_basis = Matrix.LocRotScale(Vector((10, 20, 30)), Quaternion((0, 0, 1), 0.2), Vector((1, 2, 3)))
    materials = [bpy.data.materials.new("synthetic slot " + name) for name in ("a", "b", "override")]
    for material in materials:
        material.use_nodes = True
        material.node_tree.nodes.get("Principled BSDF").inputs["Roughness"].default_value = 0.123
    source.data.materials.append(materials[0])
    source.data.materials.append(materials[1])
    for polygon in source.data.polygons:
        polygon.material_index = polygon.index % 2
    source.material_slots[1].link = "OBJECT"
    source.material_slots[1].material = materials[2]
    bpy.context.view_layer.update()
    source_mesh, source_world = source.data, source.matrix_world.copy()
    source_sig, selected = rb.mesh_sig(source_mesh), set(bpy.context.selected_objects)
    part = "Pabcdef123456"
    added = B.add_object(source, part, era="present", src="independent synthetic box")
    iid = added["blsync_id"]
    check("add_object: fresh batch id, metadata and copied mesh",
          iid.startswith(B.batch + "_bl") and added.name == iid and added["blsync_part"] == part
          and added["blsync_era"] == "present" and added["blsync_src"] == "independent synthetic box"
          and added.data is B.meshes[part] and added.data != source_mesh)
    check("add_object: parented world matrix preserved without baking local vertices",
          added.parent is None and max(abs(added.matrix_world[i][j] - source_world[i][j]) for i in range(4) for j in range(4)) < 1e-5
          and all((a.co - b.co).length < 1e-6 for a, b in zip(added.data.vertices, source_mesh.vertices)))
    check("add_object: source parent, mesh, transform, shaders and selection unchanged",
          source.parent == parent and source.data == source_mesh and rb.mesh_sig(source_mesh) == source_sig
          and source.matrix_world == source_world and set(bpy.context.selected_objects) == selected
          and bpy.context.view_layer.objects.active == source
          and all(abs(m.node_tree.nodes.get("Principled BSDF").inputs["Roughness"].default_value - 0.123) < 1e-6 for m in materials))
    r = B.publish("add independent synthetic box", wait=10)
    check("add_object: receipt counts one added, no errors",
          receipt_ok(r) and r["ue"]["counts"].get("added") == 1, r.get("ue"))
    ov = json.loads(OV.read_text(encoding="utf-8"))
    mesh = ov["meshes"][part]
    raw = Path(mesh["glb"]).read_bytes()
    gltf = json.loads(raw[20:20 + struct.unpack_from("<I", raw, 12)[0]])
    check("add_object: GLB has only exact effective slot names, no shader parameters or textures",
          sorted(gltf.get("materials", []), key=lambda m: m["name"]) == sorted(
              [{"name": materials[i].name} for i in (0, 2)], key=lambda m: m["name"])
          and not gltf.get("images") and not gltf.get("textures"))
    check("add_object: one named identity mesh with two slot primitives",
          len(gltf["meshes"]) == 1 and gltf["meshes"][0]["name"] == part
          and len(gltf["meshes"][0]["primitives"]) == 2
          and all(not any(k in n for k in ("matrix", "translation", "rotation", "scale")) for n in gltf["nodes"]))
    lo, hi = rb.glb_part_bounds(mesh["glb"])[part]
    check("add_object: exported bounds remain local and final SHA matches",
          (lo - Vector((-1, -1, -1))).length < 1e-6 and (hi - Vector((1, 1, 1))).length < 1e-6
          and hashlib.sha256(raw).hexdigest() == mesh["sha256"])

    copied = B.copy(B.group("BLD_01")[:1], (5, 0, 0))[0]
    copied.scale = (3, 4, 5)
    uniform = B.copy([added], (10, 0, 0))[0]
    uniform.scale = (2, 2, 2)
    bpy.context.view_layer.update()
    wb = B.write_back(out / "new_objects_write_back")
    rows = {row["id"]: row for row in json.loads(Path(wb["placements"]).read_text(encoding="utf-8"))["instances"]}
    check("add_object: write_back adds one row per instance, NEAR only",
          len(rows) == len(B.base) + 3 and all(rows[o["blsync_id"]]["lods"] == ["NEAR"] for o in (added, copied, uniform)))
    check("write_back: new object and copy preserve non-uniform world transforms",
          all(max(abs(rb.mat_of(rows[o["blsync_id"]])[i][j] - o.matrix_world[i][j])
                  for i in range(4) for j in range(4)) < 1e-4 for o in (added, copied))
          and rows[iid]["scale"] == [2.0, 4.0, 6.0] and rows[copied["blsync_id"]]["scale"] == [3.0, 4.0, 5.0])
    check("write_back: uniform scaling remains a compatible scalar", rows[uniform["blsync_id"]]["scale"] == 2.0)
    reread = rb.Batch(wb["placements"], out=out / "reread_overrides.json", load_meshes=False)
    check("write_back: reread preserves the new object's world matrix",
          max(abs(reread.obj[iid].matrix_world[i][j] - source_world[i][j]) for i in range(4) for j in range(4)) < 1e-4)

    for name, obj, invalid_part in (("duplicate name", source, part), ("case-colliding name", source, part.upper()),
                                    ("invalid part name", source, "../bad"), ("non-mesh source", parent, "P000000000001")):
        before = (len(B.col.objects), set(B.meshes), set(B.mesh_out))
        try:
            B.add_object(obj, invalid_part)
            rejected = False
        except (ValueError, TypeError):
            rejected = True
        check("add_object: rejects " + name + " without mutation",
              rejected and before == (len(B.col.objects), set(B.meshes), set(B.mesh_out)))
    original_export = B.export_part
    before = (len(B.col.objects), set(B.meshes), set(B.mesh_out), len(bpy.data.meshes))
    def failed_export(*args, **kwargs):
        raise RuntimeError("synthetic export failure")
    B.export_part = failed_export
    try:
        try:
            B.add_object(source, "P000000000002")
            rejected = False
        except RuntimeError:
            rejected = True
        check("add_object: failed export rolls registration back",
              rejected and before == (len(B.col.objects), set(B.meshes), set(B.mesh_out), len(bpy.data.meshes)))
    finally:
        B.export_part = original_export
    B.meshes[part].vertices[0].co.z += 0.25
    again = B.export_part(part)
    raw = Path(again["glb"]).read_bytes()
    gltf = json.loads(raw[20:20 + struct.unpack_from("<I", raw, 12)[0]])
    check("add_object: later mesh exports remain slot-name-only",
          all(set(m) == {"name"} for m in gltf["materials"]) and not gltf.get("images") and not gltf.get("textures"))
    shear_parent = bpy.data.objects.new("synthetic non-uniform parent", None)
    bpy.context.scene.collection.objects.link(shear_parent)
    shear_parent.scale = (2, 3, 4)
    sheared = source.copy()
    bpy.context.scene.collection.objects.link(sheared)
    sheared.parent = shear_parent
    sheared.matrix_basis = Matrix.Rotation(0.5, 4, "Z")
    before = (len(B.col.objects), set(B.meshes), set(B.mesh_out))
    try:
        B.add_object(sheared, "P000000000003")
        rejected = False
    except ValueError as error:
        rejected = "shear" in str(error)
    check("add_object: unsupported shear is explicit, never silently flattened",
          rejected and before == (len(B.col.objects), set(B.meshes), set(B.mesh_out)))
    B.reset()
    r = B.publish("reset added objects", wait=10)
    check("add_object: reset removes additions and returns to the base", receipt_ok(r) and r["overrides"] == 0)
    bare = bpy.data.objects.new("synthetic object without materials", source_mesh.copy())
    bpy.context.scene.collection.objects.link(bare)
    bare.data.materials.clear()
    default_added = B.add_object(bare, "P000000000004")
    r = B.publish("new object with default metadata", wait=10)
    raw = Path(B.mesh_out["P000000000004"]["glb"]).read_bytes()
    gltf = json.loads(raw[20:20 + struct.unpack_from("<I", raw, 12)[0]])
    check("add_object: default metadata and no-material mesh publish successfully",
          default_added["blsync_era"] == "both" and default_added["blsync_src"] == ""
          and receipt_ok(r) and r["ue"]["counts"].get("added") == 1 and not gltf.get("materials"))
    B.reset()
    B.publish("reset default addition", wait=10)
    temporary_slot = bpy.data.materials.new("synthetic empty slot")
    bare.data.materials.append(temporary_slot)
    bare.data.materials[0] = None
    bpy.data.materials.remove(temporary_slot)
    for polygon in bare.data.polygons:
        polygon.material_index = 0
    empty_part, derived_part = "P000000000005", "P000000000006"
    empty_added = B.add_object(bare, empty_part)
    raw = Path(B.mesh_out[empty_part]["glb"]).read_bytes()
    gltf = json.loads(raw[20:20 + struct.unpack_from("<I", raw, 12)[0]])
    check("add_object: an existing None material slot exports as an empty name",
          gltf.get("materials") == [{"name": ""}] and not gltf.get("images") and not gltf.get("textures"))
    check("add_object: an empty source material slot stays None",
          len(bare.data.materials) == 1 and bare.data.materials[0] is None and empty_added.data.materials[0] is None)
    B.new_part(empty_part, derived_part)
    derived = B.export_part(derived_part)
    raw = Path(derived["glb"]).read_bytes()
    gltf = json.loads(raw[20:20 + struct.unpack_from("<I", raw, 12)[0]])
    check("add_object: new_part derivatives inherit slot-only export",
          gltf.get("materials") == [{"name": ""}] and gltf["meshes"][0]["name"] == derived_part
          and not gltf.get("images") and not gltf.get("textures"))
    B.reset()
    B.publish("reset empty-slot addition", wait=10)

    # user 10-10: no write that clears, shrinks or rewinds an override file without a snapshot first; a new Batch can go
    # on from the file (or from any snapshot) instead of starting from the table
    SO = out / "snap_overrides.json"
    S1 = rb.Batch(P, out=SO, parts_glb=G, status=ST, track_edits=True)
    s1b = S1.group("BLD_01")
    S1.move(s1b, (7.0, 0.0, 0.0))
    S1.delete(S1.group("BLK_BAKED")[:1])
    S1.add_object(bpy.data.objects.new("snap_src", S1.meshes["PBOX_D"].copy()), "P0000000000a1")
    S1.meshes["PBOX_D"].vertices[0].co.z += 0.25
    S1.export_part("PBOX_D")
    first = S1.publish("snapshot base", wait=0)
    check("snapshots: the first file has nothing to keep", first.get("snapshot") is None and not list_snaps(SO), first)
    S1.move(s1b, (1.0, 0.0, 0.0))
    r = S1.publish("snapshot normal move", wait=0)
    check("snapshots: a normal move (same ids) makes no snapshot", not list_snaps(SO), [p.name for p in list_snaps(SO)])
    before = SO.read_bytes()
    doc_before = json.loads(before)
    S1.reset()
    r = S1.publish("全部还原", wait=0)
    snaps = list_snaps(SO)
    check("snapshots: 全部还原 keeps the file it clears, byte for byte",
          len(snaps) == 1 and snaps[0].read_bytes() == before and "__cleared" in snaps[0].name
          and r.get("snapshot") == str(snaps[0]), [p.name for p in snaps])
    rows = S1.snapshots()
    check("snapshots: listed newest first with rev, reason and counts",
          rows and rows[0]["reason"] == "cleared" and rows[0]["rev"] == str(doc_before["rev"])
          and rows[0]["instances"] == len(doc_before["instances"]) and rows[0]["meshes"] == len(doc_before["meshes"]), rows[:1])
    a1, a2 = S1.snapshot("again"), S1.snapshot("again2")
    check("snapshots: an identical copy is not made twice", a1 == a2 and len(list_snaps(SO)) == 2, [p.name for p in list_snaps(SO)])
    rd = rb.snapshot_file  # rotation with a small keep
    tmpf = out / "rot_overrides.json"
    for i in range(8):
        tmpf.write_text(json.dumps({"rev": i, "instances": {}}), encoding="utf-8")
        rd(tmpf, "test", keep=5)
        time.sleep(0.01)
    rot = sorted((out / "archive").glob("rot_overrides__*.json"))
    check("snapshots: only the newest `keep` stay", len(rot) == 5 and json.loads(rot[0].read_text())["rev"] == 3,
          [p.name for p in rot])

    S2 = rb.Batch(P, out=SO, parts_glb=G, status=ST, track_edits=True)
    check("snapshots: a new Batch never numbers below the file on disk", S2.rev >= json.loads(SO.read_text())["rev"])
    orig_pbox = S2.meshes["PBOX_D"]
    lr = S2.load_overrides(str(snaps[0]))
    got = S2.overrides()
    same_inst = set(got) == set(doc_before["instances"]) and all(
        got[k].get("deleted") == v.get("deleted") and got[k].get("part") == v.get("part")
        and (v.get("deleted") or max(abs(a - b) for a, b in zip(got[k]["pos"], v["pos"])) < 1e-4)
        for k, v in doc_before["instances"].items())
    check("load_overrides: a snapshot comes back exactly (moves, deletion, new object, edited mesh)",
          same_inst and lr["missing_meshes"] == [] and set(S2.mesh_out) == set(doc_before["meshes"]), (lr, sorted(got)))
    check("load_overrides: the loaded new part exports slot names only again", "P0000000000a1" in S2._slot_only_parts)
    r = S2.publish("restored from snapshot", wait=0)
    check("load_overrides: publishing the restored state writes the same instances and meshes",
          set(json.loads(SO.read_text())["instances"]) == set(doc_before["instances"])
          and set(json.loads(SO.read_text())["meshes"]) == set(doc_before["meshes"]), r)
    S2.reset()
    check("load_overrides: reset gives the release mesh back to a part the document had replaced",
          S2.meshes["PBOX_D"] == orig_pbox and all(o.data == orig_pbox for o in S2.col.objects if o.get("blsync_part") == "PBOX_D"))
    try:
        S2.load_overrides(dict(doc_before, base_sha256="0" * 64))
        check("load_overrides: refuses a document of another table version", False)
    except ValueError:
        check("load_overrides: refuses a document of another table version", True)
    S2.publish("snapshot test done", wait=0)

    # 10-10: optional placements fields (layer, recipe, group, pair, event, lock, tags) and unknown fields pass through
    F3 = rb.Batch(P, out=out / "fields_overrides.json", parts_glb=G, status=ST)
    b5 = F3.where(layer="L3")
    check("optional fields: where(layer=...) finds the 4 rows that carry it", len(b5) == 4, len(b5))
    check("optional fields: group() also matches the group field", set(F3.group("g012")) == set(b5))
    check("optional fields: where(tags=...) matches one tag of the list, where(lock=...) reads proc / hand",
          set(F3.where(tags="nocol")) == set(b5) and not F3.where(lock="hand") and set(F3.where(lock="proc")) >= set(b5))
    want_meta = {"layer": "L3", "recipe": "F_QUAY_LOAD", "group": "g012", "event": "E-H3-1", "lock": "proc",
                 "tags": ["clutter", "nocol"]}
    m0 = F3.meta(b5[0])
    check("optional fields: carried on the object", {k: m0.get(k) for k in want_meta} == want_meta and m0["pair"].startswith("past_"), m0)
    check("optional fields: is_locked reads hand / true / proc",
          rb.is_locked({"lock": "hand"}) and rb.is_locked({"lock": True}) and not rb.is_locked({"lock": "proc"})
          and not rb.is_locked({}))
    F3.move(b5[:1], (2.0, 0.0, 0.0))
    cp = F3.copy(b5[1:2], (0.0, 40.0, 0.0))[0]
    wb = F3.write_back(out / "fields_wb")
    tab = json.loads(Path(wb["placements"]).read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in tab["instances"]}
    base_rows = {r["id"]: r for r in json.loads(P.read_text(encoding="utf-8"))["instances"]}
    moved = rows[b5[0]["blsync_id"]]
    check("write_back: a moved row keeps every optional field and gets lock = hand",
          {k: moved.get(k) for k in want_meta if k != "lock"} == {k: v for k, v in want_meta.items() if k != "lock"}
          and moved["lock"] == "hand" and moved["pair"] == base_rows[b5[0]["blsync_id"]]["pair"], moved)
    added = rows[cp["blsync_id"]]
    check("write_back: a copy keeps its source's layer / group / tags (not its pair) and gets lock = hand",
          added.get("layer") == "L3" and added.get("group") == "g012" and added.get("tags") == ["clutter", "nocol"]
          and added.get("lock") == "hand" and "pair" not in added, added)
    fut = next(r for r in base_rows.values() if "x_future" in r)
    check("write_back: untouched rows stay identical, unknown fields included",
          rows[fut["id"]] == fut and rows[b5[2]["blsync_id"]] == base_rows[b5[2]["blsync_id"]])
    wb2 = F3.write_back(out / "fields_wb", lock_edits=False)
    check("write_back(lock_edits=False) leaves lock as it was",
          {r["id"]: r for r in json.loads(Path(wb2["placements"]).read_text(encoding="utf-8"))["instances"]}[b5[0]["blsync_id"]]["lock"] == "proc")

    # Remote mode uses the real subprocess-based transport, but PATH can only
    # reach these local stand-ins. All data is synthetic; no server is involved.
    original_path = os.environ.get("PATH")
    with FakeSSH(out) as fake:
        check("remote: ssh and scp resolve to the local stand-ins",
              all(Path(shutil.which(name)) == fake.bin_dir / name for name in ("ssh", "scp")))
        for name, command in (
                ("unknown hosts", ["ssh", "not-the-test-host", "cat /file"]),
                ("paths outside the fixture", ["ssh", fake.host, "cat /file"]),
                ("unsupported shell commands", ["ssh", fake.host, "echo unexpected"]),
                ("scp paths outside the fixture", ["scp", "-q", str(P), fake.host + ":/file"])):
            rejected = subprocess.run(command, capture_output=True, text=True)
            check("fake transport rejects " + name, rejected.returncode != 0)

        B.remote = f"{fake.host}:{fake.remote_dir}"
        B.out = out / "local files" / "test_01_overrides.json"
        B.status = fake.remote_dir / "status.json"
        remote_ov = fake.remote_dir / B.out.name
        remote_mock = subprocess.Popen([sys.executable, str(ROOT / "tests" / "mock_ue_receiver.py"),
                                        "--placements", str(P), "--overrides", str(remote_ov),
                                        "--status", str(B.status)])
        try:
            B.move(b1, (3.0, 0.0, 0.0))
            mesh = dict(B.export_part("PBOX_D"))
            doc = B.build("remote first delivery")
            r = B.deliver(doc)
            r["ue"] = B.wait_receipt(doc, wait=10)
            check("remote: deliver and ssh cat receipt report 4 moved",
                  receipt_ok(r) and r["ue"]["counts"].get("moved") == 4, r.get("ue"))
            delivered = json.loads(remote_ov.read_text(encoding="utf-8"))
            remote_glb = fake.remote_dir / "meshes" / Path(mesh["glb"]).name
            check("remote: delivered document uses the remote GLB path",
                  delivered["meshes"]["PBOX_D"] == {"glb": str(remote_glb), "sha256": mesh["sha256"]})
            check("remote: GLB bytes copied unchanged", remote_glb.read_bytes() == Path(mesh["glb"]).read_bytes())
            check("remote: override file arrives atomically and matches the local document",
                  remote_ov.read_bytes() == B.out.read_bytes()
                  and not Path(str(remote_ov) + ".tmp").exists())
            check("remote: the first GLB is pushed once and cached",
                  len(fake.commands("copy")) == 1 and B._pushed == {("PBOX_D", mesh["sha256"])})

            B.move(b1, (1.0, 0.0, 0.0))
            r = B.publish("remote move with unchanged mesh", wait=10)
            check("remote: another revision is received without resending the GLB",
                  receipt_ok(r) and r["rev"] > doc["rev"] and len(fake.commands("copy")) == 1, r.get("ue"))

            B.meshes["PBOX_D"].vertices[0].co.z += 0.5
            changed = dict(B.export_part("PBOX_D"))
            r = B.publish("remote changed mesh", wait=10)
            check("remote: a changed GLB is pushed once under its new hash",
                  receipt_ok(r) and changed["sha256"] != mesh["sha256"] and len(fake.commands("copy")) == 2
                  and B._pushed == {("PBOX_D", mesh["sha256"]), ("PBOX_D", changed["sha256"])})
            read_command = f"cat {shlex.quote(B.status.as_posix())}"
            check("remote: wait_receipt reads status through ssh cat",
                  any(row["args"] == [fake.host, read_command] for row in fake.commands("read")))
            check("remote: every revision is pushed, with no temporary file left",
                  len(fake.commands("write")) == 3 and not Path(str(remote_ov) + ".tmp").exists())
            check("remote: stale receipt times out",
                  B.wait_receipt({"rev": r["rev"] + 1, "written": time.time()}, wait=0.1) is None)
        finally:
            remote_mock.terminate()
            remote_mock.wait(timeout=5)
    check("remote: restores PATH after the test", os.environ.get("PATH") == original_path)
except Exception:
    traceback.print_exc()
    fails.append("exception")
finally:
    mock.terminate()

print("RESULT " + ("OK" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
