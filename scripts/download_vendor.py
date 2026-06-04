#!/usr/bin/env python3
"""下载前端 CDN 依赖到 static/vendor/，实现离线运行。"""

import urllib.request
import os
import sys

VENDOR_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "vendor")

DEPENDENCIES = {
    "alpinejs.min.js": "https://cdn.jsdelivr.net/npm/alpinejs@3.13.0/dist/cdn.min.js",
    "daisyui.min.css": "https://cdn.jsdelivr.net/npm/daisyui@4.4.0/dist/full.min.css",
    "tailwind.min.css": "https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css",
    "marked.min.js": "https://cdn.jsdelivr.net/npm/marked@11.0.0/marked.min.js",
}

def download():
    os.makedirs(VENDOR_DIR, exist_ok=True)
    for name, url in DEPENDENCIES.items():
        dest = os.path.join(VENDOR_DIR, name)
        if os.path.exists(dest):
            print(f"  ✓ {name} (已存在)")
            continue
        print(f"  ↓ 下载 {name} ...", end=" ", flush=True)
        try:
            urllib.request.urlretrieve(url, dest)
            print("✓")
        except Exception as e:
            print(f"✗ 失败: {e}")
            return False
    print(f"\n完成！{len(DEPENDENCIES)} 个依赖已下载到 {VENDOR_DIR}")
    return True

if __name__ == "__main__":
    sys.exit(0 if download() else 1)
