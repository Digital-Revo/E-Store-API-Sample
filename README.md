# E-Store 商品上传公开 API

供第三方系统程序式调用：你本地或云端有商品 ID 和图片，想批量上传到对应的 E-Store 实例。本文档是接入这套接口的全部内容。

---

## 1. 鉴权

所有写请求需要 Bearer Token。Token 由你账户在 E-Store Panel 自行签发：

1. 浏览器打开你被授权管理的店铺 Panel（如 `https://e-store-00.xenotech.studio/`）
2. 登录后点左下角头像 → **"访问管理"**
3. **"+ 新建访问令牌"**：填名称（如 `external-importer`）、选 TTL（推荐 365 天或永不过期）
4. 提交后**一次性**复制返回的 token（关窗后无法再看，丢了只能重新生成）

请求时携带：
```
Authorization: Bearer <token>
```

**作用域**：token 继承签发者的 `allowed_store_ids`。也就是说，要上传到 `e-store-01`，token 必须由 `e-store-01` 的管理员账号签发。同一个 token 不能跨店写入（写错店会 403）。

---

## 2. 端点

实例 host 形如 `https://e-store-XX.xenotech.studio`（XX = 00/01/02/03/06）。下文用 `$HOST` 占位。

### 2.1 上传图片

```
POST $HOST/api/file_to_url
Authorization: Bearer <token>
Content-Type: multipart/form-data

Form fields:
  file:   <二进制，PNG/JPG/WEBP；按 nginx 上限 ≤ 50 MB>
  folder: <必填 string，必须以你授权的 store_id 开头；详见下方"folder（COS 路径，强制规则）">
```

**响应**
```json
200 { "url": "https://e-store-1302933783.cos.ap-guangzhou.myqcloud.com/IMAGES/<folder>/<filename>" }
```

说明
- 同一 URL 可被多个商品复用；图片 URL 永久有效
- 上传成功但商品 upsert 失败，孤儿图片不会影响数据一致性（服务端会按周期 GC）
- **每个商品支持多张图**：循环调用本接口拿到多个 URL，按变体填入下一步 `grouped_images[variant]` 的 URL 数组

#### 图片文件命名规则（平台约定）

平台内部所有图片都按下面这套规则取名，强烈建议你也照此做——可以直接复用我们提供的 [`examples/python/parser.py`](./examples/python/parser.py)，省得自己再写解析逻辑。

```
<类别>-<4 位数字>[<变体码>][(N)].<ext>
  └┬┘    └──┬───┘ └──┬───┘  └┬┘
   │       │       │       └─ 同一变体的额外图序号；主图无序号，第 2 张起 (1)、(2)…
   │       │       │
   │       │       └─ 平台真实变体码（**可选**，同一 product_id 下的 SKU 子项，
   │       │         与商品的 `subcat_*` 子分类标签是两码事——见 2.3 字段表注释）：
   │       │         AQ（最常见）/ CGAQ / S / M / V / RJ / DSAQ / SZAQ ...
   │       │         **不要自行编造**，未列出的须先与运维确认。
   │       │         **不带变体码**时（4 位数字后直接是 `.ext` 或 `(N)`），
   │       │         平台把这张图归到一个固定的中文字面量 `"默认"` 变体下。
   │       │
   │       └─ 4 位数字 SKU 序号
   │
   └─ 平台真实类别：TSX（手链/项链）/ YDJ（戒指）/ AC（耳饰）/
                    C1 / C10（耳饰）/ RC（耳饰）/ KBS / KBZ（手链）/
                    TSL（手链）/ YTL（套装）...
      **不要自行编造**，未列出的须先与运维确认。
```

例子：

| 文件名 | 解析得到 |
|---|---|
| `TSX-2760AQ.jpg` | product_id=`TSX-2760`，变体=`AQ`，类别=`TSX`，序号=主图 |
| `TSX-2760AQ(1).jpg` | product_id=`TSX-2760`，变体=`AQ`，类别=`TSX`，序号=第 2 张 |
| `TSX-2760CGAQ.jpg` | product_id=`TSX-2760`，变体=`CGAQ`（同一商品的另一变体） |
| `YDJ-7493S(红).jpg` | product_id=`YDJ-7493`，变体=`S`（括号中文标注会被自动剥离） |
| `TSX-2760.jpg` | product_id=`TSX-2760`，变体=`默认`（4 位数字后无字母 → 归到 `"默认"` 这个 sentinel key 下） |
| `TSX-2760(1).jpg` | 同上，变体=`默认`，序号=第 2 张 |

#### product_id 与变体（SKU）的关系

API 上的 `product_id` 是**类别 + 4 位数字**那段（如 `TSX-2760`），变体码 `AQ`/`CGAQ` 不属于 product_id，而是同一商品下的 SKU 子项。**真正的 SKU = `product_id` + `variant_id`**，体现在两个 dict 字段上：

```json
{
  "product_id": "TSX-2760",
  "grouped_images": {           // 每个变体的图片
    "AQ":   ["url1", "url2"],
    "CGAQ": ["url3"]
  },
  "prices": {                   // 每个变体的价格
    "AQ":   89,
    "CGAQ": 99
  }
}
```

- `grouped_images` 和 `prices` 都是 dict，**key 集合必须完全一致**，都为变体码
- **SKU 编号到 4 位数字就结束、没有字母后缀的商品**（也就是该商品不存在变体维度）：dict 里**有且仅有一个 key，值固定为中文字面量 `"默认"`**——这是 Panel 批量上传工具同款约定（参见 [filePreprocess.js:40](https://github.com/Digital-Revo/E-Store-Panel/blob/master/src/filePreprocess.js#L40) 和 [productImportTool.js:336](https://github.com/Digital-Revo/E-Store-Panel/blob/master/src/pages/productImportTool.js#L336)）。例子：

  ```json
  {
    "product_id": "TSX-2760",
    "prices":         { "默认": 199 },
    "grouped_images": { "默认": ["url1", "url2"] }
  }
  ```

  > ⚠️ **不要**自创其他 sentinel（如 `"default"` / `""` / `"_"`）。Panel 的批量预览、价格编辑、合并去重等逻辑都字面量匹配 `"默认"` 这两个汉字；换别的值会让你的商品在 Panel 界面里被当成"有个叫 `default` 的真实变体"展示，并污染未来的合并导入流程。

- 商品详情页、加购、报表都按变体维度（`selected_type`）从这两个 dict 里取数据。单变体商品（dict 只有 `"默认"` 这一个 key）在小程序商品页上**不会渲染变体选择 tab**，"默认" 二字也不会作为标签露出给买家

> 文件名严格上不强制必须按此规范（后端只看 query/body），但**平台内部 100% 按此约定**上传。如果你的命名能对齐，路线 B 的自动脚本可以零配置跑通。

#### folder（COS 路径，强制规则）

`/api/file_to_url` 的 `folder` 字段**必填**，**第一段必须是你 token 授权店铺的 store_id**——
否则返回 400。服务端不做静默改写，不合规直接拒绝。

| 合法 | 拒绝（400） |
|---|---|
| `e-store-00` | （空字符串 / 字段缺失，422） |
| `e-store-00/SAMPLE` | `SAMPLE`（缺 store_id 前缀） |
| `e-store-00/2026Q2/IMPORT` | `e-store-99/anything`（不是你授权的店）|
| `e-store-00/<任意你自定义子路径>` | `e-store-00/../X`（路径回溯）|
| | `e-store-001`（前缀近似但不相等）|

- `<store_id>` = 你 token 授权店铺的编号；与 host 首段一致（`e-store-00.xenotech.studio` → `e-store-00`）
- **store_id 后面的子路径完全是你的自由**，平台不强求约定——拆分子路径主要解决"不同源同名图片"的文件冲突。常见选法：
  - `GRAY` / `SCENE` / `DEFAULT` —— Panel 内部约定（脱底图 / 场景图 / 原图）
  - `SAMPLE` / `IMPORT-2026Q2` / `acme-batch-001` —— 你的业务/批次自定义

合起来 COS key 形如 `IMAGES/<folder>/<原始 filename>`，例如：
- `IMAGES/e-store-00/SAMPLE/TSX-2760AQ(1).jpg`
- `IMAGES/e-store-00/2026Q2/IMPORT/AC-1611AQ.jpg`

### 2.2 查询商品（GET）

读取接口**不需要 token**——`/api/product/` 的 GET 全部公开，方便前端在 upsert 前先查存在性 / 拉列表 / 搜索。

#### 2.2.1 单个商品 / 查存在性

```
GET $HOST/api/product/?product_id=<id>
```

**响应**

- **找得到**：返回完整 product dict（字段同 2.3 upsert 接受的字段，**外加** `sales_count`、`timestamp`、`view` 等服务端维护字段）
  ```json
  200 {
    "product_id": "TSX-9001",
    "name": "动物造型铜质手链",
    "prices":         { "AQ": 89 },
    "grouped_images": { "AQ": ["https://...", "https://..."] },
    "category": "TSX",
    "sales_count": 0,
    "timestamp": 1715400000,
    ...
  }
  ```
- **找不到**：⚠ **HTTP 仍然是 200，body 是空对象 `{}`**。**不会**返回 404，请勿用状态码判断。

**判断存在性的正确姿势**：

```python
import requests
r = requests.get(f"{HOST}/api/product/", params={"product_id": "TSX-9001"})
data = r.json()
exists = bool(data) and data.get("product_id") == "TSX-9001"
```

或者更宽松一点 —— `exists = bool(data)`（空 dict falsy）。

#### 2.2.2 列表 / 搜索 / 分页

不传 `product_id` 即进入列表模式，所有过滤参数都是**可选**，可叠加：

| 字段 | 类型 | 说明 |
|---|---|---|
| `category` | string | 按 category_id 过滤；与 `tag` 互斥（同时传以 category 为准） |
| `tag` | string | 按 tag_id 过滤 |
| `search` | string | 全字段关键词搜索（product_id / category / prices 各值 / tag_ids） |
| `filter_field` + `filter_value` | string | 二级筛选；`filter_field` 必须是 `subcat_<id>` 之一，或字面量 `category`（按 supercat 名前缀过滤） |
| `page` | int ≥ 1 | 默认 `1` |
| `page_size` | int 1-1000 | 默认 `50` |
| `sort_by` | string | `timestamp` / `created_time` / `sales_count` / `price`；缺省按 `timestamp` 倒序。⚠ **`price` 走的是 product 顶层标量 `price` 字段，对 dict-only 上传的新商品会被当成 0 处理**——若需要按价格排序，目前建议自己拉回结果集后在客户端对 `prices` dict 聚合排序 |
| `sort_order` | `asc`/`desc` | 默认 `desc` |

**响应**：

```json
200 {
  "results": [ { ...product... }, ... ],   // 当前页的商品数组
  "count": 123,                            // 应用过滤后的总数
  "total_all_products": 456,               // 过滤前的库内总数
  "page": 1,
  "page_size": 50,
  "total_pages": 3
}
```

**典型用法**：

```python
# 检查某个分类下你已经上传过多少 SKU
r = requests.get(
    f"{HOST}/api/product/",
    params={"category": "TSX", "page": 1, "page_size": 1},
)
already_uploaded_in_category = r.json()["count"]

# 按 product_id 模糊搜
r = requests.get(f"{HOST}/api/product/", params={"search": "9001"})
matched = r.json()["results"]
```

---

### 2.3 创建 / 更新商品（upsert）

```
POST $HOST/api/product/?product_id=<id>
Authorization: Bearer <token>
Content-Type: application/json

Body: { ...product_info... }
```

Query 参数：
| 字段 | 必填 | 说明 |
|---|---|---|
| `product_id` | ✅ | 你侧的商品唯一 ID；同 ID 再 POST 为更新 |
| `image_tag` | ❌ | 图搜库标签；缺省自动取本实例 store_id，一般无需传 |

Body（`product_info`）建议字段：
| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `product_id` | ✅ | string | 与 query 一致即可（也可省略，服务端会自动补） |
| `prices` | ✅ | `{variant: number}` | 按变体存价格的 dict，key 为变体码（如 `"AQ"`、`"CGAQ"`），无变体的商品统一用 `"默认"`。详见 2.1 |
| `grouped_images` | ✅ | `{variant: string[]}` | 按变体存图片 URL 的 dict，key 同 `prices`。详见 2.1 |
| `category` | ✅ | string | 分类 ID；该分类需事先在 Panel "分类管理"中存在 |
| `name` | ❌ | string | 商品名；缺省时 Panel 与小程序回退显示 `product_id` |
| `tag_ids` | ❌ | string[] | 商品标签 ID 列表，如 `["C1_银制", "C1_耳饰"]` |
| `subcat_<id>` | ❌ | string | 子分类取值；键名形如 `subcat_classify`、`subcat_material`，值为子分类的可选值 ID。注意 subcat 是**给整个商品打的分类标签**（便于筛选），与上面的变体维度不是一回事 |
| `plating` | ❌ | string | 镀层 |
| `material` | ❌ | string | 材质 |
| `stone` | ❌ | string | 锆石 / 主石 |
| `page` | ❌ | string | 版面（商家内部分页） |
| `showroom_number` | ❌ | string | 展厅柜号 |
| `require_groups` | ❌ | string[] | 仅供指定分组用户可见时使用的分组 ID；不传即对所有顾客可见 |

**关于必填字段**：上表前 4 个 ✅ 字段是首次创建商品的最小集合，全部可以从 SKU 文件名按平台命名规则解析得到（只有 `prices` 的**数值**有时需要自己提供）：

| 必填字段 | 来源 |
|---|---|
| `product_id` | 文件名前两段 `<类别>-<4位数字>`，例如 `TSX-2760AQ.jpg` → `TSX-2760` |
| `category` | 文件名第一段，例如 `TSX-2760AQ.jpg` → `TSX` |
| `grouped_images` 的 **key 集合** | 文件名第二段尾部字母（变体码），无字母后缀 → `"默认"`；URL 列表来自 2.1 上传图片接口的返回 |
| `prices` 的 **key 集合** | 同上，key 与 `grouped_images` 完全对齐 |
| `prices` 的**数值** | 若文件名第三段以数字开头（如 `R2-0115B-49.8.jpg` → 49.8）可解析得到；否则需自己提供 |

解析方法见 §2.1 "图片文件命名规则" 与示例 [`examples/python/parser.py`](./examples/python/parser.py)；端到端跑通参见 §7 "路线 B：你只有一堆按命名规范取名的图"。

> **创建 / 更新语义**：
> - **首次创建**（该 `product_id` 在库中不存在）—— 上述 4 个必填字段必须带齐，缺任意一个服务端 **400 拒绝**，错误体 `detail` 里列出缺失字段名。
> - **后续 POST 更新**（该 `product_id` 已存在）—— 视为**部分更新**，只带要改的字段即可；其它字段保持原值。不做完整性校验。
>
> 这样设计的好处：避免新接入方意外创建出半残商品（缺图缺价、无分类），同时不影响"补一两个字段"的增量更新场景。

未列出的字段会**透传保存**，后续可在 Panel 中读出来。

**响应**
```json
200 {
  "product_id": "RING-001",
  "name": "玫瑰金戒指",
  "prices":         { "默认": 199 },
  "grouped_images": { "默认": ["https://...", "https://..."] },
  ...
  "created": true,           // true=新建；false=已存在仅更新
  "updated": false,          // 本次 POST 是否有字段被修改
  "tag_update_success": true // 仅当 tag_ids 有改动时出现
}
```

幂等：完整重发同样 body 得到 `"updated": false`。

### 2.4 删除商品

```
DELETE $HOST/api/product/?product_id=<id>
Authorization: Bearer <token>
```

**响应**
```json
200 { "success": true, "message": "Product RING-001 deleted successfully" }
404 { "detail": "Product not found" }
```

### 2.5 批量删除

```
DELETE $HOST/api/products/
Authorization: Bearer <token>
Content-Type: application/json

Body: { "product_ids": ["A", "B", "C"] }
```

**响应**
```json
200 {
  "success": true,
  "deleted_count": 2,
  "failed_products": [{ "product_id": "C", "reason": "Product not found" }],
  "message": "Successfully deleted 2 products"
}
```

---

## 3. 最小可运行（Python）

```python
import requests

TOKEN = "fe1db579..."                           # 在 Panel "访问管理"生成
HOST  = "https://e-store-00.xenotech.studio"   # 你被授权的实例
AUTH  = {"Authorization": f"Bearer {TOKEN}"}

# Step 1：依次上传 N 张图
image_urls = []
for path in ["img-front.jpg", "img-back.jpg", "img-detail.jpg"]:
    with open(path, "rb") as f:
        r = requests.post(
            f"{HOST}/api/file_to_url",
            files={"file": (path, f)},
            data={"folder": "my-batch"},
            headers=AUTH,
        )
        r.raise_for_status()
        image_urls.append(r.json()["url"])

# Step 2：上传商品本身。价格和图片都按变体维度走 dict；
#         没有变体维度的商品统一用 "默认" 作为唯一 key。
r = requests.post(
    f"{HOST}/api/product/",
    params={"product_id": "RING-001"},
    json={
        "product_id": "RING-001",
        "name": "玫瑰金戒指",
        "category": "YDJ",
        "prices":         {"默认": 199},          # 按变体存价
        "grouped_images": {"默认": image_urls},   # 按变体存图
        "subcat_classify": "ring",
        "subcat_main material": "s925 silver",
    },
    headers={**AUTH, "Content-Type": "application/json"},
)
print(r.json())
```

> 多变体商品就把 `prices` / `grouped_images` 的 key 换成真实变体码（如 `"AQ"`、`"CGAQ"`），两个 dict 的 key 集合必须一致。

---

## 4. 错误码

| HTTP | 含义 | 常见原因 |
|---|---|---|
| 400 | `folder 必须以 '<store_id>' 开头...` / `folder 不能包含空段或 '..' 路径回溯` | 调 `/api/file_to_url` 传了不合规 folder（详见 2.1） |
| 400 | `首次创建商品 <id> 时缺少必填字段：[...]` | 首次 POST `/api/product/` 时 body 没带齐 `prices` / `grouped_images` / `category` 之一（详见 2.3）。已存在商品的后续 POST 不触发此错 |
| 401 | `Authorization header is required` / `Invalid access token` | 没带 token / 格式错 / token 被吊销 |
| 403 | `当前登录用户无权管理本实例业务员` | token 有效但其 `allowed_store_ids` 不含本实例（用错店的 token） |
| 404 | `Product not found` | 删除 / 操作不存在的商品 |
| 422 | pydantic 校验失败 | 缺必填 query/body 字段，或类型不对 |
| 500 | 服务端错误 | 带上请求时间联系运维 |

---

## 5. 限速与限制

- **图片体积**：单次 multipart `file` ≤ 50 MB（nginx `client_max_body_size`）
- **并发**：暂无显式限流；批量导入时建议 ≤ 10 并发图片上传
- **作用域**：token 不能跨店写入，必须用对应店签发的 token
- **删除是软副作用**：会同步删除图搜库的索引；误删需要重新 POST 商品和图

---

## 6. Token 生命周期管理

- **撤销单个 token**：Panel "访问管理"列表里该行 ⋯ → 退出登录（立即作废）
- **修改密码**：不会作废现有 token，需要逐条吊销
- **观察**：会话列表中 `is_manual: true` 显示为"手动"徽标，区分浏览器登录会话与脚本签发的 token

---

## 7. 直接跑示例

`examples/` 下有两条对应不同场景的可运行样例，使用的都是从平台真实下载的 11 张样本图（4 个商品、1~4 张图不等）。

公共准备：

```bash
cd examples/python
pip install -r requirements.txt
export E_STORE_HOST="https://e-store-00.xenotech.studio"   # 你被授权的实例
export E_STORE_TOKEN="<paste-your-token>"
```

### 路线 A：你已经有结构化数据（product_id + 元数据）

适合：你自己系统里已经维护好商品台账，能导出成 JSON。

```bash
python upload_products.py    # 按 data/products.json 上传 4 个示例商品
python delete_products.py    # 清场
```

[`data/products.json`](./examples/python/data/products.json) 里 4 条覆盖了两种典型情况：

| product_id | 演示重点 |
|---|---|
| `TSX-9001`、`YDJ-9001`、`AC-9001` | **有变体后缀**（`AQ`），dict 的 key 是变体码本身（这里都只有 `AQ` 一个 key，但若有多变体写法相同） |
| `KBS-9001` | **无变体后缀**（文件名 `KBS-9001.jpg`、`KBS-9001(1).jpg` 不带字母），dict 的 key 是中文字面量 `"默认"`——和 Panel 批量上传工具的产物完全等价 |

修改这份 JSON 就能换成你自己的数据。

### 路线 B：你只有一堆按命名规范取名的图

适合：你只有一文件夹按上节命名规则取名的图片（如 `TSX-2760AQ.jpg`、`TSX-2760AQ(1).jpg`、`TSX-2760CGAQ.jpg` …），没有别的元数据。

```bash
python auto_upload_from_folder.py data/images/
# 或换成你自己的目录、自定义 COS group：
python auto_upload_from_folder.py /path/to/my-images/ --group 2026Q2-IMPORT
```

脚本会：
1. 扫目录里所有 `.jpg/.jpeg/.png/.webp`
2. 用 [`parser.py`](./examples/python/parser.py) 按命名规则解析每个文件名，提取 product_id / 变体 / 类别 / 价格（可选）
3. 同一 product_id 的不同变体合并、同一变体下多张图按 `(N)` 排序
4. 调 `/api/file_to_url` 上传每张图（folder = `<store_id>/<--group>`）
5. 调 `/api/product/` 一次性带 `grouped_images`（按变体分组的 URL）+ `prices`（按变体的价格，文件名解出）+ `category`

跟 Panel 批量上传页 ([productImportTool.js](https://github.com/Digital-Revo/E-Store-Panel/blob/master/src/pages/productImportTool.js) + [filePreprocess.js](https://github.com/Digital-Revo/E-Store-Panel/blob/master/src/filePreprocess.js)) 走的是等价规则；结果与点 Panel 完全一致。

### 纯 bash 单商品演示

```bash
cd examples/curl
./upload-one-product.sh ../python/data/images/TSX-9001AQ.jpg "TSX-9001" "示例手链" 89
```

---

**版本：v1.6（2026-05-11）**
- **服务端开始强制校验首次创建的必填字段**：首次 POST `/api/product/?product_id=<id>` 若 body 缺 `prices` / `grouped_images` / `category` 任意一项，返回 400 并在 `detail` 里列出缺失字段；已存在商品的后续 POST 仍按部分更新处理（不校验完整性）。错误码表新增对应行。`name` **不在必填集**——storefront 和 Panel 都有 `product.name || product.product_id` 的兜底渲染，与 Panel 批量上传不录入 name 的现有约定保持一致
- 2.3 Body 字段表新增 "必填" 列，标出 4 个必填字段，并附 "来源对照表" 说明哪些可从文件名直接解析、哪些需自己提供
- 订正变体码与 `subcat_*` 子分类的概念混淆——SKU 子项 vs 商品级标签是两件事
- 新增 2.2 查询商品（GET）小节：单条查存在性 / 列表 / 搜索 / 分页；明确 "查不到返回 200 + `{}`，不返回 404" 的判存在性陷阱。原 2.2/2.3/2.4 顺延到 2.3/2.4/2.5
- 商品字段统一为 `prices` / `grouped_images` 两个 dict（变体维度即 SKU），废弃 `price` / `images` 扁平字段
- SKU 编号到 4 位数字结束、无字母后缀的商品，dict 用中文字面量 `"默认"` 作为唯一 key（与 Panel 既有约定对齐）
