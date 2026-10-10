"""Sidebar panel: View3D > N > Renou."""
import time

import bpy

from . import state


class RENOU_PT_sync(bpy.types.Panel):
    bl_label = "Renou 实时同步"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Renou"

    def draw(self, context):
        s = state.settings(context)
        col = self.layout.column(align=True)
        for p in ("placements", "parts_glb", "load_meshes", "only_src", "out", "status", "remote"):
            col.prop(s, p)
        col.operator("renou.attach", icon="IMPORT")
        self.layout.separator()
        row = self.layout.row(align=True)
        row.prop(s, "live", toggle=True, icon="PLAY" if not s.live else "PAUSE")
        row.prop(s, "interval")
        row = self.layout.row(align=True)
        row.operator("renou.publish_now", icon="EXPORT")
        row.operator("renou.reset", icon="LOOP_BACK")
        col = self.layout.column(align=True)
        col.prop(s, "writeback_dir")
        col.operator("renou.write_back", icon="CHECKMARK")
        col.operator("renou.detach", icon="X")
        box = self.layout.box()
        if not state.BATCHES:
            box.label(text="没有载入的批")
        for name, B in state.BATCHES.items():
            r = state.RESULTS.get(name) or {}
            ue = r.get("ue") or {}
            box.label(text=f"{name}  实例 {len(B.obj)}  覆盖 {r.get('overrides', '-')}  第 {r.get('rev', '-')} 版")
            if r:
                lat = ue.get("latency_s")
                age = int(time.time() - r.get("t", time.time()))
                box.label(text=f"UE 回执：{'%.2f s' % lat if lat is not None else '未收到'}，{age} 秒前，{r.get('label', '')}")
            c = ue.get("counts") or {}
            if c:
                names = (("moved", "挪"), ("added", "新增"), ("hidden", "隐藏"), ("swapped", "换件"))
                box.label(text="这一版改动：" + " · ".join(f"{t} {c[k]}" for k, t in names if c.get(k)))
            ms = ue.get("meshes") or []
            if ms:
                box.label(text=f"重导网格 {len(ms)} 个，UE 用时 {sum(m.get('seconds', 0) for m in ms):.1f} s", icon="MESH_DATA")
            if ue.get("save_guard"):
                box.label(text="UE 批次层只读中（预览和正式表不同，存盘不会混进预览）", icon="LOCKED")
            conflicts = ue.get("conflicts") or []
            if conflicts:
                sub = box.box()
                sub.alert = True
                sub.label(text=f"和 UE 里手摆的东西重叠 {len(conflicts)} 处（只报告，不会动它们）：", icon="ERROR")
                for k in conflicts[:6]:
                    sub.label(text=f"{k.get('inst', '')} ↔ {k.get('actor', '')}  {k.get('overlap_m', '')} m")
            unmapped = ue.get("unmapped_slots") or []
            if unmapped:
                sub = box.box()
                sub.label(text=f"材质槽 UE 没映射 {len(unmapped)} 个（显示斑马纹，请视效补表）：", icon="MATERIAL")
                sub.label(text="，".join(unmapped[:6]) + ("…" if len(unmapped) > 6 else ""))
            err = r.get("error") or ue.get("errors") or ue.get("error")
            if err:
                row = box.row()
                row.alert = True
                row.label(text=str(err)[:160], icon="ERROR")
        if state.LAST_ERROR:
            row = self.layout.row()
            row.alert = True
            row.label(text=state.LAST_ERROR.strip().splitlines()[-1][:160], icon="ERROR")


def register():
    bpy.utils.register_class(RENOU_PT_sync)


def unregister():
    bpy.utils.unregister_class(RENOU_PT_sync)
