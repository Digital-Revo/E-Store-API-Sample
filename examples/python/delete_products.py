#!/usr/bin/env python3
"""按 data/products.json 中的 product_id 列表，DELETE 一遍清场。"""

import json
import os
import sys
from pathlib import Path

import requests


def env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"❌ 缺少环境变量 {name}")
    return v.rstrip("/") if name == "E_STORE_HOST" else v


HOST = env("E_STORE_HOST")
TOKEN = env("E_STORE_TOKEN")
AUTH = {"Authorization": f"Bearer {TOKEN}"}

HERE = Path(__file__).parent
products = json.loads((HERE / "data" / "products.json").read_text(encoding="utf-8"))

print(f"➡  从 {HOST} 删除 {len(products)} 个样例商品")
for p in products:
    pid = p["product_id"]
    r = requests.delete(
        f"{HOST}/api/product/",
        params={"product_id": pid},
        headers=AUTH,
        timeout=15,
    )
    print(f"  - {pid}  HTTP {r.status_code}  {r.text[:120]}")
