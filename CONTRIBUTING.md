# 一起改代码的规矩（Claude、GPT/Codex、其他 bot 都适用）

## 分工

- **维护者：Ash**（2026-10-09 起，用户指定）。负责整个仓库的代码：写功能、审 PR、合并。框架初稿由协调（Claude）写好交接。
- **UE 实测：**「Blender→UE 实时预览」这个 Claude 会话。CI 和 bot 都没有 UE，凡是动到 `ue/` 的 PR，或者改了覆盖文件、回执含义的 PR，合并前都要等它在服务器的 UE 测试工程上实测，在 PR 里留言“UE 实测通过”。
- GPT/Codex 和其他 bot：按 issue 写确定性的部分（标了 `good-for-bot` 的），提 PR 给维护者。
- 协调（Claude）：分任务、定优先级、和用户确认需求。需求以 `docs/需求_按D5分工.md` 为准。

## 怎么改

1. 不直接推 `main`。从 `main` 开分支，名字写清楚，比如 `ls01-panel`、`fix-quat-sign`。
2. 改完跑自测，两套都必须 `RESULT OK`（CI 也会跑）：
   ```bash
   blender -b --factory-startup --python-exit-code 1 --python tests/test_lib_mock.py -- build
   blender -b --factory-startup --python-exit-code 1 --python tests/test_addon_mock.py -- build
   ```
   加了新功能，就在对应的测试里加检查。函数库的进 `test_lib_mock.py`，插件的进 `test_addon_mock.py`。
3. 提 PR，说明写：改了什么、为什么、自测结果。动到 UE 侧的，写明“需要 UE 实测”，等实时预览会话测完再合并。
4. **只有一份函数库。** 不要另起一套；插件只调库，不重复实现。要改 `renou_blsync_lib.py` 的已有接口（函数名、参数、覆盖文件格式），先开 issue 说明理由，维护者同意后再改；只加新函数不算改接口。
5. 线程规矩：读写 Blender 数据（bpy）只在主线程；工作线程只做写文件、ssh 推送、等回执。

## 不能做的

- 不提交任何游戏素材：GLB、blend、uasset、贴图、Megascans，以及真实的摆放表和零件包。测试一律用 `tests/make_fixture.py` 生成的合成数据。
- 不提交账号、密码、密钥、令牌，不提交服务器地址或 ssh 配置。远程推送只调用系统里已经配好的 `ssh`/`scp`，地址做成参数，默认空。
- 不改覆盖文件格式 `renou-overrides/1` 和摆放表格式 `renou-placements/1` 的已有字段含义。
- 同步永远不碰 UE 管的东西：材质、灯光、雾、后期、植被、水、机位。Blender 的材质不传，只传槽名。
- 不开网络端口，不加第三方依赖：Blender 侧只用 Blender 自带的 Python 和 glTF 插件，UE 侧只用 UE 自带的 Python。

## 坐标和格式速查

- Blender 世界坐标，米，Z 朝上；四元数按 wxyz 排列，w < 0 时整体取反。
- 覆盖文件是累计的：所有和摆放表不同的实例都要列出来，改回原样的要去掉。写入用原子方式，先写 `.tmp` 再 `os.replace`。
- 新增实例 id 用 `<批>_bl…`，必须带 `part`、`era`、`src`。
- 详细说明见 `docs/SPEC_v2_Blender侧.md`。
