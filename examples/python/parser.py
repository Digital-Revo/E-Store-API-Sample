"""
按平台命名规范解析图片文件名。

与 E-Store-Panel/src/filePreprocess.js 的 parseFileName + handleRead 行为完全等价：

  TSX-2760AQ.jpg            → product_id="TSX-2760",  variant="AQ",    category="TSX"
  TSX-2760AQ(1).jpg         → product_id="TSX-2760",  variant="AQ",    category="TSX"  (序号被剥离)
  AC_1611SZAQ (1).jpg       → product_id="AC-1611",   variant="SZAQ",  category="AC"
  YDJ-7493S(红).jpg         → product_id="YDJ-7493",  variant="S",     category="YDJ"  (中文被剥离)
  R2-0115B-49.8.jpg         → product_id="R2-0115",   variant="B",     category="R2",   price=49.8

平台技术 product_id 是"类别 + 数字"那段；后面的字母（变体码）单独走 grouped_images。
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
    price: Optional[float]    # 文件名第三段开头的数字，单位元；缺省 None


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
    price: Optional[float]
    grouped_images: Mapping[str, List[str]]   # {variant: [filename, ...]}
    image_filenames: List[str]                # 扁平顺序，主图（无 (N)）在前


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
                "price": parsed["price"],
                "grouped_images": {},
                "image_filenames": [],
            },
        )
        if prod["price"] is None and parsed["price"] is not None:
            prod["price"] = parsed["price"]

        seq = _extract_seq(fname)
        variant_buckets.setdefault((pid, parsed["variant"]), []).append((seq, fname))

    # 把每个 variant 桶按序号排序，写回 grouped_images / image_filenames
    for (pid, variant), items in variant_buckets.items():
        items.sort(key=lambda kv: (kv[0], kv[1]))
        sorted_files = [fn for _, fn in items]
        products[pid]["grouped_images"][variant] = sorted_files
        products[pid]["image_filenames"].extend(sorted_files)

    return list(products.values())


_SEQ_PATTERN = re.compile(r"[\(（](\d+)[\)）]")


def _extract_seq(filename: str) -> int:
    """从文件名里提取 '(N)' 中的 N；缺省 0（视为主图）。"""
    m = _SEQ_PATTERN.search(Path(filename).stem)
    return int(m.group(1)) if m else 0


__all__ = ["parse_filename", "group_by_product", "ParsedName", "ProductTask"]
