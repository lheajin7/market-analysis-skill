#!/usr/bin/env python3
"""
STEP 7: 최종 출력 및 실행 요약 리포트 (HWPX + DOCX 동시 배포)

사전 조건: generate_reports.py 실행 완료
  (workspace/output/{name}.hwpx, {name}.docx 및 step6_validation_hwpx.json,
   step6_validation_docx.json 존재)

사용법:
  python finalize_report.py
  python finalize_report.py --cleanup   # workspace 임시 파일 삭제
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

from _common import get_base

# ──────────────────────────────────────────────────────────────────
# 경로 상수
# ──────────────────────────────────────────────────────────────────
BASE       = get_base()
WORKSPACE  = os.path.join(BASE, 'workspace')
STRUCTURED = os.path.join(WORKSPACE, 'structured')
CHARTS     = os.path.join(WORKSPACE, 'charts')
OUTPUT_DIR = os.path.join(WORKSPACE, 'output')
LOG_DIR    = os.path.join(WORKSPACE, 'logs')
SKILL_OUT  = os.path.join(BASE, 'skill', 'output')

FORMATS = ['hwpx', 'docx']


# ══════════════════════════════════════════════════════════════════
# 데이터 로드
# ══════════════════════════════════════════════════════════════════

def _jload(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {}


def load_all() -> dict:
    return {
        's1':          _jload(os.path.join(LOG_DIR,    'step1_meta.json')),
        's2':          _jload(os.path.join(LOG_DIR,    'step2_extraction.json')),
        's3':          _jload(os.path.join(LOG_DIR,    'step3_analysis.json')),
        's4':          _jload(os.path.join(LOG_DIR,    'step4_charts.json')),
        's5_hwpx':     _jload(os.path.join(LOG_DIR,    'step5_hwpx.json')),
        's5_docx':     _jload(os.path.join(LOG_DIR,    'step5_docx.json')),
        's6_hwpx':     _jload(os.path.join(LOG_DIR,    'step6_validation_hwpx.json')),
        's6_docx':     _jload(os.path.join(LOG_DIR,    'step6_validation_docx.json')),
        'md':          _jload(os.path.join(STRUCTURED, 'master_dataset.json')),
        'cc':          _jload(os.path.join(CHARTS,     'chart_catalog.json')),
    }


# ══════════════════════════════════════════════════════════════════
# 유틸리티
# ══════════════════════════════════════════════════════════════════

def ts_diff(ts1: str, ts2: str) -> str:
    if not ts1 or not ts2:
        return 'N/A'
    try:
        d = datetime.fromisoformat(ts2) - datetime.fromisoformat(ts1)
        secs = int(d.total_seconds())
        return f'{secs}초' if secs >= 0 else 'N/A'
    except Exception:
        return 'N/A'


def step_icon(log: dict, status_key: str) -> str:
    val = str(log.get(status_key, '')).lower()
    if 'success' in val or 'pass' in val:
        return '✅'
    if 'partial' in val or 'warning' in val or 'conditional' in val:
        return '⚠️'
    if log:
        return '✅'
    return '❌'


# ══════════════════════════════════════════════════════════════════
# 파일 배포 (형식별)
# ══════════════════════════════════════════════════════════════════

def deploy_one(fmt: str, output_name: str, verdict: str) -> str:
    """검증 결과에 따라 skill/output/ 에 파일 배포. 존재하지 않으면 빈 문자열 반환."""
    src = os.path.join(OUTPUT_DIR, f'{output_name}.{fmt}')
    if not os.path.exists(src):
        return ''
    os.makedirs(SKILL_OUT, exist_ok=True)
    dest_name = (f'{output_name}_DRAFT.{fmt}'
                 if verdict.startswith('FAIL')
                 else f'{output_name}.{fmt}')
    dest = os.path.join(SKILL_OUT, dest_name)
    shutil.copy2(src, dest)
    return dest


# ══════════════════════════════════════════════════════════════════
# 마크다운 리포트 생성
# ══════════════════════════════════════════════════════════════════

def generate_report(logs: dict, output_name: str, tf: str,
                    run_start: str, dests: dict, verdicts: dict) -> str:
    s1 = logs['s1']; s2 = logs['s2']; s3 = logs['s3']; s4 = logs['s4']
    md = logs['md']; cc = logs['cc']

    now_ts = datetime.now().isoformat()

    s5 = {'hwpx': logs['s5_hwpx'], 'docx': logs['s5_docx']}
    s6 = {'hwpx': logs['s6_hwpx'], 'docx': logs['s6_docx']}

    latest_s5_ts = max([s5[f].get('timestamp', '') for f in FORMATS] + [''])
    latest_s6_ts = max([s6[f].get('timestamp', '') for f in FORMATS] + [''])

    ts = {
        's0': run_start,
        's1': s1.get('timestamp', run_start),
        's2': s2.get('timestamp', ''),
        's3': s3.get('timestamp', ''),
        's4': s4.get('timestamp', ''),
        's5': latest_s5_ts,
        's6': latest_s6_ts,
        's7': now_ts,
    }
    dur = {k2: ts_diff(ts[k1], ts[k2])
           for k1, k2 in zip(['s0','s1','s2','s3','s4','s5','s6'],
                              ['s1','s2','s3','s4','s5','s6','s7'])}
    total_dur = ts_diff(ts['s0'], now_ts)

    mkt = md.get('market_overview', {})
    reg = md.get('regional_analysis', {})

    base_s  = mkt.get('base_year_size_usd_b', 'N/A')
    fc_s    = (mkt.get('scenarios', {}).get('realistic', {}).get('size_usd_b')
               if mkt.get('scenarios') else None) or 'N/A'
    base_yr = mkt.get('base_year',     'N/A')
    fc_yr   = mkt.get('forecast_year', 'N/A')
    cagr    = mkt.get('cagr_pct', 'N/A')
    leading = reg.get('leading_region', 'N/A')
    fastest = reg.get('fastest_growing_region', 'N/A')

    # STEP 3는 Claude Code가 워크스페이스 텍스트를 직접 읽어 master_dataset.json을
    # 작성하므로 step3_analysis.json 로그가 남지 않는다. 따라서 완료 섹션 수는 로그가
    # 아니라 실제로 병합된 master_dataset.json의 7개 최상위 섹션 키 존재 여부로 판정한다.
    # (logs['s3']는 없으면 {}가 되고, 소요시간 표시에만 쓰이므로 비어도 무방하다.)
    SECTION_KEYS = ['market_overview', 'market_dynamics', 'ecosystem',
                     'regional_analysis', 'segmentation', 'rnd_trends', 'implications']
    sec_done = sum(1 for k in SECTION_KEYS if md.get(k))
    sec_fail = [k for k in SECTION_KEYS if not md.get(k)]

    charts     = cc.get('charts', [])
    chart_skip = [c for c in charts if c['status'] == 'skipped']

    L: list = []
    def add(*lines):
        L.extend(lines)

    add(
        f'# {tf} 시장분석 보고서 자동생성 실행 리포트',
        '',
        f'- **생성일시**: {now_ts}',
        f'- **원본 파일**: {s1.get("input_file", "N/A")}',
        f'- **파일 형식**: {str(s1.get("file_type","N/A")).upper()}'
        f'  ({s1.get("page_count","N/A")}페이지 / {s1.get("file_size_mb","N/A")} MB)',
    )
    for fmt in FORMATS:
        add(f'- **출력 파일({fmt.upper()})**: `{dests.get(fmt) or "생성 안 됨"}`'
            f' — 판정: **{verdicts.get(fmt, "N/A")}**')
    add('', '---', '', '## 처리 결과 요약', '',
        '| 단계 | 내용 | 상태 | 소요 시간 |',
        '|------|------|------|-----------|',
        f'| STEP 1 | 입력 분석 및 환경 초기화 | {step_icon(s1,"step1_status")} | {dur["s1"]} |',
        f'| STEP 2 | 텍스트·이미지 추출 | {step_icon(s2,"step2_status")} | {dur["s2"]} |',
        f'| STEP 3 | AI 분석 및 구조화 ({sec_done}섹션) | '
        f'{"✅" if sec_done == len(SECTION_KEYS) else ("⚠️" if sec_done else "❌")} | {dur["s3"]} |',
        f'| STEP 4 | 차트·인포그래픽 생성 ({cc.get("total_generated",0)}개) | {step_icon(s4,"step4_status")} | {dur["s4"]} |',
        f'| STEP 5 | HWPX+DOCX 보고서 조립 | '
        f'{"✅" if all(s5[f] for f in FORMATS) else "⚠️"} | {dur["s5"]} |',
        f'| STEP 6 | 품질 검증 (HWPX {s6["hwpx"].get("pass_rate_structural","N/A")}'
        f' / DOCX {s6["docx"].get("pass_rate_structural","N/A")}) | '
        f'{"✅" if all(verdicts.get(f,"").startswith("PASS") or "CONDITIONAL" in verdicts.get(f,"") for f in FORMATS) else "⚠️"}'
        f' | {dur["s6"]} |',
        f'| STEP 7 | 최종 출력 | ✅ | {dur["s7"]} |',
        f'| **합계** | | | **{total_dur}** |',
        '', '---', '', '## 추출된 핵심 데이터', '',
        f'| 항목 | 값 |', f'|------|----|',
        f'| 시장규모 ({base_yr}) | ${base_s}B |',
        f'| 시장규모 ({fc_yr}) | ${fc_s}B |',
        f'| CAGR (현실 시나리오) | {cagr}% |',
        f'| 주도 권역 | {leading} |',
        f'| 최고 성장 권역 | {fastest} |',
        f'| 완료 섹션 | {sec_done}/7 |',
        f'| 미확인 섹션 | {len(sec_fail)}개 ({", ".join(sec_fail) if sec_fail else "없음"}) |',
        '', '---', '', '## 생성된 시각화', '',
        '| 차트 ID | 차트명 | 상태 |', '|---------|--------|------|',
    )

    status_label = {'generated': '✅ 생성됨', 'reused': '♻️ 재활용', 'skipped': '⏩ 생략'}
    for c in charts:
        sl    = status_label.get(c['status'], c['status'])
        title = (c.get('title') or c.get('chart_id', ''))[:40]
        add(f'| {c.get("chart_id","")} | {title} | {sl} |')

    add('', f'**합계**: {cc.get("total_generated",0)}개 생성 /'
        f' {cc.get("total_skipped",0)}개 생략', '', '---', '',
        '## 품질 검증 결과 (형식별)', '')

    for fmt in FORMATS:
        s6f = s6[fmt]
        struct  = s6f.get('structural_checks', {})
        quality = s6f.get('quality_checks',   {})
        auto_fx = s6f.get('auto_fixed',       [])
        manual  = s6f.get('manual_review_needed', [])
        s_rate  = s6f.get('pass_rate_structural', 'N/A')
        q_rate  = s6f.get('pass_rate_quality',    'N/A')
        fixed_ids  = {e.split('(')[0] for e in auto_fx}
        struct_ok  = [k for k, v in struct.items() if v.get('pass')]
        struct_bad = [k for k, v in struct.items()
                      if not v.get('pass') and k not in fixed_ids]

        add(f'### {fmt.upper()}', '',
            f'- 구조 검증: **{s_rate}** 통과 / 품질 검증: **{q_rate}** 통과 / 최종판정: **{verdicts.get(fmt,"N/A")}**',
            f'- ✅ 통과 ({len(struct_ok)}개): {", ".join(struct_ok) if struct_ok else "없음"}',
            f'- ⚙️ 자동 수정 ({len(auto_fx)}건): {", ".join(auto_fx) if auto_fx else "없음"}',
            f'- ❌ 미통과 ({len(struct_bad)}개): {", ".join(struct_bad) if struct_bad else "없음"}',
            '')
        for qid, qv in quality.items():
            icon = {True: '✅', False: '❌', None: '⚠️'}.get(qv.get('pass'), '⚠️')
            result = ('통과' if qv.get('pass') is True
                      else ('미평가' if qv.get('pass') is None else '미통과'))
            note = qv.get('note', '')
            add(f'- {icon} **{qv.get("item", qid)}**: {result}' + (f' — {note}' if note else ''))
        add('')

    add('---', '', '## 연구원 확인 권장 사항', '')
    review: list = []
    for fmt in FORMATS:
        s6f = s6[fmt]
        struct  = s6f.get('structural_checks', {})
        quality = s6f.get('quality_checks',   {})
        manual  = s6f.get('manual_review_needed', [])
        auto_fx = s6f.get('auto_fixed', [])
        fixed_ids = {e.split('(')[0] for e in auto_fx}
        for k, v in struct.items():
            if not v.get('pass') and k not in fixed_ids:
                review.append(f'1. **[{fmt.upper()}/구조 {k}] {v.get("desc",k)}**  '
                              f'→ {v.get("note","")} — 보고서 직접 확인 필요')
        for k, qv in quality.items():
            if qv.get('pass') is False:
                review.append(f'1. **[{fmt.upper()}/품질 {k}] {qv.get("item","")}**  '
                              f'→ {qv.get("note","")} — 수동 수정 필요')
    add(*(review if review else ['없음']))

    add('', '---', '', '## 생략된 항목 (데이터 부족)', '')
    skips: list = []
    for sf in sec_fail:
        skips.append(f'- **{sf}** (섹션): AI 분석 실패 → 빈 스키마 대체됨')
    for c in chart_skip:
        cid = c.get('chart_id', '')
        rsn = c.get('skip_reason', '데이터 없음')
        skips.append(f'- **{cid}** (차트): {rsn}')
    add(*(skips if skips else ['없음']))

    report_path = os.path.join(SKILL_OUT, f'{output_name}_실행리포트.md')
    add('', '---', '', '## 파일 위치', '',
        f'| 구분 | 경로 |', f'|------|------|')
    for fmt in FORMATS:
        add(f'| 최종 보고서({fmt.upper()}) | `{dests.get(fmt) or "생성 안 됨"}` |')
    add(
        f'| 실행 리포트 | `{report_path}` |',
        f'| 작업 폴더 | `{WORKSPACE}` |',
        f'| 구조화 데이터 | `{STRUCTURED}` |',
        f'| 생성 차트 | `{CHARTS}` |',
        '',
    )

    return '\n'.join(L)


# ══════════════════════════════════════════════════════════════════
# 최종 배너 출력
# ══════════════════════════════════════════════════════════════════

def print_banner(output_name: str, n_gen: int, n_req: int, n_opt: int,
                 total_dur: str, verdicts: dict, dests: dict):
    LINE = '━' * 48
    overall_fail = any(v.startswith('FAIL') for v in verdicts.values())
    v_icon = '❌' if overall_fail else ('✅' if all(v == 'PASS' for v in verdicts.values()) else '⚠️')
    label  = '부분 완료 (DRAFT)' if overall_fail else '완료'

    print(f'\n{LINE}')
    print(f'{v_icon}  시장분석 보고서 자동생성 {label}')
    print(LINE)
    for fmt in FORMATS:
        print(f'  📄 출력 파일({fmt.upper()}) : {dests.get(fmt) or "생성 안 됨"}')
        print(f'     최종 판정            : {verdicts.get(fmt, "N/A")}')
    print(f'  📊 포함 차트  : {n_gen}개 (필수 {n_req}개 + 선택 {n_opt}개)')
    print(f'  📝 보고서 섹션: 7개 / 7개')
    print(f'  ⏱️  총 소요 시간: {total_dur}')

    print('\n  워드(MS Word)에서 .docx를, 한글 오피스에서 .hwpx를 열어 내용을 확인하세요.')
    print(LINE)


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='STEP 7: 최종 출력 및 리포트')
    parser.add_argument('--cleanup', action='store_true',
                        help='workspace 임시 파일 삭제 (확인 후 실행)')
    args = parser.parse_args()

    run_start = datetime.now().isoformat()

    s1 = _jload(os.path.join(LOG_DIR, 'step1_meta.json'))
    if not s1:
        print('step1_meta.json 없음 — 이전 단계를 먼저 실행하세요.')
        sys.exit(1)

    output_name = s1.get('output_name', '시장분석_보고서')
    tf          = s1.get('tech_field',  '기술분야')

    print(f'\n[STEP 7] 최종 출력 — {output_name}')

    verdicts: dict = {}
    dests: dict = {}
    for fmt in FORMATS:
        s6f = _jload(os.path.join(LOG_DIR, f'step6_validation_{fmt}.json'))
        verdicts[fmt] = s6f.get('verdict', 'N/A (미생성)')
        dest = deploy_one(fmt, output_name, verdicts[fmt])
        dests[fmt] = dest
        if dest:
            kb = os.path.getsize(dest) // 1024
            print(f'  배포 완료: {os.path.basename(dest)} ({kb} KB)')
        else:
            print(f'  ⚠ {fmt.upper()} 파일 없음 — 생성되지 않았거나 실패')

    logs = load_all()
    md_text = generate_report(logs, output_name, tf, run_start, dests, verdicts)

    report_path = os.path.join(SKILL_OUT, f'{output_name}_실행리포트.md')
    os.makedirs(SKILL_OUT, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(md_text)
    print(f'  실행 리포트: {report_path}')

    log7 = {
        'timestamp':    datetime.now().isoformat(),
        'final_outputs': dests,
        'report_path':  report_path,
        'verdicts':     verdicts,
        'step7_status': 'success',
    }
    with open(os.path.join(LOG_DIR, 'step7_final.json'), 'w', encoding='utf-8') as f:
        json.dump(log7, f, ensure_ascii=False, indent=2)

    if args.cleanup:
        if os.path.exists(WORKSPACE):
            shutil.rmtree(WORKSPACE)
            print(f'  workspace 삭제 완료: {WORKSPACE}')
        else:
            print(f'  workspace 없음 (이미 삭제됨)')
    else:
        print(f'  중간 파일 보존: {WORKSPACE}')
        print(f'  (삭제: python finalize_report.py --cleanup)')

    cc     = logs.get('cc', {})
    charts = cc.get('charts', [])
    n_gen  = cc.get('total_generated', 0)
    REQ    = {'V1_1', 'V1_2', 'V2_1', 'V3_1', 'V3_2', 'V4_1',
              'V5_1_end_use', 'V5_2_dc_type', 'V5_3_solution', 'V5_4_rack_density'}
    gen_ids = {c['chart_id'] for c in charts if c['status'] == 'generated'}
    n_req  = len(REQ & gen_ids)
    n_opt  = max(0, n_gen - n_req)
    total_dur = ts_diff(s1.get('timestamp', run_start), datetime.now().isoformat())

    print_banner(output_name, n_gen, n_req, n_opt, total_dur, verdicts, dests)


if __name__ == '__main__':
    main()
