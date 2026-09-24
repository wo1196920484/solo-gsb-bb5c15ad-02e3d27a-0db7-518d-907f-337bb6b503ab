"""离线小册子拼版 API。"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict, model_validator

from .imposition import impose, impose_chapters, plan_reprint

app = FastAPI(
    title="离线小册子拼版 API",
    description=(
        "按帖拆分并完成小册子拼版（signature imposition）。"
        "左装订最外张正面为 末页/首页，背面为 次页/倒数第二页；"
        "右装订左右页位镜像交换。"
        "支持按章节首页分帖：章节不可跨帖，相邻章节可合帖。"
        "支持旧版/新版重印复用：四页位完全相同且均未改动的旧印张可整张复用。"
    ),
    version="1.2.0",
)


class ImpositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_pages: int = Field(
        ..., ge=1, description="总页数，正整数（1, 2, 3, ...）"
    )
    max_sheets_per_signature: int = Field(
        ..., ge=1, description="每帖最多纸张数，正整数；每帖最多容纳其 4 倍页数"
    )
    binding: Literal["left", "right"] = Field(
        ..., description="装订方向：left=左装订，right=右装订"
    )


class PagePair(BaseModel):
    left: Optional[int] = Field(..., description="左页页码，空白页为 null")
    right: Optional[int] = Field(..., description="右页页码，空白页为 null")


class Sheet(BaseModel):
    sheet_index: int = Field(..., description="帖内纸张序号，从 1 开始（1 为最外张）")
    front: PagePair = Field(..., description="正面左右页码")
    back: PagePair = Field(..., description="背面左右页码")


class Signature(BaseModel):
    signature_index: int = Field(..., description="帖号，从 1 开始")
    sheet_count: int = Field(..., description="本帖纸张数")
    page_count_padded: int = Field(..., description="本帖补齐空白后的总页数（4 的倍数）")
    sheets: list[Sheet] = Field(..., description="帖内纸张，按从外到内排列")


class ImpositionResponse(BaseModel):
    total_pages: int
    max_sheets_per_signature: int
    binding: Literal["left", "right"]
    signature_count: int
    signatures: list[Signature]


class ChapterImpositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_pages: int = Field(
        ..., ge=1, description="总页数，正整数（1, 2, 3, ...）"
    )
    max_sheets_per_signature: int = Field(
        ..., ge=1, description="每帖最多纸张数，正整数；每帖最多容纳其 4 倍页数"
    )
    binding: Literal["left", "right"] = Field(
        ..., description="装订方向：left=左装订，right=右装订"
    )
    chapter_starts: list[int] = Field(
        ..., min_length=1, description="各章节首页页码，严格递增且首项为 1"
    )

    @model_validator(mode="after")
    def validate_chapter_starts(self) -> "ChapterImpositionRequest":
        starts = self.chapter_starts
        if starts[0] != 1:
            raise ValueError("chapter_starts 首项必须为 1")
        if any(curr <= prev for prev, curr in zip(starts, starts[1:])):
            raise ValueError("chapter_starts 必须严格递增")
        if starts[-1] > self.total_pages:
            raise ValueError("chapter_starts 不能超过 total_pages")
        capacity = self.max_sheets_per_signature * 4
        ends = starts[1:] + [self.total_pages + 1]
        for start, end in zip(starts, ends):
            if end - start > capacity:
                raise ValueError(
                    f"起始页为 {start} 的章节共 {end - start} 页，"
                    f"超过单帖容量 {capacity} 页（4 × max_sheets_per_signature）"
                )
        return self


class ChapterSignature(BaseModel):
    signature_index: int = Field(..., description="帖号，从 1 开始")
    sheet_count: int = Field(..., description="本帖纸张数")
    page_count_padded: int = Field(..., description="本帖补齐空白后的总页数（4 的倍数）")
    page_start: int = Field(..., description="本帖原页起始页码")
    page_end: int = Field(..., description="本帖原页结束页码")
    blank_count: int = Field(..., description="本帖尾部补齐的空白页数")
    sheets: list[Sheet] = Field(..., description="帖内纸张，按从外到内排列")


class ChapterImpositionResponse(BaseModel):
    total_pages: int
    max_sheets_per_signature: int
    binding: Literal["left", "right"]
    chapter_starts: list[int]
    signature_count: int
    signatures: list[ChapterSignature]


class ReprintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_page_ids: list[str] = Field(
        ..., min_length=1, description="旧版页面 ID，按阅读顺序排列，非空字符串且不重复"
    )
    new_page_ids: list[str] = Field(
        ..., min_length=1, description="新版页面 ID，按阅读顺序排列，非空字符串且不重复"
    )
    max_sheets_per_signature: int = Field(
        ..., ge=1, description="两版共用的每帖最多纸张数，正整数；每帖最多容纳其 4 倍页数"
    )
    binding: Literal["left", "right"] = Field(
        ..., description="两版共用的装订方向：left=左装订，right=右装订"
    )
    changed_page_ids: list[str] = Field(
        ..., description="新版内容改动的页面 ID，可重复、可空；每项必须属于新版"
    )

    @model_validator(mode="after")
    def validate_page_ids(self) -> "ReprintRequest":
        for field_name in ("old_page_ids", "new_page_ids"):
            page_ids = getattr(self, field_name)
            if any(not page_id or not page_id.strip() for page_id in page_ids):
                raise ValueError(f"{field_name} 中不能包含空字符串页面 ID")
            if len(page_ids) != len(set(page_ids)):
                raise ValueError(f"{field_name} 中的页面 ID 不能重复")
        if any(not page_id or not page_id.strip() for page_id in self.changed_page_ids):
            raise ValueError("changed_page_ids 中不能包含空字符串页面 ID")
        new_set = set(self.new_page_ids)
        unknown = [page_id for page_id in self.changed_page_ids if page_id not in new_set]
        if unknown:
            raise ValueError(
                f"changed_page_ids 中的页面 ID 必须属于新版：{unknown}"
            )
        return self


class IdPagePair(BaseModel):
    left: Optional[str] = Field(..., description="左页页面 ID，空白页为 null")
    right: Optional[str] = Field(..., description="右页页面 ID，空白页为 null")


class ReprintSheet(BaseModel):
    sheet_index: int = Field(..., description="新版帖内纸张序号，从 1 开始（1 为最外张）")
    front: IdPagePair = Field(..., description="正面左右页面 ID")
    back: IdPagePair = Field(..., description="背面左右页面 ID")
    reused: bool = Field(
        ..., description="是否复用旧版印张；false 表示整张重印"
    )
    old_signature_index: Optional[int] = Field(
        ..., description="复用的旧帖号（从 1 开始）；整张重印时为 null"
    )
    old_sheet_index: Optional[int] = Field(
        ..., description="复用的旧帖内张号（从 1 开始，1 为最外张）；整张重印时为 null"
    )


class ReprintSignature(BaseModel):
    signature_index: int = Field(..., description="新版帖号，从 1 开始")
    sheet_count: int = Field(..., description="本帖纸张数")
    page_count_padded: int = Field(..., description="本帖补齐空白后的总页数（4 的倍数）")
    sheets: list[ReprintSheet] = Field(..., description="帖内纸张，按从外到内排列")


class ReprintResponse(BaseModel):
    old_page_ids: list[str]
    new_page_ids: list[str]
    changed_page_ids: list[str]
    max_sheets_per_signature: int
    binding: Literal["left", "right"]
    signature_count: int = Field(..., description="新版帖数")
    reprint_sheet_count: int = Field(..., description="整张重印的总张数")
    signatures: list[ReprintSignature] = Field(..., description="新版逐帖的复用/重印计划")


@app.get("/health", tags=["健康检查"])
def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/api/v1/impose",
    response_model=ImpositionResponse,
    tags=["拼版"],
    summary="小册子拼版",
)
def create_imposition(request: ImpositionRequest) -> ImpositionResponse:
    signatures = impose(
        total_pages=request.total_pages,
        max_sheets=request.max_sheets_per_signature,
        binding=request.binding,
    )
    return ImpositionResponse(
        total_pages=request.total_pages,
        max_sheets_per_signature=request.max_sheets_per_signature,
        binding=request.binding,
        signature_count=len(signatures),
        signatures=signatures,
    )


@app.post(
    "/api/v1/impose/chapters",
    response_model=ChapterImpositionResponse,
    tags=["拼版"],
    summary="按章节分帖的小册子拼版",
)
def create_chapter_imposition(
    request: ChapterImpositionRequest,
) -> ChapterImpositionResponse:
    signatures = impose_chapters(
        total_pages=request.total_pages,
        max_sheets=request.max_sheets_per_signature,
        binding=request.binding,
        chapter_starts=request.chapter_starts,
    )
    return ChapterImpositionResponse(
        total_pages=request.total_pages,
        max_sheets_per_signature=request.max_sheets_per_signature,
        binding=request.binding,
        chapter_starts=request.chapter_starts,
        signature_count=len(signatures),
        signatures=signatures,
    )


@app.post(
    "/api/v1/impose/reprint",
    response_model=ReprintResponse,
    tags=["重印"],
    summary="旧版/新版重印复用计算",
)
def create_reprint_plan(request: ReprintRequest) -> ReprintResponse:
    plan = plan_reprint(
        old_page_ids=request.old_page_ids,
        new_page_ids=request.new_page_ids,
        max_sheets=request.max_sheets_per_signature,
        binding=request.binding,
        changed_page_ids=request.changed_page_ids,
    )
    return ReprintResponse(
        old_page_ids=request.old_page_ids,
        new_page_ids=request.new_page_ids,
        changed_page_ids=request.changed_page_ids,
        max_sheets_per_signature=request.max_sheets_per_signature,
        binding=request.binding,
        signature_count=plan["signature_count"],
        reprint_sheet_count=plan["reprint_sheet_count"],
        signatures=plan["signatures"],
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request, exc: Exception) -> JSONResponse:
    # 兜底：未预期错误统一返回 500，避免向前端泄漏堆栈
    return JSONResponse(status_code=500, content={"detail": "内部错误"})
