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
- **每个商品支持多张图**：循环调用本接口拿到多个 URL，作为下一步的 `images` 数组传入

#### 图片文件命名规则（平台约定）

平台内部所有图片都按下面这套规则取名，强烈建议你也照此做——可以直接复用我们提供的 [`examples/python/parser.py`](./examples/python/parser.py)，省得自己再写解析逻辑。

```
<类别>-<4 位数字><变体码>[(N)].<ext>
  └┬┘    └──┬───┘ └─┬─┘  └┬┘
   │       │      │    └─ 同一变体的额外图序号；主图无序号，第 2 张起 (1)、(2)…
   │       │      │
   │       │      └─ 平台真实变体码（business 子分类）：
   │       │        AQ（最常见）/ CGAQ / S / M / V / RJ / DSAQ / SZAQ ...
   │       │        **不要自行编造**，未列出的须先与运维确认。
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

#### product_id 与变体的关系

API 上的 `product_id` 是**类别 + 4 位数字**那段（如 `TSX-2760`），变体码 `AQ` 不属于 product_id，而是同一商品下的 SKU 子项——通过 `grouped_images` 字段表达：

```json
{
  "product_id": "TSX-2760",
  "images": ["url1", "url2", "url3"],
  "grouped_images": {
    "AQ":   ["url1", "url2"],   // 变体 AQ 下的 2 张图
    "CGAQ": ["url3"]            // 变体 CGAQ 下的 1 张图
  }
}
```

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

### 2.2 创建 / 更新商品（upsert）

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
| 字段 | 类型 | 说明 |
|---|---|---|
| `product_id` | string | 与 query 一致即可（也可省略，服务端会自动补） |
| `name` | string | 商品名 |
| `price` | number | 价格 |
| `images` | string[] | 步骤 2.1 返回的 URL 数组；**多图就放多个 URL** |
| `category` | string | 分类 ID；该分类需事先在 Panel "分类管理"中存在 |
| `tag_ids` | string[] | 商品标签 ID 列表，如 `["C1_银制", "C1_耳饰"]` |
| `subcat_<id>` | string | 子分类取值；键名形如 `subcat_classify`、`subcat_material`，值为子分类的可选值 ID |
| `plating` | string | 镀层 |
| `material` | string | 材质 |
| `stone` | string | 锆石 / 主石 |
| `page` | string | 版面（商家内部分页） |
| `showroom_number` | string | 展厅柜号 |
| `require_groups` | string[] | 仅供指定分组用户可见时使用的分组 ID；不传即对所有顾客可见 |

未列出的字段会**透传保存**，后续可在 Panel 中读出来。

**响应**
```json
200 {
  "product_id": "RING-001",
  "name": "玫瑰金戒指",
  "price": 199,
  "images": ["https://...", "https://..."],
  ...
  "created": true,           // true=新建；false=已存在仅更新
  "updated": false,          // 本次 POST 是否有字段被修改
  "tag_update_success": true // 仅当 tag_ids 有改动时出现
}
```

幂等：完整重发同样 body 得到 `"updated": false`。

### 2.3 删除商品

```
DELETE $HOST/api/product/?product_id=<id>
Authorization: Bearer <token>
```

**响应**
```json
200 { "success": true, "message": "Product RING-001 deleted successfully" }
404 { "detail": "Product not found" }
```

### 2.4 批量删除

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

# Step 2：上传商品本身，把多张图的 URL 全塞 images 字段
r = requests.post(
    f"{HOST}/api/product/",
    params={"product_id": "RING-001"},
    json={
        "product_id": "RING-001",
        "name": "玫瑰金戒指",
        "price": 199,
        "images": image_urls,            # ← 多图
        "category": "YDJ",
        "subcat_classify": "ring",
        "subcat_main material": "s925 silver",
    },
    headers={**AUTH, "Content-Type": "application/json"},
)
print(r.json())
```

---

## 4. 错误码

| HTTP | 含义 | 常见原因 |
|---|---|---|
| 400 | `folder 必须以 '<store_id>' 开头...` / `folder 不能包含空段或 '..' 路径回溯` | 调 `/api/file_to_url` 传了不合规 folder（详见 2.1） |
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

`examples/` 下有两条对应不同场景的可运行样例，使用的都是从平台真实下载的 9 张样本图（3 个商品、2~4 张图不等）。

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
python upload_products.py    # 按 data/products.json 上传 3 个示例商品
python delete_products.py    # 清场
```

修改 [`data/products.json`](./examples/python/data/products.json) 就能换成你自己的数据。

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
5. 调 `/api/product/` 一次性带 `images`（扁平 URL）+ `grouped_images`（按变体分组）+ `category`

跟 Panel 批量上传页 ([productImportTool.js](https://github.com/Digital-Revo/E-Store-Panel/blob/master/src/pages/productImportTool.js) + [filePreprocess.js](https://github.com/Digital-Revo/E-Store-Panel/blob/master/src/filePreprocess.js)) 走的是等价规则；结果与点 Panel 完全一致。

### 纯 bash 单商品演示

```bash
cd examples/curl
./upload-one-product.sh ../python/data/images/TSX-9001AQ.jpg "TSX-9001" "示例手链" 89
```

---

**版本：v1.2（2026-05-11）**
