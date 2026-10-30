"""All editing decisions refer to source seconds; renderers consume the same map."""
import math
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class Timed(BaseModel):
    model_config = ConfigDict(extra='ignore', allow_inf_nan=False)
    id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('Điểm kết thúc phải sau điểm bắt đầu')
        return self

class Cut(Timed):
    reason: str = ''
    enabled: bool = True
    locked: bool = False

class Caption(Timed):
    vi: str = Field(max_length=1000)
    en: str = Field(default='', max_length=1500)
    original_vi: str = ''
    locked: bool = False

class Visual(Timed):
    kind: Literal['photo', 'vocab', 'title'] = 'vocab'
    layout: Literal['auto', 'card', 'full'] = 'auto'
    query: str = Field(default='', max_length=200)
    text: str = Field(default='', max_length=180)
    translation: str = Field(default='', max_length=240)
    asset_id: str | None = None
    enabled: bool = True
    locked: bool = False
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    scale: float = Field(default=1, ge=0.5, le=1.3)

class LessonChunk(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    vi: str = Field(min_length=1, max_length=100)
    en: str = Field(min_length=1, max_length=140)

class Lesson(Timed):
    model_config = ConfigDict(extra='ignore',allow_inf_nan=False,str_strip_whitespace=True)
    vi: str = Field(min_length=1, max_length=800)
    en: str = Field(min_length=1, max_length=1000)
    chunks: list[LessonChunk] = Field(default_factory=list, max_length=3)
    photo_query: str = Field(default='', max_length=200)
    asset_id: str | None = None
    locked: bool = False

class Plan(BaseModel):
    model_config = ConfigDict(extra='ignore')
    summary: str = ''
    glossary: list[dict[str, str]] = Field(default_factory=list, max_length=300)
    cuts: list[Cut] = Field(default_factory=list, max_length=5000)
    captions: list[Caption] = Field(default_factory=list, max_length=10000)
    visuals: list[Visual] = Field(default_factory=list, max_length=1500)
    schema_version: Literal[1, 2] = 1
    lessons: list[Lesson] = Field(default_factory=list, max_length=1500)

def validate_plan(raw, duration):
    plan = Plan.model_validate(raw).model_dump()
    # Inward frame alignment prevents cumulative A/V drift across many small cuts.
    for cut in plan['cuts']:
        cut['start'] = math.ceil(cut['start']*30-1e-6)/30
        cut['end'] = math.floor(cut['end']*30+1e-6)/30
        if cut['end'] <= cut['start']:
            raise ValueError('Đoạn cắt cần dài ít nhất một khung hình (1/30 giây).')
    for name in ['cuts', 'captions', 'visuals', 'lessons']:
        ids = set()
        for item in plan[name]:
            if item['end'] > duration + 0.05:
                raise ValueError('Mốc thời gian vượt độ dài video')
            if item['id'] in ids:
                raise ValueError('Trùng mã đoạn')
            ids.add(item['id'])
        plan[name].sort(key=lambda item: item['start'])
    if plan['schema_version']==2:
        lessons=plan['lessons']
        if not lessons or abs(lessons[0]['start'])>.005 or abs(lessons[-1]['end']-duration)>.005:
            raise ValueError('Các mục bài học phải phủ từ đầu tới cuối video. Hãy chỉnh ranh giới hoặc gộp mục.')
        for previous,current in zip(lessons,lessons[1:]):
            if abs(previous['end']-current['start'])>.005:
                raise ValueError('Các mục bài học cần nối liền, không chồng nhau và không có khoảng trống.')
    if sum(s['end'] - s['start'] for s in keep_spans(duration, plan['cuts'])) < min(0.5, duration):
        raise ValueError('Cần giữ lại ít nhất một đoạn video')
    return plan

def keep_spans(duration, cuts):
    intervals = sorted((max(0, c['start']), min(duration, c['end'])) for c in cuts if c.get('enabled', True))
    merged = []
    for start, end in intervals:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    result, cursor, out = [], 0.0, 0.0
    for start, end in merged + [[duration, duration]]:
        if start > cursor + 0.001:
            result.append({'start': cursor, 'end': start, 'output_start': out, 'output_end': out + start - cursor})
            out += start - cursor
        cursor = max(cursor, end)
    return result

def map_interval(start, end, spans):
    result = []
    for span in spans:
        a, b = max(start, span['start']), min(end, span['end'])
        if b > a + 0.005:
            result.append((span['output_start'] + a - span['start'], span['output_start'] + b - span['start']))
    return result

def source_to_output(value, spans):
    for s in spans:
        if s['start'] <= value <= s['end']:
            return s['output_start'] + value - s['start']
    for s in spans:
        if s['start'] > value:
            return s['output_start']
    return spans[-1]['output_end'] if spans else 0

def output_to_source(value, spans):
    for s in spans:
        if s['output_start'] <= value < s['output_end']:
            return s['start'] + value - s['output_start']
    return spans[-1]['end'] if spans else 0

def cue_words(words):
    cues, group = [], []
    def flush():
        if group:
            text = ' '.join(w['word'].strip() for w in group).strip()
            if text:
                cues.append({'id': f'c{len(cues):05}', 'start': group[0]['start'], 'end': max(group[-1]['end'], group[0]['start'] + 0.12), 'vi': text, 'original_vi': text, 'en': '', 'locked': False})
            group.clear()
    for word in words:
        if group and (word['start'] - group[-1]['end'] > 0.8 or word['end'] - group[0]['start'] > 4.5 or len(' '.join(w['word'] for w in group)) + len(word['word']) > 72):
            flush()
        group.append(word)
        if word['word'].endswith(('.', '?', '!', ';')) or len(group) >= 10:
            flush()
    flush()
    return cues
