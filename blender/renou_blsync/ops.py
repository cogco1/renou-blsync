"""Operators. All real work is done by renou_blsync_lib (state.rb); these only wire it to the panel and the live switch."""
import bpy

from . import live, state


def _abs(p):
    return bpy.path.abspath(p) if p else p


class RENOU_OT_attach(bpy.types.Operator):
    """载入一批摆放表，每个实例一个物体"""
    bl_idname = "renou.attach"
    bl_label = "载入批"
    bl_options = {"REGISTER"}

    def execute(self, context):
        s = state.settings(context)
        if not s.placements or not s.out:
            self.report({"ERROR"}, "先填摆放表和覆盖文件")
            return {"CANCELLED"}
        kw = dict(parts_glb=_abs(s.parts_glb) or None, only_src=s.only_src or None, remote=s.remote or None,
                  load_meshes=s.load_meshes, track_edits=True)
        if s.status:
            kw["status"] = _abs(s.status)
        B = state.rb.Batch(_abs(s.placements), out=_abs(s.out), **kw)
        if B.batch in state.BATCHES:
            self.report({"WARNING"}, f"{B.batch} 已载入过，新载入的这一份替换旧的")
        msg = f"{B.batch}: {len(B.obj)} 个实例"
        state.BLOCKED.pop(B.batch, None)
        on_disk = B.out.exists()
        doc = B.read_out() if s.resume and on_disk else None
        if s.resume and on_disk and doc is None:
            state.BLOCKED[B.batch] = "覆盖文件读不了（损坏？）"
        elif doc and (doc.get("instances") or doc.get("meshes")):
            # user 10-10: reattaching (a reopened window) goes on from the file instead of overwriting it with the table
            try:
                r = B.load_overrides(doc)
                msg += f"，接着已有覆盖：{r['instances']} 条，网格 {r['meshes']} 个"
            except Exception as e:                       # all or nothing: the scene is still the table
                state.BLOCKED[B.batch] = f"已有覆盖没载回：{e}"
        state.BATCHES[B.batch] = B
        state.SNAPS.pop(B.batch, None)
        if B.batch in state.BLOCKED:                     # Ash 10-10: nothing is published until the user decides
            self.report({"WARNING"}, f"{msg}；{state.BLOCKED[B.batch]}。这一批暂不发布：在面板里重试载回，或从正式表开始")
            return {"FINISHED"}
        state.DIRTY.add(B.batch)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class RENOU_OT_detach(bpy.types.Operator):
    """停止同步所有已载入的批（Blender 里的物体留着）"""
    bl_idname = "renou.detach"
    bl_label = "全部卸下"

    def execute(self, context):
        n = len(state.BATCHES)
        state.BATCHES.clear()
        state.DIRTY.clear()
        state.GEO_DIRTY.clear()
        self.report({"INFO"}, f"卸下 {n} 批")
        return {"FINISHED"}


class RENOU_OT_publish_now(bpy.types.Operator):
    """不等实时开关，立刻把所有批发一次"""
    bl_idname = "renou.publish_now"
    bl_label = "立即发布"

    def execute(self, context):
        state.DIRTY.update(state.BATCHES)
        for name, B in state.BATCHES.items():           # a manual publish also checks every loaded part mesh
            state.GEO_DIRTY.setdefault(name, set()).update(B.meshes)
        sent = live.flush("publish now")
        self.report({"INFO"}, f"已发出：{', '.join(sent) or '无'}")
        return {"FINISHED"}


class RENOU_OT_reset(bpy.types.Operator):
    """全部回到正式摆放表，并发布一次（UE 也回到正式版）"""
    bl_idname = "renou.reset"
    bl_label = "全部还原"

    def execute(self, context):
        for B in state.BATCHES.values():
            B.reset()
        state.DIRTY.update(state.BATCHES)
        live.flush("reset")
        return {"FINISHED"}


class RENOU_OT_restore_snapshot(bpy.types.Operator):
    """把一份快照载回场景并发布（当前文件先存一份快照，载错了还能再换回来）"""
    bl_idname = "renou.restore_snapshot"
    bl_label = "载回"

    batch: bpy.props.StringProperty()
    path: bpy.props.StringProperty()

    def execute(self, context):
        B = state.BATCHES.get(self.batch)
        if B is None:
            self.report({"ERROR"}, f"{self.batch} 没有载入")
            return {"CANCELLED"}
        if context.mode != "OBJECT":                     # edit-mode changes are not in the mesh yet (Ash 10-10)
            self.report({"ERROR"}, "先退出编辑模式再载回：编辑模式里的改动还没写进网格，备份会漏掉")
            return {"CANCELLED"}
        try:
            B.snapshot("before-restore")                 # the file on disk ...
            B.snapshot_scene("before-restore")           # ... and the scene, unpublished edits included (Ash 10-10)
            r = B.load_overrides(self.path)              # all or nothing
        except Exception as e:
            self.report({"ERROR"}, f"载回失败，场景没动：{e}")
            return {"CANCELLED"}
        state.BLOCKED.pop(self.batch, None)
        state.SNAPS.pop(self.batch, None)
        state.DIRTY.add(self.batch)
        live.flush("restore snapshot")
        self.report({"INFO"}, f"{self.batch}: 已载回 {r['instances']} 条覆盖、{r['meshes']} 个网格")
        return {"FINISHED"}


class RENOU_OT_unblock(bpy.types.Operator):
    """不载回已有覆盖，从正式表开始发布（发布前旧文件会自动存快照）"""
    bl_idname = "renou.unblock"
    bl_label = "从正式表开始"

    batch: bpy.props.StringProperty()

    def execute(self, context):
        state.BLOCKED.pop(self.batch, None)
        state.DIRTY.add(self.batch)
        self.report({"INFO"}, f"{self.batch}: 从正式表开始；旧文件在发布前存进 archive/")
        return {"FINISHED"}


class RENOU_OT_write_back(bpy.types.Operator):
    """定稿：生成新版摆放表和改动说明（交工程发布，不覆盖任何旧文件）"""
    bl_idname = "renou.write_back"
    bl_label = "定稿写回"

    def execute(self, context):
        d = _abs(state.settings(context).writeback_dir)
        if not d:
            self.report({"ERROR"}, "先填写回目录")
            return {"CANCELLED"}
        msgs = []
        for name, B in state.BATCHES.items():
            r = B.write_back(d)
            msgs.append(f"{name}: 挪 {r['moved']} 换 {r['swapped']} 增 {r['added']} 删 {r['deleted']}")
        self.report({"INFO"}, "；".join(msgs) or "没有载入的批")
        return {"FINISHED"}


CLASSES = (RENOU_OT_attach, RENOU_OT_detach, RENOU_OT_publish_now, RENOU_OT_reset, RENOU_OT_restore_snapshot,
           RENOU_OT_unblock, RENOU_OT_write_back)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
