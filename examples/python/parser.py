"""
按平台命名规范解析图片文件名。

与 E-Store-Panel/src/filePreprocess.js 的 parseFileName + handleRead 行为完全等价：

  TSX-2760AQ.jpg            → product_id="TSX-2760",  variant="AQ",    category="TSX"
  TSX-2760AQ(1).jpg         → product_id="TSX-2760",  variant="AQ",    category="TSX"  (序号被剥离)
  AC_1611SZAQ (1).jpg       → product_id="AC-1611",   variant="SZAQ",  category="AC"
  YDJ-7493S(红).jpg         → product_id="YDJ-7493",  variant="S",     category="YDJ"  (中文被剥离)
  R2-0115B-49.8.jpg         → product_id="R2-0115",   variant="B",     category="R2",   price=49.8
  TSX-2760.jpg              → product_id="TSX-2760",  variant="默认",  category="TSX"  (4 位数字后无字母 → 固定字面量 "默认")
  TSX-2760(1).jpg           → 同上，variant="默认"，序号=1

平台技术 product_id 是"类别 + 数字"那段；后面的字母（变体码）单独走 grouped_images。
4 位数字后无字母后缀的商品，按平台约定使用中文 sentinel "默认" 作为唯一变体 key
（与 Panel 的 filePreprocess.js / productImportTool.js 完全一致；不要替换成其他值）。
价格按变体维度聚合，最终输出 prices: {variant: price} 的 dict（对应 API 字段 `prices`）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, TypedDict


_PARENS_EN = re.compile(r"\(.*?\)")
_PARENS_CN = re.compile(r"（.*?）")
_CHINESE = re.compile(r"[一-龥]")
_LEADING_DIGITS = re.compile(r"^(\d+)")
_LEADING_PRICE = re.compile(r"^(\d+(?:\.\d+)?)")
_DASH_RUN = re.compile(r"-+")


class ParsedName(TypedDict):
    product_id: str           # 例 "TSX-2760"
    variant: str              # 例 "AQ"；缺省为 "默认"
    category: str             # 例 "TSX"
    price: Optional[float]    # 文件名第三段开头的数字（单位元）；该变体的价格，缺省 None
                              # 聚合到 ProductTask 时进 prices[variant]


def parse_filename(filename: str) -> Optional[ParsedName]:
    """解析一个文件名，失败返回 None。"""
    base = Path(filename).stem
    base = _PARENS_EN.sub("", base)
    base = _PARENS_CN.sub("", base)
    base = base.replace("_", "-")
    base = _DASH_RUN.sub("-", base)
    base = _CHINESE.sub("", base)

    parts = base.split("-")
    if len(parts) < 2:
        return None

    category = parts[0].strip()
    id_part = parts[1].strip()

    m = _LEADING_DIGITS.match(id_part)
    if not m:
        return None
    num_part = m.group(1)

    product_id = f"{category}-{num_part}"

    variant_raw = id_part[len(num_part):]
    variant = re.sub(r"[^A-Za-z]", "", variant_raw).upper() or "默认"

    price: Optional[float] = None
    if len(parts) >= 3:
        tail = _PARENS_EN.sub("", parts[-1])
        tail = _PARENS_CN.sub("", tail).strip()
        pm = _LEADING_PRICE.match(tail)
        if pm:
            try:
                price = round(float(pm.group(1)) * 10) / 10
            except ValueError:
                price = None

    return {
        "product_id": product_id,
        "variant": variant,
        "category": category,
        "price": price,
    }


class ProductTask(TypedDict):
    product_id: str
    category: str
    prices: Mapping[str, float]               # {variant: price}，仅含从文件名解出的变体
    grouped_images: Mapping[str, List[str]]   # {variant: [filename, ...]}


def group_by_product(filenames: Iterable[str]) -> List[ProductTask]:
    """
    把一批文件名按平台规范分组：
      - 同 (product_id, variant) 的图属同一变体；同变体内主图（无序号）放最前
      - 同一 product_id 下多个变体合并到同一 task 的 grouped_images
    无法解析的文件名被忽略（建议调用方先 warn）。
    """
    products: dict[str, dict] = {}
    # (product_id, variant) -> [(seq, filename)]，seq=0 表示主图，>=1 是 (N)
    variant_buckets: dict[tuple[str, str], list[tuple[int, str]]] = {}

    for fname in filenames:
        parsed = parse_filename(fname)
        if not parsed:
            continue
        pid = parsed["product_id"]
        prod = products.setdefault(
            pid,
            {
                "product_id": pid,
                "category": parsed["category"],
                "prices": {},
                "grouped_images": {},
            },
        )
        # 同一变体多张图、只要其中一张文件名带价格就采纳；同一变体出现多个价格时
        # 保留先解出的那个（生产数据里同变体应只有一种价格）
        variant = parsed["variant"]
        if parsed["price"] is not None and variant not in prod["prices"]:
            prod["prices"][variant] = parsed["price"]

        seq = _extract_seq(fname)
        variant_buckets.setdefault((pid, variant), []).append((seq, fname))

    # 把每个 variant 桶按序号排序，写回 grouped_images
    for (pid, variant), items in variant_buckets.items():
        items.sort(key=lambda kv: (kv[0], kv[1]))
        products[pid]["grouped_images"][variant] = [fn for _, fn in items]

    return list(products.values())


_SEQ_PATTERN = re.compile(r"[\(（](\d+)[\)）]")


def _extract_seq(filename: str) -> int:
    """从文件名里提取 '(N)' 中的 N；缺省 0（视为主图）。"""
    m = _SEQ_PATTERN.search(Path(filename).stem)
    return int(m.group(1)) if m else 0


__all__ = ["parse_filename", "group_by_product", "ParsedName", "ProductTask"]
