#!/usr/bin/env python3
"""
STEP 5+6: HWPX·DOCX 보고서를 모두 생성하고 각각 검증한다.

사전 조건: STEP 3(master_dataset.json) + generate_charts.py 실행 완료

사용법:
  python generate_reports.py
  python generate_reports.py --only hwpx   # hwpx만
  python generate_reports.py --only docx   # docx만
"""

import argparse
import os
import subprocess
import sys

# Windows 기본 콘솔(cp949)에서 이모지·한글 출력이 UnicodeEncodeError로 죽는 문제 방지.
# 이 스크립트는 _common을 import하지 않으므로(오케스트레이터) 여기서 직접 stdout/stderr을 UTF-8로 맞춘다.
# (하위 스크립트에는 PYTHONIOENCODING=utf-8 환경변수로 별도 전달 — run() 참고)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run(label: str, script_name: str) -> bool:
    print(f'\n{"=" * 55}')
    print(f'  {label}')
    print(f'{"=" * 55}')
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, script_name)],
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'},
    )
    ok = result.returncode == 0
    if not ok:
        print(f'❌ {script_name} 실패 (exit {result.returncode})')
    return ok


def main():
    parser = argparse.ArgumentParser(description='HWPX·DOCX 보고서 동시 생성')
    parser.add_argument('--only', choices=['hwpx', 'docx'],
                        help='한 형식만 생성 (기본: 둘 다)')
    args = parser.parse_args()

    targets = [args.only] if args.only else ['hwpx', 'docx']
    results: dict = {}

    if 'hwpx' in targets:
        ok1 = run('STEP 5a — HWPX 보고서 생성', 'generate_hwpx.py')
        ok2 = run('STEP 6a — HWPX 품질 검증',   'validate_output_hwpx.py') if ok1 else False
        results['hwpx'] = ok1 and ok2

    if 'docx' in targets:
        ok3 = run('STEP 5b — DOCX 보고서 생성', 'generate_docx.py')
        ok4 = run('STEP 6b — DOCX 품질 검증',   'validate_output_docx.py') if ok3 else False
        results['docx'] = ok3 and ok4

    print(f'\n{"=" * 55}')
    print('  요약')
    print(f'{"=" * 55}')
    for fmt, ok in results.items():
        print(f'  {fmt.upper()}: {"✅ 완료" if ok else "❌ 실패"}')

    if not all(results.values()):
        sys.exit(1)


if __name__ == '__main__':
    main()
