# renou-blsync · Blender → UE 实时同步

《人偶之心》用的一层同步：Blender 里改了，UE 编辑器里 0.1–2 秒就能看到。改东西的主要是脚本，人手改也行。做法参照 D5 Render 的 LiveSync（Rhino ↔ D5）。

*Live sync from Blender to Unreal Engine 5 for the game project 人偶之心: Blender owns layout and geometry, UE owns materials, lighting and scatter; changes travel as a small cumulative override file and are applied to instanced meshes in place.*

## 分工（和 D5 一样）

| | Blender 管（同步推过去） | UE 管（同步永远不碰） |
|---|---|---|
| 内容 | 用哪个件、位置、旋转、缩放、增删；件本身的网格 | 材质、灯光、天空和雾、后期、植被和草、水、特效、机位 |
| 在哪改 | Blender：脚本，或者人手改 | UE 编辑器 |

- 只做 Blender → UE 单向，不回传。UE 里依赖 Blender 几何的散布（PCG 草、植被、碎石），同步后由 UE 自己重算。
- 材质靠**材质槽名**对应：Blender 只给槽起名，UE 按名字套自己的材质。形状改了，槽名不变，UE 的材质就留着。

## 怎么工作

1. Blender 写一个累计的覆盖文件 `<批>_overrides.json`（`renou-overrides/1`），里面是和正式摆放表（`renou-placements/1`）的全部差异，原子写入。
2. UE 编辑器里的 `bl_sync` 每秒看它 10 次，按实例 id 原地修改 HISM 实例，不重导，也不存关卡。
3. 某个件的网格改了，只导出这一件的 GLB，UE 导入后换上，所有用这件的实例一起变，材质按槽名沿用 UE 的。
4. 满意了调 `write_back()`，生成新版摆放表和改动说明，由工程发布正式版。

实测（服务器测试工程，708 个实例）：挪、转、换件、删除、复制 0.08–0.20 秒；单件网格重导约 0.9 秒；笔记本经 ssh 推送约 1 秒。之前整块导入一次要 70 秒。

## 目录

| 路径 | 内容 |
|---|---|
| `blender/renou_blsync_lib.py` | **R1 函数库**（唯一一份）：载入批、按楼分组、挪、绕楼中心转、换件、复制、删除、单件导出、发布并等回执、写回、本机经 ssh 推送 |
| `blender/renou_blsync/` | **Blender 插件（LS01）**：实时开关（对应 D5 的开始/暂停）、变化监听、侧栏面板 View3D > N > Renou。底座就是上面的函数库 |
| `tools/build_addon.py` | 打出可安装的插件 zip（把函数库一起打进去） |
| `ue/Content/Python/` | UE 侧接收器：`bl_sync_core.py`、`bl_sync.py`、`bl_setup_level.py`。依赖视效工程里的 `lk_session.py` 请求通道（不在本仓库） |
| `tools/req.py` | 向 UE 请求通道发命令的小工具 |
| `tests/` | 不需要 UE 的自测：`make_fixture.py` 生成合成数据（纯方盒，不含任何团队素材），`mock_ue_receiver.py` 是假的 UE 接收器，`test_lib_mock.py` 跑一遍完整流程 |
| `tests/ue_probes/` | 只能在装了 UE 的服务器上跑的探针（材质指纹、存盘只读测试） |
| `examples/server/` | 服务器上用真实批次跑过的脚本，路径是服务器上的，仅作参考 |
| `docs/` | 需求（按 D5 分工）、Blender 侧插件任务书 SPEC_v2、使用说明、给工程的脚本摆楼说明、现成工具调研 |

## 跑自测（不需要 UE）

需要 Blender 5.2.2：

```bash
blender -b --factory-startup --python-exit-code 1 --python tests/test_lib_mock.py -- build
blender -b --factory-startup --python-exit-code 1 --python tests/test_addon_mock.py -- build
```

两套最后一行都是 `RESULT OK` 就算通过，退出码 0。当前函数库 53 项、插件 19 项全部通过。GitHub Actions 每个 PR 也会自动跑。

函数库测试包括远程模式：`tests/fake_ssh.py` 把假 `ssh` / `scp` 放到 PATH 最前面，只在临时本地目录里模拟推送和回执，不连接服务器、不读取 ssh 配置。覆盖 GLB 去重、网格变化后重推、原子写入、回执读取和超时；测试结束恢复 PATH 并清理临时目录。

## 装插件

```bash
python3 tools/build_addon.py
```

生成 `build/renou_blsync-<版本>.zip`，在 Blender 里用“编辑 > 偏好设置 > 插件 > 从磁盘安装”装上。侧栏 Renou 面板依次填摆放表、零件包、覆盖文件，点“载入批”，再打开“实时同步”。

架构和以后的扩展方向见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 脚本登记新的独立物体

在已经载入的批 `B` 中，登记一个 Blender 网格物体：

```python
instance = B.add_object(obj, "P0123456789ab", era="both", src="independent asset")
receipt = B.publish("add independent asset")
```

件名必须是 `P` 加 12 位十六进制，不能与本批已有件重名（大小写也不能碰撞）。返回新实例对象，id 沿用 `<批>_bl…` 规则；复制网格，单独保留世界位置、旋转和三轴缩放，源物体、父级与材质不变。只导出网格和有效材质槽名，不带源材质参数或贴图；后续重导这个新件也保留这条规则。

必须在主线程、物体模式下调用。使用物体的原始网格，不自动应用修改器。支持有父级的世界 TRS；无法用现有 TRS 格式表示的剪切会明确报错。`write_back()` 的新增实例保持 `NEAR`，非均匀缩放保留三轴列表，均匀缩放仍写标量。UE 新独立物体的对象层和材质映射仍需对应 UE issue 完成与实测。

## 现在在做什么

- [x] 第 1 步：楼的摆放、换件、改单件形状（R1–R4、R7）
- [x] LS01 框架初稿：Blender 插件（实时开关、变化监听、面板），底座是 R1 函数库，见 `docs/SPEC_v2_Blender侧.md`
- [x] 第 2 步 Blender 侧：`add_object()` 登记独立物体，生成新件和实例，只导出材质槽名
- [ ] 第 2 步：新的独立大件直接进 UE（永久 id、材质槽契约、未映射槽用醒目占位）
- [ ] 第 3 步：地形、道路、地面按块同步；UE 只在受影响的格子里重跑 PCG

一起改代码的规矩见 [CONTRIBUTING.md](CONTRIBUTING.md)。

本仓库只有代码和文档。游戏素材、摆放数据和服务器配置都不在这里，也不要提交进来。没有附开源许可证。
