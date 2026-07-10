#!/usr/bin/env python3
"""공용 헬퍼: config.json의 base_dir을 읽어 프로젝트 루트 경로를 반환한다.

모든 파이프라인 스크립트(analyze_sections.py, extract_input.py 등)는
이 함수로 BASE를 계산해, 폴더나 입력 보고서가 바뀌어도 config.json 값만
수정하면 재사용할 수 있도록 한다.
"""
import json
import os

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
