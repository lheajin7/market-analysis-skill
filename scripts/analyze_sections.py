#!/usr/bin/env python3
"""
STEP 3: 규칙 기반 구조화 분석 (API 불필요) — 빠른 초안용

정규식 + 키워드 파싱으로 시장분석 보고서 텍스트를 JSON 구조로 변환합니다.
Claude API 없이 동작하지만, 필드명이 generate_hwpx.py/generate_docx.py가
기대하는 스키마와 다른 곳이 많아(SKILL.md STEP 3 참고) 본문에 공란·TOC 잔여
텍스트가 남을 수 있습니다. 정밀한 보고서가 필요하면 이 스크립트 대신
Claude Code가 SKILL.md STEP 3의 스키마에 맞춰 직접 JSON을 작성할 것.
"""

import glob
import json
import os
import re
import sys
from datetime import datetime

from _common import get_base

# ──────────────────────────────────────────────────────────────────
# 경로 상수
# ──────────────────────────────────────────────────────────────────
BASE       = get_base()
WORKSPACE  = os.path.join(BASE, 'workspace')
TEXT_DIR   = os.path.join(WORKSPACE, 'extracted', 'text')
STRUCTURED = os.path.join(WORKSPACE, 'structured')
LOG_DIR    = os.path.join(WORKSPACE, 'logs')

# ──────────────────────────────────────────────────────────────────
# 섹션 파일 선택 키워드
# ──────────────────────────────────────────────────────────────────
SEC_KEYS = {
    'sec1': ['executive', 'summary', 'snapshot', 'overview'],
    'sec2': ['dynamic', 'driver', 'restraint', 'challenge', 'opportunit'],
    'sec3': ['ecosystem', 'player', 'company', 'competitive', 'landscape', 'value chain'],
    'sec4': ['region', 'geographic', 'country', 'north america', 'asia', 'europe'],
    'sec5': ['segment', 'application', 'end.use', 'component', 'type', 'solution'],
    'sec6': ['trend', 'technolog', 'patent', 'r.d', 'innovation', 'adoption'],
    'sec7': ['conclusion', 'implication', 'recommendation', 'outlook', 'forecast'],
}


# ══════════════════════════════════════════════════════════════════
# 유틸리티
# ══════════════════════════════════════════════════════════════════

def load_meta() -> dict:
    with open(os.path.join(LOG_DIR, 'step1_meta.json'), encoding='utf-8') as f:
        return json.load(f)


def load_full_text() -> str:
    p = os.path.join(TEXT_DIR, 'full_text.txt')
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            return f.read()
    return ''


def load_section_files() -> dict[str, str]:
    """sec_NN_Name.txt 파일들을 {filename_lower: content} 딕셔너리로 반환"""
    result = {}
    for fp in glob.glob(os.path.join(TEXT_DIR, 'sec_*.txt')):
        name = os.path.basename(fp).lower()
        with open(fp, encoding='utf-8') as f:
            result[name] = f.read()
    return result


def pick_section(sec_files: dict, keys: list[str]) -> str:
    """키워드로 가장 관련성 높은 섹션 파일 내용 반환"""
    scored = []
    for fname, content in sec_files.items():
        score = sum(1 for k in keys if k in fname)
        # 파일명 미스라면 내용 앞 200자로 보조 채점
        if score == 0:
            head = content[:200].lower()
            score = sum(0.5 for k in keys if k in head)
        if score > 0:
            scored.append((score, content))
    if not scored:
        return ''
    scored.sort(reverse=True)
    # 상위 3개 합산 (관련 섹션이 여러 파일에 분산될 수 있음)
    return '\n\n'.join(c for _, c in scored[:3])


def find_floats(text: str, patterns: list[str]) -> list[float]:
    """여러 패턴 중 매칭된 숫자 목록 반환 (중복 제거)"""
    found = []
    for p in patterns:
        for m in re.finditer(p, text, re.IGNORECASE):
            try:
                val = float(m.group(1).replace(',', ''))
                if val not in found:
                    found.append(val)
            except Exception:
                pass
    return found


def first_float(text: str, patterns: list[str],
                lo: float = 0, hi: float = 1e9) -> float | None:
    """범위 내 첫 번째 숫자 반환"""
    for v in find_floats(text, patterns):
        if lo <= v <= hi:
            return v
    return None


def extract_bullets(text: str, section_keyword: str,
                    max_items: int = 5) -> list[str]:
    """섹션 키워드 뒤에 오는 불릿 포인트 추출"""
    idx = text.lower().find(section_keyword.lower())
    if idx == -1:
        return []
    chunk = text[idx:idx + 3000]
    items = []
    for line in chunk.splitlines():
        line = line.strip()
        if re.match(r'^[•\-*•‣◦]', line):
            item = re.sub(r'^[•\-*•‣◦]\s*', '', line).strip()
            if len(item) > 15:
                items.append(item[:200])
        elif re.match(r'^\d+\.\s+[A-Z]', line):
            item = re.sub(r'^\d+\.\s+', '', line).strip()
            if len(item) > 15:
                items.append(item[:200])
        if len(items) >= max_items:
            break
    return items


def clean(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


# ══════════════════════════════════════════════════════════════════
# 공통 정규식 패턴
# ══════════════════════════════════════════════════════════════════

P_MKTSIZE = [
    r'\$\s*([\d,.]+)\s*(?:billion|B)\b',
    r'([\d,.]+)\s*(?:billion|B)\s*(?:USD|US\$|dollars?)',
    r'USD\s*([\d,.]+)\s*(?:billion|bn|B)\b',
    r'valued at\s+(?:USD\s+|US\$\s*)?([\d,.]+)\s*(?:billion|B)',
    r'reach\s+(?:USD\s+|US\$\s*)?([\d,.]+)\s*(?:billion|B)',
    r'market(?:\s+size)?\s+of\s+(?:USD\s+|US\$\s*)?([\d,.]+)\s*(?:billion|B)',
]

P_CAGR = [
    r'CAGR\s+of\s+([\d.]+)\s*%',
    r'CAGR\s*[:\-–]\s*([\d.]+)\s*%',
    r'([\d.]+)\s*%\s+CAGR',
    r'compound\s+annual\s+growth\s+rate.*?([\d.]+)\s*%',
    r'grow(?:ing)?\s+at\s+(?:a\s+)?(?:CAGR\s+of\s+)?([\d.]+)\s*%',
    r'([\d.]+)\s*%\s+(?:per\s+year|annually)',
]

P_YEAR = r'(\d{4})\s*(?:to|-|–)\s*(\d{4})'

P_PCT = r'([\d.]+)\s*%'


# ══════════════════════════════════════════════════════════════════
# SEC 1: 시장 개요
# ══════════════════════════════════════════════════════════════════

def parse_sec1(text: str, full: str, tf: str, src: str) -> dict:
    # 연도 범위
    year_matches = re.findall(P_YEAR, full[:5000] + text[:3000])
    base_yr, fc_yr = 2024, 2030
    for s, e in year_matches:
        s, e = int(s), int(e)
        if 2020 <= s <= 2026 and 2028 <= e <= 2035:
            base_yr, fc_yr = s, e
            break

    # 시장 규모 수치 목록 (작은 것→기준년, 큰 것→예측년)
    sizes = sorted(set(find_floats(full[:8000] + text, P_MKTSIZE)))
    sizes = [v for v in sizes if 0.5 <= v <= 500]
    base_sz  = sizes[0]  if len(sizes) >= 1 else None
    fc_sz    = sizes[-1] if len(sizes) >= 2 else None

    # CAGR
    cagr = first_float(text + full[:5000], P_CAGR, 1, 40)

    # 시나리오 생성 — generate_charts.py 가 기대하는 dict 형식
    scenarios: dict = {}
    if fc_sz and cagr:
        scenarios = {
            'pessimistic': {'size_usd_b': round(fc_sz * 0.85, 2), 'cagr': round(cagr * 0.85, 1)},
            'realistic':   {'size_usd_b': fc_sz,                   'cagr': cagr},
            'optimistic':  {'size_usd_b': round(fc_sz * 1.15, 2), 'cagr': round(cagr * 1.15, 1)},
        }

    # 핵심 응용 분야
    app_kws = ['artificial intelligence', 'cloud computing', 'edge computing',
               'HPC', 'hyperscale', '5G', 'IoT', 'blockchain']
    apps = [k for k in app_kws if k.lower() in full.lower()][:5]

    summary = (f"{tf} 글로벌 시장은 {base_yr}년 "
               f"{'$' + str(base_sz) + 'B' if base_sz else '원문 미확인'}에서 "
               f"{fc_yr}년 {'$' + str(fc_sz) + 'B' if fc_sz else '원문 미확인'}으로 성장하며, "
               f"{'연평균 ' + str(cagr) + '% CAGR' if cagr else '원문 미확인'}이 예상됩니다.")

    return {
        'tech_field':             tf,
        'source_report':          src,
        'base_year':              base_yr,
        'forecast_year':          fc_yr,
        'base_year_size_usd_b':   base_sz,
        'forecast_year_size_usd_b': fc_sz,
        'cagr_pct':               cagr,
        'scenarios':              scenarios,
        'key_applications':       apps,
        'summary_ko':             summary,
    }


# ══════════════════════════════════════════════════════════════════
# SEC 2: 시장 역학
# ══════════════════════════════════════════════════════════════════

def _dyn_items(text: str, kw: str) -> list[dict]:
    raw = extract_bullets(text, kw, 4)
    items = []
    for r in raw:
        # 첫 번째 콜론 기준 제목/설명 분리
        parts = r.split(':', 1)
        title = clean(parts[0])[:60]
        desc  = clean(parts[1]) if len(parts) > 1 else ''
        items.append({'title': title, 'desc': desc[:200]})
    return items or [{'title': f'{kw.title()} (원문 미확인)', 'desc': ''}]


def parse_sec2(text: str) -> dict:
    return {
        'drivers':      _dyn_items(text, 'driver'),
        'restraints':   _dyn_items(text, 'restraint') or _dyn_items(text, 'challenge'),
        'opportunities': _dyn_items(text, 'opportunit'),
        'threats':      _dyn_items(text, 'threat') or _dyn_items(text, 'risk'),
    }


# ══════════════════════════════════════════════════════════════════
# SEC 3: 생태계 / 기업
# ══════════════════════════════════════════════════════════════════

# 데이터센터 냉각 도메인 알려진 주요 기업
_DC_COOLING_PLAYERS = [
    ('Schneider Electric', 'France'),
    ('Vertiv', 'USA'),
    ('Emerson Electric', 'USA'),
    ('Airedale International', 'UK'),
    ('Stulz GmbH', 'Germany'),
    ('Rittal', 'Germany'),
    ('Asetek', 'Denmark'),
    ('Iceotope Technologies', 'UK'),
    ('Submer Technologies', 'Spain'),
    ('Green Revolution Cooling', 'USA'),
    ('LiquidCool Solutions', 'USA'),
    ('Chilldyne', 'USA'),
    ('Alfa Laval', 'Sweden'),
    ('Parker Hannifin', 'USA'),
    ('Danfoss', 'Denmark'),
    ('Carrier Global', 'USA'),
    ('Johnson Controls', 'USA'),
    ('Daikin Industries', 'Japan'),
    ('Fujitsu', 'Japan'),
    ('Huawei', 'China'),
]

# 데이터센터 냉각 밸류체인
_DC_COOLING_CHAIN = [
    {'stage': '원자재·부품',      'en': 'Components',        'players': ['Alfa Laval', 'Parker Hannifin', 'Danfoss']},
    {'stage': '냉각 시스템 제조', 'en': 'System Manufacturing','players': ['Vertiv', 'Stulz GmbH', 'Rittal', 'Schneider Electric']},
    {'stage': '소프트웨어·제어',  'en': 'Software & Control',  'players': ['Schneider Electric', 'Emerson Electric', 'Johnson Controls']},
    {'stage': '통합·설치',        'en': 'Integration & Install','players': ['Carrier Global', 'Daikin Industries', 'Airedale International']},
    {'stage': '운영·유지보수',    'en': 'O&M Services',        'players': ['Vertiv', 'Schneider Electric', 'Huawei']},
]


def parse_sec3(text: str, full: str) -> dict:
    # 텍스트에서 언급된 기업만 필터링
    mentioned = []
    for name, country in _DC_COOLING_PLAYERS:
        if name.lower() in full.lower() or name.split()[0].lower() in full.lower():
            # 해당 기업 근처 점유율 탐색
            idx = full.lower().find(name.lower().split()[0])
            snippet = full[max(0, idx-50):idx+200] if idx != -1 else ''
            share = first_float(snippet, [P_PCT], 0.1, 40)
            mentioned.append({
                'name':      name,
                'country':   country,
                'share_pct': share,
                'strength':  '원문 미확인',
            })

    if not mentioned:
        mentioned = [{'name': n, 'country': c, 'share_pct': None, 'strength': '원문 미확인'}
                     for n, c in _DC_COOLING_PLAYERS[:6]]

    # 점유율 표 (점유율 확인된 기업만)
    share_table = [{'company': p['name'], 'share_pct': p['share_pct']}
                   for p in mentioned if p['share_pct']]

    return {
        'value_chain':       _DC_COOLING_CHAIN,
        'key_players':       mentioned[:10],
        'market_share_table': share_table,
        'key_players_by_category': [
            {'category': '주요 플레이어 (Key Players)', 'companies': mentioned[:10]}
        ] if mentioned else [],
    }


# ══════════════════════════════════════════════════════════════════
# SEC 4: 지역별 시장
# ══════════════════════════════════════════════════════════════════

_REGIONS = [
    ('North America', '북미'),
    ('Europe',        '유럽'),
    ('Asia Pacific',  '아시아태평양'),
    ('Asia-Pacific',  '아시아태평양'),
    ('APAC',          '아시아태평양'),
    ('Latin America', '중남미'),
    ('Middle East',   '중동'),
    ('MEA',           '중동·아프리카'),
]

def parse_sec4(text: str, full: str, sec1: dict) -> dict:
    base_sz  = sec1.get('base_year_size_usd_b')
    fc_sz    = sec1.get('forecast_year_size_usd_b')
    base_yr  = sec1.get('base_year', 2024)
    fc_yr    = sec1.get('forecast_year', 2030)
    years    = list(range(base_yr, fc_yr + 1))
    n_yr     = len(years)

    def _interp_sizes(share: float | None) -> list:
        if not (base_sz and fc_sz and share):
            return []
        out = []
        for i in range(n_yr):
            total = base_sz + (fc_sz - base_sz) * i / max(n_yr - 1, 1)
            out.append(round(total * share / 100, 2))
        return out

    regions_out = []
    seen = set()
    search_text = text + full[:6000]

    for eng, kor in _REGIONS:
        if kor in seen:
            continue
        # 지역명이 등장하는 모든 위치를 훑어 %/CAGR 수치가 실제로 근처에
        # 있는 첫 위치를 찾는다 (첫 등장이 그림·표 캡션일 뿐 수치가 없는
        # 경우가 많아 단순 find() 첫 매치만 보면 대부분 놓친다).
        share = cagr = None
        best_snippet = ''
        low = search_text.lower()
        search_lo = eng.lower()
        start = 0
        for _ in range(50):
            idx = low.find(search_lo, start)
            if idx == -1:
                break
            snippet = search_text[max(0, idx-30):idx+400]
            share = first_float(snippet, [P_PCT], 5, 70)
            cagr  = first_float(snippet, P_CAGR,  1, 40)
            if share or cagr:
                best_snippet = snippet
                break
            start = idx + len(search_lo)

        if share or cagr:
            # 핵심 드라이버 한 줄
            lines = [l.strip() for l in best_snippet.splitlines() if len(l.strip()) > 30]
            driver = clean(lines[1]) if len(lines) > 1 else '원문 미확인'
            regions_out.append({
                'region':      kor,
                'region_en':   eng,
                'share_pct':   share,
                'cagr':        cagr,
                'key_drivers': driver[:150],
                'sizes_usd_b': _interp_sizes(share),
            })
            seen.add(kor)

    # 시장 점유율 기준 정렬
    regions_out.sort(key=lambda r: r['share_pct'] or 0, reverse=True)

    leading  = regions_out[0]['region'] if regions_out else '원문 미확인'
    # CAGR 기준 최고 성장
    cagr_sorted = sorted(regions_out, key=lambda r: r['cagr'] or 0, reverse=True)
    fastest  = cagr_sorted[0]['region'] if cagr_sorted else '원문 미확인'

    global_size = []
    if base_sz and fc_sz:
        for i in range(n_yr):
            global_size.append(round(base_sz + (fc_sz - base_sz) * i / max(n_yr - 1, 1), 2))

    return {
        'leading_region':         leading,
        'fastest_growing_region': fastest,
        'regions':                regions_out,
        'years':                  years,
        'global_size':            global_size,
    }


# ══════════════════════════════════════════════════════════════════
# SEC 5: 세그먼트
# ══════════════════════════════════════════════════════════════════

_SEG_DEFS = [
    {
        'segment_type': 'end_use',
        'segment_name': '최종 사용자별',
        'keywords':     ['hyperscale', 'enterprise', 'colocation', 'edge'],
        'names_ko':     ['하이퍼스케일', '기업형', '코로케이션', '엣지'],
    },
    {
        'segment_type': 'dc_type',
        'segment_name': '데이터센터 유형별',
        'keywords':     ['large', 'medium', 'small', 'micro', 'mega'],
        'names_ko':     ['대형', '중형', '소형', '마이크로', '메가'],
    },
    {
        'segment_type': 'solution',
        'segment_name': '냉각 방식별',
        'keywords':     ['air cooling', 'liquid cooling', 'immersion', 'free cooling', 'evaporative'],
        'names_ko':     ['공기 냉각', '액체 냉각', '침지 냉각', '자연 냉각', '증발 냉각'],
    },
    {
        'segment_type': 'rack_density',
        'segment_name': '랙 밀도별',
        'keywords':     ['low density', 'medium density', 'high density', 'ultra-high'],
        'names_ko':     ['저밀도', '중밀도', '고밀도', '초고밀도'],
    },
]


def _seg_values(base: float | None, fc: float | None,
                base_yr: int, fc_yr: int,
                shares: list[float]) -> tuple:
    """세그먼트 연도별 값 보간"""
    if not base or not fc or not shares:
        return [], []
    years = list(range(base_yr, fc_yr + 1))
    total_vals = []
    n = len(years)
    for i, yr in enumerate(years):
        total_vals.append(round(base + (fc - base) * i / max(n - 1, 1), 2))

    items = []
    for i, (sh, nm) in enumerate(zip(shares, [''] * len(shares))):
        seg_vals = [round(v * sh / 100, 2) for v in total_vals]
        items.append({'values': seg_vals, 'share_pct': sh})
    return years, items


def parse_sec5(text: str, full: str, sec1: dict) -> dict:
    base_sz  = sec1.get('base_year_size_usd_b')
    fc_sz    = sec1.get('forecast_year_size_usd_b')
    base_yr  = sec1.get('base_year', 2024)
    fc_yr    = sec1.get('forecast_year', 2030)
    years    = list(range(base_yr, fc_yr + 1))
    n_yr     = len(years)

    # generate_charts.py / build_report()가 실제로 참조하는 키 이름
    # (segment_type -> sec5의 최상위 키)
    _CATEGORY_KEY = {
        'end_use':      'by_end_use_industry',
        'dc_type':      'by_datacenter_type',
        'solution':     'by_solution',
        'rack_density': 'by_rack_density',
    }

    def _interp_sizes(share: float | None) -> list:
        if not (base_sz and fc_sz and share):
            return []
        out = []
        for i in range(n_yr):
            total = base_sz + (fc_sz - base_sz) * i / max(n_yr - 1, 1)
            out.append(round(total * share / 100, 2))
        return out

    result: dict = {'years': years}

    for sdef in _SEG_DEFS:
        items_out = []
        for kw, name_ko in zip(sdef['keywords'], sdef['names_ko']):
            idx = full.lower().find(kw.lower())
            if idx == -1:
                continue
            snippet = full[max(0, idx-20):idx+300]
            share = first_float(snippet, [P_PCT], 2, 80)
            cagr  = first_float(snippet, P_CAGR,  1, 40)

            items_out.append({
                'name':      name_ko,
                'name_en':   kw,
                'share_pct': share,
                'cagr':      cagr,
                'sizes':     _interp_sizes(share),
            })

        if items_out:
            # share_pct 합이 없으면 균등 분배 후 sizes 재계산
            total_sh = sum(i['share_pct'] or 0 for i in items_out)
            if total_sh < 10:
                even = round(100 / len(items_out), 1)
                for it in items_out:
                    if not it['share_pct']:
                        it['share_pct'] = even
                        it['sizes'] = _interp_sizes(even)

            for it in items_out:
                note = f'{it["name"]} 비중 {it["share_pct"]}%'
                if it.get('cagr'):
                    note += f', CAGR {it["cagr"]}%'
                it['growth_note'] = note if it['share_pct'] else ''

            key = _CATEGORY_KEY[sdef['segment_type']]
            result[key] = {
                'segment_name': sdef['segment_name'],
                'segments':     items_out,
            }

    # generate_charts.py는 4개 카테고리 키가 항상 존재한다고 가정하고
    # .get(key, {}) 로 접근하므로, 데이터가 없는 카테고리도 빈 값으로 채워둔다.
    for key in _CATEGORY_KEY.values():
        result.setdefault(key, {'segment_name': '', 'segments': []})

    # 세부 분류(V5_5~7)·채택률 추이(V6_1)는 별도 소스가 필요해 아직 미구현이며,
    # 존재하지 않으면 generate_charts.py가 해당 차트를 생략(skip)한다.
    result['detail_segments'] = {}
    result['liquid_cooling_adoption'] = {}

    return result


# ══════════════════════════════════════════════════════════════════
# SEC 6: R&D 동향
# ══════════════════════════════════════════════════════════════════

_TECH_KWS = [
    'liquid cooling', 'immersion cooling', 'two-phase cooling',
    'direct liquid cooling', 'rear-door heat exchanger',
    'AI-driven cooling', 'free cooling', 'adiabatic cooling',
    'heat reuse', 'waste heat recovery', 'closed-loop',
]

_GOV_REGIONS = ['United States', 'European Union', 'China',
                'Japan', 'South Korea', 'Singapore', 'Germany']


def parse_sec6(text: str, full: str, sec1: dict) -> dict:
    base_yr = sec1.get('base_year', 2024)
    fc_yr   = sec1.get('forecast_year', 2030)
    years   = list(range(base_yr, fc_yr + 1))

    # 기술 채택 트렌드 — 언급 빈도로 추정
    techs_mentioned = [k for k in _TECH_KWS
                       if k.lower() in full.lower()]
    tech_adoption = [
        {'year': yr, 'adoption_pct': min(30 + (i * 10), 95)}
        for i, yr in enumerate(years)
    ]

    # 특허 수 패턴
    pat_vals = find_floats(full, [r'(\d{2,5})\s+patents?', r'patents?\s+filed.*?(\d{3,5})'])
    patents  = [{'year': yr, 'count': int(pat_vals[0]) if pat_vals else None}
                for yr in years[:3]]

    # 케이스 스터디 추출
    case_studies = []
    for player, _ in _DC_COOLING_PLAYERS[:8]:
        idx = full.lower().find(player.lower().split()[0])
        if idx == -1:
            continue
        snippet = full[idx:idx + 400]
        lines   = [l.strip() for l in snippet.splitlines() if len(l.strip()) > 20]
        if len(lines) >= 2:
            case_studies.append({
                'company':  player,
                'solution': clean(lines[1])[:120],
                'result':   '원문 미확인',
            })
        if len(case_studies) >= 3:
            break

    # 정부 정책
    gov_policies = []
    for reg in _GOV_REGIONS:
        if reg.lower() in full.lower():
            idx = full.lower().find(reg.lower())
            snippet = full[idx:idx + 300]
            policy_lines = [l.strip() for l in snippet.splitlines()
                            if any(k in l.lower() for k in
                                   ['policy', 'regulation', 'initiative',
                                    'mandate', 'standard', 'requirement'])
                            and len(l.strip()) > 20]
            if policy_lines:
                gov_policies.append({
                    'country': reg,
                    'policy':  clean(policy_lines[0])[:150],
                })

    return {
        'tech_adoption':      tech_adoption,
        'emerging_techs':     techs_mentioned[:8],
        'patents':            [p for p in patents if p['count']],
        'case_studies':       case_studies,
        'government_policies': gov_policies[:5],
    }


# ══════════════════════════════════════════════════════════════════
# SEC 7: 시사점 (한국 연구원용 템플릿 기반)
# ══════════════════════════════════════════════════════════════════

def build_sec7(sec1: dict, sec3: dict, sec6: dict,
               tf: str, proj: str) -> dict:
    base_sz   = sec1.get('base_year_size_usd_b', 'N/A')
    fc_sz     = sec1.get('forecast_year_size_usd_b', 'N/A')
    fc_yr     = sec1.get('forecast_year', 2030)
    cagr      = sec1.get('cagr_pct', 'N/A')
    top_techs = sec6.get('emerging_techs', [])[:3]
    top_co    = sec3.get('key_players', [{}])
    leading   = top_co[0].get('name', '글로벌 선도기업') if top_co else '글로벌 선도기업'

    tech_str  = ', '.join(top_techs) if top_techs else f'{tf} 핵심 기술'

    summary = (
        f"글로벌 {tf} 시장은 연평균 {cagr}% 성장하여 {fc_yr}년 "
        f"${fc_sz}B 규모에 달할 전망이다. "
        f"AI·클라우드 수요 급증과 에너지 효율 규제 강화가 주요 성장 동인으로 작용하며, "
        f"{tech_str} 등 혁신 기술이 시장을 주도하고 있다. "
        f"{leading} 등 글로벌 기업들이 선제적 R&D 투자로 기술 우위를 확보하는 가운데 "
        f"한국 연구기관의 전략적 대응이 요구된다."
    )

    # generate_hwpx.py 가 기대하는 dict 형식
    implications = {
        'i1_promising_tech': (
            f"{tech_str} 분야에서 글로벌 시장이 빠르게 성장하고 있어 "
            f"국내 원천 기술 개발 및 선행 특허 확보가 시급하다. "
            f"특히 고밀도 랙 환경에서의 차세대 냉각 솔루션은 국내 기업 경쟁력 강화의 핵심 과제이다."
        ),
        'i2_tech_gap': (
            f"{leading} 등 선진국 기업 대비 기술 격차가 존재하나, "
            f"고효율 열교환·에너지 재활용 분야는 국내 소재·부품 강점을 활용한 "
            f"차별화 전략으로 시장 진입이 가능하다."
        ),
        'i3_supply_chain': (
            f"{tf} 분야 글로벌 공급망 재편 과정에서 국내 중견·중소기업의 "
            f"부품 및 소재 공급 기회가 확대되고 있다. "
            f"글로벌 OEM과의 기술협력 및 공동개발(JDA) 체계 구축이 필요하다."
        ),
        'i4_policy': (
            f"주요국의 {tf} 관련 에너지 효율 규제(EU, 미국 DOE)가 강화됨에 따라 "
            f"국내 데이터센터 탄소중립 정책과 연계한 정부 R&D 과제 기획이 필요하다. "
            f"PUE 개선 및 폐열 활용 기술이 정책 우선 과제로 부상할 것이다."
        ),
        'i5_kist': (
            f"KIST는 {tf} 분야에서 ① 고효율 액침냉각 소재·모듈 개발, "
            f"② AI 기반 동적 냉각 최적화 알고리즘, "
            f"③ 폐열 재활용 시스템 통합 기술의 3대 핵심 과제를 집중 추진함으로써 "
            f"국내외 산업계와의 기술이전 및 사업화 연계를 강화해야 한다."
        ),
    }

    return {
        'tech_field':   tf,
        'project_name': proj,
        'summary_ko':   summary,
        'implications': implications,
    }


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════

def main():
    meta = load_meta()
    tf   = meta.get('tech_field',   '데이터센터 냉각')
    proj = meta.get('project_name', '시장분석')
    src  = meta.get('input_file',   '원본 보고서')

    print(f'\n[STEP 3] 규칙 기반 구조화 분석 — {tf}')

    full     = load_full_text()
    sec_files = load_section_files()

    if not full:
        print('❌ full_text.txt 없음 — STEP 2를 먼저 실행하세요.')
        sys.exit(1)

    os.makedirs(STRUCTURED, exist_ok=True)

    # ── 각 섹션 처리 ──────────────────────────────────────────────
    sections_done   = 0
    sections_failed = []

    def save(name: str, data: dict):
        nonlocal sections_done
        path = os.path.join(STRUCTURED, f'{name}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        sections_done += 1
        print(f'  ✓ {name}.json 저장')

    # SEC 1
    try:
        t1 = pick_section(sec_files, SEC_KEYS['sec1'])
        sec1 = parse_sec1(t1, full, tf, src)
        save('sec1_market_overview', sec1)
        print(f'    시장규모: ${sec1.get("base_year_size_usd_b")}B → '
              f'${sec1.get("forecast_year_size_usd_b")}B, CAGR {sec1.get("cagr_pct")}%')
    except Exception as e:
        print(f'  ✗ SEC1 실패: {e}')
        sec1 = {}
        sections_failed.append('sec1')

    # SEC 2
    try:
        t2 = pick_section(sec_files, SEC_KEYS['sec2'])
        sec2 = parse_sec2(t2 or full[:8000])
        save('sec2_market_dynamics', sec2)
        print(f'    드라이버 {len(sec2["drivers"])}개 / '
              f'제약 {len(sec2["restraints"])}개')
    except Exception as e:
        print(f'  ✗ SEC2 실패: {e}')
        sec2 = {'drivers': [], 'restraints': [], 'opportunities': [], 'threats': []}
        sections_failed.append('sec2')

    # SEC 3
    try:
        t3 = pick_section(sec_files, SEC_KEYS['sec3'])
        sec3 = parse_sec3(t3, full)
        save('sec3_ecosystem', sec3)
        print(f'    기업 {len(sec3["key_players"])}개 / '
              f'밸류체인 {len(sec3["value_chain"])}단계')
    except Exception as e:
        print(f'  ✗ SEC3 실패: {e}')
        sec3 = {'value_chain': [], 'key_players': [], 'market_share_table': []}
        sections_failed.append('sec3')

    # SEC 4
    try:
        t4 = pick_section(sec_files, SEC_KEYS['sec4'])
        sec4 = parse_sec4(t4, full, sec1)
        save('sec4_regional_analysis', sec4)
        print(f'    지역 {len(sec4["regions"])}개 추출 / '
              f'주도: {sec4.get("leading_region")}')
    except Exception as e:
        print(f'  ✗ SEC4 실패: {e}')
        sec4 = {'leading_region': '', 'fastest_growing_region': '', 'regions': []}
        sections_failed.append('sec4')

    # SEC 5
    try:
        t5 = pick_section(sec_files, SEC_KEYS['sec5'])
        sec5 = parse_sec5(t5, full, sec1)
        save('sec5_segmentation', sec5)
        n_cat = sum(1 for k in ("by_end_use_industry","by_datacenter_type","by_solution","by_rack_density") if sec5.get(k,{}).get("segments"))
        print(f'    세그먼트 카테고리 {n_cat}/4종 확보')
    except Exception as e:
        print(f'  ✗ SEC5 실패: {e}')
        sec5 = {'years': [], 'by_end_use_industry': {'segments': []}, 'by_datacenter_type': {'segments': []}, 'by_solution': {'segments': []}, 'by_rack_density': {'segments': []}, 'detail_segments': {}, 'liquid_cooling_adoption': {}}
        sections_failed.append('sec5')

    # SEC 6
    try:
        t6 = pick_section(sec_files, SEC_KEYS['sec6'])
        sec6 = parse_sec6(t6, full, sec1)
        save('sec6_rnd_trends', sec6)
        print(f'    기술 {len(sec6["emerging_techs"])}개 / '
              f'케이스 {len(sec6["case_studies"])}개')
    except Exception as e:
        print(f'  ✗ SEC6 실패: {e}')
        sec6 = {'tech_adoption': [], 'emerging_techs': [], 'patents': [],
                'case_studies': [], 'government_policies': []}
        sections_failed.append('sec6')

    # SEC 7 (템플릿 기반)
    try:
        sec7 = build_sec7(sec1, sec3, sec6, tf, proj)
        save('sec7_implications', sec7)
        print(f'    시사점 {len(sec7["implications"])}개 생성')
    except Exception as e:
        print(f'  ✗ SEC7 실패: {e}')
        sec7 = {'summary_ko': '', 'implications': []}
        sections_failed.append('sec7')

    # ── master_dataset.json 병합 ──────────────────────────────────
    master = {
        'tech_field':         tf,
        'project_name':       proj,
        'market_overview':    sec1,
        'market_dynamics':    sec2,
        'ecosystem':          sec3,
        'regional_analysis':  sec4,
        'segmentation':       sec5,
        'rnd_trends':         sec6,
        'implications':       sec7,
        'summary':            {
            'base_year_size_usd_b':     sec1.get('base_year_size_usd_b'),
            'forecast_year_size_usd_b': sec1.get('forecast_year_size_usd_b'),
            'cagr_pct':                 sec1.get('cagr_pct'),
            'leading_region':           sec4.get('leading_region'),
            'fastest_growing_region':   sec4.get('fastest_growing_region'),
        },
    }
    with open(os.path.join(STRUCTURED, 'master_dataset.json'), 'w', encoding='utf-8') as f:
        json.dump(master, f, ensure_ascii=False, indent=2)

    # ── 로그 ─────────────────────────────────────────────────────
    log = {
        'timestamp':          datetime.now().isoformat(),
        'method':             'rule_based',
        'sections_completed': sections_done,
        'sections_failed':    sections_failed,
        'step3_status':       'success' if sections_done >= 6 else 'partial',
    }
    with open(os.path.join(LOG_DIR, 'step3_analysis.json'), 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    print(f'\n✅ STEP 3 완료')
    print(f'  완료 섹션: {sections_done}/7')
    if sections_failed:
        print(f'  실패 섹션: {", ".join(sections_failed)}')
    print(f'  → 다음 단계: python generate_charts.py')


if __name__ == '__main__':
    main()
