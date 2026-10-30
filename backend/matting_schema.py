"""Portable user edits only; model/cache/runtime paths never come from archives."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class BrushPoint(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class MaskStroke(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    mode: Literal['keep', 'remove']
    radius: float = Field(default=.012, ge=.002, le=.1)
    points: list[BrushPoint] = Field(min_length=1, max_length=300)

    @model_validator(mode='after')
    def interval(self):
        if self.end <= self.start:
            raise ValueError('Mốc kết thúc nét sửa phải sau mốc bắt đầu.')
        return self


class BackgroundRemoval(BaseModel):
    model_config = ConfigDict(extra='ignore', allow_inf_nan=False)
    enabled: bool = False  # Absent in old projects means OFF.
    device: Literal['cuda', 'cpu'] = 'cuda'  # Never silently fall back to CPU.
    soften: float = Field(default=.6, ge=0, le=4)
    contract: float = Field(default=0, ge=-4, le=4)
    strokes: list[MaskStroke] = Field(default_factory=list, max_length=100)


def validate_duration(options, duration):
    cfg = BackgroundRemoval.model_validate(options.get('background_removal', {}))
    if len({s.id for s in cfg.strokes}) != len(cfg.strokes):
        raise ValueError('Mã nét sửa bị trùng.')
    if any(s.end > duration + .034 or s.start >= duration for s in cfg.strokes):
        raise ValueError('Nét sửa nằm ngoài thời lượng video nguồn.')
    return cfg
