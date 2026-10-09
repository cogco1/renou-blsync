"""Scene settings (saved in the .blend). No passwords or keys: the server is reached with the system's own ssh/scp."""
import bpy
from bpy.props import BoolProperty, FloatProperty, PointerProperty, StringProperty

from . import live


def _live_update(self, context):
    live.set_live(self.live)


class RenouSyncSettings(bpy.types.PropertyGroup):
    placements: StringProperty(name="摆放表", subtype="FILE_PATH",
                               description="<批>_placements.json（renou-placements/1），正式发布的那一版")
    parts_glb: StringProperty(name="零件包", subtype="FILE_PATH",
                              description="<批>_parts.glb；不填就只载空物体，不能改网格")
    load_meshes: BoolProperty(name="载入网格", default=True,
                              description="关掉 = 快速模式：只读 GLB 头里的包围盒，物体是空物体")
    only_src: StringProperty(name="只载入", description="可选：src 的正则，只载入匹配的楼")
    out: StringProperty(name="覆盖文件", subtype="FILE_PATH",
                        description="<批>_overrides.json 写到哪；本机模式下是本地路径，再推到服务器同名目录")
    status: StringProperty(name="UE 回执", subtype="FILE_PATH",
                           description="UE 写的 status.json；不填用函数库的默认路径")
    remote: StringProperty(name="服务器目录",
                           description="本机模式才填，例如 myserver:/path/to/data（只调用系统里已配好的 ssh/scp）")
    interval: FloatProperty(name="间隔 (s)", default=0.25, min=0.05, max=5.0,
                            description="实时模式下多久收集一次改动")
    writeback_dir: StringProperty(name="写回目录", subtype="DIR_PATH",
                                  description="定稿时生成新版摆放表和改动说明的目录；不会覆盖任何旧文件")
    live: BoolProperty(name="实时同步", default=False, update=_live_update,
                       description="开着时，脚本改的、手改的都自动发到 UE（对应 D5 LiveSync 的开始/暂停）")


def register():
    bpy.utils.register_class(RenouSyncSettings)
    bpy.types.Scene.renou_sync = PointerProperty(type=RenouSyncSettings)


def unregister():
    del bpy.types.Scene.renou_sync
    bpy.utils.unregister_class(RenouSyncSettings)
