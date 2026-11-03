#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""获取 CS2 (AppID 730) 最新 public_buildid 及关键 depot manifest。

★ 2026-11-03 重写(修复"CI 检测不到新版本"):
   原实现依赖 SteamCMD(+app_info_print 730), 但 SteamCMD 的 32 位二进制
   在部分环境跑不起来:
     /root/steamcmd/steamcmd.sh: line 37: /root/steamcmd/linux32/steamcmd:
       cannot execute: required file not found
   该错误导致本脚本恒失败; 而工作流里 `python3 ... | tee current.json`
   又把退出码吞掉, 后面的兜底校验因 heredoc 结束符缩进错误而完全没执行,
   于是 job 一直显示 success、state 永不更新、rebuild 永不触发 ——
   服务器就一直停在旧版本(实测 10-31 之后 10 次 schedule 全是空转)。

   新实现改用纯 HTTP 数据源, 不需要任何二进制:
     主: https://api.steamcmd.net/v1/info/730         (SteamCMD 数据的镜像)
     备: https://api.steampowered.com/ISteamApps/UpToDateCheck/v1/?appid=730&version=0
         返回 required_version 这类数字(如 14195 = 1.41.9.5), 仅用于主源失败时
         在日志里说明"确实落后了", 不参与 buildid 计算。

每次运行输出单行 JSON 到 stdout:
{"buildid":"26393695","depots":{"2347770":"...","2347773":"...","2347771":"..."}}
"""

import json
import sys
import time
import urllib.request

APPID = 730
UA = "cs2-slim-replica-updater/2.0 (+https://github.com/CYanChan/cs2-slim-replica)"

# 关心的 depot: 2347770=共享内容, 2347773=Linux 服务端二进制, 2347771=Windows 服务端二进制
DEPOTS = ("2347770", "2347773", "2347771")

PRIMARY = "https://api.steamcmd.net/v1/info/730"
FALLBACK = ("https://api.steampowered.com/ISteamApps/UpToDateCheck/v1/"
            "?appid=730&version=0")


def _get(url, timeout=60, retries=3):
    """带重试的 GET, 返回 bytes。"""
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            print("第 %d/%d 次请求失败: %s" % (attempt, retries, e),
                  file=sys.stderr, flush=True)
            if attempt < retries:
                time.sleep(5 * attempt)
    raise RuntimeError("全部 %d 次请求失败: %s" % (retries, last))


def fetch_primary():
    """从 steamcmd.net 镜像取 buildid + depot gid。"""
    raw = _get(PRIMARY)
    doc = json.loads(raw.decode("utf-8", "replace"))
    app = doc["data"][str(APPID)]
    depots = app["depots"]
    pub = depots["branches"]["public"]
    bid = str(pub.get("buildid", ""))
    if not bid.isdigit():
        raise RuntimeError("buildid 非法: %r" % (bid,))

    gids = {}
    for d in DEPOTS:
        node = depots.get(d, {}) or {}
        gid = (node.get("manifests", {}) or {}).get("public", {})
        if isinstance(gid, dict):
            gid = gid.get("gid")
        gids[d] = str(gid or "")
    return bid, gids


def fetch_required_version():
    """备用源: Steam 官方 up-to-date 检查, 取 required_version 数字。"""
    raw = _get(FALLBACK, timeout=30, retries=2)
    doc = json.loads(raw.decode("utf-8", "replace"))
    resp = doc.get("response", {})
    return resp.get("required_version"), resp.get("up_to_date"), resp.get("message")


def main():
    try:
        bid, gids = fetch_primary()
    except Exception as e:
        print("主数据源失败: %s" % e, file=sys.stderr, flush=True)
        # 主源挂掉时用官方 up-to-date 说明现状, 但拿不到 buildid
        # → 明确失败退出, 让工作流红掉, 而不是静默 success(这是旧版最大的坑)
        try:
            rv, utd, msg = fetch_required_version()
            print("备用源: required_version=%s up_to_date=%s msg=%s"
                  % (rv, utd, msg), file=sys.stderr, flush=True)
        except Exception as e2:
            print("备用源也失败: %s" % e2, file=sys.stderr, flush=True)
        sys.exit("ERROR: 无法获取 CS2 buildid(主备数据源均失败)")

    print(json.dumps({"buildid": bid, "depots": gids},
                     separators=(",", ":"), sort_keys=False))


if __name__ == "__main__":
    main()
