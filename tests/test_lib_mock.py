"""renou_blsync_lib against the mock UE receiver: no UE, no team assets.
    blender -b --factory-startup --python-exit-code 1 --python tests/test_lib_mock.py -- build
Builds the synthetic fixture (tests/make_fixture.py), starts tests/mock_ue_receiver.py with Blender's own Python, then
drives the library the way an engineering script would. Prints PASS/FAIL per check; exit code 0 = everything passed."""
import json, os, shlex, shutil, subprocess, sys, time, traceback
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
from mathutils import Matrix, Vector               # noqa: E402

fails = []


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {info}" if info != "" else ""))
    if not cond:
        fails.append(name)


def receipt_ok(r):
    ue = r.get("ue") or {}
    return ue.get("rev") == r["rev"] and not ue.get("errors")


try:
    # fast mode: Empties only, part bounds read from the GLB header
    Bf = rb.Batch(P, out=out / "fast_overrides.json", parts_glb=G, status=ST, load_meshes=False)
    c = Bf.centre(Bf.group("BLK_BAKED"), base=False)
    check("fast mode: world-baked block centre from the GLB header", (c - Vector((110, 60, 20))).length < 1e-3, tuple(c))

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
