# 纯手动复刻 CS2 精简服务端（仅用 DepotDownloader + Source2Viewer-CLI）

> 本指南由 [cs2-slim-replica](https://github.com/cyqmq/cs2-slim-replica) 项目收录，作为官方「纯手动复刻」参考；如需自动化构建 / 一键脚本 / 功能组件，见项目 README。
>
> 本文不依赖任何现成的精简仓库/脚本，只用两个通用开源工具，从 Steam depot 手动拉取并拼装出一个可运行的 CS2 精简服务端（约 1.7GB，单地图 de_dust2）。
>
> 工具：
> - **DepotDownloader** — Steam depot 精确下载（GitHub: `SteamRE/DepotDownloader`）
> - **Source2Viewer-CLI** — ValveResourceFormat 的命令行版，负责 VPK 解析与提取（官网: https://s2v.app ）

---

## 一、原理回顾（为什么能精简）

- CS2 服务端 72.3GB 里，约 53GB 是 `game/csgo/pak01_*.vpk`（其中 44GB 是客户端纹理、4.4GB 音频）。
- **服务器进程不渲染、不播音**，这些纯客户端资产可以不要。
- 但引擎会通过 `pak01_dir.vpk` 索引全部编号包，缺包即 FATAL，所以不能直接删。
- 利用 Source 2 加载优先级 **`loose files > addon VPK > game VPK`**：
  把服务器需要的文件从编号包里**提取成散文件**放回 `csgo/`，然后**移走全部编号包**，引擎就只读散文件，不会再碰 VPK。

---

## 二、准备工作

### 2.1 下载工具

| 工具 | 获取方式 |
|------|---------|
| DepotDownloader | GitHub `SteamRE/DepotDownloader` Releases → 下载对应平台 zip，解压后得到可执行文件（Linux 是 `DepotDownloader`，Windows 是 `DepotDownloader.exe`） |
| Source2Viewer-CLI | https://s2v.app → Download → 选择 `Source2Viewer-CLI`（Linux 二进制 / Windows exe） |

Linux 下如果运行 Source2Viewer-CLI 报 libicu 缺失：
```bash
apt install -y libicu72        # Debian/Ubuntu
# 或免安装：
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
```

### 2.2 磁盘预算

| 阶段 | 占用 |
|------|-----|
| depot 原始下载（filelist 精选） | ~7GB |
| 提取出的 loose files | ~0.6GB |
| 最终精简树 | ~1.7GB 解压后 |

建议预留 **20GB** 磁盘。

---

## 三、第一步：拉取 depot manifest（只分析，不下载）

CS2（AppID 730）相关的 depot：

| Depot ID | 内容 | 体积 |
|----------|------|------|
| 2347770 | 共享内容（csgo 资产 + core 引擎） | ~65GB |
| 2347773 | Linux 服务端二进制 | ~7.2GB |
| 2347771 | Windows 服务端二进制 | ~7GB |

用 DepotDownloader 只拉 manifest，生成人类可读的文件清单：
```bash
mkdir -p manifests
./DepotDownloader -app 730 -depot 2347770 -manifest-only -dir manifests
./DepotDownloader -app 730 -depot 2347773 -manifest-only -dir manifests
./DepotDownloader -app 730 -depot 2347771 -manifest-only -dir manifests
```

manifest 会输出到 `manifests/`，用于确认文件路径、大小，以及写 filelist 时抄路径。

---

## 四、第二步：编写 filelist 精确下载

DepotDownloader 的 `-filelist` 支持三种行：
```text
精确路径:        game/csgo/maps/de_dust2.vpk
通配路径:        game/csgo/maps/prefabs/*
正则:            regex:.*\.vpk$
```

### 4.1 共享内容（depot 2347770）的 filelist

关键：**不能只下 pak01_dir.vpk**，目录索引必须连它索引到的编号块一起下，否则提取时找不到数据。

```text
# —— VPK 目录索引（必须）——
game/csgo/pak01_dir.vpk
game/core/pak01_dir.vpk

# —— 含服务器必需数据的编号包（按需迭代补充，见第八节踩坑）——
game/csgo/pak01_003.vpk
game/csgo/pak01_009.vpk
game/csgo/pak01_022.vpk
game/csgo/pak01_039.vpk
game/csgo/pak01_050.vpk
game/csgo/pak01_064.vpk
game/csgo/pak01_081.vpk
game/csgo/pak01_099.vpk
game/csgo/pak01_106.vpk
game/csgo/pak01_107.vpk
game/csgo/pak01_109.vpk
game/csgo/pak01_136.vpk
game/csgo/pak01_140.vpk
game/csgo/pak01_141.vpk
game/csgo/pak01_147.vpk
game/csgo/pak01_157.vpk
game/csgo/pak01_158.vpk
game/csgo/pak01_160.vpk
game/csgo/pak01_166.vpk
game/csgo/pak01_176.vpk
game/csgo/pak01_178.vpk
game/csgo/pak01_187.vpk
game/csgo/pak01_188.vpk
game/csgo/pak01_190.vpk
game/core/pak01_004.vpk
game/core/pak01_005.vpk
# ……（首次可按此集合下载；启动报缺哪个包就补哪个，见第八节）

# —— 地图与 prefabs（必须）——
game/csgo/maps/de_dust2.vpk
game/csgo/maps/prefabs/*

# —— 服务器散配置 ——
game/csgo/cfg/*
game/csgo/gameinfo.gi
game/csgo/gameinfo_branchspecific.gi
game/csgo/steam.inf
game/core/gameinfo.gi
game/core/gameinfo_branchspecific.gi
```

### 4.2 服务端二进制（depot 2347773，Linux）

```text
game/bin/linuxsteamrt64/*
game/csgo/bin/linuxsteamrt64/*
```

（Windows 则用 depot 2347771，路径换成 `game/bin/win64/*` 和 `game/csgo/bin/win64/*`。）

### 4.3 执行下载

```bash
mkdir -p cs2_depot
./DepotDownloader -app 730 -depot 2347770 -filelist csgo_filelist.txt -dir cs2_depot -os linux -osarch 64
./DepotDownloader -app 730 -depot 2347773 -filelist bin_filelist.txt  -dir cs2_depot -os linux -osarch 64
```

> `-os linux -osarch 64` 显式指定目标平台；Windows 上换 `-os windows`。
> 下载公开内容不需要登录；如遇旧 manifest 权限问题，加 `-username 你的账号` 交互登录。

---

## 五、第三步：用 Source2Viewer-CLI 提取 loose files

### 5.1 确认 VPK 结构

```bash
cd cs2_depot/game/csgo
./Source2Viewer-CLI -i pak01_dir.vpk --vpk_list | head -50
```

你会看到 VPK 内的路径形如 `models/...`、`materials/...`、`textures/...`（不带 `game/csgo` 前缀）。

### 5.2 提取服务器需要的目录

**保留**（服务器运行必需）：
- `models/`（碰撞体/命中盒/物理）
- `materials/`（材质表面属性）
- `particles/`（粒子定义）
- `resource/`（游戏数据）
- `scripts/`（脚本/配置）
- `weapons/`、`characters/`（武器/角色数据）
- `soundevents/`（音效事件表，服务器要读触发逻辑）

**排除**（纯客户端）：
- `textures/`（44GB 纹理）
- `sounds/`（音频采样）
- `panorama/`、`stickers/`、`patches/`、`sprays/`、`shaders/`（UI/贴纸/着色器）

用 `--vpk_filepath`（匹配路径开头，逗号分隔多个）精确提取：
```bash
mkdir -p loose
./Source2Viewer-CLI -i pak01_dir.vpk -o loose \
  --vpk_filepath "models/,materials/,particles/,resource/,scripts/,weapons/,characters/,soundevents/"
```

> 不加 `--vpk_decompile`，输出的是**编译后原样文件**（`.vmdl_c`、`.vmat_c` 等），这正是服务器需要的格式。
> `pak01_dir.vpk` 是 multi-chunk 的索引，Source2Viewer-CLI 会自动读取同目录的 `pak01_*.vpk` 编号块。

core 引擎同样提取（排除客户端工具/UI）：
```bash
cd ../core
mkdir -p loose_core
./Source2Viewer-CLI -i pak01_dir.vpk -o loose_core \
  --vpk_filepath "engine/,cfg/,resource/,scripts/"   # 根据实际 --vpk_list 结果调整
```
（core 体积小，也可以直接 `-o loose_core` 全量提取后手动删掉 `panorama/`、`tools/`。）

### 5.3 验证提取结果

```bash
find loose -type f | wc -l          # 预期约 1.9 万个文件，~550MB
du -sh loose
```

---

## 六、第四步：手动组装精简树

```bash
mkdir -p slim/game
cd slim

# 1) 服务端二进制（来自 depot 2347773）
cp -r ../cs2_depot/game/bin/linuxsteamrt64        game/bin/
cp -r ../cs2_depot/game/csgo/bin/linuxsteamrt64   game/csgo/bin/

# 2) 共享内容：loose files 按 VPK 内相对路径放回 game/csgo
cp -r ../cs2_depot/game/csgo/loose/*             game/csgo/

# 3) 引擎 core
cp -r ../cs2_depot/game/core/loose_core/*        game/core/

# 4) 服务器散配置 + 地图 + prefabs
cp -r ../cs2_depot/game/csgo/cfg                  game/csgo/cfg
cp    ../cs2_depot/game/csgo/maps/de_dust2.vpk    game/csgo/maps/
cp -r ../cs2_depot/game/csgo/maps/prefabs         game/csgo/maps/
cp    ../cs2_depot/game/csgo/gameinfo.gi          game/csgo/
cp    ../cs2_depot/game/csgo/gameinfo_branchspecific.gi  game/csgo/
cp    ../cs2_depot/game/csgo/steam.inf            game/csgo/
cp    ../cs2_depot/game/core/gameinfo.gi          game/core/
cp    ../cs2_depot/game/core/gameinfo_branchspecific.gi  game/core/

# 5) 移走所有编号包（核心！）
rm -f game/csgo/pak01_*.vpk
rm -f game/core/pak01_*.vpk
```

> 精简树里**绝不能残留任何 `pak*_dir.vpk` 或 `pak01_*.vpk`**，否则引擎会挂载索引并找编号块。

最终结构：
```text
slim/
├── game/
│   ├── bin/linuxsteamrt64/          # cs2 服务端主程序 + 依赖 .so
│   ├── core/                     # 引擎核心（loose files + gameinfo.gi）
│   └── csgo/
│       ├── bin/linuxsteamrt64/   # csgo 层二进制
│       ├── cfg/                  # 服务器配置
│       ├── maps/de_dust2.vpk     # 地图
│       ├── maps/prefabs/         # 地图预置实体（必须）
│       ├── models/ materials/ particles/ resource/ scripts/ weapons/ characters/ soundevents/  # loose files
│       ├── gameinfo.gi
│       └── steam.inf
```

---

## 七、第五步：部署与启动

### 7.1 steamclient.so（64 位）

CS2 需要 64 位 `steamclient.so`，新版 SteamCMD 已不带，从 Steam SDK 包获取：
```bash
curl -fsSL -o manifest.txt https://client-update.akamai.steamstatic.com/steam_client_ubuntu12
SDK_FILE=$(grep -A4 '"bins_sdk_ubuntu12"' manifest.txt | grep '"file"' | sed -n 's/.*"file"[[:space:]]*"\([^"]*\)".*/\1/p')
curl -fsSL -o bins_sdk.zip "https://steamcdn-a.akamaihd.net/client/$SDK_FILE"
python3 - <<'PY'
import zipfile, os
with zipfile.ZipFile("bins_sdk.zip") as z:
    z.extract("linux64/steamclient.so")
os.replace("linux64/steamclient.so", "steamclient.so")
PY
mkdir -p "$HOME/.steam/sdk64"
ln -sf "$(pwd)/steamclient.so" "$HOME/.steam/sdk64/steamclient.so"
```

### 7.2 V8 库符号链接（关键）

CS2 去 `game/csgo/bin/linuxsteamrt64/` 找 V8 库，但它们实际在 `game/bin/linuxsteamrt64/`：
```bash
cd game/csgo/bin/linuxsteamrt64
for f in libv8.so libv8system.so libv8_icui18n.so libv8_icuuc.so \
         libv8_libbase.so libv8_libcpp.so libv8_libplatform.so libv8_zlib.so; do
  ln -sf "../../../bin/linuxsteamrt64/$f" "$f"
done
cd -
```

### 7.3 可执行权限 + 启动

```bash
chmod +x game/bin/linuxsteamrt64/cs2

./game/bin/linuxsteamrt64/cs2 \
  -dedicated +map de_dust2 +hostname "ManualSlim" \
  -maxplayers 12 -ip 0.0.0.0 -port 27015 \
  -insecure -condebug +game_type 0 +game_mode 0 \
  +sv_pure 0 +sv_cheats 1
```

验证启动日志出现：
```text
[Server] SV:  12 player server started
[Server] CSource2Server::GameServerSteamAPIActivated()
[Networking] Network socket 'server' opened on port 27015
```

---

## 八、踩坑与迭代

### 8.1 缺包 FATAL（最重要）

启动时报：
```text
FATAL ERROR: Error reading from loaded packed store ".../pak01_NNN.vpk"
```
说明该编号包含服务器必需文件。处理：
1. 从 console.log 提取包号 `NNN`
2. 把该包加进 filelist 重新下载
3. **重新用 Source2Viewer-CLI 提取**（因为该包里的必需文件还没进 loose files）
4. 重新组装

重复直到无 FATAL。实测首轮之后通常还要补约 26 个包。

### 8.2 prefabs 缺失 → 服务器回退 Idle

地图加载后 `GameServerSteamAPIDeactivated` 回退 Idle，多半是 `maps/prefabs/` 没复制。补上即可。

### 8.3 启动报 `Failed to load module ... steamclient.so`

- 检查 `$HOME/.steam/sdk64/steamclient.so` 是否为有效 64 位 ELF：`file` 命令应输出 `ELF 64-bit ... x86-64`
- 检查 V8 符号链接是否建立

### 8.4 缺 libicu / Source2Viewer-CLI 跑不起来

```bash
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
```

### 8.5 `-insecure` 必须

精简树缺少完整客户端资产，必须用 `-insecure` 模式（社区服务器常规做法），不要连官方匹配。

---

## 九、参考

| 资源 | 链接 |
|------|------|
| DepotDownloader | https://github.com/SteamRE/DepotDownloader |
| ValveResourceFormat / Source2Viewer-CLI | https://github.com/ValveResourceFormat/ValveResourceFormat |
| Source2Viewer-CLI 命令行文档 | https://s2v.app/ValveResourceFormat/guides/command-line.html |
| CS2 SteamDB depot 信息（2347770/2347771/2347773） | https://steamdb.info/app/730/depots/ |