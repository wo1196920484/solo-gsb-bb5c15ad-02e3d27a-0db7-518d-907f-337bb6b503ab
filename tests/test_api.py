"""API 层测试：正常请求与非法参数（4xx）。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_impose_basic_left():
    response = client.post(
        "/api/v1/impose",
        json={
            "total_pages": 16,
            "max_sheets_per_signature": 4,
            "binding": "left",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["signature_count"] == 1
    assert data["signatures"][0]["signature_index"] == 1
    assert data["signatures"][0]["sheet_count"] == 4
    first = data["signatures"][0]["sheets"][0]
    assert first["sheet_index"] == 1
    assert first["front"] == {"left": 16, "right": 1}
    assert first["back"] == {"left": 2, "right": 15}


def test_impose_right_binding():
    response = client.post(
        "/api/v1/impose",
        json={
            "total_pages": 16,
            "max_sheets_per_signature": 4,
            "binding": "right",
        },
    )
    assert response.status_code == 200
    first = response.json()["signatures"][0]["sheets"][0]
    assert first["front"] == {"left": 1, "right": 16}
    assert first["back"] == {"left": 15, "right": 2}


def test_impose_null_blank_pages():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 1, "max_sheets_per_signature": 1, "binding": "left"},
    )
    assert response.status_code == 200
    sheet = response.json()["signatures"][0]["sheets"][0]
    # 1 页补 3 空白：最外张正面 空白/1
    assert sheet["front"] == {"left": None, "right": 1}
    assert sheet["back"] == {"left": None, "right": None}


def test_invalid_total_pages_zero():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 0, "max_sheets_per_signature": 4, "binding": "left"},
    )
    assert 400 <= response.status_code < 500
    assert response.status_code == 422


def test_invalid_total_pages_negative():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": -5, "max_sheets_per_signature": 4, "binding": "left"},
    )
    assert response.status_code == 422


def test_invalid_total_pages_not_integer():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 1.5, "max_sheets_per_signature": 4, "binding": "left"},
    )
    assert response.status_code == 422


def test_invalid_max_sheets_zero():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 10, "max_sheets_per_signature": 0, "binding": "left"},
    )
    assert response.status_code == 422


def test_invalid_binding_value():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 10, "max_sheets_per_signature": 4, "binding": "top"},
    )
    assert response.status_code == 422


def test_missing_required_field():
    response = client.post(
        "/api/v1/impose",
        json={"total_pages": 10, "max_sheets_per_signature": 4},
    )
    assert response.status_code == 422


def test_unknown_field_rejected():
    response = client.post(
        "/api/v1/impose",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 4,
            "binding": "left",
            "extra": 1,
        },
    )
    assert response.status_code == 422


def test_empty_body_returns_422():
    response = client.post("/api/v1/impose", json={})
    assert response.status_code == 422


def test_impose_chapters_basic():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 20,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [1, 5, 9, 13],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["signature_count"] == 3
    ranges = [
        (s["page_start"], s["page_end"], s["blank_count"])
        for s in data["signatures"]
    ]
    assert ranges == [(1, 4, 0), (5, 12, 0), (13, 20, 0)]
    # 沿用 sheets 页位结构：首帖最外张正面 = 末页/首页
    first = data["signatures"][0]["sheets"][0]
    assert first["front"] == {"left": 4, "right": 1}
    assert first["back"] == {"left": 2, "right": 3}


def test_impose_chapters_right_binding_and_blanks():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "right",
            "chapter_starts": [1, 6, 9],
        },
    )
    assert response.status_code == 200
    sigs = response.json()["signatures"]
    assert [(s["page_start"], s["page_end"]) for s in sigs] == [(1, 8), (9, 10)]
    # 右装订镜像：最外张正面 = 首页/末页
    assert sigs[0]["sheets"][0]["front"] == {"left": 1, "right": 8}
    # 末帖 2 页补 2 空白
    assert sigs[1]["blank_count"] == 2
    assert sigs[1]["sheets"][0]["front"] == {"left": 9, "right": None}


def test_chapters_first_start_not_one():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [2, 5],
        },
    )
    assert response.status_code == 422


def test_chapters_not_strictly_increasing():
    for starts in ([1, 3, 3], [1, 5, 4]):
        response = client.post(
            "/api/v1/impose/chapters",
            json={
                "total_pages": 10,
                "max_sheets_per_signature": 2,
                "binding": "left",
                "chapter_starts": starts,
            },
        )
        assert response.status_code == 422


def test_chapters_empty_list():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [],
        },
    )
    assert response.status_code == 422


def test_chapters_start_beyond_total_pages():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [1, 11],
        },
    )
    assert response.status_code == 422


def test_chapters_single_chapter_too_long():
    # 单章 10 页 > 容量 8（2 张 × 4）-> 422
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [1],
        },
    )
    assert response.status_code == 422


def test_chapters_missing_field():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
        },
    )
    assert response.status_code == 422


def test_chapters_unknown_field_rejected():
    response = client.post(
        "/api/v1/impose/chapters",
        json={
            "total_pages": 10,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "chapter_starts": [1],
            "extra": 1,
        },
    )
    assert response.status_code == 422


def test_reprint_unchanged_reuses_all():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["p1", "p2", "p3", "p4"],
            "new_page_ids": ["p1", "p2", "p3", "p4"],
            "max_sheets_per_signature": 2,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["signature_count"] == 1
    assert data["reprint_sheet_count"] == 0
    sheet = data["signatures"][0]["sheets"][0]
    assert sheet["front"] == {"left": "p4", "right": "p1"}
    assert sheet["back"] == {"left": "p2", "right": "p3"}
    assert sheet["reused"] is True
    assert sheet["old_signature_index"] == 1
    assert sheet["old_sheet_index"] == 1


def test_reprint_changed_page_marks_sheet():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["p1", "p2", "p3", "p4"],
            "new_page_ids": ["p1", "p2X", "p3", "p4"],
            "max_sheets_per_signature": 2,
            "binding": "left",
            "changed_page_ids": ["p2X"],
        },
    )
    assert response.status_code == 200
    sheet = response.json()["signatures"][0]["sheets"][0]
    assert sheet["reused"] is False
    assert sheet["old_signature_index"] is None
    assert sheet["old_sheet_index"] is None
    # 新版四页位照常返回
    assert sheet["back"] == {"left": "p2X", "right": "p3"}
    assert response.json()["reprint_sheet_count"] == 1


def test_reprint_cross_signature():
    old_ids = [f"p{i:02d}" for i in range(1, 25)]
    new_ids = [f"p{i:02d}" for i in list(range(17, 25)) + list(range(9, 17)) + list(range(1, 9))]
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": old_ids,
            "new_page_ids": new_ids,
            "max_sheets_per_signature": 2,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reprint_sheet_count"] == 0
    first_sheet = data["signatures"][0]["sheets"][0]
    assert first_sheet["reused"] is True
    # 新帖 1 的 8 页块来自旧帖 3
    assert first_sheet["old_signature_index"] == 3
    assert first_sheet["old_sheet_index"] == 1


def test_reprint_right_binding():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a", "b", "c", "d"],
            "new_page_ids": ["a", "b", "c", "d"],
            "max_sheets_per_signature": 2,
            "binding": "right",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 200
    sheet = response.json()["signatures"][0]["sheets"][0]
    assert sheet["front"] == {"left": "a", "right": "d"}
    assert sheet["reused"] is True


def test_reprint_blank_positions_null():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a"],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 200
    sheet = response.json()["signatures"][0]["sheets"][0]
    assert sheet["front"] == {"left": None, "right": "a"}
    assert sheet["back"] == {"left": None, "right": None}
    assert sheet["reused"] is True


def test_reprint_empty_old_page_ids():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": [],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 2,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 422


def test_reprint_blank_page_id_string():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a", "  "],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 2,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 422


def test_reprint_duplicate_page_id_within_version():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a", "b"],
            "new_page_ids": ["a", "a"],
            "max_sheets_per_signature": 2,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 422


def test_reprint_changed_id_not_in_new_version():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a", "b"],
            "new_page_ids": ["a", "b"],
            "max_sheets_per_signature": 2,
            "binding": "left",
            "changed_page_ids": ["c"],
        },
    )
    assert response.status_code == 422


def test_reprint_changed_id_may_repeat():
    # changed_page_ids 不要求去重
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a", "b"],
            "new_page_ids": ["a", "b"],
            "max_sheets_per_signature": 2,
            "binding": "left",
            "changed_page_ids": ["a", "a"],
        },
    )
    assert response.status_code == 200
    assert response.json()["reprint_sheet_count"] == 1


def test_reprint_invalid_max_sheets():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a"],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 0,
            "binding": "left",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 422


def test_reprint_invalid_binding():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a"],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 2,
            "binding": "top",
            "changed_page_ids": [],
        },
    )
    assert response.status_code == 422


def test_reprint_unknown_field_rejected():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a"],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 2,
            "binding": "left",
            "changed_page_ids": [],
            "extra": 1,
        },
    )
    assert response.status_code == 422


def test_reprint_missing_field():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a"],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 2,
            "binding": "left",
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 印张抽检 /api/v1/impose/inspect
# ---------------------------------------------------------------------------

INSPECT_BASE = {
    "page_ids": [f"p{i}" for i in range(1, 13)],
    "max_sheets_per_signature": 2,
    "binding": "left",
}


def test_inspect_perfect_and_unseen_and_unmatched():
    # 12 页、每帖 2 张：帖1 p1..p8 两张，帖2 p9..p12（补 4 空白）一张
    # obs1 原样=帖1最外张；obs2 正反互换=帖1内张；obs3 全 "?" -> 无法配对；
    # 未见：帖2 的唯一印张
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            **INSPECT_BASE,
            "observed_sheets": [
                {"front": {"left": "p8", "right": "p1"},
                 "back": {"left": "p2", "right": "p7"}},
                {"front": {"left": "p4", "right": "p5"},
                 "back": {"left": "p6", "right": "p3"}},
                {"front": {"left": "?", "right": "?"},
                 "back": {"left": "?", "right": "?"}},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["matched_observation_count"] == 2
    assert data["unmatched_observation_count"] == 1
    assert data["unseen_sheet_count"] == 1

    o1, o2, o3 = data["observations"]
    assert o1["matched"] is True
    assert (o1["signature_index"], o1["sheet_index"]) == (1, 1)
    assert o1["transform"] == "none"
    assert o1["matched_slot_count"] == 4
    assert o1["errors"] == []

    assert o2["matched"] is True
    assert (o2["signature_index"], o2["sheet_index"]) == (1, 2)
    assert o2["transform"] == "flip_fb"
    assert o2["matched_slot_count"] == 4

    assert o3["matched"] is False
    assert o3["signature_index"] is None
    assert o3["sheet_index"] is None
    assert o3["transform"] is None
    assert o3["matched_slot_count"] == 0

    assert [o["observation_index"] for o in data["unmatched_observations"]] == [3]
    unseen = data["unseen_signatures"]
    assert len(unseen) == 1
    assert (unseen[0]["signature_index"], unseen[0]["sheet_index"]) == (2, 1)


def test_inspect_mirror_and_both_transforms():
    # 8 页单帖两张：最外张 (p8,p1)/(p2,p7)，内张 (p6,p3)/(p4,p5)
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            "page_ids": [f"p{i}" for i in range(1, 9)],
            "max_sheets_per_signature": 2,
            "binding": "left",
            "observed_sheets": [
                {"front": {"left": "p1", "right": "p8"},
                 "back": {"left": "p7", "right": "p2"}},  # 最外张的 mirror_lr
                {"front": {"left": "p5", "right": "p4"},
                 "back": {"left": "p3", "right": "p6"}},  # 内张的 mirror_lr_flip_fb
            ],
        },
    )
    assert response.status_code == 200
    observations = response.json()["observations"]
    assert observations[0]["transform"] == "mirror_lr"
    assert observations[0]["matched_slot_count"] == 4
    assert (observations[0]["signature_index"], observations[0]["sheet_index"]) == (1, 1)
    assert observations[1]["transform"] == "mirror_lr_flip_fb"
    assert observations[1]["matched_slot_count"] == 4
    assert (observations[1]["signature_index"], observations[1]["sheet_index"]) == (1, 2)


def test_inspect_errors_listed_and_question_mark_ignored():
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            "page_ids": ["a", "b", "c", "d"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "observed_sheets": [
                {"front": {"left": "d", "right": "?"},
                 "back": {"left": "X", "right": "c"}}
            ],
        },
    )
    assert response.status_code == 200
    obs = response.json()["observations"][0]
    assert obs["matched"] is True
    assert obs["matched_slot_count"] == 2  # d 与 c 吻合；"?" 不计
    assert obs["errors"] == [
        {"position": "back_left", "observed": "X", "expected": "b"}
    ]


def test_inspect_null_blank_mismatch_error():
    # 单页补 3 空白：预期 (null,a)/(null,null)
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            "page_ids": ["a"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "observed_sheets": [
                {"front": {"left": "a", "right": "a"},
                 "back": {"left": None, "right": None}}
            ],
        },
    )
    assert response.status_code == 200
    obs = response.json()["observations"][0]
    assert obs["matched_slot_count"] == 3
    assert obs["errors"] == [
        {"position": "front_left", "observed": "a", "expected": None}
    ]


def test_inspect_foreign_only_observation_unpaired():
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            "page_ids": ["a", "b", "c", "d"],
            "max_sheets_per_signature": 1,
            "binding": "left",
            "observed_sheets": [
                {"front": {"left": "x", "right": "y"},
                 "back": {"left": None, "right": "?"}}
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["matched_observation_count"] == 0
    assert data["unmatched_observation_count"] == 1
    assert data["observations"][0]["matched"] is False
    assert data["unseen_sheet_count"] == 1


def test_inspect_right_binding():
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            "page_ids": ["a", "b", "c", "d"],
            "max_sheets_per_signature": 1,
            "binding": "right",
            "observed_sheets": [
                {"front": {"left": "a", "right": "d"},
                 "back": {"left": "c", "right": "b"}}
            ],
        },
    )
    assert response.status_code == 200
    obs = response.json()["observations"][0]
    assert obs["transform"] == "none"
    assert obs["matched_slot_count"] == 4


def test_inspect_pair_count_takes_priority_over_matches():
    # 两张观测都只能配帖1最外张（p8 只出现在该张）：
    # 高吻合的 obs1 先取该张，obs2 落单；反之总配对数相同（1 对），
    # 但 obs1 配对吻合更多，字典序也优先 obs1。
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            **INSPECT_BASE,
            "observed_sheets": [
                {"front": {"left": "p8", "right": "p1"},
                 "back": {"left": "p2", "right": "p7"}},
                {"front": {"left": "p8", "right": None},
                 "back": {"left": None, "right": None}},
            ],
        },
    )
    data = response.json()
    assert data["matched_observation_count"] == 1
    assert data["observations"][0]["matched"] is True
    assert data["observations"][0]["matched_slot_count"] == 4
    assert data["observations"][1]["matched"] is False
    # 未见另外两张
    assert data["unseen_sheet_count"] == 2


def test_inspect_invalid_page_id_question_mark():
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            **INSPECT_BASE,
            "page_ids": ["p1", "?", "p3"],
            "observed_sheets": [
                {"front": {"left": "p1", "right": "p2"},
                 "back": {"left": None, "right": None}}
            ],
        },
    )
    assert response.status_code == 422


def test_inspect_duplicate_page_ids():
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            **INSPECT_BASE,
            "page_ids": ["p1", "p1", "p2"],
            "observed_sheets": [
                {"front": {"left": "p1", "right": "p2"},
                 "back": {"left": None, "right": None}}
            ],
        },
    )
    assert response.status_code == 422


def test_inspect_empty_page_ids():
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            **INSPECT_BASE,
            "page_ids": [],
            "observed_sheets": [
                {"front": {"left": "p1", "right": "p2"},
                 "back": {"left": None, "right": None}}
            ],
        },
    )
    assert response.status_code == 422


def test_inspect_empty_observed_sheets():
    response = client.post(
        "/api/v1/impose/inspect",
        json={**INSPECT_BASE, "observed_sheets": []},
    )
    assert response.status_code == 422


def test_inspect_blank_slot_string_rejected():
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            **INSPECT_BASE,
            "observed_sheets": [
                {"front": {"left": "  ", "right": "p1"},
                 "back": {"left": None, "right": None}}
            ],
        },
    )
    assert response.status_code == 422


def test_inspect_invalid_max_sheets():
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            **INSPECT_BASE,
            "max_sheets_per_signature": 0,
            "observed_sheets": [
                {"front": {"left": "p1", "right": "p2"},
                 "back": {"left": None, "right": None}}
            ],
        },
    )
    assert response.status_code == 422


def test_inspect_invalid_binding():
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            **INSPECT_BASE,
            "binding": "top",
            "observed_sheets": [
                {"front": {"left": "p1", "right": "p2"},
                 "back": {"left": None, "right": None}}
            ],
        },
    )
    assert response.status_code == 422


def test_inspect_unknown_field_rejected():
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            **INSPECT_BASE,
            "observed_sheets": [
                {"front": {"left": "p8", "right": "p1"},
                 "back": {"left": "p2", "right": "p7"},
                 "extra": 1}
            ],
        },
    )
    assert response.status_code == 422


def test_inspect_missing_field():
    response = client.post(
        "/api/v1/impose/inspect",
        json={
            "page_ids": INSPECT_BASE["page_ids"],
            "max_sheets_per_signature": 2,
            "binding": "left",
        },
    )
    assert response.status_code == 422


def test_reprint_missing_field_legacy():
    response = client.post(
        "/api/v1/impose/reprint",
        json={
            "old_page_ids": ["a"],
            "new_page_ids": ["a"],
            "max_sheets_per_signature": 2,
            "binding": "left",
        },
    )
    assert response.status_code == 422
