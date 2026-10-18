#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""准备 GitHub Actions 重建所需工具：
1. DepotDownloader (linux-x64)
2. steamclient 文件：
   - linux: bins_sdk_ubuntu12.zip 中的 linux64/steamclient.so
   - win64: bins_win32.zip 中的 steamclient64.dll / tier0_s64.dll / vstdlib_s64.dll
"""

import argparse
import os
import re
import shutil
import sys
import urllib.request
import zipfile

DD_URL = "https://github.com/SteamRE/DepotDownloader/releases/latest/download/DepotDownloader-linux-x64.zip"
LINUX_MANIFEST_URL = "https://client-update.akamai.steamstatic.com/steam_client_ubuntu12"
WIN_MANIFEST_URL = "https://client-update.akamai.steamstatic.com/steam_client_win32"


def download(url, dst, label):
    print(f"[prepare] 下载 {label}: {url}", flush=True)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    tmp = dst + ".part"
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, dst)
    print(f"[prepare] {label} -> {dst} ({os.path.getsize(dst)} bytes)", flush=True)


def extract_zip(zip_path, members, out_dir):
    with zipfile.ZipFile(zip_path) as z:
        for m in members:
            z.extract(m, out_dir)
            print(f"[prepare] 解压 {m} -> {os.path.join(out_dir, m)}", flush=True)


def get_steamclient(platform, tools_dir):
    """下载并放置 steamclient 文件到 <workdir>/tools/ 下。"""
    if platform == "linux":
        manifest_url = LINUX_MANIFEST_URL
        zip_key = "bins_sdk_ubuntu12"
        member = "linux64/steamclient.so"
        dst_dir = os.path.join(tools_dir, "steamclient64")
        marker = os.path.join(dst_dir, "steamclient.so")
        members = [member]
    else:
        manifest_url = WIN_MANIFEST_URL
        zip_key = "bins_win32"
        members = ["steamclient64.dll", "tier0_s64.dll", "vstdlib_s64.dll"]
        dst_dir = os.path.join(tools_dir, "steamclient64_win")
        marker = os.path.join(dst_dir, "steamclient64.dll")

    if os.path.exists(marker) and os.path.getsize(marker) > 1_000_000:
        print(f"[prepare] {marker} 已存在，跳过", flush=True)
        return

    content = download_text(manifest_url, f"steam_client_{platform}")
    m = re.search(r'"%s\.zip\.([0-9a-f]+)"' % zip_key, content)
    if not m:
        sys.exit(f"ERROR: 无法在 Steam manifest 中找到 {zip_key}.zip 的哈希")
    zip_url = f"https://steamcdn-a.akamaihd.net/client/{zip_key}.zip.{m.group(1)}"
    zip_path = os.path.join("/tmp", f"{zip_key}.zip")
    download(zip_url, zip_path, f"{zip_key}.zip")

    os.makedirs(dst_dir, exist_ok=True)
    extract_zip(zip_path, members, dst_dir)
    if platform == "linux":
        # 将 linux64/steamclient.so 上移为 steamclient64/steamclient.so
        shutil.move(os.path.join(dst_dir, member), marker)
    print(f"[prepare] steamclient 就绪: {dst_dir}", flush=True)


def download_text(url, label):
    tmp = os.path.join("/tmp", label)
    download(url, tmp, f"{label} manifest")
    with open(tmp, encoding="utf-8", errors="replace") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="cs2-build",
                    help="构建工作目录（其下会创建 tools/）")
    ap.add_argument("--platform", choices=["linux", "win64"], required=True)
    args = ap.parse_args()

    tools_dir = os.path.join(args.workdir, "tools")
    os.makedirs(tools_dir, exist_ok=True)

    # DepotDownloader
    dd_zip = os.path.join("/tmp", "DepotDownloader-linux-x64.zip")
    if not os.path.exists(os.path.join(tools_dir, "DepotDownloader")):
        download(DD_URL, dd_zip, "DepotDownloader-linux-x64")
        extract_zip(dd_zip, ["DepotDownloader"], tools_dir)
        dd_bin = os.path.join(tools_dir, "DepotDownloader")
        os.chmod(dd_bin, 0o755)
        print(f"[prepare] DepotDownloader -> {dd_bin}", flush=True)
    else:
        print(f"[prepare] DepotDownloader 已存在，跳过", flush=True)

    get_steamclient(args.platform, tools_dir)
    print("[prepare] 工具准备完成", flush=True)


if __name__ == "__main__":
    main()