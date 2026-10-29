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
import time
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


def fetch_appinfo(retries=3):
    """运行 steamcmd 拉取 CS2 appinfo，返回输出文本。

    失败重试原因：SteamCMD 首次运行需要自更新，且 app_info_print 常因 CDN
    抖动/匿名登录未就绪返回空或不完整输出。旧实现只跑一次，一旦空输出整个
    检测就失败（表现为 Actions 红叉或误判"无更新"）。
    这里最多重试 retries 次，解析到 buildid 就提前返回。
    """
    ensure_steamcmd()
    last = ""
    for attempt in range(1, retries + 1):
        print(f"Fetching appinfo for CS2 (730) [第 {attempt}/{retries} 次] ...",
              file=sys.stderr, flush=True)
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
            last = f.read()
        if parse_buildid(last):
            return last
        print(f"第 {attempt} 次未取到 buildid，重试 ...", file=sys.stderr, flush=True)
        time.sleep(5 * attempt)
    return last


def _find_block(text, key, start=0):
    """按 Valve KeyValues 语法取出 "key" { ... } 的块内文本。

    用花括号配平扫描，不依赖相邻键名。旧实现假设 branches 块之后紧跟
    "privatebranches"，一旦 VDF 键序或缩进变化就匹配失败，只能靠兜底正则
    蒙对，属于随时会静默退化的隐患。
    正确跳过字符串内的 { } 与转义引号。
    返回块内文本；找不到返回 None。
    """
    if not text:
        return None
    pat = re.compile(r'"' + re.escape(key) + r'"')
    for m in pat.finditer(text, start):
        i = m.end()
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if i >= len(text) or text[i] != "{":
            # 该 "key" 的值是字符串而非块，继续找下一个同名键
            continue
        depth = 0
        j = i
        in_str = False
        while j < len(text):
            c = text[j]
            if in_str:
                if c == "\\":
                    j += 2
                    continue
                if c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        return text[i + 1:j]
            j += 1
        return None  # 括号不配平，放弃
    return None


def _get_str(block, key):
    """取块内 "key" "value" 的 value。"""
    if not block:
        return ""
    m = re.search(r'"' + re.escape(key) + r'"\s*"([^"]*)"', block)
    return m.group(1) if m else ""


def parse_buildid(log):
    """从 branches -> public 分支提取当前 buildid。

    三级策略，逐级放宽：
      1) branches 块 -> public 块 -> buildid   （最准，不受键序影响）
      2) 任意 public 块 -> buildid
      3) 全文第一个 buildid
    """
    branches = _find_block(log, "branches")
    if branches is not None:
        pub = _find_block(branches, "public")
        if pub is not None:
            bid = _get_str(pub, "buildid")
            if bid.isdigit():
                print(f"[buildid] 策略1命中 (branches->public): {bid}",
                      file=sys.stderr, flush=True)
                return bid

    # 策略2：全局找 public 块
    idx = 0
    while True:
        pub = _find_block(log, "public", idx)
        if pub is None:
            break
        bid = _get_str(pub, "buildid")
        if bid.isdigit():
            print(f"[buildid] 策略2命中 (任意public块): {bid}",
                  file=sys.stderr, flush=True)
            return bid
        pos = log.find('"public"', idx)
        if pos == -1:
            break
        idx = pos + 8

    # 策略3：全文第一个 buildid
    m = re.search(r'"buildid"\s*"(\d+)"', log)
    if m:
        print(f"[buildid] 策略3命中 (全文首个buildid): {m.group(1)}",
              file=sys.stderr, flush=True)
        return m.group(1)

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

    旧实现用固定 3000 字符窗口切片，depot 块偏大时会漏；这里改为先定位
    depots 块，再逐个取 depot 子块，最后取 manifests->public->gid。
    """
    depots = {}
    depots_block = _find_block(log, "depots")
    scope = depots_block if depots_block is not None else log

    for depot in DEPOTS:
        block = _find_block(scope, depot)
        if block is None:
            depots[depot] = ""
            continue
        man = _find_block(block, "manifests")
        if man is None:
            depots[depot] = ""
            continue
        pub = _find_block(man, "public")
        if pub is None:
            depots[depot] = ""
            continue
        gid = _get_str(pub, "gid")
        if not gid:
            m = re.search(r'"gid"\s*"(\d+)"', pub)
            gid = m.group(1) if m else ""
        depots[depot] = gid
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