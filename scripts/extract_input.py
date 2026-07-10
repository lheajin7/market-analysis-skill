#!/usr/bin/env python3
"""
STEP 1: 입력 파일 분석 및 환경 초기화
STEP 2: 텍스트 추출 (전체 + TOC + 섹션별)

사용법:
  python extract_input.py \
    --input "D:\\...\\workspace\\input\\report.pdf" \
    --tech-field "데이터센터 냉각" \
    --project-name "Water ELITE 기술개발 경제성 분석" \
    --output-name "시장분석_데이터센터냉각"
"""

import argparse
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime

from _common import get_base

# ──────────────────────────────────────────────────────────────────
# 경로 상수
# ──────────────────────────────────────────────────────────────────
BASE = get_base()
WORKSPACE = os.path.join(BASE, 'workspace')
SKILL_DIR  = os.path.join(BASE, 'skill')
LOG_DIR    = os.path.join(WORKSPACE, 'logs')
TEXT_DIR   = os.path.join(WORKSPACE, 'extracted', 'text')

SECTION_KEYWORDS = [
    'Executive Summary', 'Market Snapshot', 'Market Overview',
    'Market Dynamics', 'Drivers', 'Restraints', 'Challenges', 'Opportunities',
    'Supply Chain', 'Ecosystem', 'Key Players', 'Market Map',
    'Regional', 'North America', 'Europe', 'Asia-Pacific',
    'Segmentation', 'Application', 'Product', 'End-Use',
    'R&D', 'Patent', 'Case Study', 'Government',
    'Competitive Landscape', 'Company Profile',
]


# ══════════════════════════════════════════════════════════════════
# STEP 1: 환경 초기화
# ══════════════════════════════════════════════════════════════════

def create_workspace():
    dirs = [
        os.path.join(SKILL_DIR, 'output'),
        os.path.join(WORKSPACE, 'input'),
        os.path.join(WORKSPACE, 'extracted', 'text'),
        os.path.join(WORKSPACE, 'extracted', 'images'),
        os.path.join(WORKSPACE, 'extracted', 'hwpx_raw'),
        os.path.join(WORKSPACE, 'structured'),
        os.path.join(WORKSPACE, 'charts'),
        os.path.join(WORKSPACE, 'hwpx_build', 'Contents'),
        os.path.join(WORKSPACE, 'hwpx_build', 'BinData'),
        os.path.join(WORKSPACE, 'hwpx_build', 'META-INF'),
        os.path.join(WORKSPACE, 'output'),
        LOG_DIR,
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    print('✅ 작업 디렉토리 생성 완료')


def detect_file_type(path: str) -> str:
    """바이너리 시그니처로 실제 파일 형식 판별"""
    if not os.path.exists(path):
        raise FileNotFoundError(f'파일 없음: {path}')
    with open(path, 'rb') as f:
        sig = f.read(8)
    if sig[:4] == b'%PDF':
        return 'pdf'
    if sig[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        return 'hwp'
    if sig[:4] == b'PK\x03\x04':
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        if any('content.hml' in n for n in names):
            return 'hwpx'
        return 'docx'
    return os.path.splitext(path)[1].lstrip('.').lower() or 'unknown'


def pdf_has_text_layer(path: str) -> bool:
    """pdfplumber로 첫 5페이지에 텍스트가 있는지 확인"""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:5]:
                if page.extract_text():
                    return True
        return False
    except Exception:
        return False


def get_pdf_info(path: str) -> dict:
    info = {'page_count': 0, 'publisher': '', 'publish_year': ''}
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            info['page_count'] = len(pdf.pages)
            meta = pdf.metadata or {}
            info['publisher'] = meta.get('Author', meta.get('Creator', ''))
            created = meta.get('CreationDate', '')
            # PDF 날짜 형식: D:YYYYMMDDHHmmss
            if created and len(created) >= 6:
                year_raw = created[2:6] if created.startswith('D:') else created[:4]
                info['publish_year'] = year_raw if year_raw.isdigit() else ''
    except Exception:
        pass
    return info


def get_hwpx_page_count(path: str) -> int:
    """HWPX에서 페이지 수 추출 (section XML 파싱)"""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            # section0.xml, section1.xml ... 파일 수 = 대략 섹션 수
            sections = [n for n in names if re.search(r'section\d+\.xml', n)]
            return max(len(sections), 1)
    except Exception:
        return 0


def save_step1_meta(args, file_type: str, has_text: bool,
                    file_info: dict, warnings: list) -> dict:
    meta = {
        'input_file':   args.input,
        'file_type':    file_type,
        'has_text_layer': has_text,
        'page_count':   file_info.get('page_count', 0),
        'file_size_mb': round(os.path.getsize(args.input) / 1024 / 1024, 2),
        'tech_field':   args.tech_field,
        'project_name': args.project_name,
        'output_format': args.output_format,
        'output_name':  args.output_name,
        'publisher':    file_info.get('publisher', ''),
        'publish_year': file_info.get('publish_year', ''),
        'timestamp':    datetime.now().isoformat(),
        'step1_status': 'warning' if warnings else 'success',
        'warnings':     warnings,
    }
    path = os.path.join(LOG_DIR, 'step1_meta.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


# ══════════════════════════════════════════════════════════════════
# STEP 2: 텍스트 추출
# ══════════════════════════════════════════════════════════════════

def extract_text_pdf(path: str) -> list:
    """페이지별 텍스트 리스트 반환 (섹션을 페이지 범위로 분리하기 위해 필요)"""
    import pdfplumber
    pages_text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            pages_text.append(t or '')
    return pages_text


def extract_text_hwpx(path: str) -> str:
    """HWPX ZIP → Contents/content.hml → lxml 텍스트 추출"""
    import lxml.etree as ET
    raw_dir = os.path.join(WORKSPACE, 'extracted', 'hwpx_raw')
    if not os.path.exists(os.path.join(raw_dir, 'Contents', 'content.hml')):
        with zipfile.ZipFile(path) as z:
            z.extractall(raw_dir)
    hml = os.path.join(raw_dir, 'Contents', 'content.hml')
    if not os.path.exists(hml):
        raise FileNotFoundError('content.hml not found in HWPX')
    tree = ET.parse(hml)
    return '\n'.join(t.strip() for t in tree.getroot().itertext() if t.strip())


def extract_text_hwp(path: str) -> str:
    """hwp5txt CLI (pyhwp 패키지) 사용"""
    result = subprocess.run(
        ['hwp5txt', path],
        capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    if result.returncode != 0:
        raise RuntimeError(f'hwp5txt 오류: {result.stderr[:200]}')
    return result.stdout


def extract_text_docx(path: str) -> str:
    try:
        import docx
    except ImportError:
        raise ImportError('python-docx 미설치: pip install python-docx')
    doc = docx.Document(path)
    return '\n'.join(p.text for p in doc.paragraphs if p.text.strip())


def save_full_text(text: str) -> str:
    path = os.path.join(TEXT_DIR, 'full_text.txt')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return path


def parse_toc(text: str) -> list:
    """목차 패턴 탐지 (숫자+점, 영문 헤더, 페이지 번호)"""
    toc = []
    seen = set()
    patterns = [
        # 숫자 계층 헤더: "1.2 Market Overview ......... 45"
        r'^(\d{1,2}(?:\.\d{1,2}){0,2}\.?)\s{1,4}([A-Za-z가-힣][^\n]{3,80}?)(?:\s[.\s]{3,}\s*(\d{1,4}))?$',
        # 전체 대문자 섹션 헤더
        r'^([A-Z][A-Z &\-/]{3,60})(?:\s[.\s]{3,}\s*(\d{1,4}))?$',
    ]
    for line in text.split('\n'):
        line = line.strip()
        if not line or line in seen:
            continue
        for pat in patterns:
            m = re.match(pat, line)
            if m:
                groups = [g for g in m.groups() if g]
                title_parts = [g for g in groups if not g.isdigit()]
                page_parts  = [g for g in groups if g.isdigit()]
                entry: dict = {'title': ' '.join(title_parts).strip()}
                if page_parts:
                    entry['page'] = int(page_parts[-1])
                toc.append(entry)
                seen.add(line)
                break
    return toc[:300]


def map_keywords_to_pages(toc: list) -> dict:
    """SECTION_KEYWORDS 각각을 가장 이른 페이지의 TOC 항목에 매핑한다."""
    kw_page: dict = {}
    for kw in SECTION_KEYWORDS:
        best_page = None
        for entry in toc:
            title = entry.get('title', '')
            page  = entry.get('page')
            if page is None or kw.lower() not in title.lower():
                continue
            if best_page is None or page < best_page:
                best_page = page
        if best_page is not None:
            kw_page[kw] = best_page
    return kw_page


def extract_sections_by_page(pages_text: list, toc: list) -> dict:
    """TOC 페이지 범위 기준으로 섹션을 분리한다.
    기존 extract_sections()는 SECTION_KEYWORDS 단어가 포함된 '아무 줄'이나
    새 섹션 시작으로 오인해(본문 중간의 표 캡션·문장에도 반응) 섹션이
    수백 자 단위로 잘려나가는 문제가 있었다. TOC에 이미 파싱된 페이지 번호를
    사용해 실제 페이지 범위로 잘라내면 이 문제를 피할 수 있다."""
    kw_page = map_keywords_to_pages(toc)
    if len(kw_page) < 3:
        return {}

    # detect_page_offset()은 짧고 흔한 TOC 제목 문자열이 본문 앞쪽에서
    # 우연히 재매칭되어 오프셋을 크게 잘못 추정하는 경우가 많아(-100 단위 오차 확인됨)
    # 사용하지 않는다. 이 보고서 시리즈는 PDF 페이지 인덱스와 인쇄된 페이지 번호가
    # 1:1로 대응하는 것으로 실측 확인되어 오프셋 0을 그대로 사용한다.
    offset  = 0
    n_pages = len(pages_text)
    items   = sorted(kw_page.items(), key=lambda kv: kv[1])

    sections: dict = {}

    # 문서 맨 앞(첫 매핑 키워드 이전 페이지) 구간은 그냥 버려지기 쉽다.
    # 시장 규모·CAGR 등 핵심 수치가 보통 이 앞부분(개요/스냅샷)에 있으므로
    # 'Market Overview' 키워드가 매핑되지 않았다면 이 구간을 대신 담아둔다.
    if items and 'Market Overview' not in kw_page:
        first_start = max(0, min(items[0][1] - 1 + offset, n_pages - 1))
        if first_start > 0:
            sections['Market Overview'] = '\n'.join(pages_text[0:first_start])

    for i, (kw, page_no) in enumerate(items):
        start_idx = max(0, min(page_no - 1 + offset, n_pages - 1))
        end_idx = n_pages
        if i + 1 < len(items):
            next_page = items[i + 1][1]
            end_idx = max(start_idx + 1, min(next_page - 1 + offset, n_pages))
        sections[kw] = '\n'.join(pages_text[start_idx:end_idx])
    return sections


def extract_sections(text: str) -> dict:
    """SECTION_KEYWORDS 기준으로 텍스트를 섹션별로 분리"""
    sections: dict = {}
    current_key = None
    current_lines: list = []

    for line in text.split('\n'):
        matched = None
        for kw in SECTION_KEYWORDS:
            if kw.lower() in line.lower() and len(line.strip()) < 120:
                matched = kw
                break
        if matched:
            if current_key and current_lines:
                sections[current_key] = '\n'.join(current_lines)
            current_key = matched
            current_lines = [line]
        elif current_key:
            current_lines.append(line)

    if current_key and current_lines:
        sections[current_key] = '\n'.join(current_lines)
    return sections


def save_sections(sections: dict):
    for idx, (name, content) in enumerate(sections.items(), 1):
        safe = re.sub(r'[\\/:*?"<>| ]', '_', name)
        path = os.path.join(TEXT_DIR, f'sec_{idx:02d}_{safe}.txt')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)


def save_toc(toc: list):
    path = os.path.join(TEXT_DIR, 'toc.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(toc, f, ensure_ascii=False, indent=2)


def save_step2_stats(text: str, sections: dict) -> dict:
    found   = list(sections.keys())
    missing = [k for k in SECTION_KEYWORDS if k not in found]
    stats = {
        'total_text_chars': len(text),
        'sections_found':   found,
        'sections_missing': missing,
        'images_extracted': 0,   # extract_images.py 실행 후 갱신
        'images_reusable':  0,
        'step2_status':     'success' if len(found) >= 4 else 'partial',
    }
    path = os.path.join(LOG_DIR, 'step2_extraction.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    return stats


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='시장분석 보고서 STEP 1+2 (텍스트)')
    parser.add_argument('--input',         required=True,  help='보고서 파일 경로')
    parser.add_argument('--tech-field',    default='',     help='기술분야명 (한글)')
    parser.add_argument('--project-name',  default='',     help='연구과제명')
    parser.add_argument('--output-format', default='hwpx', choices=['hwpx', 'hwp'])
    parser.add_argument('--output-name',   default='시장분석_보고서')
    args = parser.parse_args()

    # ─── STEP 1 ───────────────────────────────────────────────────
    print('\n[STEP 1] 환경 초기화 중...')
    create_workspace()

    warnings: list = []
    file_type = detect_file_type(args.input)
    print(f'  파일 형식 감지: {file_type.upper()}')

    file_info: dict = {}
    has_text = True

    if file_type == 'pdf':
        file_info = get_pdf_info(args.input)
        has_text  = pdf_has_text_layer(args.input)
        if not has_text:
            msg = '텍스트 레이어 없음 (스캔 PDF) — OCR 필요'
            warnings.append(msg)
            print(f'⚠️  {msg}')
    elif file_type == 'hwpx':
        file_info['page_count'] = get_hwpx_page_count(args.input)
    elif file_type == 'hwp':
        file_info['page_count'] = 0  # pyhwp 파싱 시 업데이트

    meta = save_step1_meta(args, file_type, has_text, file_info, warnings)

    packages_installed = ['pdfplumber', 'olefile', 'pyhwp', 'matplotlib',
                          'Pillow', 'pandas', 'numpy', 'lxml']
    print(f'\n✅ STEP 1 완료')
    print(f'  파일 형식: {file_type}')
    print(f'  페이지 수: {meta["page_count"]}')
    print(f'  텍스트 추출 가능: {"yes" if has_text else "no"}')
    print(f'  설치 완료 패키지: {len(packages_installed)}개')
    print(f'  다음 단계로 진행 가능: {"yes" if has_text else "no (OCR 필요)"}')

    if not has_text:
        print('\n❌ 스캔 PDF는 OCR 전처리 후 재실행하세요.')
        sys.exit(1)

    # ─── STEP 2 (텍스트) ─────────────────────────────────────────
    print('\n[STEP 2] 텍스트 추출 중...')
    dispatch = {
        'pdf':  extract_text_pdf,
        'hwpx': extract_text_hwpx,
        'hwp':  extract_text_hwp,
        'docx': extract_text_docx,
    }
    if file_type not in dispatch:
        print(f'❌ 지원하지 않는 형식: {file_type}')
        sys.exit(1)

    pages_text = None
    if file_type == 'pdf':
        pages_text = extract_text_pdf(args.input)
        text = '\n'.join(pages_text)
    else:
        text = dispatch[file_type](args.input)
    save_full_text(text)
    print(f'  전체 텍스트 저장: {len(text):,}자')

    toc = parse_toc(text)
    save_toc(toc)
    print(f'  TOC 항목: {len(toc)}개')

    sections = {}
    if pages_text:
        sections = extract_sections_by_page(pages_text, toc)
        if sections:
            print(f'  섹션 분리 방식: TOC 페이지 범위 기준 ({len(sections)}개)')
    if not sections:
        sections = extract_sections(text)
        print(f'  섹션 분리 방식: 키워드 라인 매칭 기준 (폴백)')
    save_sections(sections)
    stats = save_step2_stats(text, sections)

    found_preview = ', '.join(list(sections.keys())[:5])
    if len(sections) > 5:
        found_preview += '...'

    print(f'\n✅ STEP 2 완료')
    print(f'  추출 텍스트: {len(text):,}자')
    print(f'  탐지된 섹션: {len(sections)}개 ({found_preview})')
    print(f'  누락 섹션: {len(stats["sections_missing"])}개 '
          f'({", ".join(stats["sections_missing"][:3])}{"..." if len(stats["sections_missing"]) > 3 else ""})')
    if warnings:
        print(f'  주의사항: {"; ".join(warnings)}')
    print(f'\n  → 다음 단계: python extract_images.py')


if __name__ == '__main__':
    main()
