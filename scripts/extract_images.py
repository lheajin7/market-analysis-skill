#!/usr/bin/env python3
"""
STEP 2 (이미지): 원본 보고서에서 이미지 추출 및 품질 평가

extract_input.py 실행 후 step1_meta.json이 있어야 합니다.

사용법:
  python extract_images.py
"""

import io
import json
import os
import re
import shutil
import zipfile
import zlib
from pathlib import Path

from PIL import Image

from _common import get_base

# ──────────────────────────────────────────────────────────────────
# 경로 상수
# ──────────────────────────────────────────────────────────────────
BASE       = get_base()
WORKSPACE  = os.path.join(BASE, 'workspace')
LOG_DIR    = os.path.join(WORKSPACE, 'logs')
IMAGES_DIR = os.path.join(WORKSPACE, 'extracted', 'images')
HWPX_RAW   = os.path.join(WORKSPACE, 'extracted', 'hwpx_raw')


# ──────────────────────────────────────────────────────────────────
# 메타데이터 로드
# ──────────────────────────────────────────────────────────────────
def load_step1_meta() -> dict:
    path = os.path.join(LOG_DIR, 'step1_meta.json')
    if not os.path.exists(path):
        raise FileNotFoundError(
            'step1_meta.json 없음 — extract_input.py를 먼저 실행하세요.'
        )
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════════
# 형식별 이미지 추출
# ══════════════════════════════════════════════════════════════════

def _pdf_priority_pages(total: int) -> list[int]:
    """300페이지 초과 PDF: 앞 30% + 뒤 20% 페이지 인덱스 반환"""
    front = list(range(0, int(total * 0.30)))
    back  = list(range(int(total * 0.70), total))
    return list(dict.fromkeys(front + back))  # 중복 제거, 순서 유지


def extract_images_pdf(input_file: str, page_count: int) -> list[str]:
    """pdfplumber로 PDF 이미지 추출"""
    import pdfplumber

    saved: list[str] = []
    os.makedirs(IMAGES_DIR, exist_ok=True)

    with pdfplumber.open(input_file) as pdf:
        if page_count > 300:
            target_indices = _pdf_priority_pages(len(pdf.pages))
            pages = [pdf.pages[i] for i in target_indices if i < len(pdf.pages)]
            print(f'  300p 초과 → 우선순위 {len(pages)}페이지만 처리')
        else:
            pages = pdf.pages

        for page in pages:
            pnum = page.page_number
            for img_idx, img_obj in enumerate(page.images):
                try:
                    x0 = img_obj.get('x0', 0)
                    y0 = img_obj.get('y0', 0)
                    x1 = img_obj.get('x1', page.width)
                    y1 = img_obj.get('y1', page.height)
                    # 유효 bbox 검증
                    if x1 <= x0 or y1 <= y0:
                        continue
                    cropped = page.within_bbox((x0, y0, x1, y1)).to_image(resolution=150)
                    fname = f'p{pnum:04d}_img{img_idx + 1:02d}.png'
                    fpath = os.path.join(IMAGES_DIR, fname)
                    cropped.save(fpath)
                    saved.append(fpath)
                except Exception:
                    pass

    return saved


def extract_images_hwp(input_file: str) -> list[str]:
    """olefile로 HWP 5.0 BinData 스트림에서 이미지 추출"""
    import olefile

    saved: list[str] = []
    os.makedirs(IMAGES_DIR, exist_ok=True)

    try:
        ole = olefile.OleFileIO(input_file)
    except Exception as e:
        print(f'  olefile 열기 실패: {e}')
        return saved

    for entry in ole.listdir():
        if len(entry) < 2 or entry[0] != 'BinData':
            continue
        stream_name = '/'.join(entry)
        try:
            data = ole.openstream(stream_name).read()
        except Exception:
            continue

        raw = None
        # raw deflate 시도 → 실패 시 원본 데이터로 fallback
        for attempt_decomp in (True, False):
            try:
                candidate = zlib.decompress(data, -15) if attempt_decomp else data
                img = Image.open(io.BytesIO(candidate))
                img.verify()                     # 손상 여부 확인
                img = Image.open(io.BytesIO(candidate))  # verify 후 재오픈 필요
                raw = candidate
                break
            except Exception:
                pass

        if raw is None:
            continue

        fname = re.sub(r'[\\/:*?"<>|]', '_', entry[1]) + '.png'
        fpath = os.path.join(IMAGES_DIR, fname)
        try:
            img.save(fpath, 'PNG')
            saved.append(fpath)
        except Exception:
            pass

    ole.close()
    return saved


def extract_images_hwpx(input_file: str) -> list[str]:
    """HWPX ZIP의 BinData 폴더에서 이미지 추출"""
    saved: list[str] = []
    os.makedirs(IMAGES_DIR, exist_ok=True)

    # hwpx_raw가 아직 해제 안 됐으면 해제
    hml_path = os.path.join(HWPX_RAW, 'Contents', 'content.hml')
    if not os.path.exists(hml_path):
        with zipfile.ZipFile(input_file) as z:
            z.extractall(HWPX_RAW)

    bin_dir = os.path.join(HWPX_RAW, 'BinData')
    if not os.path.exists(bin_dir):
        print('  BinData 폴더 없음 — 포함된 이미지 없음')
        return saved

    for fname in os.listdir(bin_dir):
        src  = os.path.join(bin_dir, fname)
        base = os.path.splitext(fname)[0]
        dst  = os.path.join(IMAGES_DIR, base + '.png')
        try:
            img = Image.open(src)
            img.save(dst, 'PNG')
        except Exception:
            shutil.copy2(src, os.path.join(IMAGES_DIR, fname))
            dst = os.path.join(IMAGES_DIR, fname)
        saved.append(dst)

    return saved


# ══════════════════════════════════════════════════════════════════
# 이미지 품질 평가
# ══════════════════════════════════════════════════════════════════

def estimate_image_type(width: int, height: int, size_kb: float) -> str:
    ratio = width / max(height, 1)
    if size_kb < 5:
        return 'logo'
    if 0.9 <= ratio <= 1.1:
        return 'logo'          # 거의 정방형 → 아이콘/로고 가능성
    if ratio > 10 or ratio < 0.1:
        return 'unknown'       # 극단적 비율
    if width >= 600 and height >= 250:
        return 'bar_chart' if ratio >= 1.8 else 'infographic'
    if width >= 300 and height >= 150:
        return 'line_chart' if ratio >= 1.5 else 'table'
    return 'unknown'


def evaluate_images(image_paths: list[str]) -> list[dict]:
    catalog: list[dict] = []
    for fpath in image_paths:
        if not os.path.exists(fpath):
            continue
        size_kb = os.path.getsize(fpath) / 1024
        try:
            with Image.open(fpath) as img:
                width, height = img.size
        except Exception:
            continue

        ratio    = width / max(height, 1)
        reusable = (
            width   >= 100 and
            height  >= 100 and
            size_kb >= 5   and
            0.1 <= ratio <= 10
        )
        catalog.append({
            'filename':      os.path.basename(fpath),
            'width':         width,
            'height':        height,
            'size_kb':       round(size_kb, 1),
            'reusable':      reusable,
            'estimated_type': estimate_image_type(width, height, size_kb),
        })
    return catalog


def save_image_catalog(catalog: list[dict]) -> str:
    path = os.path.join(IMAGES_DIR, 'image_catalog.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'images': catalog}, f, ensure_ascii=False, indent=2)
    return path


def update_step2_stats(extracted: int, reusable: int):
    """step2_extraction.json의 이미지 통계 갱신"""
    stats_path = os.path.join(LOG_DIR, 'step2_extraction.json')
    if not os.path.exists(stats_path):
        return
    with open(stats_path, encoding='utf-8') as f:
        stats = json.load(f)
    stats['images_extracted'] = extracted
    stats['images_reusable']  = reusable
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════

def main():
    meta        = load_step1_meta()
    input_file  = meta['input_file']
    file_type   = meta['file_type']
    page_count  = meta.get('page_count', 0)

    print(f'\n[STEP 2-이미지] {file_type.upper()} 이미지 추출 중...')

    dispatch = {
        'pdf':  lambda: extract_images_pdf(input_file, page_count),
        'hwp':  lambda: extract_images_hwp(input_file),
        'hwpx': lambda: extract_images_hwpx(input_file),
    }

    if file_type not in dispatch:
        print(f'  이미지 추출 미지원 형식: {file_type} — 빈 카탈로그 생성')
        image_paths: list[str] = []
    else:
        image_paths = dispatch[file_type]()

    catalog  = evaluate_images(image_paths)
    reusable = sum(1 for c in catalog if c['reusable'])
    save_image_catalog(catalog)
    update_step2_stats(len(catalog), reusable)

    # 유형 분포 집계
    type_dist: dict[str, int] = {}
    for c in catalog:
        type_dist[c['estimated_type']] = type_dist.get(c['estimated_type'], 0) + 1

    print(f'\n✅ STEP 2 (이미지) 완료')
    print(f'  추출 이미지: {len(catalog)}개')
    print(f'  재활용 가능: {reusable}개')
    if type_dist:
        dist_str = ', '.join(f'{k}: {v}' for k, v in sorted(type_dist.items()))
        print(f'  유형 분포: {dist_str}')
    print(f'\n  → 다음 단계: python generate_charts.py')


if __name__ == '__main__':
    main()
