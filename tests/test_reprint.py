"""重印复用算法单元测试。"""
from app.imposition import (
    impose_from_pages,
    plan_reprint,
    split_signatures_from_pages,
)


def test_split_page_ids_pads_last_signature():
    # 10 个页面 ID、每帖最多 4 张（16 容量）-> 单帖，尾部补 2 空白
    sigs = split_signatures_from_pages(["p1", "p2"], 4)
    assert sigs == [["p1", "p2", None, None]]


def test_split_page_ids_multi_signature():
    ids = [f"p{i}" for i in range(1, 9)]  # 容量 4 页/帖
    sigs = split_signatures_from_pages(ids, 1)
    assert sigs == [["p1", "p2", "p3", "p4"], ["p5", "p6", "p7", "p8"]]


def test_impose_from_pages_positions_match_basic():
    # 页位规则与普通拼版一致，仅把页码换成页面 ID
    result = impose_from_pages(["a", "b", "c", "d"], 2, "left")
    sheet = result[0]["sheets"][0]
    assert sheet["front"] == {"left": "d", "right": "a"}
    assert sheet["back"] == {"left": "b", "right": "c"}


def test_impose_from_pages_blanks_are_none():
    result = impose_from_pages(["a"], 1, "left")
    sheet = result[0]["sheets"][0]
    assert sheet["front"] == {"left": None, "right": "a"}
    assert sheet["back"] == {"left": None, "right": None}


def test_unchanged_identical_book_reuses_everything():
    ids = [f"p{i}" for i in range(1, 17)]
    plan = plan_reprint(ids, list(ids), 4, "left", set())
    assert plan["reprint_sheet_count"] == 0
    sheets = [s for sig in plan["signatures"] for s in sig["sheets"]]
    assert all(s["reused"] for s in sheets)
    # 同帖同张复用
    assert [(s["old_signature_index"], s["old_sheet_index"]) for s in sheets] == [
        (1, 1), (1, 2), (1, 3), (1, 4)
    ]
    # 页位为新版页面 ID
    assert sheets[0]["front"] == {"left": "p16", "right": "p1"}


def test_changed_page_forces_whole_sheet_reprint():
    # 8 页一帖两张：左装订下 p8..p1 在最外张，p6..p3 在内张
    old = ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"]
    new = ["p1", "p2", "p3", "p4", "p5", "p6X", "p7", "p8"]
    plan = plan_reprint(old, new, 2, "left", {"p6X"})
    outer, inner = plan["signatures"][0]["sheets"]
    # 最外张四页位均未改动且与旧版相同 -> 复用
    assert outer["reused"] is True
    assert (outer["old_signature_index"], outer["old_sheet_index"]) == (1, 1)
    # 内张含改动页 -> 整张重印
    assert inner["reused"] is False
    assert inner["old_signature_index"] is None
    assert inner["old_sheet_index"] is None
    assert plan["reprint_sheet_count"] == 1


def test_changed_page_id_not_on_matched_sheet_still_allows_reuse():
    # 改动的是新版页面，但复用张四页位不含该 ID
    old = ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"]
    # 新版额外插入内容导致帖结构变化（10 页 -> 8 + 2 补空白），
    # 改动页 p9 落在第 2 帖，第 1 帖与旧版完全相同
    new = ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10"]
    plan = plan_reprint(old, new, 2, "left", {"p9", "p10"})
    sig1 = plan["signatures"][0]
    assert all(s["reused"] for s in sig1["sheets"])
    # 末帖两张页位均为新内容 -> 重印
    assert plan["signatures"][1]["sheets"][0]["reused"] is False
    assert plan["reprint_sheet_count"] == 1


def test_cross_signature_reuse_when_blocks_move():
    # 24 页、每帖 2 张（8 页/帖）：新版把帖 1 与帖 3 的 8 页块整体交换，
    # 允许跨帖匹配 -> 新帖 1 复用旧帖 3、新帖 3 复用旧帖 1
    old = [f"p{i:02d}" for i in range(1, 25)]
    new = [f"p{i:02d}" for i in list(range(17, 25)) + list(range(9, 17)) + list(range(1, 9))]
    plan = plan_reprint(old, new, 2, "left", set())
    assert plan["reprint_sheet_count"] == 0
    mapping = {
        (sig["signature_index"], s["sheet_index"]): (
            s["old_signature_index"],
            s["old_sheet_index"],
        )
        for sig in plan["signatures"]
        for s in sig["sheets"]
    }
    assert mapping[(1, 1)] == (3, 1)
    assert mapping[(1, 2)] == (3, 2)
    assert mapping[(2, 1)] == (2, 1)
    assert mapping[(3, 2)] == (1, 2)


def test_each_old_sheet_used_at_most_once():
    # 旧版 2 页补 2 空白：唯一印张键为 (None,p1,p2,None)（左装订）
    # 新版 10 页 -> 8 页满帖 + 末帖 2 页补 2 空白，末帖页位与旧版相同，
    # 但旧版只有 1 张可复用；再构造一张相同键的新张也不得二次复用。
    old = ["x1", "x2"]
    # 新版前 8 页均为新 ID，末 2 页恰好是 x1/x2
    new = ["n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8", "x1", "x2"]
    plan = plan_reprint(old, new, 2, "left", set())
    reused = [
        s
        for sig in plan["signatures"]
        for s in sig["sheets"]
        if s["reused"]
    ]
    assert len(reused) == 1
    assert (reused[0]["old_signature_index"], reused[0]["old_sheet_index"]) == (1, 1)
    # 被复用的是新版末帖那张
    assert plan["signatures"][1]["sheets"][0]["reused"] is True
    assert plan["reprint_sheet_count"] == 2  # 满帖 2 张重印


def test_right_binding_key_match():
    # 右装订镜像页位：两版一致即可复用
    ids = ["a", "b", "c", "d"]
    plan = plan_reprint(ids, list(ids), 2, "right", set())
    sheet = plan["signatures"][0]["sheets"][0]
    assert sheet["front"] == {"left": "a", "right": "d"}
    assert sheet["reused"] is True


def test_reprinted_sheet_still_lists_new_positions():
    old = ["a", "b", "c", "d"]
    new = ["a", "B", "c", "d"]
    plan = plan_reprint(old, new, 2, "left", {"B"})
    sheet = plan["signatures"][0]["sheets"][0]
    assert sheet["reused"] is False
    assert sheet["front"] == {"left": "d", "right": "a"}
    assert sheet["back"] == {"left": "B", "right": "c"}
