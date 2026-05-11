#!/usr/bin/env python3
"""
路线 B：扫一个图片文件夹 → 按平台命名规范自动解析 → 上传。

适用场景：你只有一堆按 <类别>-<4位数字><变体>[(N)].<ext> 命名的图，没有
预先准备好的 products.json。脚本会：

  1) 调 parser.group_by_product() 把文件名解析成 task：
       同一 product_id 的不同变体合并；
       同一变体的多张图按 (1)(2)... 序号排序。
  2) 顺序上传每张图到 /api/file_to_url（folder = "<store_id>/<--group>"）
  3) POST /api/product/ 一次性带 images（扁平 URL 列表）+ grouped_images
       （按变体码分组的 URL 列表）+ category（解析得到）+ 可选 price。

完全对应 E-Store-Panel 批量上传页 (productImportTool) 的行为，但跑在你
本地，结果跟人肉点 Panel 等价。

用法：
  pip install -r requirements.txt
  export E_STORE_HOST=https://e-store-00.xenotech.studio
  export E_STORE_TOKEN=<panel 生成的 token>
  python auto_upload_from_folder.py ./path/to/images/
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

from parser import group_by_product


def env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"❌ 缺少环境变量 {name}")
    return v.rstrip("/") if name == "E_STORE_HOST" else v


HOST = env("E_STORE_HOST")
TOKEN = env("E_STORE_TOKEN")
AUTH = {"Authorization": f"Bearer {TOKEN}"}

STORE_ID = urlparse(HOST).hostname.split(".")[0]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def upload_image(image_path: Path, group: str) -> str:
    folder = f"{STORE_ID}/{group}"
    with open(image_path, "rb") as f:
        r = requests.post(
            f"{HOST}/api/file_to_url",
            files={"file": (image_path.name, f)},
            data={"folder": folder},
            headers=AUTH,
            timeout=60,
        )
    if r.status_code != 200:
        raise RuntimeError(
            f"上传 {image_path.name} 失败 HTTP {r.status_code}：{r.text[:300]}"
        )
    return r.json()["url"]


def upsert_product(pid: str, body: dict) -> dict:
    r = requests.post(
        f"{HOST}/api/product/",
        params={"product_id": pid},
        json=body,
        headers={**AUTH, "Content-Type": "application/json"},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"upsert {pid} 失败 HTTP {r.status_code}：{r.text[:300]}"
        )
    return r.json()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(f"用法：python {Path(sys.argv[0]).name} <image_dir> [--group <NAME>]")

    image_dir = Path(sys.argv[1]).resolve()
    if not image_dir.is_dir():
        sys.exit(f"❌ {image_dir} 不是一个目录")

    group = "SAMPLE"
    if "--group" in sys.argv:
        i = sys.argv.index("--group")
        if i + 1 < len(sys.argv):
            group = sys.argv[i + 1]

    image_files = sorted(
        [
            f for f in image_dir.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        ]
    )
    if not image_files:
        sys.exit(f"❌ {image_dir} 下没有 .jpg/.jpeg/.png/.webp 文件")

    print(f"➡  目标实例: {HOST}（store_id={STORE_ID}）")
    print(f"➡  扫描目录: {image_dir}")
    print(f"➡  上传 group: {group}（COS folder = IMAGES/{STORE_ID}/{group}/）")
    print(f"➡  发现图片: {len(image_files)} 张")

    name_to_path = {f.name: f for f in image_files}
    tasks = group_by_product([f.name for f in image_files])

    parsed_count = sum(len(t["image_filenames"]) for t in tasks)
    skipped = len(image_files) - parsed_count
    if skipped > 0:
        print(f"⚠  {skipped} 张文件名无法解析，已跳过")

    if not tasks:
        sys.exit("❌ 没有任何文件名能解析。请检查命名是否符合 <类别>-<4位数字><变体>[(N)].<ext>")

    print(f"➡  解析出 {len(tasks)} 个商品\n")

    for task in tasks:
        pid = task["product_id"]
        variants = list(task["grouped_images"].keys())
        print(f"---- {pid}  (类别={task['category']}, 变体={variants}, "
              f"价格={task['price']}) ----")

        # 上传每张图，记下 filename → URL 映射
        url_by_fname: dict[str, str] = {}
        for fname in task["image_filenames"]:
            print(f"  ↑ 上传 {fname} ...")
            url = upload_image(name_to_path[fname], group)
            url_by_fname[fname] = url

        grouped_urls = {
            variant: [url_by_fname[fn] for fn in fnames]
            for variant, fnames in task["grouped_images"].items()
        }
        all_urls = [url_by_fname[fn] for fn in task["image_filenames"]]

        body: dict = {
            "product_id": pid,
            "category": task["category"],
            "images": all_urls,
            "grouped_images": grouped_urls,
        }
        if task["price"] is not None:
            body["price"] = task["price"]

        resp = upsert_product(pid, body)
        verb = (
            "✚ 新建" if resp.get("created")
            else "↻ 更新" if resp.get("updated")
            else "= 无变化"
        )
        print(f"  {verb}\n")

    print("✅ 全部完成")


if __name__ == "__main__":
    main()
