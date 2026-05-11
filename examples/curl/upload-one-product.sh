#!/usr/bin/env bash
# 单商品端到端：上传 1 张图 + upsert 1 个商品。纯 bash 演示。
#
# 用法：
#   export E_STORE_HOST="https://e-store-00.xenotech.studio"
#   export E_STORE_TOKEN="paste-your-token-here"
#   ./upload-one-product.sh ../python/data/images/ring-gold.png "BASH-DEMO-001" "bash 演示戒指" 99

set -euo pipefail

: "${E_STORE_HOST:?need E_STORE_HOST}"
: "${E_STORE_TOKEN:?need E_STORE_TOKEN}"

IMAGE_PATH="${1:?usage: $0 <image_path> <product_id> <name> <price>}"
PRODUCT_ID="${2:?missing product_id}"
NAME="${3:?missing name}"
PRICE="${4:?missing price}"

echo "[1/2] 上传图片 $IMAGE_PATH ..."
URL=$(curl -sS -X POST "$E_STORE_HOST/api/file_to_url" \
  -H "Authorization: Bearer $E_STORE_TOKEN" \
  -F "file=@$IMAGE_PATH" \
  -F "folder=bash-imports" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["url"])')
echo "      → $URL"

echo "[2/2] upsert 商品 $PRODUCT_ID ..."
curl -sS -X POST "$E_STORE_HOST/api/product/?product_id=$PRODUCT_ID" \
  -H "Authorization: Bearer $E_STORE_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"product_id\":\"$PRODUCT_ID\",\"name\":\"$NAME\",\"price\":$PRICE,\"images\":[\"$URL\"]}" \
  | python3 -m json.tool
