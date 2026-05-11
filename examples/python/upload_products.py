#!/usr/bin/env python3
"""
E-Store 商品上传 端到端示例

读取 data/products.json，每条记录：
  1) 把 grouped_image_filenames 里每个变体下的本地图通过 POST /api/file_to_url
     上传到 COS，拿到 URL（按变体分组保留）
  2) 把 grouped URL + prices + 元数据合成 product_info，POST /api/product/ upsert

变体（SKU）模型：
  product_info 里的 prices / grouped_images 都是 dict，key 是变体码（如 "AQ"），
  无变体的商品统一用 "默认" 作为唯一 key。

环境变量：
  E_STORE_HOST   你被授权的实例 host（如 https://e-store-00.xenotech.studio）
  E_STORE_TOKEN  你在 Panel "访问管理" 里生成的 manual token

用法：
  pip install -r requirements.txt
  export E_STORE_HOST=...
  export E_STORE_TOKEN=...
  python upload_products.py
"""

import json
import os
import sys
from pathlib import Path

import requests
from urllib.parse import urlparse


def env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"❌ 缺少环境变量 {name}")
    return v.rstrip("/") if name == "E_STORE_HOST" else v


HOST = env("E_STORE_HOST")
TOKEN = env("E_STORE_TOKEN")
AUTH = {"Authorization": f"Bearer {TOKEN}"}

HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
IMG_DIR = DATA_DIR / "images"

# 平台命名规范：folder = "<store_id>/<group>"，其中 store_id 是 host 的首段（如 e-store-00）。
# sample 用 "SAMPLE" 作为 group key，COS 上自然落到 IMAGES/<store_id>/SAMPLE/ 下，便于回收。
STORE_ID = urlparse(HOST).hostname.split(".")[0]
DEFAULT_FOLDER = f"{STORE_ID}/SAMPLE"


def upload_image(image_path: Path, folder: str = DEFAULT_FOLDER) -> str:
    """上传单张图，返回 COS 上的 URL。"""
    with open(image_path, "rb") as f:
        # MIME 由 requests 按文件名自动推断（jpg / png / webp 均支持）
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


def upsert_product(product_id: str, info: dict) -> dict:
    """创建或更新商品。同 product_id 反复调用是 upsert。"""
    r = requests.post(
        f"{HOST}/api/product/",
        params={"product_id": product_id},
        json={"product_id": product_id, **info},
        headers={**AUTH, "Content-Type": "application/json"},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"upsert {product_id} 失败 HTTP {r.status_code}：{r.text[:300]}"
        )
    return r.json()


def main() -> None:
    products = json.loads((DATA_DIR / "products.json").read_text(encoding="utf-8"))
    print(f"➡  目标实例: {HOST}")
    print(f"➡  样例商品数: {len(products)}\n")

    for p in products:
        pid = p["product_id"]
        print(f"---- {pid}：{p['name']} ----")

        # 1) 按变体逐张上传图片，保留变体 → URL 列表的映射
        grouped_filenames: dict = p.pop("grouped_image_filenames", {})
        grouped_images: dict[str, list[str]] = {}
        for variant, fnames in grouped_filenames.items():
            urls: list[str] = []
            for fname in fnames:
                img_path = IMG_DIR / fname
                print(f"  ↑ [{variant}] 上传 {fname} ...")
                url = upload_image(img_path)
                urls.append(url)
                print(f"      → {url}")
            grouped_images[variant] = urls

        # 2) upsert 商品：只用 dict 形式（prices / grouped_images）
        info = {**p, "grouped_images": grouped_images}
        resp = upsert_product(pid, info)
        verb = "✚ 新建" if resp.get("created") else (
            "↻ 更新" if resp.get("updated") else "= 无变化"
        )
        print(f"  {verb}\n")

    print("✅ 全部完成")


if __name__ == "__main__":
    main()
