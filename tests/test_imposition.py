"""拼版算法单元测试。"""
import pytest

from app.imposition import (
    split_signatures,
    split_signatures_by_chapters,
    impose_signature,
    impose,
    impose_chapters,
)


def test_split_exact_multiple_no_padding():
    # 10 页、每帖最多 4 张（16 页容量）-> 单帖 12 页补 2 空白
    sigs = split_signatures(10, 4)
    assert len(sigs) == 1
    assert sigs[0] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, None, None]


def test_split_full_signatures_no_padding():
    # 100 页、每帖 4 张 -> 6 个满帖 + 末帖 4 页
    sigs = split_signatures(100, 4)
    assert len(sigs) == 7
    for i in range(6):
        assert len(sigs[i]) == 16
        assert all(isinstance(p, int) for p in sigs[i])
        assert sigs[i][0] == 1 + 16 * i
        assert sigs[i][-1] == 16 + 16 * i
    assert sigs[6] == [97, 98, 99, 100]


def test_split_last_signature_padding_sizes():
    # 1..4 页、每帖 4 张，末帖（=唯一帖）都应补到 4 的倍数
    expected = {
        1: [1, None, None, None],
        2: [1, 2, None, None],
        3: [1, 2, 3, None],
        4: [1, 2, 3, 4],
    }
    for total, pages in expected.items():
        assert split_signatures(total, 4) == [pages]


def test_split_respects_max_sheets_capacity():
    # 每帖 2 张 -> 容量 8 页；18 页 -> 8 + 8 + 2(补到 4)
    sigs = split_signatures(18, 2)
    assert [len(s) for s in sigs] == [8, 8, 4]
    assert sigs[2] == [17, 18, None, None]
    # 任何帖的纸张数都不超过上限
    assert all(len(s) // 4 <= 2 for s in sigs)


def test_left_binding_outermost_sheet_4pages():
    # 最外张正面 = 末页/首页；背面 = 次页/倒数第二页
    sheets = impose_signature([1, 2, 3, 4], "left")
    assert sheets[0]["front"] == {"left": 4, "right": 1}
    assert sheets[0]["back"] == {"left": 2, "right": 3}


def test_left_binding_16_pages_order():
    pages = list(range(1, 17))
    sheets = impose_signature(pages, "left")
    assert len(sheets) == 4
    # 从外到内四张
    assert sheets[0]["front"] == {"left": 16, "right": 1}
    assert sheets[0]["back"] == {"left": 2, "right": 15}
    assert sheets[1]["front"] == {"left": 14, "right": 3}
    assert sheets[1]["back"] == {"left": 4, "right": 13}
    assert sheets[2]["front"] == {"left": 12, "right": 5}
    assert sheets[2]["back"] == {"left": 6, "right": 11}
    assert sheets[3]["front"] == {"left": 10, "right": 7}
    assert sheets[3]["back"] == {"left": 8, "right": 9}


def test_right_binding_mirrors_left():
    pages = list(range(1, 17))
    left = impose_signature(pages, "left")
    right = impose_signature(pages, "right")
    for ls, rs in zip(left, right):
        assert ls["sheet_index"] == rs["sheet_index"]
        assert rs["front"] == {"left": ls["front"]["right"], "right": ls["front"]["left"]}
        assert rs["back"] == {"left": ls["back"]["right"], "right": ls["back"]["left"]}


def test_blank_pages_appear_as_none():
    # 5 页 -> 末帖 1..5 + 3 空白
    result = impose(5, 4, "left")
    assert len(result) == 1
    sheets = result[0]["sheets"]
    # 帖共 8 页: [1,2,3,4,5,None,None,None]
    # 最外张: 正面 8(None)/1, 背面 2/7(None)
    assert sheets[0]["front"] == {"left": None, "right": 1}
    assert sheets[0]["back"] == {"left": 2, "right": None}
    # 最内张: 正面 6(None)/5, 背面 6索引? 本地索引:
    # k=1: front_left=n-1-2=5 -> pages[5]=None; front_right=pages[2]=3
    # back_left=pages[3]=4; back_right=pages[4]=5
    assert sheets[1]["front"] == {"left": None, "right": 3}
    assert sheets[1]["back"] == {"left": 4, "right": 5}


def test_impose_multi_signature_indexes_and_page_continuity():
    result = impose(20, 2, "left")  # 容量 8 页/帖 -> 8,8,4
    assert [s["signature_index"] for s in result] == [1, 2, 3]
    assert [s["sheet_count"] for s in result] == [2, 2, 1]
    assert result[2]["sheets"][0]["front"] == {"left": 20, "right": 17}
    assert result[2]["sheets"][0]["back"] == {"left": 18, "right": 19}

    # 所有非空页码 1..20 且不重不漏
    seen = []
    for sig in result:
        for sheet in sig["sheets"]:
            for side in ("front", "back"):
                for pos in ("left", "right"):
                    value = sheet[side][pos]
                    if value is not None:
                        seen.append(value)
    assert sorted(seen) == list(range(1, 21))


def test_chapters_single_chapter_matches_basic_split():
    # 单章 = 整本书，结果与无章节分帖一致
    assert split_signatures_by_chapters(10, 4, [1]) == split_signatures(10, 4)


def test_chapters_adjacent_merged_into_one_signature():
    # 相邻章节可合帖：两章共 8 页、容量 8 -> 合为一帖，0 空白
    sigs = split_signatures_by_chapters(8, 2, [1, 5])
    assert sigs == [[1, 2, 3, 4, 5, 6, 7, 8]]


def test_chapters_never_cross_signature():
    # 每章 4 页、容量 4 -> 每章独占一帖
    sigs = split_signatures_by_chapters(8, 1, [1, 5])
    assert sigs == [[1, 2, 3, 4], [5, 6, 7, 8]]


def test_chapters_minimize_blank_pages():
    # 容量 8、章长 5/3/2：[1-5]+[6-10] 需 6 空白；[1-8]+[9-10] 仅需 2 空白
    sigs = split_signatures_by_chapters(10, 2, [1, 6, 9])
    assert sigs == [
        [1, 2, 3, 4, 5, 6, 7, 8],
        [9, 10, None, None],
    ]


def test_chapters_minimize_signature_count_after_blanks():
    # 空白相同（0）时取帖数更少：合帖 1 帖优于分 2 帖
    sigs = split_signatures_by_chapters(8, 2, [1, 5])
    assert len(sigs) == 1


def test_chapters_prefer_earliest_split_on_tie():
    # 空白、帖数均相同：优先最早分帖边界
    # -> [1-4]|[5-12]|[13-20] 而非 [1-8]|[9-12]|[13-20]
    sigs = split_signatures_by_chapters(20, 2, [1, 5, 9, 13])
    assert sigs == [
        [1, 2, 3, 4],
        [5, 6, 7, 8, 9, 10, 11, 12],
        [13, 14, 15, 16, 17, 18, 19, 20],
    ]


def test_chapters_too_long_single_chapter_raises():
    # 单章 10 页 > 容量 8，无法分帖
    with pytest.raises(ValueError):
        split_signatures_by_chapters(10, 2, [1])


def test_impose_chapters_reports_page_range_and_blanks():
    result = impose_chapters(10, 2, "left", [1, 6, 9])
    assert [s["signature_index"] for s in result] == [1, 2]
    assert result[0]["page_start"] == 1
    assert result[0]["page_end"] == 8
    assert result[0]["blank_count"] == 0
    assert result[1]["page_start"] == 9
    assert result[1]["page_end"] == 10
    assert result[1]["blank_count"] == 2
    # 每帖仍按现有正反面规则拼版
    assert result[0]["sheets"][0]["front"] == {"left": 8, "right": 1}
    assert result[1]["sheets"][0]["front"] == {"left": None, "right": 9}
    assert result[1]["sheets"][0]["back"] == {"left": 10, "right": None}


def test_impose_chapters_page_coverage_and_right_binding():
    result = impose_chapters(20, 2, "right", [1, 5, 9, 13])
    # 所有非空页码 1..20 且不重不漏
    seen = []
    for sig in result:
        for sheet in sig["sheets"]:
            for side in ("front", "back"):
                for pos in ("left", "right"):
                    value = sheet[side][pos]
                    if value is not None:
                        seen.append(value)
    assert sorted(seen) == list(range(1, 21))
    # 右装订镜像：首帖最外张正面 = 首页/末页
    assert result[0]["sheets"][0]["front"] == {"left": 1, "right": 4}
