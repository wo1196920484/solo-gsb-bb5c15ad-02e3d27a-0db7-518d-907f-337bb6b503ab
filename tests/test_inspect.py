"""印张抽检算法单元测试。"""
from app.imposition import inspect_observed_sheets, impose_from_pages, UNREAD


def _r(result, index):
    return result["observations"][index - 1]


def test_perfect_as_is_observation_matches_none():
    pages = [f"p{i}" for i in range(1, 9)]
    # 左装订最外张：正面 (p8,p1)、背面 (p2,p7)
    result = inspect_observed_sheets(pages, 2, "left", [("p8", "p1", "p2", "p7")])
    obs = _r(result, 1)
    assert obs["matched"] is True
    assert (obs["signature_index"], obs["sheet_index"]) == (1, 1)
    assert obs["transform"] == "none"
    assert obs["matched_slot_count"] == 4
    assert obs["errors"] == []
    assert result["unseen_signatures"] == [
        {
            "signature_index": 1,
            "sheet_index": 2,
            "front": {"left": "p6", "right": "p3"},
            "back": {"left": "p4", "right": "p5"},
        }
    ]


def test_transforms_mirror_flip_and_both():
    pages = ["a", "b", "c", "d"]
    # 左装订单帖单张：正面 (d,a)、背面 (b,c)
    cases = [
        ("mirror_lr", ("a", "d", "c", "b")),
        ("flip_fb", ("b", "c", "d", "a")),
        ("mirror_lr_flip_fb", ("c", "b", "a", "d")),
    ]
    for transform, observed in cases:
        result = inspect_observed_sheets(pages, 1, "left", [observed])
        obs = _r(result, 1)
        assert obs["matched"] is True
        assert obs["transform"] == transform
        assert obs["matched_slot_count"] == 4
        assert obs["errors"] == []


def test_unread_question_mark_never_counts_as_error():
    pages = ["a", "b", "c", "d"]
    # 预期 (d,a)/(b,c)；两个页位未读出，其余吻合
    result = inspect_observed_sheets(
        pages, 1, "left", [(UNREAD, "a", "b", UNREAD)]
    )
    obs = _r(result, 1)
    assert obs["matched"] is True
    assert obs["transform"] == "none"
    assert obs["matched_slot_count"] == 2
    assert obs["errors"] == []


def test_known_mismatch_reported_with_position_and_values():
    pages = ["a", "b", "c", "d"]
    result = inspect_observed_sheets(
        pages, 1, "left", [("d", "a", "X", "c")]
    )
    obs = _r(result, 1)
    assert obs["matched"] is True
    assert obs["matched_slot_count"] == 3
    assert obs["errors"] == [
        {"position": "back_left", "observed": "X", "expected": "b"}
    ]


def test_null_blank_known_slot_counts_as_match_or_error():
    # 1 页补 3 空白：预期正面 (None,a)、背面 (None,None)
    pages = ["a"]
    result = inspect_observed_sheets(
        pages, 1, "left", [(None, "a", None, None)]
    )
    assert _r(result, 1)["matched_slot_count"] == 4

    # 空白页位读成具体 ID 也算错误
    result = inspect_observed_sheets(
        pages, 1, "left", [("a", "a", None, None)]
    )
    obs = _r(result, 1)
    assert obs["matched_slot_count"] == 3
    assert obs["errors"] == [
        {"position": "front_left", "observed": "a", "expected": None}
    ]


def test_observation_needs_at_least_one_expected_id():
    pages = ["a", "b", "c", "d"]
    # 全未读出、全空白、仅外来 ID 均无法配对
    result = inspect_observed_sheets(
        pages,
        1,
        "left",
        [
            (UNREAD, UNREAD, UNREAD, UNREAD),
            (None, None, None, None),
            ("x1", "x2", None, UNREAD),
        ],
    )
    assert result["matched_observation_count"] == 0
    assert result["unmatched_observation_count"] == 3
    assert [o["observation_index"] for o in result["unmatched_observations"]] == [
        1,
        2,
        3,
    ]
    # 唯一预期印张未见
    assert result["unseen_sheet_count"] == 1
    assert result["unseen_signatures"][0]["sheet_index"] == 1


def test_maximize_pairs_then_matches_overlapping_observations():
    # 两张观测都含 p8（同属预期最外张）：
    #   obs1 与最外张 4 吻合；obs2 仅 p8 一点线索，可与含 p8 的张配对。
    # 配对数优先：obs2 抢先占最外张会让 obs1 无法配对（p1..p7 不在其他张），
    # 最优方案为 obs1->最外张、obs2 落单。
    pages = [f"p{i}" for i in range(1, 9)]
    result = inspect_observed_sheets(
        pages,
        2,
        "left",
        [("p8", "p1", "p2", "p7"), ("p8", None, None, None)],
    )
    assert _r(result, 1)["matched"] is True
    assert _r(result, 1)["matched_slot_count"] == 4
    assert _r(result, 2)["matched"] is False
    assert result["matched_observation_count"] == 1


def test_tie_break_observation_then_signature_sheet():
    # 8 页恰好 2 张：观测只携带内张页面 p3 的线索 -> 只能配内张 (1,2)。
    pages = [f"p{i}" for i in range(1, 9)]
    imposed = impose_from_pages(pages, 2, "left")
    # 最外张 (p8,p1)/(p2,p7)，内张 (p6,p3)/(p4,p5)
    assert imposed[0]["sheets"][0]["front"] == {"left": "p8", "right": "p1"}
    assert imposed[0]["sheets"][1]["front"] == {"left": "p6", "right": "p3"}

    # 原样与左右镜像都只有 1 吻合，同分取变换顺序在前的 none
    result = inspect_observed_sheets(
        pages, 2, "left", [("p3", "p3", None, None)]
    )
    obs = _r(result, 1)
    assert (obs["signature_index"], obs["sheet_index"]) == (1, 2)
    assert obs["transform"] == "none"
    assert obs["matched_slot_count"] == 1


def test_transform_tie_prefers_none_then_declared_order():
    pages = ["a", "b", "c", "d"]
    # 预期 (d,a)/(b,c)。观测 (a,d,b,c)：原样与左右镜像都恰好 2 吻合
    # （原样错在正面两位，镜像错在背面两位），同分取顺序在前的 none。
    result = inspect_observed_sheets(
        pages, 1, "left", [("a", "d", "b", "c")]
    )
    obs = _r(result, 1)
    assert obs["transform"] == "none"
    assert obs["matched_slot_count"] == 2
    assert [error["position"] for error in obs["errors"]] == [
        "front_left",
        "front_right",
    ]


def test_cross_signature_and_unseen_listing():
    # 16 页、每帖 1 张（4 页/帖）共 4 帖；只抽到第 3 帖的实物（正反互换）
    pages = [f"p{i}" for i in range(1, 17)]
    # 帖 3 原页 p9..p12：正面 (p12,p9)、背面 (p10,p11)
    observed = [("p10", "p11", "p12", "p9")]
    result = inspect_observed_sheets(pages, 1, "left", observed)
    obs = _r(result, 1)
    assert (obs["signature_index"], obs["sheet_index"]) == (3, 1)
    assert obs["transform"] == "flip_fb"
    assert [s["signature_index"] for s in result["unseen_signatures"]] == [
        1,
        2,
        4,
    ]
    assert result["unseen_sheet_count"] == 3


def test_right_binding_expected_positions():
    pages = ["a", "b", "c", "d"]
    # 右装订：正面 (a,d)、背面 (c,b)
    result = inspect_observed_sheets(
        pages, 1, "right", [("a", "d", "c", "b")]
    )
    obs = _r(result, 1)
    assert obs["transform"] == "none"
    assert obs["matched_slot_count"] == 4


def test_matched_slot_optimization_global():
    # 观测可与两张预期配对但吻合数不同：最大化总吻合数
    # 帖 1：p1..p4 -> (p4,p1)/(p2,p3)
    # 帖 2：p5..p8 -> (p8,p5)/(p6,p7)
    pages = [f"p{i}" for i in range(1, 9)]
    # obs1 原样最外张 4 吻合；obs2 是内张原样 4 吻合，
    # 但额外构造一张只能低吻合配内张的观测，验证高吻合优先
    obs_outer = ("p4", "p1", "p2", "p3")
    obs_inner = ("p8", "p5", "p6", "p7")
    result = inspect_observed_sheets(
        pages, 1, "left", [obs_outer, obs_inner]
    )
    assert result["matched_observation_count"] == 2
    assert _r(result, 1)["matched_slot_count"] == 4
    assert _r(result, 2)["matched_slot_count"] == 4
    assert (_r(result, 1)["signature_index"], _r(result, 2)["signature_index"]) == (
        1,
        2,
    )
