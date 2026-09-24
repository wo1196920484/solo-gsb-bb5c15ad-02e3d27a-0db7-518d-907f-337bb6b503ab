"""小册子拼版核心算法。

规则
----
1. 按原页顺序分帖，每帖最多容纳 ``max_sheets * 4`` 页；
2. 仅末帖在尾部补空白页至 4 的倍数，空白页用 ``None`` 表示；
3. 每帖内部按纸张“从外到内”给出正反面左右页码；
4. 左装订（left）：最外张正面 = 末页/首页，背面 = 次页/倒数第二页，
   逐张向内递推；右装订（right）将左右页位镜像交换。

章节分帖（``split_signatures_by_chapters`` / ``impose_chapters``）
----
- 章节不可跨帖，相邻章节可合帖；每帖实际页数不超过 ``max_sheets * 4``；
- 分帖边界依次最小化：各帖补至 4 的倍数所需空白总数 → 帖数；
  仍相同则优先最早的分帖边界；
- 每帖各自在尾部补空白至 4 的倍数，再按规则 3/4 拼版。
"""
from __future__ import annotations

from typing import Collection, List, Literal, Optional, Tuple, TypeVar

Binding = Literal["left", "right"]

# 页面标识类型：页码（int）或页面 ID（str）
P = TypeVar("P")

# 单张纸的一页描述：(全局页码或 None, 在帖内纸张上的位置)
# side: "front" 正面 / "back" 背面；position: "left" 左页 / "right" 右页


def split_signatures(total_pages: int, max_sheets: int) -> List[List[Optional[int]]]:
    """按原页顺序分帖，末帖补空白至 4 的倍数。

    返回二维列表：外层为帖（顺序），内层为该帖按原页顺序排列的页码，
    末帖补齐位置为 ``None``。
    """
    capacity = max_sheets * 4
    signatures: List[List[Optional[int]]] = []

    start = 1
    while start <= total_pages:
        end = min(start + capacity - 1, total_pages)
        pages: List[Optional[int]] = list(range(start, end + 1))
        # 仅末帖需要补齐（前面的帖都恰好装满，本身就是 4 的倍数）
        if len(pages) % 4 != 0:
            pages.extend([None] * (4 - len(pages) % 4))
        signatures.append(pages)
        start = end + 1

    return signatures


def impose_signature(
    pages: List[Optional[P]],
    binding: Binding,
) -> List[dict]:
    """对一个帖拼版，按纸张从外到内返回各张正反面的左右页码。

    ``pages`` 长度必须为 ``4s``（``s`` 为纸张数），其中保存的已是**全局页码**
    （重印接口中为页面 ID）；末帖补齐位置为 ``None``，对应页位返回 ``null``。
    """
    sheet_count = len(pages) // 4
    n = len(pages)  # 帖页数（含补齐的空白）
    sheets: List[dict] = []

    for k in range(sheet_count):
        # 左装订下，第 k 张（k=0 最外张）四个页位的帖内位置索引（0-based）：
        #   正面左 n-1-2k、正面右 2k
        #   背面左 2k+1、背面右 n-2-2k
        front_left = pages[n - 1 - 2 * k]
        front_right = pages[2 * k]
        back_left = pages[2 * k + 1]
        back_right = pages[n - 2 - 2 * k]

        if binding == "right":
            # 右装订：左右页位镜像交换
            front_left, front_right = front_right, front_left
            back_left, back_right = back_right, back_left

        sheets.append(
            {
                "sheet_index": k + 1,
                "front": {"left": front_left, "right": front_right},
                "back": {"left": back_left, "right": back_right},
            }
        )

    return sheets


def impose(total_pages: int, max_sheets: int, binding: Binding) -> List[dict]:
    """完整拼版：分帖并逐帖返回拼版结果。"""
    grouped = split_signatures(total_pages, max_sheets)
    result: List[dict] = []
    for index, pages in enumerate(grouped, start=1):
        result.append(
            {
                "signature_index": index,
                "sheet_count": len(pages) // 4,
                "page_count_padded": len(pages),
                "sheets": impose_signature(pages, binding),
            }
        )
    return result


def split_signatures_by_chapters(
    total_pages: int,
    max_sheets: int,
    chapter_starts: List[int],
) -> List[List[Optional[int]]]:
    """按章节边界分帖：章节不可跨帖，相邻章节可合帖。

    在满足“单帖实际页数 ≤ ``max_sheets * 4``”的分帖方案中，依次最小化：

    1. 各帖补至 4 的倍数所需空白页总数；
    2. 帖数；
    3. 仍相同则取最早的分帖边界（排在前面的帖尽量短）。

    每帖尾部补空白至 4 的倍数（``None``）。
    任一单章页数超过容量时抛 ``ValueError``。
    """
    capacity = max_sheets * 4
    starts = list(chapter_starts)
    ends = starts[1:] + [total_pages + 1]
    lengths = [end - start for start, end in zip(starts, ends)]
    for start, length in zip(starts, lengths):
        if length > capacity:
            raise ValueError(
                f"起始页为 {start} 的章节共 {length} 页，超过单帖容量 {capacity} 页"
            )

    m = len(lengths)
    # 章节页数前缀和，O(1) 求连续若干章的总页数
    prefix = [0] * (m + 1)
    for i, length in enumerate(lengths, 1):
        prefix[i] = prefix[i - 1] + length

    def blanks(count: int) -> int:
        # 补至 4 的倍数所需空白页数
        return (-count) % 4

    # 后缀 DP：best[i] = 章节 i..m（1-based）的最优 (空白总数, 帖数)。
    # 内层循环最多推进 capacity 章（每章至少 1 页），整体 O(m * capacity)。
    best: List[Tuple[int, int]] = [(0, 0)] * (m + 2)
    for i in range(m, 0, -1):
        best_cost: Optional[Tuple[int, int]] = None
        for j in range(i, m + 1):
            count = prefix[j] - prefix[i - 1]
            if count > capacity:
                break
            candidate = (blanks(count) + best[j + 1][0], 1 + best[j + 1][1])
            if best_cost is None or candidate < best_cost:
                best_cost = candidate
        # 单章必能成帖（前面已校验容量），best_cost 不会为 None
        assert best_cost is not None
        best[i] = best_cost

    # 重建：达到最优成本的边界中取最早者（每步选最小的 j）
    signatures: List[List[Optional[int]]] = []
    i = 1
    while i <= m:
        for j in range(i, m + 1):
            count = prefix[j] - prefix[i - 1]
            if count > capacity:
                break
            if (blanks(count) + best[j + 1][0], 1 + best[j + 1][1]) == best[i]:
                pages: List[Optional[int]] = list(
                    range(starts[i - 1], starts[i - 1] + count)
                )
                pages.extend([None] * blanks(count))
                signatures.append(pages)
                i = j + 1
                break
    return signatures


def impose_chapters(
    total_pages: int,
    max_sheets: int,
    binding: Binding,
    chapter_starts: List[int],
) -> List[dict]:
    """按章节分帖的完整拼版：每帖额外给出原页起止页码与空白数。"""
    grouped = split_signatures_by_chapters(total_pages, max_sheets, chapter_starts)
    result: List[dict] = []
    for index, pages in enumerate(grouped, start=1):
        real_pages = [p for p in pages if p is not None]
        result.append(
            {
                "signature_index": index,
                "sheet_count": len(pages) // 4,
                "page_count_padded": len(pages),
                "page_start": real_pages[0],
                "page_end": real_pages[-1],
                "blank_count": len(pages) - len(real_pages),
                "sheets": impose_signature(pages, binding),
            }
        )
    return result


# ---------------------------------------------------------------------------
# 重印（reprint）：基于页面 ID 的两版拼版复用
# ---------------------------------------------------------------------------

# 一张印张四个页位的键：(正面左, 正面右, 背面左, 背面右)，空白页位为 None
SheetKey = Tuple[Optional[P], Optional[P], Optional[P], Optional[P]]


def split_signatures_from_pages(
    page_ids: List[P],
    max_sheets: int,
) -> List[List[Optional[P]]]:
    """按阅读顺序把页面 ID 分帖，规则与 :func:`split_signatures` 相同。

    每帖最多容纳 ``max_sheets * 4`` 页，前面的帖装满；仅末帖在尾部补 ``None``
    至 4 的倍数。
    """
    capacity = max_sheets * 4
    signatures: List[List[Optional[P]]] = []

    start = 0
    total = len(page_ids)
    while start < total:
        end = min(start + capacity, total)
        pages: List[Optional[P]] = list(page_ids[start:end])
        if len(pages) % 4 != 0:
            pages.extend([None] * (4 - len(pages) % 4))
        signatures.append(pages)
        start = end

    return signatures


def impose_from_pages(
    page_ids: List[P],
    max_sheets: int,
    binding: Binding,
) -> List[dict]:
    """页面 ID 版本的完整拼版：分帖并逐帖返回四页位（ID 或 ``None``）。"""
    grouped = split_signatures_from_pages(page_ids, max_sheets)
    result: List[dict] = []
    for index, pages in enumerate(grouped, start=1):
        result.append(
            {
                "signature_index": index,
                "sheet_count": len(pages) // 4,
                "page_count_padded": len(pages),
                "sheets": impose_signature(pages, binding),
            }
        )
    return result


def _sheet_key(sheet: dict) -> SheetKey:
    """取一张拼版结果四个页位，构成可比较的键（正左、正右、背左、背右）。"""
    return (
        sheet["front"]["left"],
        sheet["front"]["right"],
        sheet["back"]["left"],
        sheet["back"]["right"],
    )


def plan_reprint(
    old_page_ids: List[P],
    new_page_ids: List[P],
    max_sheets: int,
    binding: Binding,
    changed_page_ids: Collection[P],
) -> dict:
    """计算新版各印张能否复用旧版印张，否则标记整张重印。

    复用条件（缺一不可）：

    1. 新版印张四个页位（``None`` 表示空白）与某张旧版印张**完全相同**，
       允许跨帖匹配；
    2. 四个页位中的非空页面 ID 均不在 ``changed_page_ids`` 内；
    3. 每张旧版印张最多被复用一次。

    含空白页位的多张印张键可能相同（全空白张），按旧版帖号、张号顺序取用，
    保证结果确定。按新版帖号、张号顺序依次匹配可最大化复用张数：一旦一张新
    张被标记重印，相应的旧张仍留给后续新张。

    返回新版逐帖的复用/重印计划与重印总张数。
    """
    old_imposed = impose_from_pages(old_page_ids, max_sheets, binding)
    new_imposed = impose_from_pages(new_page_ids, max_sheets, binding)
    changed = set(changed_page_ids)

    # 旧版各四页位组合对应的可用印张列表（旧帖号, 旧张号），按帖号、张号排序
    available: dict = {}
    for signature in old_imposed:
        for sheet in signature["sheets"]:
            available.setdefault(_sheet_key(sheet), []).append(
                (signature["signature_index"], sheet["sheet_index"])
            )

    reprint_count = 0
    result_signatures: List[dict] = []

    for signature in new_imposed:
        result_sheets: List[dict] = []
        for sheet in signature["sheets"]:
            key = _sheet_key(sheet)
            is_changed = any(
                page_id is not None and page_id in changed for page_id in key
            )
            reuse: Optional[Tuple[int, int]] = None
            if not is_changed:
                candidates = available.get(key)
                if candidates:
                    reuse = candidates.pop(0)

            if reuse is None:
                reused = False
                old_signature_index: Optional[int] = None
                old_sheet_index: Optional[int] = None
                reprint_count += 1
            else:
                reused = True
                old_signature_index, old_sheet_index = reuse

            result_sheets.append(
                {
                    "sheet_index": sheet["sheet_index"],
                    "front": sheet["front"],
                    "back": sheet["back"],
                    "reused": reused,
                    "old_signature_index": old_signature_index,
                    "old_sheet_index": old_sheet_index,
                }
            )

        result_signatures.append(
            {
                "signature_index": signature["signature_index"],
                "sheet_count": signature["sheet_count"],
                "page_count_padded": signature["page_count_padded"],
                "sheets": result_sheets,
            }
        )

    return {
        "max_sheets_per_signature": max_sheets,
        "binding": binding,
        "signature_count": len(result_signatures),
        "reprint_sheet_count": reprint_count,
        "signatures": result_signatures,
    }


# ---------------------------------------------------------------------------
# 印张抽检（inspect）：乱序实物印张与预期拼版的配对核对
# ---------------------------------------------------------------------------

# 四页位固定顺序：(正面左, 正面右, 背面左, 背面右)，索引 0..3
SLOT_ORDER: Tuple[str, str, str, str] = (
    "front_left",
    "front_right",
    "back_left",
    "back_right",
)

# 实物印张可被解释的四种变换（顺序即同分裁决时的变换顺序）：
# 原样、左右镜像、正反互换、两者组合。
# 每项给出“观测页位 i 应与预期页位 PERM[i] 比较”的位置置换。
TRANSFORMS: Tuple[Tuple[str, Tuple[int, int, int, int]], ...] = (
    ("none", (0, 1, 2, 3)),
    ("mirror_lr", (1, 0, 3, 2)),
    ("flip_fb", (2, 3, 0, 1)),
    ("mirror_lr_flip_fb", (3, 2, 1, 0)),
)


class _Unread:
    """页位标记：实物页位未读出（请求中的 ``"?"``）。单例 :data:`UNREAD`。"""

    _instance = None

    def __new__(cls) -> "_Unread":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - 仅便于调试
        return "UNREAD"

    def __bool__(self) -> bool:
        return True


UNREAD = _Unread()

# 单个页位的值：页面 ID / None（空白）/ UNREAD（未读出）
SlotValue = object


def _hungarian_min(cost: List[List[int]]) -> List[int]:
    """方阵最小权完美匹配（O(n³) 匈牙利算法）。

    返回每个行号（0-based）匹配的列号（0-based）；输入方阵元素为整数
    （允许负权、数值较大），不可行的行/列以 0 权“哑边”填充，由调用方按
    真实边解码。
    """
    n = len(cost)
    # 比任意可行松弛量都大：任意真实边的缩减代价绝对值不超过全部边权绝对值之和
    inf = sum(abs(value) for row in cost for value in row) + 1
    u = [0] * (n + 1)
    v = [0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (n + 1)
        used = [False] * (n + 1)
        while p[j0] != 0:
            used[j0] = True
            i0 = p[j0]
            delta = inf
            j1 = 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    assignment = [0] * n
    for j in range(1, n + 1):
        assignment[p[j] - 1] = j - 1
    return assignment


def inspect_observed_sheets(
    page_ids: List[P],
    max_sheets: int,
    binding: Binding,
    observed_sheets: List[Tuple[SlotValue, SlotValue, SlotValue, SlotValue]],
) -> dict:
    """将乱序实物印张与按 :func:`impose_from_pages` 生成的预期印张配对核对。

    每张观测四页位的取值为页面 ID、``None``（空白）或 :data:`UNREAD`（未读出）。
    观测可按 :data:`TRANSFORMS` 的四种变换（原样、左右镜像、正反互换、两者组合）
    解释；仅当观测至少有一个**非空已读页面 ID**出现在某张预期印张上时，二者才
    允许配对。在每张预期印张、每张观测至多使用一次的约束下：

    1. 先最大化配对数；
    2. 再最大化已读页位吻合数（``None`` 与 ``None`` 也算吻合，``UNREAD`` 不计）；
    3. 同分按观测序号升序、预期帖号/张号升序、变换顺序裁决。

    返回逐观测的配对结果（帖号/张号/变换/吻合数/已知页位错误明细），
    以及未见的预期印张与无法配对的观测。
    """
    imposed = impose_from_pages(page_ids, max_sheets, binding)
    expected: List[dict] = []
    for signature in imposed:
        for sheet in signature["sheets"]:
            expected.append(
                {
                    "signature_index": signature["signature_index"],
                    "sheet_index": sheet["sheet_index"],
                    "slots": (
                        sheet["front"]["left"],
                        sheet["front"]["right"],
                        sheet["back"]["left"],
                        sheet["back"]["right"],
                    ),
                }
            )

    m = len(observed_sheets)
    n = len(expected)

    # edges[i]：观测 i 可配对的预期列 -> 候选信息（列号按帖号/张号升序）
    edges: List[List[dict]] = []
    for obs in observed_sheets:
        known_ids = {v for v in obs if v is not None and v is not UNREAD}
        candidates: List[dict] = []
        for col, exp in enumerate(expected):
            if not any(page_id in exp["slots"] for page_id in known_ids):
                continue
            best: Optional[dict] = None
            for transform_index, (transform_name, perm) in enumerate(TRANSFORMS):
                matches = 0
                mismatches: List[dict] = []
                for slot_index, value in enumerate(obs):
                    if value is UNREAD:
                        continue
                    expected_value = exp["slots"][perm[slot_index]]
                    if value == expected_value:
                        matches += 1
                    else:
                        mismatches.append(
                            {
                                "position": SLOT_ORDER[slot_index],
                                "observed": value,
                                "expected": expected_value,
                            }
                        )
                candidate = {
                    "col": col,
                    "matches": matches,
                    "transform_index": transform_index,
                    "transform": transform_name,
                    "errors": mismatches,
                }
                # 变换顺序裁决：取吻合数最多、序号最小者
                if best is None or (
                    candidate["matches"],
                    -candidate["transform_index"],
                ) > (best["matches"], -best["transform_index"]):
                    best = candidate
            assert best is not None
            candidates.append(best)
        candidates.sort(key=lambda c: c["col"])
        edges.append(candidates)

    # 单次最大权匹配完成“配对数 → 吻合数 → 字典序”三级目标：
    #   权重 = (PAIR_BASE + 吻合数) * BASE**m + 字典序奖赏
    # PAIR_BASE 大于任一方案的吻合数与字典序奖赏上限，BASE 大于任一字典序数位
    # 上限，因此整数位级比较严格对应目标优先级。字典序数位按观测序号从高位到
    # 低位排列：配对（数位 (n-col)）恒优于不配对（0），同配对下列号越小越优。
    size = max(m, n)
    lex_base = size + 1
    pair_base = 4 * m + lex_base ** m + 1
    # lex_weight[i][col] 已按 BASE 定位到观测 i 的数位
    lex_weight: List[List[int]] = [[0] * n for _ in range(m)]
    lex_scale = 1
    for i in range(m - 1, -1, -1):
        for candidate in edges[i]:
            lex_weight[i][candidate["col"]] = (n - candidate["col"]) * lex_scale
        lex_scale *= lex_base

    weight: List[List[int]] = [[0] * n for _ in range(m)]
    for i in range(m):
        for candidate in edges[i]:
            col = candidate["col"]
            weight[i][col] = (
                (pair_base + candidate["matches"]) * lex_base ** m
                + lex_weight[i][col]
            )

    # 匈牙利算法求最小权完美匹配；目标为最大化权和，故代价取负。
    # 方阵补 0 权“哑边”（不可配对的观测/预期列），解码时只认真实边。
    cost = [[0] * size for _ in range(size)]
    for i in range(m):
        for j in range(n):
            cost[i][j] = -weight[i][j]
    assignment = _hungarian_min(cost)

    chosen: List[Optional[dict]] = [None] * m
    edge_lookup = [
        {candidate["col"]: candidate for candidate in candidates}
        for candidates in edges
    ]
    for i, j in enumerate(assignment):
        if i < m and j < n and j in edge_lookup[i]:
            chosen[i] = edge_lookup[i][j]

    fixed_pairs = sum(1 for candidate in chosen if candidate is not None)

    result_observations: List[dict] = []
    matched_cols = set()
    for index, (obs, candidate) in enumerate(
        zip(observed_sheets, chosen), start=1
    ):
        front_left, front_right, back_left, back_right = obs
        item = {
            "observation_index": index,
            "front": {"left": front_left, "right": front_right},
            "back": {"left": back_left, "right": back_right},
            "matched": candidate is not None,
            "signature_index": None,
            "sheet_index": None,
            "transform": None,
            "matched_slot_count": 0,
            "errors": [],
        }
        if candidate is not None:
            exp = expected[candidate["col"]]
            matched_cols.add(candidate["col"])
            item.update(
                {
                    "signature_index": exp["signature_index"],
                    "sheet_index": exp["sheet_index"],
                    "transform": candidate["transform"],
                    "matched_slot_count": candidate["matches"],
                    "errors": candidate["errors"],
                }
            )
        result_observations.append(item)

    unseen_signatures = [
        {
            "signature_index": exp["signature_index"],
            "sheet_index": exp["sheet_index"],
            "front": {
                "left": exp["slots"][0],
                "right": exp["slots"][1],
            },
            "back": {
                "left": exp["slots"][2],
                "right": exp["slots"][3],
            },
        }
        for col, exp in enumerate(expected)
        if col not in matched_cols
    ]

    unmatched_observations = [
        {
            "observation_index": item["observation_index"],
            "front": item["front"],
            "back": item["back"],
        }
        for item in result_observations
        if not item["matched"]
    ]

    return {
        "max_sheets_per_signature": max_sheets,
        "binding": binding,
        "matched_observation_count": fixed_pairs,
        "unmatched_observation_count": m - fixed_pairs,
        "unseen_sheet_count": n - fixed_pairs,
        "observations": result_observations,
        "unmatched_observations": unmatched_observations,
        "unseen_signatures": unseen_signatures,
    }
