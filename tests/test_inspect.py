"""印张抽检算法与 API 测试。"""
from fastapi.testclient import TestClient

from app.imposition import inspect_imposition
from app.main import app

client = TestClient(app)


def _observed(front_left, front_right, back_left, back_right):
    return {
        "front": {"left": front_left, "right": front_right},
        "back": {"left": back_left, "right": back_right},
    }


# p1..p8、每帖 2 张、左装订 -> 单帖两张：
#   张 1: front (p8, p1) / back (p2, p7)
#   张 2: front (p6, p3) / back (p4, p5)
PAGE_IDS_8 = [f"p{i}" for i in range(1, 9)]


def _inspect(observed, page_ids=PAGE_IDS_8, max_sheets=2, binding="left"):
    return inspect_imposition(page_ids, max_sheets, binding, observed)


def test_identity_exact_match():
    result = _inspect([_observed("p8", "p1", "p2", "p7")])
    obs = result["observations"][0]
    assert obs["matched"] is True
    assert (obs["signature_index"], obs["sheet_index"]) == (1, 1)
    assert obs["transform"] == "identity"
    assert obs["matched_positions"] == 4
    assert obs["errors"] == []
    assert result["matched_count"] == 1
    # 张 2 未被观测 -> 未见印张
    assert result["missing_sheets"] == [
        {
            "signature_index": 1,
            "sheet_index": 2,
            "front": {"left": "p6", "right": "p3"},
            "back": {"left": "p4", "right": "p5"},
        }
    ]
    assert result["unmatched_observations"] == []


def test_mirror_transform():
    # 左右镜像：观测左右页位与预期对调
    result = _inspect([_observed("p1", "p8", "p7", "p2")])
    obs = result["observations"][0]
    assert obs["transform"] == "mirror"
    assert obs["matched_positions"] == 4
    assert obs["errors"] == []


def test_flip_transform():
    # 正反互换：观测正面实为预期背面
    result = _inspect([_observed("p2", "p7", "p8", "p1")])
    obs = result["observations"][0]
    assert obs["transform"] == "flip"
    assert obs["matched_positions"] == 4


def test_mirror_flip_transform():
    # 左右镜像 + 正反互换的组合
    result = _inspect([_observed("p7", "p2", "p1", "p8")])
    obs = result["observations"][0]
    assert obs["transform"] == "mirror_flip"
    assert obs["matched_positions"] == 4


def test_unread_positions_neither_match_nor_error():
    # "?" 不计入吻合数也不计错
    result = _inspect([_observed("p8", "?", "?", "p7")])
    obs = result["observations"][0]
    assert obs["transform"] == "identity"
    assert obs["matched_positions"] == 2
    assert obs["errors"] == []


def test_error_details_for_known_positions():
    # 读到的 ID 与预期不符 -> 已知页位错误
    result = _inspect([_observed("p8", "p99", "p2", "p7")])
    obs = result["observations"][0]
    assert obs["matched_positions"] == 3
    assert obs["errors"] == [
        {"position": "front.right", "observed": "p99", "expected": "p1"}
    ]


def test_error_details_blank_vs_page_both_directions():
    # 观测空白但预期有页
    result = _inspect([_observed(None, "p1", "p2", "p7")])
    obs = result["observations"][0]
    assert obs["matched_positions"] == 3
    assert obs["errors"] == [
        {"position": "front.left", "observed": None, "expected": "p8"}
    ]
    # 观测有页但预期空白（单页小册子：front (None, a) / back (None, None)）
    result = _inspect([_observed("x", "a", None, None)], page_ids=["a"], max_sheets=1)
    obs = result["observations"][0]
    assert obs["matched_positions"] == 3
    assert obs["errors"] == [
        {"position": "front.left", "observed": "x", "expected": None}
    ]


def test_observation_without_common_id_unmatched():
    # 全部 ID 都不在任何预期印张上 -> 不允许配对
    result = _inspect([_observed("x1", "x2", None, None)])
    obs = result["observations"][0]
    assert obs["matched"] is False
    assert obs["signature_index"] is None
    assert obs["sheet_index"] is None
    assert obs["transform"] is None
    assert obs["matched_positions"] is None
    assert obs["errors"] == []
    assert result["matched_count"] == 0
    assert result["unmatched_observations"] == [
        {
            "observation_index": 1,
            "front": {"left": "x1", "right": "x2"},
            "back": {"left": None, "right": None},
        }
    ]
    assert len(result["missing_sheets"]) == 2


def test_all_unread_observation_unmatched():
    # 没有任何非空已读 ID（全 "?" / 全空白）-> 不允许配对
    for observed in (
        _observed("?", "?", "?", "?"),
        _observed(None, None, None, None),
        _observed("?", None, "?", None),
    ):
        result = _inspect([observed])
        assert result["observations"][0]["matched"] is False
        assert result["matched_count"] == 0


def test_each_expected_sheet_used_at_most_once():
    # 两张相同观测、只有一张预期 -> 先观测序号的配对，后者无法配对
    result = _inspect([_observed("p8", "p1", "p2", "p7"), _observed("p8", "p1", "p2", "p7")])
    first, second = result["observations"]
    assert first["matched"] is True
    assert (first["signature_index"], first["sheet_index"]) == (1, 1)
    assert second["matched"] is False
    assert result["matched_count"] == 1
    assert [o["observation_index"] for o in result["unmatched_observations"]] == [2]


def test_pair_count_maximized_before_matches():
    # obs1 与两张预期都有公共 ID（各 2 吻合），obs2 只能配张 1（4 吻合）：
    # 配对数最大 = 2 -> obs1 必须让出张 1 去配张 2，即使吻合数因此降低
    obs1 = _observed("p8", "p1", "p4", "p5")
    obs2 = _observed("p8", "p1", "p2", "p7")
    result = _inspect([obs1, obs2])
    first, second = result["observations"]
    assert result["matched_count"] == 2
    assert (first["signature_index"], first["sheet_index"]) == (1, 2)
    assert first["matched_positions"] == 2
    assert first["errors"] == [
        {"position": "front.left", "observed": "p8", "expected": "p6"},
        {"position": "front.right", "observed": "p1", "expected": "p3"},
    ]
    assert (second["signature_index"], second["sheet_index"]) == (1, 1)
    assert second["matched_positions"] == 4


def test_tie_break_by_observation_order():
    # obs2、obs3 对张 1 同为 3 吻合：配对数与吻合总数都打平时，
    # 观测序号靠前者获得配对
    obs1 = _observed("p3", "p6", "p5", "p4")  # 张 2 的镜像，4 吻合
    obs2 = _observed("p8", "?", "p2", "p7")  # 张 1，3 吻合
    obs3 = _observed("p9", "p1", "p2", "p7")  # 张 1，3 吻合（p9 为错页）
    result = _inspect([obs1, obs2, obs3])
    first, second, third = result["observations"]
    assert result["matched_count"] == 2
    assert (first["signature_index"], first["sheet_index"]) == (1, 2)
    assert first["transform"] == "mirror"
    assert second["matched"] is True
    assert (second["signature_index"], second["sheet_index"]) == (1, 1)
    assert third["matched"] is False
    assert [o["observation_index"] for o in result["unmatched_observations"]] == [3]


def test_tie_break_transform_order():
    # identity 与 mirror_flip 同为 1 吻合 -> 按变换顺序取 identity
    result = _inspect([_observed("p8", "?", "?", "p8")])
    obs = result["observations"][0]
    assert obs["transform"] == "identity"
    assert obs["matched_positions"] == 1
    assert obs["errors"] == [
        {"position": "back.right", "observed": "p8", "expected": "p7"}
    ]


def test_multi_signature_expected():
    # 16 页、每帖 1 张 -> 4 帖；第 3 帖为 p9..p12
    result = _inspect(
        [_observed("p12", "p9", "p10", "p11")],
        page_ids=[f"p{i}" for i in range(1, 17)],
        max_sheets=1,
    )
    obs = result["observations"][0]
    assert (obs["signature_index"], obs["sheet_index"]) == (3, 1)
    assert result["signature_count"] == 4
    assert result["sheet_count"] == 4
    assert len(result["missing_sheets"]) == 3


def test_right_binding():
    # 右装订左右页位镜像：front (a, d) / back (c, b)
    result = _inspect(
        [_observed("a", "d", "c", "b")],
        page_ids=["a", "b", "c", "d"],
        max_sheets=1,
        binding="right",
    )
    obs = result["observations"][0]
    assert obs["matched"] is True
    assert obs["transform"] == "identity"
    assert obs["matched_positions"] == 4


def test_empty_observations():
    result = _inspect([])
    assert result["matched_count"] == 0
    assert result["observations"] == []
    assert result["unmatched_observations"] == []
    assert len(result["missing_sheets"]) == 2


# ---------------------------------------------------------------------------
# API 层
# ---------------------------------------------------------------------------

INSPECT_URL = "/api/v1/impose/inspect"


def _post(payload):
    return client.post(INSPECT_URL, json=payload)


def _base_payload(**overrides):
    payload = {
        "page_ids": [f"p{i}" for i in range(1, 13)],
        "max_sheets_per_signature": 3,
        "binding": "left",
        "observed_sheets": [
            _observed("p3", "p10", "p9", "p4"),   # 张 2 的左右镜像
            _observed("p12", "?", "p99", "p11"),  # 张 1，含未读出与错页
            _observed("x1", "x2", None, None),    # 无法配对
        ],
    }
    payload.update(overrides)
    return payload


def test_api_inspect_full_flow():
    response = _post(_base_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["signature_count"] == 1
    assert data["sheet_count"] == 3
    assert data["observation_count"] == 3
    assert data["matched_count"] == 2

    first, second, third = data["observations"]
    assert first["observation_index"] == 1
    assert first["matched"] is True
    assert (first["signature_index"], first["sheet_index"]) == (1, 2)
    assert first["transform"] == "mirror"
    assert first["matched_positions"] == 4
    assert first["errors"] == []

    assert second["observation_index"] == 2
    assert (second["signature_index"], second["sheet_index"]) == (1, 1)
    assert second["transform"] == "identity"
    # FL/BR 吻合，FR 未读出（"?" 不计），BL 错页 -> 2 吻合 1 错误
    assert second["matched_positions"] == 2
    assert second["errors"] == [
        {"position": "back.left", "observed": "p99", "expected": "p2"}
    ]

    assert third["observation_index"] == 3
    assert third["matched"] is False
    assert third["signature_index"] is None
    assert third["transform"] is None

    # 张 3 未被任何观测配对 -> 未见的预期印张
    assert data["missing_sheets"] == [
        {
            "signature_index": 1,
            "sheet_index": 3,
            "front": {"left": "p8", "right": "p5"},
            "back": {"left": "p6", "right": "p7"},
        }
    ]
    assert data["unmatched_observations"] == [
        {
            "observation_index": 3,
            "front": {"left": "x1", "right": "x2"},
            "back": {"left": None, "right": None},
        }
    ]


def test_api_empty_observed_sheets_ok():
    response = _post(_base_payload(observed_sheets=[]))
    assert response.status_code == 200
    data = response.json()
    assert data["matched_count"] == 0
    assert len(data["missing_sheets"]) == 3


def test_api_question_mark_page_id_rejected():
    response = _post(_base_payload(page_ids=["p1", "?"]))
    assert response.status_code == 422


def test_api_duplicate_page_ids_rejected():
    response = _post(_base_payload(page_ids=["p1", "p1"]))
    assert response.status_code == 422


def test_api_empty_page_ids_rejected():
    response = _post(_base_payload(page_ids=[]))
    assert response.status_code == 422


def test_api_blank_page_id_rejected():
    response = _post(_base_payload(page_ids=["p1", "  "]))
    assert response.status_code == 422


def test_api_blank_observed_position_rejected():
    response = _post(_base_payload(
        observed_sheets=[_observed("p1", "", None, None)]
    ))
    assert response.status_code == 422


def test_api_invalid_max_sheets():
    response = _post(_base_payload(max_sheets_per_signature=0))
    assert response.status_code == 422


def test_api_invalid_binding():
    response = _post(_base_payload(binding="top"))
    assert response.status_code == 422


def test_api_missing_observed_sheets():
    payload = _base_payload()
    del payload["observed_sheets"]
    response = _post(payload)
    assert response.status_code == 422


def test_api_unknown_field_rejected():
    response = _post(_base_payload(extra=1))
    assert response.status_code == 422


def test_api_observed_sheet_unknown_field_rejected():
    sheet = _observed("p1", None, None, None)
    sheet["front"]["middle"] = "p2"
    response = _post(_base_payload(observed_sheets=[sheet]))
    assert response.status_code == 422
