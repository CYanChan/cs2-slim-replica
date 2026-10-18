#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 extract 之后、build 之前运行：
删除 depot/2347770 中不再需要的 pak01 编号包，控制 GitHub Actions 磁盘占用。

保留：cfg / maps(de_dust2.vpk, prefabs) / gameinfo.gi / steam.inf / pak01_dir.vpk 等
      build 阶段仍需要的文件。
删除：pak01_000.vpk ... pak01_077.vpk（约 10GB，仅在 extract 阶段用于解包）。
"""

import argparse
import os
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="cs2-build")
    args = ap.parse_args()

    shared = os.path.join(args.workdir, "depot", "2347770", "game", "csgo")
    if not os.path.isdir(shared):
        print(f"[cleanup] WARN: {shared} 不存在，跳过", flush=True)
        return

    removed = 0
    freed = 0
    for fn in sorted(os.listdir(shared)):
        if re.fullmatch(r"pak01_\d+\.vpk", fn):
            p = os.path.join(shared, fn)
            freed += os.path.getsize(p)
            os.remove(p)
            removed += 1

    print(f"[cleanup] 已删除 {removed} 个编号包，释放 {freed / 1024**3:.2f} GB", flush=True)

    for top in ("depot", "loose"):
        d = os.path.join(args.workdir, top)
        if os.path.isdir(d):
            total = sum(os.path.getsize(os.path.join(r, f))
                        for r, _, fs in os.walk(d) for f in fs)
            print(f"[cleanup] {top}/ 当前大小: {total / 1024**3:.2f} GB", flush=True)


if __name__ == "__main__":
    main()