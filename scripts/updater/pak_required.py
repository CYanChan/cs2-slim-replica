#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 pak01_dir.vpk 反查「服务端启动必备文件」引用的编号包。

根治背景 (2026-11-18 事故):
    core/filelists/filelist_2347770.txt 硬编码了 77 个 pak01_NNN.vpk。
    CS2 每次新增地图/资源都会重排归档分配 —— 本次更新把
    scripts/*.vdata_c、gamemodes.txt、workshop_cvar_whitelist.txt 等
    引擎启动必备的 schema 文件挪进了新分配的 pak01_541/544/545/546。
    这些编号不在硬编码清单里 ⇒ DepotDownloader 不下载 ⇒
    extract_vpk.py 记为 missing_archive 跳过 ⇒ 精简树缺文件 ⇒
    引擎初始化解引用空指针 ⇒ SIGSEGV(si_addr=NULL) ⇒ 服务反复重启。

根治原理:
    不写死包号，改为「从 dir.vpk 的目录树里反查必备文件落在哪些包」。
    这样游戏无论怎么重排归档，只要 dir.vpk 更新，清单自动跟随。

用法:
    python scripts/updater/pak_required.py --dir-vpk <path> --format csv
    python scripts/updater/pak_required.py --dir-vpk <path> --format filelist
    python scripts/updater/pak_required.py --dir-vpk <path> --check
"""

import argparse
import fnmatch
import os
import struct
import sys

VPK_MAGIC = 0x55AA1234
TERMINATOR = 0xFFFF
EMBEDDED = 0x7FFF

# 「服务端启动必须存在」的文件类别。
# 依据: 2026-11-18 事故定位 —— 缺 scripts/*.vdata_c 导致引擎 SIGSEGV。
# 只列引擎初始化阶段就要读取的 schema/数据文件，不含客户端渲染资源。
REQUIRED_PATTERNS = (
    "scripts/*.vdata_c",
    "scripts/*.txt",
    "scripts/*.kv3",
    "scripts/**/*.kv3",
    "resource/*.gameevents",
    "cfg/*",
    "gameinfo.gi",
    "gameinfo_branchspecific.gi",
    "steam.inf",
    "gamemodes.txt",
    "gamemodes_server.txt",
    "items/*.txt",
    "misc/*.txt",
)

# 这些 schema 文件缺失会直接导致引擎启动崩溃，体检时逐个核对
CRITICAL_SCHEMAS = (
    "scripts/weapons.vdata_c",
    "scripts/propdata.vdata_c",
    "scripts/decalgroups.vdata_c",
    "scripts/light_styles.vdata_c",
    "scripts/light_style_event_types.vdata_c",
    "scripts/precipitation.vdata_c",
    "scripts/explosion_types.vdata_c",
    "scripts/nav_hulls.vdata_c",
    "scripts/nav_hulls_presets.vdata_c",
    "scripts/navlinks.vdata_c",
    "scripts/workshop_cvar_whitelist.txt",
    "gamemodes.txt",
)


def _read_null_string(buf, offset):
    end = buf.find(b"\x00", offset)
    if end == -1:
        raise ValueError(f"未找到字符串结束符，偏移 {offset}")
    return buf[offset:end].decode("utf-8", errors="replace"), end + 1


def normalize_path(path):
    if path == " ":
        return ""
    return path.strip().replace("\\", "/")


def make_full_path(path, name, ext):
    p = normalize_path(path)
    return f"{p}/{name}.{ext}" if p else f"{name}.{ext}"


def iter_entries(dir_vpk):
    """流式产出 (full_path, archive_index, entry_length)。只读目录树，不碰数据。"""
    with open(dir_vpk, "rb") as f:
        head = f.read(28)
        if len(head) < 12:
            raise ValueError(f"文件太小: {dir_vpk}")
        magic, version = struct.unpack_from("<II", head, 0)
        if magic != VPK_MAGIC:
            raise ValueError(f"VPK magic 不匹配 {magic:#x}: {dir_vpk}")
        if version not in (1, 2):
            raise ValueError(f"不支持的 VPK 版本: {version}")
        tree_size = struct.unpack_from("<I", head, 8)[0]
        header_size = 28 if version == 2 else 12
        f.seek(header_size)
        buf = f.read(tree_size)
        if len(buf) != tree_size:
            raise ValueError(f"目录树截断: 期望 {tree_size} 实读 {len(buf)}")

    pos = 0
    while True:
        ext, pos = _read_null_string(buf, pos)
        if not ext:
            break
        while True:
            sub, pos = _read_null_string(buf, pos)
            if not sub:
                break
            while True:
                name, pos = _read_null_string(buf, pos)
                if not name:
                    break
                if pos + 18 > len(buf):
                    raise ValueError("目录树意外结束（越界）")
                (_crc, preload_len, archive_idx,
                 _off, entry_len, term) = struct.unpack_from("<IHHIIH", buf, pos)
                pos += 18
                if term != TERMINATOR:
                    raise ValueError(f"条目终结符异常 {term:#x}")
                pos += preload_len
                yield make_full_path(sub, name, ext), archive_idx, entry_len


def is_required(full_path):
    lp = full_path.lower()
    for pat in REQUIRED_PATTERNS:
        p = pat.lower()
        if "**" in p:
            prefix = p.split("/**")[0] + "/"
            suffix = p.rsplit("**", 1)[1].lstrip("/")
            if lp.startswith(prefix) and fnmatch.fnmatch(lp, "*" + suffix):
                return True
        elif fnmatch.fnmatch(lp, p):
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description="反查必备文件引用的 pak01 编号包")
    ap.add_argument("--dir-vpk", required=True, help="pak01_dir.vpk 路径")
    ap.add_argument("--format", choices=["csv", "filelist", "json"], default="csv")
    ap.add_argument("--prefix", default="game/csgo",
                    help="filelist 模式的路径前缀")
    ap.add_argument("--check", action="store_true", help="体检模式")
    args = ap.parse_args()

    try:
        entries = list(iter_entries(args.dir_vpk))
    except Exception as e:
        print(f"ERROR: 解析 {args.dir_vpk} 失败: {e}", file=sys.stderr)
        return 1

    total = len(entries)
    required = [(p, a) for p, a, _l in entries if is_required(p)]
    indexes = sorted({a for _, a in required if a != EMBEDDED})
    embedded = sum(1 for _, a in required if a == EMBEDDED)

    print(f"[pak_required] {os.path.basename(args.dir_vpk)}: 条目 {total}", file=sys.stderr)
    print(f"[pak_required] 必备文件 {len(required)} (内联 {embedded}, "
          f"来自编号包 {len(required) - embedded})", file=sys.stderr)
    print(f"[pak_required] 引用编号包 {len(indexes)} 个: "
          f"{','.join(f'{i:03d}' for i in indexes[:20])}"
          f"{'...' if len(indexes) > 20 else ''}", file=sys.stderr)

    if args.check:
        have = {p for p, _a, _l in entries}
        print("\n=== 关键 schema 存在性 ===", file=sys.stderr)
        miss = 0
        for m in CRITICAL_SCHEMAS:
            ok = m in have
            if not ok:
                miss += 1
            print(f"  {'OK    ' if ok else 'ABSENT'} {m}", file=sys.stderr)
        print(f"[pak_required] 关键文件缺失 {miss}/{len(CRITICAL_SCHEMAS)}", file=sys.stderr)
        if miss:
            print("[pak_required] 警告: 缺关键 schema，精简树启动会崩溃", file=sys.stderr)
            return 2
        return 0

    if args.format == "csv":
        print(",".join(f"{i:03d}" for i in indexes))
    elif args.format == "filelist":
        base = args.prefix.rstrip("/")
        print(f"{base}/pak01_dir.vpk")
        for i in indexes:
            print(f"{base}/pak01_{i:03d}.vpk")
    else:
        import json
        print(json.dumps({
            "dir_vpk": os.path.abspath(args.dir_vpk),
            "entries": total,
            "required_files": len(required),
            "archive_indexes": indexes,
        }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
