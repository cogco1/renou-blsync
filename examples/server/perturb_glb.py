"""copy a GLB with one vertex of the first POSITION accessor nudged by 0.1 mm, so the mesh hash (and every DDC key) is new.
    python3 perturb_glb.py in.glb out.glb seed"""
import json, struct, sys

src, dst, seed = sys.argv[1], sys.argv[2], int(sys.argv[3])
b = bytearray(open(src, "rb").read())
clen = struct.unpack_from("<I", b, 12)[0]
g = json.loads(b[20:20 + clen])
bin_off = 20 + clen + 8                            # BIN chunk data
acc = next(a for m in g["meshes"] for p in m["primitives"] for k, a in [("POSITION", p["attributes"]["POSITION"])])
a = g["accessors"][acc]
v = g["bufferViews"][a["bufferView"]]
stride = v.get("byteStride", 12)
i = (seed * 7919) % a["count"]
off = bin_off + v.get("byteOffset", 0) + a.get("byteOffset", 0) + i * stride
x = struct.unpack_from("<f", b, off)[0]
struct.pack_into("<f", b, off, x + 0.0001 * (1 + seed % 3))
open(dst, "wb").write(b)
print(dst, "vertex", i, x, "->", struct.unpack_from("<f", b, off)[0])
