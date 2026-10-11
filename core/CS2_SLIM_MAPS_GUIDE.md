# CS2 精简服务端 · 地图复刻指南（手动添加竞技地图）

> 本文档属于 [cs2-slim-replica](https://github.com/cyqmq/cs2-slim-replica) 项目文档，与 [《纯手动复刻指南》](CS2_SLIM_GUIDE.md)、[《精简树全解析》](CS2_SLIM_TREE_GUIDE.md) 配套阅读。
>
> 用 DepotDownloader + Source2Viewer-CLI，手动为精简服务端添加任意竞技地图。不依赖任何现成脚本/仓库。
> 原理：CS2 地图是独立的 VPK 文件，存放在 Steam depot 2347770 的 `game/csgo/maps/` 下，只需把地图 VPK 和对应 prefabs（天空盒）下载放入精简树即可。

---

## 一、原理：CS2 地图在 Steam 里是怎么存的

通过拉取 depot 2347770 的 manifest 可以看到，每张竞技地图由两部分组成：

```text
game/csgo/maps/de_mirage.vpk                        ← 地图本体（实体/几何/导航/灯光）
game/csgo/maps/prefabs/de_mirage/3dskybox_mirage.vpk ← 天空盒/3D 远景（prefabs）
game/csgo/maps/de_mirage_vanity.vpk                  ← 客户端装饰（服务器不需要）
```

要点：

- **地图本体**是单个 VPK（不是 multi-chunk），文件名 `de_<图名>.vpk`
- 每张地图在 `maps/prefabs/<图名>/` 下有自己的天空盒 VPK（`*_skybox.vpk`、`3dskybox*.vpk` 等）
- `_vanity.vpk` 是给客户端看的装饰内容（涂鸦/花哨），**服务器不需要，不要下载**
- 服务器加载地图时按 `maps/<图名>.vpk` 读取，并从 `maps/prefabs/<图名>/` 加载天空盒

### 竞技地图真实大小（2026-10-08 manifest）

| 地图 | 地图 VPK | 主要 prefabs |
|------|---------|-------------|
| de_dust2 | 262 MB | `de_dust2_skybox.vpk`（4.8 MB） |
| de_mirage | 176 MB | `3dskybox_mirage.vpk`（4.9 MB） |
| de_inferno | 453 MB | `de_inferno_skybox.vpk`（2.5 MB）+ 多个 3d 天空盒 |
| de_ancient | 405 MB | `de_ancient_skybox.vpk`（52 MB） |
| de_anubis | 270 MB | `de_anubis_skybox.vpk`（2.6 MB） |
| de_cache | 309 MB | `de_cache_sky.vpk`（22.6 MB） |
| de_nuke | 247 MB | `de_nuke_skybox02.vpk`（4.7 MB） |
| de_overpass | 327 MB | 对应 prefabs 目录 |
| de_train | 382 MB | `3dskybox.vpk`（2.1 MB）+ `de_train_skybox.vpk`（5.8 MB） |
| de_vertigo | 191 MB | 对应 prefabs 目录 |

> 体积会随 CS2 更新略有浮动；精确大小以 SteamDB 或 manifest 为准。

---

## 二、工具准备

| 工具 | 用途 | 获取 |
|------|------|------|
| DepotDownloader | 从 Steam depot 下载地图 VPK | https://github.com/SteamRE/DepotDownloader |
| Source2Viewer-CLI | 验证地图 VPK 内容完整性 | https://s2v.app |

---

## 三、第一步：下载地图 VPK

### 3.1 写 filelist

DepotDownloader 的 `-filelist` 每行一个精确路径。以添加 `de_mirage` 为例，创建 `maps.txt`：

```text
game/csgo/maps/de_mirage.vpk
game/csgo/maps/prefabs/de_mirage/3dskybox_mirage.vpk
```

> 如何知道某张地图的 prefabs 具体文件名？
> 先拉 manifest 再 grep，最准确：
> ```bash
> ./DepotDownloader -app 730 -depot 2347770 -manifest-only -dir manifests
> grep "maps/prefabs/de_mirage/" manifests/manifest_*.txt | awk '{print $NF}'
> ```
> 或者去 SteamDB https://steamdb.info/app/730/depots/ 看 depot 2347770 的文件列表。

### 3.2 下载

```bash
./DepotDownloader -app 730 -depot 2347770 -filelist maps.txt -dir cs2_depot -os linux -osarch 64
```

下载完成后文件在 `cs2_depot/game/csgo/maps/` 下（含 prefabs 子目录）。

> 同时下载多张地图：把多行路径写进同一个 `maps.txt` 即可，一次跑完。

---

## 四、第二步：放入精简树

假设精简树在 `~/cs2-slim-build/slim`（或你手动组装的 `slim/`）：

```bash
cd cs2_depot/game/csgo

# 1) 地图本体 VPK
cp maps/de_mirage.vpk ~/cs2-slim-build/slim/game/csgo/maps/

# 2) 对应 prefabs（天空盒）——必须！
mkdir -p ~/cs2-slim-build/slim/game/csgo/maps/prefabs/de_mirage
cp -r maps/prefabs/de_mirage/* ~/cs2-slim-build/slim/game/csgo/maps/prefabs/de_mirage/
```

> 精简树里已自带 `de_dust2.vpk` 和 `maps/prefabs/de_dust2/`，新地图按同样结构追加即可。
> 本仓库核心包的核心清单已包含**全部竞技地图的 prefabs**（见 `core/filelists/filelist_2347770.txt`），因此使用本仓库构建的精简树通常已自带 `maps/prefabs/<图名>/`，此步可跳过或用于覆盖更新。

---

## 五、第三步：配置与启动

### 5.1 直接指定地图启动

```bash
cd ~/cs2-slim-build/slim
./game/bin/linuxsteamrt64/cs2 \
  -dedicated +map de_mirage +hostname "Slim Mirage" \
  -maxplayers 12 -ip 0.0.0.0 -port 27015 \
  -insecure -condebug +game_type 0 +game_mode 0 \
  +sv_pure 0 +sv_cheats 1
```

### 5.2 配置地图循环（mapcycle）

CS2 服务器首次启动会在 `game/csgo/cfg/` 自动生成 `mapcycle.txt`。手动编辑：

```text
de_dust2
de_mirage
de_inferno
```

然后在启动参数加 `+mapgroupname mg_active`（竞技图组）或用 `sm_nextmap` 之类的插件管理。最简方式：启动后控制台输入 `changelevel de_mirage` 即可切换。

---

## 六、验证地图 VPK 完整性

用 Source2Viewer-CLI 检查地图 VPK 内容是否正常：

```bash
# 列出地图 VPK 内的关键资源
./Source2Viewer-CLI -i de_mirage.vpk --vpk_list | head -40
# 应看到 world/ entities/ 等条目
./Source2Viewer-CLI -i de_mirage.vpk --vpk_list | grep -E "world|entities|spawn"
```

确认地图能被解析、条目完整，再放进精简树启动。

---

## 七、踩坑清单

| 坑 | 现象 | 解决 |
|----|------|------|
| 只下地图 VPK，没下 prefabs | 地图加载后天空盒缺失/黑背景，或加载异常 | 补下 `maps/prefabs/<图名>/` 下所有 VPK |
| 下载了 `_vanity.vpk` | 白白多下几 MB~几十 MB，服务器用不到 | 忽略所有 `*_vanity.vpk` |
| 路径写错 | DepotDownloader 报 `No files matched` | 用 manifest grep 确认精确路径 |
| 地图名带 `.vpk` 启动 | 服务器找不到地图 | 启动参数用 `+map de_mirage`（不带后缀） |
| `-insecure` 缺失 | 精简树校验失败/连不上 | 保持 `-insecure` 启动 |
| 想确认地图 VPK 是否损坏 | 启动时报地图读取错误 | 用 Source2Viewer-CLI `--vpk_verify` 校验 |

---

## 八、参考

| 资源 | 链接 |
|------|------|
| SteamDB CS2 depots（查文件路径/大小） | https://steamdb.info/app/730/depots/ |
| DepotDownloader | https://github.com/SteamRE/DepotDownloader |
| Source2Viewer-CLI 文档 | https://s2v.app/ValveResourceFormat/guides/command-line.html |
| 本仓库地图组件（预构建包/注册表） | https://github.com/cyqmq/cs2-slim-maps |