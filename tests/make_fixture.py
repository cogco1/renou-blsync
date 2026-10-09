#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic test data for renou_blsync: no team assets, plain boxes only.
    python3 tests/make_fixture.py build/fixture
Writes batch "test_01":
  test_01_placements.json  renou-placements/1, 6 buildings x 4 instances + 1 world-baked block (pos 0,0,0, geometry offset,
                           like the real CBD fill blocks) = 25 instances
  test_01_parts.glb        5 box parts, one top-level node per part (node name = part), one material slot each
Standard library only, so it runs with any Python 3 (Blender's own included)."""
import json, math, struct, sys
from pathlib import Path

BATCH = "test_01"
# part: (Blender-space min, max, material slot name); boxes stand on z = 0 around the origin, except the baked block
PARTS = {
    "PBOX_A": ((-5, -5, 0), (5, 5, 20), "C_stone_dark"),
    "PBOX_B": ((-4, -6, 0), (4, 6, 30), "C_brick"),
    "PBOX_C": ((-3, -3, 0), (3, 3, 12), "C_brass"),
    "PBOX_D": ((-2, -2, 0), (2, 2, 4), "C_iron"),
    "PBAKED_BLK1": ((100, 50, 0), (120, 70, 40), "C_stone_dark"),
}
FACES = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (2, 3, 7), (2, 7, 6), (1, 2, 6), (1, 6, 5), (0, 4, 7), (0, 7, 3)]


def to_gltf(p):
    """Blender (x, y, z), Z up -> glTF (x, z, -y), Y up."""
    return (p[0], p[2], -p[1])


def box_vertices(lo, hi):
    corners = [(x, y, z) for z in (lo[2], hi[2]) for (x, y) in ((lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1]))]
    return [to_gltf(c) for c in corners]


def write_glb(path):
    bin_, views, accessors, meshes, materials, nodes = bytearray(), [], [], [], [], []
    mat_index = {}

    def add_view(data, target):
        while len(bin_) % 4:
            bin_.append(0)
        views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": len(data), "target": target})
        bin_.extend(data)
        return len(views) - 1

    for name, (lo, hi, slot) in PARTS.items():
        v = box_vertices(lo, hi)
        pos = b"".join(struct.pack("<3f", *p) for p in v)
        idx = b"".join(struct.pack("<3H", *f) for f in FACES)
        pv, iv = add_view(pos, 34962), add_view(idx, 34963)
        accessors.append({"bufferView": pv, "componentType": 5126, "count": len(v), "type": "VEC3",
                          "min": [min(p[i] for p in v) for i in range(3)], "max": [max(p[i] for p in v) for i in range(3)]})
        accessors.append({"bufferView": iv, "componentType": 5123, "count": len(FACES) * 3, "type": "SCALAR"})
        if slot not in mat_index:
            mat_index[slot] = len(materials)
            materials.append({"name": slot, "pbrMetallicRoughness": {"baseColorFactor": [0.6, 0.6, 0.6, 1.0]}})
        meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": len(accessors) - 2},
                                                     "indices": len(accessors) - 1, "material": mat_index[slot]}]})
        nodes.append({"name": name, "mesh": len(meshes) - 1})
    while len(bin_) % 4:
        bin_.append(0)
    g = {"asset": {"version": "2.0", "generator": "renou_blsync tests/make_fixture.py"}, "scene": 0,
         "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes, "materials": materials,
         "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(bin_)}]}
    js = json.dumps(g, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<4sII", b"glTF", 2, total))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        fh.write(struct.pack("<II", len(bin_), 0x004E4942) + bytes(bin_))


def quat_z(deg):
    h = math.radians(deg) / 2
    return [round(math.cos(h), 7), 0.0, 0.0, round(math.sin(h), 7)]


def placements():
    rows, n = [], 0
    layout = [("PBOX_A", (0, 0, 0)), ("PBOX_B", (12, 0, 0)), ("PBOX_C", (0, 12, 0)), ("PBOX_D", (12, 12, 0))]
    for b in range(1, 7):
        ox, oy, yaw = (b - 1) % 3 * 60.0, (b - 1) // 3 * 60.0, (b - 1) * 10.0
        for part, (dx, dy, dz) in layout:
            n += 1
            rows.append({"id": f"{BATCH}_{n:06d}", "part": part, "lods": ["NEAR"], "pos": [ox + dx, oy + dy, dz],
                         "quat_wxyz": quat_z(yaw), "yaw_deg": yaw, "scale": 1.0, "district": BATCH, "zone": "test",
                         "era": "both", "building_id": f"BLD_{b:02d}", "src": f"BLD_{b:02d} | synthetic"})
    n += 1
    rows.append({"id": f"{BATCH}_{n:06d}", "part": "PBAKED_BLK1", "lods": ["NEAR"], "pos": [0.0, 0.0, 0.0],
                 "quat_wxyz": [1.0, 0.0, 0.0, 0.0], "yaw_deg": 0.0, "scale": 1.0, "district": BATCH, "zone": "test",
                 "era": "both", "building_id": "BLK_BAKED", "src": "BLK_BAKED | synthetic, world-baked like CBD fill blocks"})
    return {"schema": "renou-placements/1", "coord": "blender_zup_m", "batch": BATCH, "source": "synthetic fixture",
            "count": len(rows), "instances": rows}


def main(out_dir):
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    write_glb(d / f"{BATCH}_parts.glb")
    (d / f"{BATCH}_placements.json").write_text(json.dumps(placements(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"fixture written to {d}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/fixture")
