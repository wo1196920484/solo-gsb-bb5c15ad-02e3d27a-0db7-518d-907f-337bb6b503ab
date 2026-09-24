# 离线小册子拼版 API（Python / FastAPI）

按**帖（signature）**对小册子进行拼版：输入总页数、每帖最多纸张数和装订方向（左/右），
按纸张**从外到内**返回每帖各张纸正反面的左右页码。空白页用 `null` 表示。

另提供**章节分帖**接口 `/api/v1/impose/chapters`：按章节首页页码分帖，章节不可跨帖、
相邻章节可合帖，并自动选择空白最少、帖数最少的分帖边界。

还提供**重印复用**接口 `/api/v1/impose/reprint`：输入旧版与新版按阅读顺序排列的页面 ID，
在新版四页位与旧版某印张完全相同且均未改动时整张复用（允许跨帖、每张旧印张最多复用一次），
否则标记整张重印。

还提供**印张抽检**接口 `/api/v1/impose/inspect`：把车间乱序拍回的实物印张（每张可能被
原样、左右镜像、正反互换或两者组合地读出）与按相同拼版规则生成的预期印张配对，先最大化配对数、
再最大化已读页位吻合数，并逐张给出帖号/张号、解释变换与已知页位错误明细。

## 一条命令启动

需要安装 Docker（含 Compose 插件），在项目根目录执行：

```bash
docker compose up -d --build
```

该命令会自动完成：构建镜像 → 安装全部依赖 → 启动 API（容器内 uvicorn 直接拉起，无数据库等额外初始化步骤）。

停止 / 查看日志：

```bash
docker compose down        # 停止
docker compose logs -f     # 查看日志
```

## 必要配置

默认无需任何配置。唯一可选配置是**宿主机端口**（容器内固定 8000）：

```bash
HOST_PORT=9000 docker compose up -d --build
```

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `HOST_PORT` | `8000` | 宿主机暴露端口，通过环境变量覆盖；容器内端口固定为 `8000` |

服务完全离线运行，不连接任何外部服务。

## API 地址与端口

- 服务地址：`http://localhost:8000`（改了 `HOST_PORT` 则对应替换端口）
- 健康检查：`GET http://localhost:8000/health`
- 交互式文档（Swagger UI）：`http://localhost:8000/docs`
- 拼版接口：`POST http://localhost:8000/api/v1/impose`
- 章节分帖拼版接口：`POST http://localhost:8000/api/v1/impose/chapters`
- 重印复用接口：`POST http://localhost:8000/api/v1/impose/reprint`
- 印张抽检接口：`POST http://localhost:8000/api/v1/impose/inspect`

## 接口说明

### 请求

`POST /api/v1/impose`，`Content-Type: application/json`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `total_pages` | 整数 | ≥ 1 | 总页数（正整数） |
| `max_sheets_per_signature` | 整数 | ≥ 1 | 每帖最多纸张数；每帖最多容纳其 **4 倍**页数 |
| `binding` | 字符串 | `left` / `right` | 装订方向：左装订 / 右装订 |

```bash
curl -X POST http://localhost:8000/api/v1/impose \
  -H "Content-Type: application/json" \
  -d '{"total_pages": 16, "max_sheets_per_signature": 4, "binding": "left"}'
```

### 响应

返回帖号 `signature_index` 与帖内纸张序号 `sheet_index`（从 1 开始，1 为最外张），
以及每张纸正面 `front` / 背面 `back` 的左 `left` / 右 `right` 页码；空白页为 `null`。

```json
{
  "total_pages": 16,
  "max_sheets_per_signature": 4,
  "binding": "left",
  "signature_count": 1,
  "signatures": [
    {
      "signature_index": 1,
      "sheet_count": 4,
      "page_count_padded": 16,
      "sheets": [
        {
          "sheet_index": 1,
          "front": { "left": 16, "right": 1 },
          "back":  { "left": 2,  "right": 15 }
        },
        {
          "sheet_index": 2,
          "front": { "left": 14, "right": 3 },
          "back":  { "left": 4,  "right": 13 }
        }
      ]
    }
  ]
}
```

> 实际响应会列出全部 4 张纸，上例只展示前 2 张。

### 拼版规则

1. 按原页顺序分帖，每帖最多容纳 `4 × max_sheets_per_signature` 页；除末帖外各帖均装满。
2. 仅**末帖**在尾部补空白页至 4 的倍数，空白位置页码为 `null`。
3. 左装订（`left`）最外张：
   - 正面（`front`）：左 = 末页，右 = 首页；
   - 背面（`back`）：左 = 次页，右 = 倒数第二页；
   - 之后逐张向内递推（帖页数为 `n`，纸张从外向内序号为 `k = 0,1,2...`，四个页位在帖内的位置索引从 0 计分别为：正左 `n-1-2k`、正右 `2k`、背左 `2k+1`、背右 `n-2-2k`，取出的即为该位置的全局页码，补齐位置为 `null`）。
4. 右装订（`right`）为镜像装订：将左装订结果的**左右页位整体交换**（正反关系不变）。

### 非法参数（4xx）

参数缺失、类型错误、`total_pages` / `max_sheets_per_signature` 小于 1、`binding` 不是
`left`/`right`、包含未定义字段时，均返回 `422 Unprocessable Entity`：

```json
{
  "detail": [
    { "type": "greater_than_equal", "loc": ["body", "total_pages"], "msg": "Input should be greater than or equal to 1" }
  ]
}
```

## 章节分帖拼版（POST /api/v1/impose/chapters）

在 `/api/v1/impose` 的基础上支持**章节感知**分帖：章节不可跨帖，相邻章节可合帖。
本地访问地址 `http://localhost:8000/api/v1/impose/chapters`（改了 `HOST_PORT` 则对应替换端口）。

### 请求

`POST /api/v1/impose/chapters`，`Content-Type: application/json`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `total_pages` | 整数 | ≥ 1 | 总页数（正整数） |
| `max_sheets_per_signature` | 整数 | ≥ 1 | 每帖最多纸张数；每帖实际页数不超过其 **4 倍** |
| `binding` | 字符串 | `left` / `right` | 装订方向：左装订 / 右装订 |
| `chapter_starts` | 整数数组 | 严格递增、首项为 1、末项 ≤ `total_pages` | 各章节首页页码 |

```bash
curl -X POST http://localhost:8000/api/v1/impose/chapters \
  -H "Content-Type: application/json" \
  -d '{"total_pages": 20, "max_sheets_per_signature": 2, "binding": "left", "chapter_starts": [1, 5, 9, 13]}'
```

### 响应

沿用 `sheets` 页位结构（与 `/api/v1/impose` 相同），并为每帖补充原页起止页码
`page_start` / `page_end` 与尾部空白数 `blank_count`：

```json
{
  "total_pages": 20,
  "max_sheets_per_signature": 2,
  "binding": "left",
  "chapter_starts": [1, 5, 9, 13],
  "signature_count": 3,
  "signatures": [
    {
      "signature_index": 1,
      "sheet_count": 1,
      "page_count_padded": 4,
      "page_start": 1,
      "page_end": 4,
      "blank_count": 0,
      "sheets": [
        {
          "sheet_index": 1,
          "front": { "left": 4, "right": 1 },
          "back":  { "left": 2, "right": 3 }
        }
      ]
    }
  ]
}
```

> 上例仅展示第 1 帖；实际响应含全部 3 帖（原页范围 1–4、5–12、13–20）。

### 分帖规则

1. 章节不可跨帖，相邻章节可合帖；每帖实际页数不超过 `4 × max_sheets_per_signature`，
   单章超过该上限时返回 `422 Unprocessable Entity`。
2. 在满足容量约束的分帖方案中，依次最小化：各帖补至 4 的倍数所需**空白页总数** →
   **帖数**；仍相同则优先**最早的分帖边界**。
3. 每帖各自在**尾部**补空白至 4 的倍数（`null`），再按与 `/api/v1/impose`
   相同的正反面拼版规则排列。

### 非法参数（4xx）

除与 `/api/v1/impose` 相同的校验外，`chapter_starts` 为空、首项不为 1、未严格递增、
超过 `total_pages`，或某一单章页数超过 `4 × max_sheets_per_signature` 时，
均返回 `422 Unprocessable Entity`。

## 重印复用（POST /api/v1/impose/reprint）

旧版加印时，若新版的某张印张与旧版某张**完全一致且页内内容均未改动**，可直接复用旧印张、
无需重印；其余印张整张重印。本地访问地址
`http://localhost:8000/api/v1/impose/reprint`（改了 `HOST_PORT` 则对应替换端口）。

两版分别沿用普通拼版（`/api/v1/impose`）的分帖、末帖尾部补空白与左右页位规则，
使用两版共用的 `max_sheets_per_signature` 与 `binding`。

### 请求

`POST /api/v1/impose/reprint`，`Content-Type: application/json`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `old_page_ids` | 字符串数组 | 非空数组；元素为非空字符串、**版内不重复** | 旧版页面 ID，按阅读顺序排列 |
| `new_page_ids` | 字符串数组 | 非空数组；元素为非空字符串、**版内不重复** | 新版页面 ID，按阅读顺序排列 |
| `max_sheets_per_signature` | 整数 | ≥ 1 | 两版共用的每帖最多纸张数 |
| `binding` | 字符串 | `left` / `right` | 两版共用的装订方向 |
| `changed_page_ids` | 字符串数组 | 每个 ID 必须属于新版；允许重复、允许为空 | 新版内容改动的页面 ID |

```bash
curl -X POST http://localhost:8000/api/v1/impose/reprint \
  -H "Content-Type: application/json" \
  -d '{
    "old_page_ids": ["p1","p2","p3","p4","p5","p6","p7","p8"],
    "new_page_ids": ["p1","p2","p3","p4","p5","p6X","p7","p8"],
    "max_sheets_per_signature": 2,
    "binding": "left",
    "changed_page_ids": ["p6X"]
  }'
```

### 复用规则

新版每张印张按下列规则判定（四个页位指 `front.left` / `front.right` /
`back.left` / `back.right`，空白页位为 `null`）：

1. 四个页位与某张**旧版印张完全相同**（页位一一对应，ID 相同、空白位置也相同），
   **允许跨帖**匹配；
2. 四个页位中的非空页面 ID **均不在** `changed_page_ids` 中；
3. 每张旧版印张**最多被复用一次**（含页位全为空白的印张，按旧版帖号、张号顺序取用）。

以上任一不满足即**整张重印**。例如改动只涉及一张纸上的其中一页，该纸四个页位所在整面
仍需整张重印，但不影响其他印张复用。

### 响应

按**新版帖号、张号**逐张返回：

- `front` / `back` 的左、右页位：新版页面 ID 或 `null`（空白）；
- `reused`：是否复用旧版印张，`false` 表示整张重印；
- `old_signature_index` / `old_sheet_index`：复用时给出旧帖号与旧帖内张号
  （均从 1 开始，张号 1 为最外张）；重印时均为 `null`；
- 顶层 `reprint_sheet_count`：整张重印的总张数。

```json
{
  "old_page_ids": ["p1","p2","p3","p4","p5","p6","p7","p8"],
  "new_page_ids": ["p1","p2","p3","p4","p5","p6X","p7","p8"],
  "changed_page_ids": ["p6X"],
  "max_sheets_per_signature": 2,
  "binding": "left",
  "signature_count": 1,
  "reprint_sheet_count": 1,
  "signatures": [
    {
      "signature_index": 1,
      "sheet_count": 2,
      "page_count_padded": 8,
      "sheets": [
        {
          "sheet_index": 1,
          "front": { "left": "p8", "right": "p1" },
          "back": { "left": "p2", "right": "p7" },
          "reused": true,
          "old_signature_index": 1,
          "old_sheet_index": 1
        },
        {
          "sheet_index": 2,
          "front": { "left": "p6X", "right": "p3" },
          "back": { "left": "p4", "right": "p5" },
          "reused": false,
          "old_signature_index": null,
          "old_sheet_index": null
        }
      ]
    }
  ]
}
```

### 非法参数（4xx）

除与 `/api/v1/impose` 相同的校验（`max_sheets_per_signature`、`binding`、未定义字段等）外，
任一版页面 ID 列表为空、包含空字符串、版内 ID 重复，或 `changed_page_ids` 包含空字符串、
含有不属于新版的页面 ID 时，均返回 `422 Unprocessable Entity`。

## 印张抽检（POST /api/v1/impose/inspect）

车间实拍/人工读回的**实物印张是乱序的**，且每张纸拿起时的朝向不固定。本接口先沿用
`/api/v1/impose` 的拼版规则（含末帖尾部补空白与左/右装订镜像）由页面 ID 生成**预期印张**，
再把每张实物观测与预期印张配对核对。本地访问地址
`http://localhost:8000/api/v1/impose/inspect`（改了 `HOST_PORT` 则对应替换端口）。

### 请求

`POST /api/v1/impose/inspect`，`Content-Type: application/json`

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `page_ids` | 字符串数组 | 非空；非空字符串、**互不重复**，且不能为 `"?"` | 页面 ID，按**阅读顺序**排列 |
| `max_sheets_per_signature` | 整数 | ≥ 1 | 每帖最多纸张数；每帖最多容纳其 4 倍页数 |
| `binding` | 字符串 | `left` / `right` | 装订方向：左装订 / 右装订 |
| `observed_sheets` | 对象数组 | 非空 | 乱序的实物印张；每张含 `front`/`back`，其 `left`/`right` 页位为页面 ID、`null`（空白）或 `"?"`（未读出） |

页位三态含义：

- 页面 ID（非空字符串，不能是 `"?"`）：该页位读出的页面；ID 不要求出现在 `page_ids`
  中——读到外来 ID 时仍可配对，但该页位计为错误；
- `null`：明确读到的**空白页位**（是已知信息，与预期 `null` 吻合算对，与预期页面 ID 不符算错）；
- `"?"`：该页位**未读出**（不计错、不参与吻合数，也不能作为配对线索）。

```bash
curl -X POST http://localhost:8000/api/v1/impose/inspect \
  -H "Content-Type: application/json" \
  -d '{
    "page_ids": ["p1","p2","p3","p4","p5","p6","p7","p8","p9","p10","p11","p12"],
    "max_sheets_per_signature": 2,
    "binding": "left",
    "observed_sheets": [
      {"front": {"left": "p8", "right": "p1"}, "back": {"left": "p2", "right": "?"}},
      {"front": {"left": "p4", "right": "p5"}, "back": {"left": "p6", "right": "pX"}},
      {"front": {"left": "?",  "right": "?"},  "back": {"left": "z9", "right": "?"}}
    ]
  }'
```

### 配对与裁决规则

每张观测可按以下 **4 种变换**之一解释（`none` 原样、`mirror_lr` 左右镜像、
`flip_fb` 正反互换、`mirror_lr_flip_fb` 两者组合）：

1. **配对门槛**：观测至少有一个非空、已读（非 `"?"`）的页面 ID 出现在该张预期印张的
   四个页位中，才允许与该张配对；全为 `null`/`"?"`、或只有外来 ID 的观测无法配对。
2. 在**每张预期印张、每张观测至多使用一次**的前提下，依次优化：
   1. **最大化配对数**；
   2. 再最大化全部配对的**已读页位吻合数**（页面 ID 相同或 `null` 对 `null` 算吻合，
      `"?"` 不计入）；
   3. 仍同分则按 **观测序号升序 → 预期帖号/张号升序 → 变换顺序
      （`none`、`mirror_lr`、`flip_fb`、`mirror_lr_flip_fb`）** 裁决。
3. 同一观测与某张预期印张之间，取吻合数最多的变换；吻合数相同取变换顺序最前者。
   `"?"` 不计错；其余已知页位（含 `null`）与按选定变换解释后的预期不符时，逐条列入
   `errors`。

### 响应

`observations` 按请求中的观测顺序逐张返回：

- `matched`：是否配对成功；成功时给出 `signature_index` / `sheet_index`（均从 1 开始，
  张号 1 为最外张）与 `transform`；失败时这三项为 `null`；
- `matched_slot_count`：已读页位吻合数（`"?"` 不计入）；
- `errors`：已知页位错误明细，每项含 `position`
  （`front_left` / `front_right` / `back_left` / `back_right`，按观测**原样朝向**）、
  `observed`（读到的 ID 或 `null`）、`expected`（按选定变换解释后的预期 ID 或 `null`）；
- 顶层另给出 `unmatched_observations`（无法配对的观测，按观测序号排列）与
  `unseen_signatures`（未见的预期印张，按帖号/张号排列）及三者的计数。

上例中：观测 1 原样对应第 1 帖最外张（1 个 `"?"`，吻合 3 个页位）；
观测 2 按正反互换对应第 1 帖内张，唯读错的 `back_right` 应为 `p3`；
观测 3 只有外来 ID `z9` 无法配对；第 2 帖印张未见。

```json
{
  "page_ids": ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10", "p11", "p12"],
  "max_sheets_per_signature": 2,
  "binding": "left",
  "matched_observation_count": 2,
  "unmatched_observation_count": 1,
  "unseen_sheet_count": 1,
  "observations": [
    {
      "observation_index": 1,
      "front": { "left": "p8", "right": "p1" },
      "back": { "left": "p2", "right": "?" },
      "matched": true,
      "signature_index": 1,
      "sheet_index": 1,
      "transform": "none",
      "matched_slot_count": 3,
      "errors": []
    },
    {
      "observation_index": 2,
      "front": { "left": "p4", "right": "p5" },
      "back": { "left": "p6", "right": "pX" },
      "matched": true,
      "signature_index": 1,
      "sheet_index": 2,
      "transform": "flip_fb",
      "matched_slot_count": 3,
      "errors": [
        { "position": "back_right", "observed": "pX", "expected": "p3" }
      ]
    },
    {
      "observation_index": 3,
      "front": { "left": "?", "right": "?" },
      "back": { "left": "z9", "right": "?" },
      "matched": false,
      "signature_index": null,
      "sheet_index": null,
      "transform": null,
      "matched_slot_count": 0,
      "errors": []
    }
  ],
  "unmatched_observations": [
    {
      "observation_index": 3,
      "front": { "left": "?", "right": "?" },
      "back": { "left": "z9", "right": "?" }
    }
  ],
  "unseen_signatures": [
    {
      "signature_index": 2,
      "sheet_index": 1,
      "front": { "left": "p12", "right": "p9" },
      "back": { "left": "p10", "right": "p11" }
    }
  ]
}
```

### 非法参数（4xx）

除与 `/api/v1/impose` 相同的校验（`max_sheets_per_signature`、`binding`、未定义字段等）外，
`page_ids` 或 `observed_sheets` 为空、页面 ID 为空字符串/重复/为 `"?"`，
或实物页位为空字符串时，均返回 `422 Unprocessable Entity`。
（页位缺字段或类型错误同样返回 422；空白页须显式传 `null`，未读出传 `"?"`。）

## 本地开发（不使用 Docker）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
pytest -q
```

## 项目结构

```
.
├── app/
│   ├── __init__.py
│   ├── imposition.py   # 拼版核心算法（分帖 + 帖内拼版）
│   └── main.py         # FastAPI 路由与参数校验
├── tests/              # 算法与 API 测试（pytest）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```
