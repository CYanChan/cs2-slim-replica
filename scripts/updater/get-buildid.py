#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""获取 CS2 (AppID 730) 最新 public_buildid 及关键 depot manifest。

SteamCMD +app_info_print 730 输出结构（关键部分）：
  "branches"
  {
      "public"
      {
          "buildid"   "25966348"
          ...
      }
      ...
  }
  "depots"
  {
      "2347770"
      {
          "manifests"
          {
              "public"   "4758919807587010422"
          }
          ...
      }
  }

每次运行输出 JSON：
{
  "buildid": "25966348",
  "depots": {"2347770": "...", "2347773": "...", "2347771": "..."},
  "checked_at": "2026-10-18T12:00:00Z"
}
"""

import datetime
import json
import os
import re
import subprocess
import sys
import urllib.request

HOME = os.path.expanduser("~")
STEAMCMD_DIR = os.path.join(HOME, "steamcmd")
STEAMCMD = os.path.join(STEAMCMD_DIR, "steamcmd.sh")
STEAMCMD_URL = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz"
APPINFO_LOG = "/tmp/appinfo730.log"

# 关心的 depot: 2347770=共享内容, 2347773=Linux 服务端二进制, 2347771=Windows 服务端二进制
DEPOTS = ("2347770", "2347773", "2347771")


def ensure_steamcmd():
    """安装 SteamCMD（仅首次运行需要）。"""
    if os.path.exists(STEAMCMD):
        return
    print("::group::Installing SteamCMD", file=sys.stderr, flush=True)
    os.makedirs(STEAMCMD_DIR, exist_ok=True)
    tarball = os.path.join("/tmp", "steamcmd_linux.tar.gz")
    print("Downloading SteamCMD ...", file=sys.stderr, flush=True)
    urllib.request.urlretrieve(STEAMCMD_URL, tarball)
    subprocess.run(["tar", "xzf", tarball, "-C", STEAMCMD_DIR], check=True)
    os.chmod(STEAMCMD, 0o755)
    print("::endgroup::", file=sys.stderr, flush=True)


def fetch_appinfo():
    """运行 steamcmd 拉取 CS2 appinfo，返回输出文本。"""
    ensure_steamcmd()
    print("Fetching appinfo for CS2 (730) ...", file=sys.stderr, flush=True)
    # steamcmd 有时因网络/登录返回非零，但日志仍可解析，因此不 check
    with open(APPINFO_LOG, "w", encoding="utf-8") as f:
        subprocess.run(
            [STEAMCMD, "+login", "anonymous", "+app_info_update", "1",
             "+app_info_print", "730", "+quit"],
            stdout=f,
            stderr=subprocess.STDOUT,
            check=False,
        )
    with open(APPINFO_LOG, encoding="utf-8", errors="replace") as f:
        return f.read()


def parse_buildid(log):
    """从 branches -> public 分支提取当前 buildid。"""
    # 精确匹配 branches 区块
    m = re.search(r'"branches"\s*\{(?P<b>.*?)\s*\}\s*"privatebranches"', log, re.S)
    if m:
        pm = re.search(r'"public"\s*\{\s*"buildid"\s*"(\d+)"', m.group("b"))
        if pm:
            return pm.group(1)
    # 兜底：任意位置找 public 分支
    pm = re.search(r'"public"\s*\{\s*"buildid"\s*"(\d+)"', log)
    if pm:
        return pm.group(1)
    return ""


def parse_depot_manifests(log):
    """提取指定 depot 的 public manifest gid。

    SteamCMD 输出中 manifests 是块结构：
        "manifests"
        {
            "public"
            {
                "gid"   "2520908610273941189"
                ...
            }
        }
    """
    depots = {}
    for depot in DEPOTS:
        idx = log.find(f'"{depot}"')
        if idx == -1:
            depots[depot] = ""
            continue
        seg = log[idx:idx + 3000]
        m = re.search(r'"manifests"\s*\{\s*"public"\s*\{\s*"gid"\s*"(\d+)"', seg, re.S)
        depots[depot] = m.group(1) if m else ""
    return depots


def main():
    log = fetch_appinfo()
    buildid = parse_buildid(log)
    if not buildid:
        print("steamcmd output tail:", file=sys.stderr)
        print("\n".join(log.splitlines()[-40:]), file=sys.stderr)
        sys.exit("ERROR: 无法在 steamcmd 输出中找到 public 分支的 buildid，请重试")

    data = {
        "buildid": buildid,
        "depots": parse_depot_manifests(log),
        "checked_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()