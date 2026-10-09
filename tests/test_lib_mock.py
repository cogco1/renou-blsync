"""renou_blsync_lib against the mock UE receiver: no UE, no team assets.
    blender -b --factory-startup --python-exit-code 1 --python tests/test_lib_mock.py -- build
Builds the synthetic fixture (tests/make_fixture.py), starts tests/mock_ue_receiver.py with Blender's own Python, then
drives the library the way an engineering script would. Prints PASS/FAIL per check; exit code 0 = everything passed."""
import json, subprocess, sys, time, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "blender"))
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
except Exception:
    traceback.print_exc()
    fails.append("exception")
finally:
    mock.terminate()

print("RESULT " + ("OK" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
