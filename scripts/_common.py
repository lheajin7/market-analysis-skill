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
