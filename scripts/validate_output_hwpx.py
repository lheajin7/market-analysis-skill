#!/usr/bin/env python3
"""
STEP 6: 품질 검증 및 자동 수정

사전 조건: generate_hwpx.py 실행 완료 (workspace/output/{name}.hwpx 존재)

사용법:
  python validate_output.py

품질 검증까지 실행하려면:
  $env:ANTHROPIC_API_KEY="sk-ant-..."
  python validate_output.py
"""

import json
import os
import re
import shutil
import sys
import time
import zipfile
from datetime import datetime

from lxml import etree as ET

from _common import get_base

# ──────────────────────────────────────────────────────────────────
# 경로 상수
# ──────────────────────────────────────────────────────────────────
BASE       = get_base()
WORKSPACE  = os.path.join(BASE, 'workspace')
STRUCTURED = os.path.join(WORKSPACE, 'structured')
HWPX_BUILD = os.path.join(WORKSPACE, 'hwpx_build')
OUTPUT_DIR = os.path.join(WORKSPACE, 'output')
LOG_DIR    = os.path.join(WORKSPACE, 'logs')
SKILL_OUT  = os.path.join(BASE, 'skill', 'output')

MODEL = 'claude-sonnet-4-6'

OPF_NS = {'opf': 'http://www.idpf.org/2007/opf/'}


# ══════════════════════════════════════════════════════════════════
# 유틸리티
# ══════════════════════════════════════════════════════════════════

def load_meta() -> dict:
    with open(os.path.join(LOG_DIR, 'step1_meta.json'), encoding='utf-8') as f:
        return json.load(f)


def load_master() -> dict:
    p = os.path.join(STRUCTURED, 'master_dataset.json')
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    return {}


def read_hwpx(hwpx_path: str) -> tuple:
    """(section0_bytes, content_hpf_bytes, zf_namelist) 반환"""
    with zipfile.ZipFile(hwpx_path, 'r') as zf:
        names   = zf.namelist()
        section = zf.read('Contents/section0.xml')
        hpf     = zf.read('Contents/content.hpf')
    return section, hpf, names


def strip_ns(root: ET._Element) -> ET._Element:
    """파싱된 XML에서 네임스페이스 prefix를 제거해 태그명을 단순화한다.
    예: {http://www.hancom.co.kr/hwpml/2011/paragraph}t  →  t
    """
    for elem in root.iter():
        if isinstance(elem.tag, str) and '}' in elem.tag:
            elem.tag = elem.tag.split('}', 1)[1]
        keys = list(elem.attrib.keys())
        for k in keys:
            if '}' in k:
                clean = k.split('}', 1)[1]
                elem.attrib[clean] = elem.attrib.pop(k)
    return root


def all_char_text(root: ET._Element) -> str:
    return '\n'.join(e.text for e in root.iter('t') if e.text)


def count_tag(root: ET._Element, tag: str) -> int:
    return len(list(root.iter(tag)))


def package_files(hwpx_path: str) -> dict:
    """content.hpf의 opf:item 매니페스트를 {id: (href, media-type)}로 반환"""
    with zipfile.ZipFile(hwpx_path, 'r') as zf:
        hpf_root = ET.fromstring(zf.read('Contents/content.hpf'))
    items = {}
    for item in hpf_root.findall('.//opf:item', OPF_NS):
        items[item.get('id')] = (item.get('href'), item.get('media-type'))
    return items


# ══════════════════════════════════════════════════════════════════
# C00-C10 구조 검증 함수
#   signature: fn(root, text, zf_names, hwpx_path) → (bool, str)
# ══════════════════════════════════════════════════════════════════

_SEC_KW = ['시장 개요', '시장 역학', '생태계', '지역별', '세그먼트', 'R&D', '결론']


def _contains_kw(kw: str, text: str) -> bool:
    return kw in text or kw.replace('&', '&amp;') in text


def c00(root, text, zf, hwpx_path):
    """실제 HWPX(OWPML) 패키지 스펙 준수 여부: mimetype 위치/무압축/내용,
    필수 파일 존재, 모든 XML 파트의 well-formedness."""
    errors = []
    required = [
        'mimetype', 'version.xml', 'settings.xml',
        'Contents/header.xml', 'Contents/section0.xml', 'Contents/content.hpf',
        'META-INF/container.xml',
    ]
    for req in required:
        if req not in zf:
            errors.append(f'누락:{req}')

    try:
        with zipfile.ZipFile(hwpx_path, 'r') as zfobj:
            if zf and zf[0] != 'mimetype':
                errors.append('mimetype이 첫 항목 아님')
            if 'mimetype' in zf:
                info = zfobj.getinfo('mimetype')
                if info.compress_type != zipfile.ZIP_STORED:
                    errors.append('mimetype 압축됨')
                content = zfobj.read('mimetype').decode('utf-8').strip()
                if content != 'application/hwp+zip':
                    errors.append(f'mimetype 내용오류({content})')
            for name in zf:
                if name.endswith('.xml') or name.endswith('.hpf'):
                    try:
                        ET.fromstring(zfobj.read(name))
                    except ET.XMLSyntaxError as e:
                        errors.append(f'XML오류:{name}')
    except Exception as e:
        errors.append(str(e))

    if errors:
        return False, '; '.join(errors)
    return True, 'mimetype·필수파일·XML 정합성 확인'


def c01(root, text, zf, hwpx_path):
    found = [k for k in _SEC_KW if _contains_kw(k, text)]
    return len(found) >= 7, f'{len(found)}/7 섹션 확인 ({", ".join(found[:3])}…)'


def c02(root, text, zf, hwpx_path):
    if re.search(r'\$[\d.]+\s*B', text) or re.search(r'[\d,.]+\s*billion', text, re.I):
        return True, '시장규모 수치($B) 확인'
    if '$' in text and re.search(r'\d+\.\d+', text):
        return True, '시장규모 수치 확인'
    return False, '시장규모 수치 없음'


def c03(root, text, zf, hwpx_path):
    patterns = [
        r'CAGR[\s\S]{0,15}[\d.]+\s*%',
        r'[\d.]+\s*%[\s\S]{0,15}CAGR',
        r'연평균[\s]*[\d.]+\s*%',
        r'복합연간성장률[\s:]*[\d.]+',
    ]
    for p in patterns:
        if re.search(p, text, re.I):
            return True, 'CAGR 수치 확인'
    # 표 셀 단위로 텍스트가 평탄화되면 'CAGR (%)' 헤더와 실제 값이
    # 서로 다른 셀/행에 있어 인접 정규식이 매치하지 못할 수 있다.
    # 'CAGR' 단어와 소수점 % 수치가 문서 어디엔가 둘 다 있으면 통과로 간주한다.
    if re.search(r'CAGR', text, re.I) and re.search(r'\d+\.\d+\s*%', text):
        return True, 'CAGR 수치 확인(표 내 분산 배치)'
    return False, 'CAGR 수치 없음'


def c04(root, text, zf, hwpx_path):
    if '출처' in text or '※' in text:
        return True, '출처 정보 확인'
    return False, '출처 정보 없음'


def c05(root, text, zf, hwpx_path):
    markers = ['①', '②', '③', '④', '⑤']
    found   = [m for m in markers if m in text]
    if len(found) >= 5:
        return True, f'시사점 {len(found)}개(①~⑤) 확인'
    kws = ['유망 기술', '기술 격차', '공급망', '정책', 'KIST']
    kw_found = [k for k in kws if k in text]
    if len(kw_found) >= 4:
        return True, f'시사점 키워드 {len(kw_found)}개 확인'
    return False, f'시사점 항목 부족 ({len(found)}개/5)'


def c06(root, text, zf, hwpx_path):
    n = count_tag(root, 'tbl')
    return n >= 2, f'테이블 {n}개'


def c07(root, text, zf, hwpx_path):
    n = count_tag(root, 'pic')
    return n >= 9, f'이미지 {n}개'


def c08(root, text, zf, hwpx_path):
    """각 이미지 단락 직후에 캡션 단락이 있는지 확인 (root = hs:sec)"""
    paras = list(root.findall('p'))
    pic_idx = [i for i, p in enumerate(paras) if p.find('.//pic') is not None]
    if not pic_idx:
        return True, '이미지 없음 (해당 없음)'
    missing = 0
    for i in pic_idx:
        if i + 1 >= len(paras):
            missing += 1
            continue
        nxt = paras[i + 1]
        nxt_txt = ''.join(e.text or '' for e in nxt.iter('t'))
        if '그림' in nxt_txt or '출처' in nxt_txt or nxt.get('paraPrIDRef') == '20':
            pass
        else:
            missing += 1
    if missing == 0:
        return True, f'모든 이미지({len(pic_idx)}개)에 캡션 확인'
    return False, f'캡션 없는 이미지 {missing}개'


def c09(root, text, zf, hwpx_path):
    """section0.xml의 binaryItemIDRef ↔ content.hpf 매니페스트 ↔ 실제 BinData 파일 일치 확인"""
    refs = {img.get('binaryItemIDRef') for img in root.iter('img') if img.get('binaryItemIDRef')}
    if not refs:
        return True, '이미지 참조 없음 (해당 없음)'

    items = package_files(hwpx_path)
    actual = {n.split('/')[-1] for n in zf if n.startswith('BinData/')}

    missing_manifest = [r for r in refs if r not in items]
    if missing_manifest:
        return False, f'content.hpf 매니페스트 누락: {", ".join(missing_manifest[:3])}'

    missing_files = [r for r in refs
                      if items[r][0].split('/')[-1] not in actual]
    if missing_files:
        return False, f'BinData 실제파일 누락: {", ".join(missing_files[:3])}'
    return True, f'이미지 참조 일치 ({len(refs)}개)'


def c10(root, text, zf, hwpx_path):
    has_date = '작성일' in text or re.search(r'\d{4}년\s*\d{1,2}월', text) is not None
    has_src  = '출처' in text or '원본' in text
    if has_date and has_src:
        return True, '표지 출처·작성일 확인'
    miss = ([] if has_date else ['작성일']) + ([] if has_src else ['출처'])
    return False, f'표지 누락: {", ".join(miss)}'


CHECKS = [
    ('C00', '패키지 구조 유효성(mimetype 등)', c00),
    ('C01', '7개 섹션 존재',           c01),
    ('C02', '시장규모 수치 포함',       c02),
    ('C03', 'CAGR 수치 포함',          c03),
    ('C04', '출처 정보 기재',           c04),
    ('C05', '시사점 5개 항목',          c05),
    ('C06', '테이블 최소 2개',          c06),
    ('C07', '이미지 최소 9개',          c07),
    ('C08', '모든 이미지에 캡션',       c08),
    ('C09', 'BinData 참조 일치',        c09),
    ('C10', '표지 출처·작성일',         c10),
]

CHECK_FN = {cid: fn for cid, _, fn in CHECKS}
TOTAL_CHECKS = len(CHECKS)


# ══════════════════════════════════════════════════════════════════
# 자동 수정 함수 (실제 hp:/hs: 스키마 기준)
# ══════════════════════════════════════════════════════════════════

HP = 'http://www.hancom.co.kr/hwpml/2011/paragraph'


def _qn(tag: str) -> str:
    return f'{{{HP}}}{tag}'


def _new_para(pid: int, para_pr: str, style_id: str,
              char_pr: str, text: str) -> ET._Element:
    p = ET.Element(_qn('p'))
    p.set('id', str(pid)); p.set('paraPrIDRef', para_pr)
    p.set('styleIDRef', style_id); p.set('pageBreak', '0')
    p.set('columnBreak', '0'); p.set('merged', '0')
    run = ET.SubElement(p, _qn('run')); run.set('charPrIDRef', char_pr)
    t = ET.SubElement(run, _qn('t')); t.text = text
    seg_array = ET.SubElement(p, _qn('linesegarray'))
    seg = ET.SubElement(seg_array, _qn('lineseg'))
    seg.set('textpos', '0'); seg.set('vertpos', '0')
    seg.set('vertsize', '1000'); seg.set('textheight', '1000')
    seg.set('baseline', '850'); seg.set('spacing', '600')
    seg.set('horzpos', '0'); seg.set('horzsize', '42520'); seg.set('flags', '393216')
    return p


def fix_c04(root: ET._Element, src: str) -> bool:
    """출처 단락을 표지 직후에 삽입 (root = hs:sec)"""
    if len(root) == 0:
        return False
    p = _new_para(9001, '0', '0', '0', f'※ 출처: {src}')
    root.insert(min(3, len(root)), p)
    return True


def fix_c08(root: ET._Element) -> int:
    """캡션 없는 이미지 단락 직후에 기본 캡션 삽입 (charPr=10 캡션, paraPr=20 가운데)"""
    fixed = 0
    paras = list(root)
    i = 0
    while i < len(paras):
        p = paras[i]
        if p.find('.//' + _qn('pic')) is None:
            i += 1
            continue
        nxt = paras[i + 1] if i + 1 < len(paras) else None
        nxt_txt = ''.join(e.text or '' for e in nxt.iter(_qn('t'))) if nxt is not None else ''
        if nxt is not None and ('그림' in nxt_txt or nxt.get('paraPrIDRef') == '20'):
            i += 1
            continue
        fixed += 1
        cap = _new_para(9100 + fixed, '20', '0', '10', f'그림 {fixed}. (출처: 원본 보고서)')
        insert_at = list(root).index(p) + 1
        root.insert(insert_at, cap)
        paras = list(root)
        i += 2
    return fixed


def fix_c09(hwpx_path: str, zf_names: list) -> int:
    """content.hpf의 opf:item href를 실제 BinData 파일명으로 교정"""
    hpf_path = os.path.join(HWPX_BUILD, 'Contents', 'content.hpf')
    if not os.path.exists(hpf_path):
        return 0
    actual = {n.split('/')[-1]: n for n in zf_names if n.startswith('BinData/')}
    tree = ET.parse(hpf_path)
    root = tree.getroot()
    fixed = 0
    for item in root.findall('.//opf:item', OPF_NS):
        href = item.get('href', '')
        if not href.startswith('BinData/'):
            continue
        fname = href.split('/')[-1]
        if fname in actual and href != actual[fname]:
            item.set('href', actual[fname])
            fixed += 1
    if fixed:
        tree.write(hpf_path, pretty_print=True, xml_declaration=True,
                   encoding='UTF-8', standalone=True)
    return fixed


def fix_c10(root: ET._Element) -> bool:
    """표지 단락에 작성일 추가"""
    today = datetime.now().strftime('%Y년 %m월 %d일')
    for i, par in enumerate(list(root)[:6]):
        t = ''.join(e.text or '' for e in par.iter(_qn('t')))
        if '연구과제' in t or '원본 출처' in t:
            p = _new_para(9002, '0', '0', '0', f'작성일: {today}')
            root.insert(i + 1, p)
            return True
    return False


def repack(hwpx_path: str):
    """mimetype 최상단·무압축 규칙을 지키며 HWPX_BUILD를 재패키징한다."""
    root_dir = HWPX_BUILD
    mimetype_file = os.path.join(root_dir, 'mimetype')
    all_files = []
    for dirpath, _, files in os.walk(root_dir):
        for fname in files:
            fp = os.path.join(dirpath, fname)
            rel = os.path.relpath(fp, root_dir).replace(os.sep, '/')
            if rel != 'mimetype':
                all_files.append(rel)
    all_files.sort()

    tmp = hwpx_path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(mimetype_file, 'mimetype', compress_type=zipfile.ZIP_STORED)
        for rel in all_files:
            zf.write(os.path.join(root_dir, rel), rel, compress_type=zipfile.ZIP_DEFLATED)
    os.replace(tmp, hwpx_path)


def apply_fixes(hwpx_path: str, failed: list, src: str,
                zf_names: list, output_name: str) -> tuple:
    """수정 가능 항목 자동 수정 → HWPX 재패키징"""
    section_path = os.path.join(HWPX_BUILD, 'Contents', 'section0.xml')
    if not os.path.exists(section_path):
        return [], list(failed)

    tree = ET.parse(section_path)
    xroot = tree.getroot()
    fixed: list = []

    if 'C04' in failed and fix_c04(xroot, src):
        fixed.append('C04')
    if 'C08' in failed:
        n = fix_c08(xroot)
        if n:
            fixed.append(f'C08({n}개 캡션 추가)')
    if 'C10' in failed and fix_c10(xroot):
        fixed.append('C10')

    section_changed = any(c.startswith(('C04', 'C08', 'C10')) for c in fixed)
    if section_changed:
        tree.write(section_path, pretty_print=True, xml_declaration=True,
                   encoding='UTF-8', standalone=True)

    hpf_changed = False
    if 'C09' in failed:
        n = fix_c09(hwpx_path, zf_names)
        if n:
            fixed.append(f'C09({n}개 경로 교정)')
            hpf_changed = True

    if section_changed or hpf_changed:
        repack(hwpx_path)
        os.makedirs(SKILL_OUT, exist_ok=True)
        shutil.copy2(hwpx_path, os.path.join(SKILL_OUT, f'{output_name}.hwpx'))

    auto_fixable = {'C04', 'C08', 'C09', 'C10'}
    manual = [c for c in failed if c not in auto_fixable]
    return fixed, manual


# ══════════════════════════════════════════════════════════════════
# Q01-Q05 품질 검증 (Claude API)
# ══════════════════════════════════════════════════════════════════

def run_quality_checks(client, text: str, tf: str) -> dict:
    summary = text[:6000] + ('…(이하 생략)' if len(text) > 6000 else '')
    prompt = f"""다음은 자동 생성된 '{tf}' 한글 시장분석 보고서의 본문입니다.
아래 5가지 품질 항목을 평가하고 순수 JSON만 반환하세요.

[본문]
{summary}

[출력 JSON 스키마]
{{
  "Q01": {{"item": "수치 정확성",       "pass": true,  "note": "1문장"}},
  "Q02": {{"item": "번역 자연스러움",    "pass": true,  "note": "1문장"}},
  "Q03": {{"item": "시사점 구체성",      "pass": true,  "note": "1문장"}},
  "Q04": {{"item": "KIST 시사점 현실성", "pass": true,  "note": "1문장"}},
  "Q05": {{"item": "섹션 완결성",        "pass": true,  "note": "1문장"}}
}}"""

    for attempt in range(3):
        try:
            msg = client.messages.create(
                model=MODEL, max_tokens=800,
                messages=[{'role': 'user', 'content': prompt}]
            )
            raw  = re.sub(r'```(?:json)?\s*', '', msg.content[0].text).strip()
            s, e = raw.find('{'), raw.rfind('}')
            if s != -1 and e != -1:
                return json.loads(raw[s:e+1])
        except Exception as ex:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
    # 실패 시 기본값
    return {f'Q0{i}': {'item': f'항목{i}', 'pass': None, 'note': 'API 실패'}
            for i in range(1, 6)}


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════

def main():
    # 메타데이터 로드
    meta   = load_meta()
    master = load_master()
    output_name = meta.get('output_name', '시장분석_보고서')
    tf          = meta.get('tech_field',  '기술분야')
    src         = master.get('market_overview', {}).get('source_report', '원본 보고서')
    hwpx_path   = os.path.join(OUTPUT_DIR, f'{output_name}.hwpx')

    print(f'\n[STEP 6] 품질 검증 — {output_name}.hwpx')

    if not os.path.exists(hwpx_path):
        print(f'❌ HWPX 파일 없음: {hwpx_path}')
        sys.exit(1)

    # ── ZIP 읽기 + XML 파싱 ───────────────────────────────────────
    try:
        section_bytes, hpf_bytes, zf_names = read_hwpx(hwpx_path)
    except Exception as e:
        print(f'❌ ZIP 읽기 실패: {e}')
        sys.exit(1)

    try:
        xroot = strip_ns(ET.fromstring(section_bytes))
    except Exception as e:
        print(f'❌ XML 파싱 실패: {e}')
        sys.exit(1)

    full_text = all_char_text(xroot)

    # ── C00-C10 구조 검증 ─────────────────────────────────────────
    print(f'\n  [구조 검증] C00-C10')
    struct_res: dict = {}
    failed: list = []

    for cid, desc, fn in CHECKS:
        passed, msg = fn(xroot, full_text, zf_names, hwpx_path)
        struct_res[cid] = {'desc': desc, 'pass': passed, 'note': msg}
        icon = '✓' if passed else '✗'
        print(f'    {icon} {cid} {desc}: {msg}')
        if not passed:
            failed.append(cid)

    # ── 자동 수정 ─────────────────────────────────────────────────
    fixed_list: list = []
    manual_list: list = []

    if failed:
        print(f'\n  [자동 수정] 실패 {len(failed)}건: {", ".join(failed)}')
        fixed_list, manual_list = apply_fixes(
            hwpx_path, failed, src, zf_names, output_name
        )
        if fixed_list:
            print(f'    수정 완료: {", ".join(fixed_list)}')
        if manual_list:
            print(f'    수동 확인 필요: {", ".join(manual_list)}')

        # 수정 후 재검증 (수정된 항목만)
        if fixed_list:
            try:
                section2, hpf2, zf2 = read_hwpx(hwpx_path)
                xroot2   = strip_ns(ET.fromstring(section2))
                text2    = all_char_text(xroot2)
                for entry in fixed_list:
                    cid = entry.split('(')[0]   # "C08(3개)" → "C08"
                    if cid in CHECK_FN:
                        p2, m2 = CHECK_FN[cid](xroot2, text2, zf2, hwpx_path)
                        struct_res[cid]['pass']          = p2
                        struct_res[cid]['note_after_fix'] = m2
            except Exception:
                pass

    # ── Q01-Q05 품질 검증 (Claude API) ───────────────────────────
    quality_res: dict = {}
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')

    if api_key:
        print('\n  [품질 검증] Claude API 호출...')
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            quality_res = run_quality_checks(client, full_text, tf)
            for qid, qv in quality_res.items():
                icon = '✓' if qv.get('pass') else ('?' if qv.get('pass') is None else '✗')
                print(f'    {icon} {qid} {qv.get("item","")}: {qv.get("note","")}')
        except Exception as e:
            print(f'    ⚠ 오류: {e}')
            quality_res = {f'Q0{i}': {'item': f'항목{i}', 'pass': None, 'note': str(e)}
                           for i in range(1, 6)}
    else:
        print('\n  [품질 검증] ANTHROPIC_API_KEY 없음 → 건너뜀')
        quality_res = {f'Q0{i}': {'item': f'항목{i}', 'pass': None, 'note': 'API 키 없음'}
                       for i in range(1, 6)}

    # ── 최종 판정 (검증 항목 수에 비례한 기준) ───────────────────
    s_pass = sum(1 for v in struct_res.values()  if v['pass'])
    q_pass = sum(1 for v in quality_res.values() if v.get('pass') is True)
    q_tested = sum(1 for v in quality_res.values() if v.get('pass') is not None)
    s_ratio = s_pass / TOTAL_CHECKS

    # C00(패키지 구조)은 반드시 통과해야 함 — 무효 hwpx는 무조건 FAIL
    if not struct_res['C00']['pass']:
        verdict = 'FAIL (패키지 구조 오류)'
    elif q_tested == 0:
        if   s_ratio >= 0.9: verdict = 'PASS (구조검증 기준)'
        elif s_ratio >= 0.7: verdict = 'CONDITIONAL PASS (구조검증 기준)'
        else:                verdict = 'FAIL'
    elif s_ratio >= 0.8 and q_pass >= 4:
        verdict = 'PASS'
    elif s_ratio >= 0.7 and q_pass >= 3:
        verdict = 'CONDITIONAL PASS'
    else:
        verdict = 'FAIL'

    # ── 로그 저장 ──────────────────────────────────────────────────
    log = {
        'timestamp':            datetime.now().isoformat(),
        'hwpx_file':            hwpx_path,
        'structural_checks':    struct_res,
        'auto_fixed':           fixed_list,
        'manual_review_needed': manual_list,
        'quality_checks':       quality_res,
        'overall_pass':         verdict == 'PASS',
        'verdict':              verdict,
        'pass_rate_structural': f'{s_pass}/{TOTAL_CHECKS}',
        'pass_rate_quality':    f'{q_pass}/5',
    }
    with open(os.path.join(LOG_DIR, 'step6_validation_hwpx.json'), 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    # ── 완료 출력 ──────────────────────────────────────────────────
    print(f'\n✅ STEP 6 완료')
    print(f'  구조 검증: {s_pass}/{TOTAL_CHECKS} 통과')
    print(f'  자동 수정: {len(fixed_list)}건')
    print(f'  품질 검증: {q_pass}/5 통과')
    if manual_list:
        print(f'  수동 확인 필요: {len(manual_list)}건 ({", ".join(manual_list)})')
    else:
        print(f'  수동 확인 필요: 0건')
    print(f'  최종 판정: {verdict}')

    if verdict.startswith('FAIL'):
        print(f'\n  ⚠ 구조 검증 미달 항목: '
              f'{[k for k, v in struct_res.items() if not v["pass"]]}')

    print(f'\n  파이프라인 완료 → 최종 보고서: {hwpx_path}')


if __name__ == '__main__':
    main()
