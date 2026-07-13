#!/usr/bin/env python3
"""공용 헬퍼: config.json의 base_dir을 읽어 프로젝트 루트 경로를 반환한다.

모든 파이프라인 스크립트(analyze_sections.py, extract_input.py 등)는
이 함수로 BASE를 계산해, 폴더나 입력 보고서가 바뀌어도 config.json 값만
수정하면 재사용할 수 있도록 한다.
"""
import json
import os
import sys

# Windows 기본 콘솔(cp949)에서 이모지·한글 출력이 UnicodeEncodeError로 죽는 문제 방지.
# 모든 파이프라인 스크립트가 _common을 import하므로 여기서 한 번만 stdout/stderr을 UTF-8로 맞춘다
# (PYTHONIOENCODING=utf-8을 매번 지정하지 않아도 되게 함). reconfigure는 Python 3.7+ 제공.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_PATH = os.path.join(_SKILL_DIR, 'config.json')


def get_base() -> str:
    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(
            f'config.json이 없습니다: {_CONFIG_PATH}\n'
            f'→ config.example.json을 config.json으로 복사한 뒤 base_dir 등 값을 채우세요.'
        )
    with open(_CONFIG_PATH, encoding='utf-8') as f:
        cfg = json.load(f)
    base = cfg.get('base_dir', '').strip()
    if not base:
        raise RuntimeError(f'config.json(base_dir)이 비어 있습니다: {_CONFIG_PATH}')
    return os.path.normpath(base)


def seg_title(axis: dict, fallback: str = '') -> str:
    """세그먼트 축(segmentation.axes[] 항목)의 절 제목·차트 제목을 만든다.

    차트 y축 라벨(generate_charts)·본문 절 제목(generate_docx/hwpx)이 같은 규칙을 쓰도록
    한곳에 모아둔다. 세그먼트 값이 시장규모가 아닌 보고서(자본 약정액·투자액 등)는
    axis['value_label']로 지표명을 덮어쓴다.

    축 이름이 이미 '…규모'로 끝나면 지표명을 덧붙이지 않는다 —
    "자본 약정 규모 시장규모"처럼 같은 말이 두 번 나오는 제목이 되기 때문.
    """
    label = axis.get('label') or fallback
    if label.endswith('규모'):
        return label
    return f"{label} {value_label(axis)}"


def value_label(axis: dict) -> str:
    """세그먼트 축의 지표명 (차트 y축 라벨에 그대로 쓰인다). 기본값은 시장규모."""
    return axis.get('value_label') or '시장규모'
