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

印张抽检（``inspect_imposition``）
----
- 先按相同规则生成预期印张；每张观测印张可按 原样 / 左右镜像 /
  正反互换 / 两者组合 四种变换解释；
- 仅当观测至少一个非空已读 ID 出现在某张预期印张上时允许两者配对；
- 每张预期印张与每张观测至多使用一次：先最大化配对数，再最大化
  已读页位吻合总数，同分按观测序号、预期帖号/张号、变换顺序裁决；
- ``"?"``（未读出）页位不计入吻合数，也不计错。
"""
from __future__ import annotations

import heapq
from typing import Collection, Dict, List, Literal, Optional, Tuple, TypeVar

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
# 印张抽检（inspect）：乱序实物印张与预期拼版的配对
# ---------------------------------------------------------------------------

#: 页位“未读出”标记（页面 ID 不得使用该字符串）
UNREAD = "?"

#: 观测印张可采用的解释变换，按裁决优先级排列：
#: identity=原样，mirror=左右镜像，flip=正反互换，mirror_flip=两者组合
INSPECT_TRANSFORMS = ("identity", "mirror", "flip", "mirror_flip")

# 四页位名称，顺序与 SheetKey 一致：正左、正右、背左、背右
_POSITION_NAMES = ("front.left", "front.right", "back.left", "back.right")


def _transform_perm(transform: str) -> Tuple[int, int, int, int]:
    """对齐排列：预期第 k 个页位对应观测四元组的第 perm[k] 个页位。"""
    if transform == "identity":
        return (0, 1, 2, 3)
    if transform == "mirror":
        # 左右镜像：观测的左页位实为预期的右页位
        return (1, 0, 3, 2)
    if transform == "flip":
        # 正反互换：观测的正面实为预期的背面
        return (2, 3, 0, 1)
    # mirror_flip：左右镜像与正反互换的组合
    return (3, 2, 1, 0)


def _best_transform(
    obs: SheetKey,
    exp: SheetKey,
) -> Tuple[int, str, Tuple[int, int, int, int]]:
    """观测 ``obs`` 对预期 ``exp`` 的最佳解释：(已读页位吻合数, 变换, 对齐排列)。

    已读出（非 ``"?"``）且与预期一致的页位计入吻合数；吻合数相同按
    :data:`INSPECT_TRANSFORMS` 顺序取先者。
    """
    best_matches = -1
    best_transform = INSPECT_TRANSFORMS[0]
    best_perm = _transform_perm(best_transform)
    for transform in INSPECT_TRANSFORMS:
        perm = _transform_perm(transform)
        matches = sum(
            1 for k in range(4)
            if obs[perm[k]] != UNREAD and obs[perm[k]] == exp[k]
        )
        if matches > best_matches:
            best_matches = matches
            best_transform = transform
            best_perm = perm
    return best_matches, best_transform, best_perm


def _max_weight_matching(
    n_left: int,
    n_right: int,
    edge_costs: Dict[Tuple[int, int], int],
) -> List[Tuple[int, int]]:
    """非负费用二分图的最小费用最大流，返回配对的 (左下标, 右下标) 列表。

    所有边费用非负，连续最短增广路（Dijkstra + 势函数）增广至无可增广路
    为止，得到最小费用最大流：先最大化配对数，再最小化总费用
    （即最大化总权重，权重 = 常数 - 费用）。
    """
    size = n_left + n_right + 2
    source, sink = 0, size - 1
    # 邻接表，边为 [终点, 剩余容量, 单位费用, 反向边下标]
    graph: List[List[list]] = [[] for _ in range(size)]

    def add_edge(u: int, v: int, cap: int, cost: int) -> None:
        graph[u].append([v, cap, cost, len(graph[v])])
        graph[v].append([u, 0, -cost, len(graph[u]) - 1])

    for i in range(n_left):
        add_edge(source, 1 + i, 1, 0)
    for (i, j), cost in edge_costs.items():
        add_edge(1 + i, 1 + n_left + j, 1, cost)
    for j in range(n_right):
        add_edge(1 + n_left + j, sink, 1, 0)

    inf = float("inf")
    potential = [0] * size  # 初始费用非负，零势函数即满足既约费用非负
    while True:
        dist = [inf] * size
        prev_node = [-1] * size
        prev_edge = [-1] * size
        dist[source] = 0
        heap: List[Tuple[int, int]] = [(0, source)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u]:
                continue
            for k, edge in enumerate(graph[u]):
                v, cap, cost, _ = edge
                if cap <= 0:
                    continue
                nd = d + cost + potential[u] - potential[v]
                if nd < dist[v]:
                    dist[v] = nd
                    prev_node[v] = u
                    prev_edge[v] = k
                    heapq.heappush(heap, (nd, v))
        if dist[sink] == inf:
            break
        for v in range(size):
            if dist[v] < inf:
                potential[v] += dist[v]
        # 沿最短增广路增广 1 单位流量
        v = sink
        while v != source:
            edge = graph[prev_node[v]][prev_edge[v]]
            edge[1] -= 1
            graph[v][edge[3]][1] += 1
            v = prev_node[v]

    pairs: List[Tuple[int, int]] = []
    for i in range(n_left):
        for edge in graph[1 + i]:
            # 左->右正向边容量被用光（剩余 0）即表示该边被选中
            if 1 + n_left <= edge[0] < 1 + n_left + n_right and edge[1] == 0:
                pairs.append((i, edge[0] - 1 - n_left))
    return pairs


def inspect_imposition(
    page_ids: List[str],
    max_sheets: int,
    binding: Binding,
    observed_sheets: List[dict],
) -> dict:
    """把乱序观测的实物印张与预期拼版印张一一配对，并给出已知页位错误明细。

    配对规则：

    1. 先用与 :func:`impose_from_pages` 相同的规则生成预期印张；
    2. 每张观测可按四种变换解释：identity（原样）、mirror（左右镜像）、
       flip（正反互换）、mirror_flip（两者组合）；
    3. 仅当观测至少一个非空且已读出的页面 ID 出现在某张预期印张上时，
       该观测才允许与该预期印张配对；
    4. 每张预期印张与每张观测至多使用一次，依次优化：配对数最大 →
       已读页位吻合总数最大 → 按观测序号、预期帖号/张号、变换顺序
       取字典序最小者（配对优于不配对）；
    5. ``"?"`` 页位不参与吻合计数，也不计入错误；空白（``None``）页位
       视为已读，与预期一致计吻合、不一致计错误。

    ``observed_sheets`` 每项为 ``{"front": {"left", "right"}, "back": {...}}``，
    页位取值为页面 ID、``None``（空白）或 ``"?"``（未读出）。

    返回每张观测的配对结果与错误明细、未被观测到的预期印张
    （``missing_sheets``）与无法配对的观测（``unmatched_observations``）。
    """
    expected = impose_from_pages(page_ids, max_sheets, binding)
    exp_sheets: List[dict] = []
    for signature in expected:
        for sheet in signature["sheets"]:
            exp_sheets.append(
                {
                    "signature_index": signature["signature_index"],
                    "sheet_index": sheet["sheet_index"],
                    "key": _sheet_key(sheet),
                    "front": sheet["front"],
                    "back": sheet["back"],
                }
            )

    obs_keys: List[SheetKey] = [
        (
            observed["front"]["left"],
            observed["front"]["right"],
            observed["back"]["left"],
            observed["back"]["right"],
        )
        for observed in observed_sheets
    ]

    n = len(obs_keys)
    m = len(exp_sheets)

    # 候选边：观测至少一个非空已读 ID 出现在该预期印张上才允许配对。
    # 边权 = 吻合数 * MATCH_MULT + 字典序项：字典序项按观测序号指数递减、
    # 同一观测内随预期（帖号, 张号）升序递减，保证“先吻合总数，再按
    # 观测序号、预期帖号/张号裁决”；配对本身权重恒正，故最大流即最大配对数。
    edge_costs: Dict[Tuple[int, int], int] = {}
    edge_info: Dict[Tuple[int, int], Tuple[int, str, Tuple[int, int, int, int]]] = {}
    if n and m:
        base = m + 1
        match_mult = base ** n  # 大于任何可能的字典序项总和
        max_weight = match_mult * 4 + base ** n  # 大于任何单边权重
        exp_id_sets = [
            {page_id for page_id in exp["key"] if page_id is not None}
            for exp in exp_sheets
        ]
        for i, obs in enumerate(obs_keys):
            read_ids = {v for v in obs if v is not None and v != UNREAD}
            if not read_ids:
                continue
            lex_unit = base ** (n - 1 - i)
            for j, exp in enumerate(exp_sheets):
                if read_ids.isdisjoint(exp_id_sets[j]):
                    continue
                matches, transform, perm = _best_transform(obs, exp["key"])
                weight = match_mult * matches + lex_unit * (m - j)
                edge_costs[(i, j)] = max_weight - weight
                edge_info[(i, j)] = (matches, transform, perm)

    pairs = _max_weight_matching(n, m, edge_costs)

    matched_obs: Dict[int, Tuple[int, int, str, Tuple[int, int, int, int]]] = {}
    used_exp = set()
    for i, j in pairs:
        matches, transform, perm = edge_info[(i, j)]
        matched_obs[i] = (j, matches, transform, perm)
        used_exp.add(j)

    observations: List[dict] = []
    for i, observed in enumerate(observed_sheets):
        entry = {
            "observation_index": i + 1,
            "front": observed["front"],
            "back": observed["back"],
        }
        if i in matched_obs:
            j, matches, transform, perm = matched_obs[i]
            exp = exp_sheets[j]
            errors: List[dict] = []
            for k in range(4):
                read = obs_keys[i][perm[k]]
                if read != UNREAD and read != exp["key"][k]:
                    errors.append(
                        {
                            "position": _POSITION_NAMES[perm[k]],
                            "observed": read,
                            "expected": exp["key"][k],
                        }
                    )
            entry.update(
                {
                    "matched": True,
                    "signature_index": exp["signature_index"],
                    "sheet_index": exp["sheet_index"],
                    "transform": transform,
                    "matched_positions": matches,
                    "errors": errors,
                }
            )
        else:
            entry.update(
                {
                    "matched": False,
                    "signature_index": None,
                    "sheet_index": None,
                    "transform": None,
                    "matched_positions": None,
                    "errors": [],
                }
            )
        observations.append(entry)

    missing_sheets = [
        {
            "signature_index": exp["signature_index"],
            "sheet_index": exp["sheet_index"],
            "front": exp["front"],
            "back": exp["back"],
        }
        for j, exp in enumerate(exp_sheets)
        if j not in used_exp
    ]
    unmatched_observations = [
        {
            "observation_index": i + 1,
            "front": observed["front"],
            "back": observed["back"],
        }
        for i, observed in enumerate(observed_sheets)
        if i not in matched_obs
    ]

    return {
        "signature_count": len(expected),
        "sheet_count": m,
        "matched_count": len(pairs),
        "observations": observations,
        "missing_sheets": missing_sheets,
        "unmatched_observations": unmatched_observations,
    }
