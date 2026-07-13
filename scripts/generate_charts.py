#!/usr/bin/env python3
"""
STEP 4: 차트 및 인포그래픽 생성 (matplotlib + Pillow)

사전 조건: analyze_sections.py 실행 완료 (master_dataset.json 존재)

사용법:
  python generate_charts.py
"""

import json
import os
import shutil
import sys
import textwrap
import warnings
from datetime import datetime

import matplotlib
matplotlib.use('Agg')                     # headless 환경용 (GUI 불필요)
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
from PIL import Image, ImageDraw, ImageFont

warnings.filterwarnings('ignore')

from _common import get_base, seg_title, value_label

# ──────────────────────────────────────────────────────────────────
# 경로 상수
# ──────────────────────────────────────────────────────────────────
BASE       = get_base()
WORKSPACE  = os.path.join(BASE, 'workspace')
STRUCTURED = os.path.join(WORKSPACE, 'structured')
CHARTS     = os.path.join(WORKSPACE, 'charts')
LOG_DIR    = os.path.join(WORKSPACE, 'logs')
EXTRACTED_IMAGES = os.path.join(WORKSPACE, 'extracted', 'images')

DPI = 150

# ──────────────────────────────────────────────────────────────────
# 컬러 팔레트
# ──────────────────────────────────────────────────────────────────
C = {
    'mint':      '#2EC4B6',
    'navy':      '#1A3A5C',
    'green':     '#4CAF50',
    'orange':    '#FF7043',
    'gray':      '#90A4AE',
    'light_bg':  '#F5F5F5',
    'text':      '#212121',
}
PALETTE = [C['mint'], C['navy'], C['green'], C['orange'], C['gray']]

# Pillow RGB 튜플 (불투명 흰·회색 포함)
RGB = {
    'mint':       (46,  196, 182),
    'navy':       (26,   58,  92),
    'green':      (76,  175,  80),
    'orange':     (255, 112,  67),
    'gray':       (144, 164, 174),
    'light_bg':   (245, 245, 245),
    'text':       (33,   33,  33),
    'white':      (255, 255, 255),
    'light_gray': (230, 230, 230),
    'mid_gray':   (100, 100, 100),
}

# ──────────────────────────────────────────────────────────────────
# 문서 삽입 폭 대비 폰트 크기 자동 환산
# ──────────────────────────────────────────────────────────────────
# 생성된 PNG는 원본 캔버스 크기와 무관하게 문서 삽입 시 "고정 폭"으로 리사이즈된다
# (DOCX/HWPX 모두 본문 폭 ~6.77in — 표와 동일 폭으로 꽉 채워 삽입하기 위함). 따라서 중요한 것은
# "이 함수 안에서 몇 pt로 그리는가"가 아니라 "문서에 삽입된 뒤 실제로 몇 pt로
# 보이는가"이며, 원본 캔버스가 넓을수록(matplotlib figsize가 크거나 Pillow 캔버스
# 픽셀 폭이 클수록) 훨씬 더 큰 원본 폰트가 있어야 삽입 후에도 읽을 수 있는 크기가
# 남는다. 반대로 캔버스가 좁으면 작은 원본 폰트로도 충분하다 — 모든 차트에 똑같은
# pt 값을 쓰면(과거 방식) 캔버스 폭 차이만큼 삽입 후 크기가 들쭉날쭉해진다.
#
# 아래 두 헬퍼가 이 환산을 전담한다. 새 차트를 추가할 때도 하드코딩된 pt/px 값
# 대신 반드시 mpl_pt()/pil_pt()를 통해 크기를 정해야, 삽입 후 크기가 본문(10pt)·
# 캡션(9pt)과 조화를 이루고 차트마다 크기가 들쭉날쭉해지지 않는다.
# 두 포맷 모두 A4 + 위·아래 2.54cm / 좌·우 1.9cm 여백을 쓰고, 표·그림 모두 그 본문
# 폭에 꽉 채워 삽입한다(generate_docx.py CONTENT_WIDTH_IN, generate_hwpx.py
# CONTENT_WIDTH) — 여백을 바꾸면 이 두 값도 반드시 함께 갱신할 것.
DOCX_WIDTH_IN = (21.0 - 2 * 1.9) / 2.54     # generate_docx.py CONTENT_WIDTH_IN
HWPX_WIDTH_IN = (59528 - 2 * 5386) / 7200   # generate_hwpx.py CONTENT_WIDTH (7200 hwpunit/in)
REF_WIDTH_IN  = (DOCX_WIDTH_IN + HWPX_WIDTH_IN) / 2   # 두 포맷 절충 기준폭 (~6.77in, 이제 거의 동일)

# 삽입 후 실제로 보이길 원하는 크기(pt) — 본문 10pt / 캡션 9pt와 조화를 이루도록
# 설정한다. 제목류만 살짝 강조하고 나머지는 본문·캡션과 비슷한 눈높이로 맞춘다.
EFFECTIVE_PT = {
    'title':       12,   # 차트 제목
    'axis_label':  10,   # 축 이름
    'tick':         9,   # 눈금 라벨
    'legend':       7.5, # 범례 (그림 레이블) — 요청에 따라 9pt에서 축소 (7~8pt 범위)
    'data_label':   8.5, # 막대/점 위 수치 라벨
    'ig_header':   11,   # Pillow 인포그래픽 컬러 헤더 바
    'ig_item':      9.5, # Pillow 인포그래픽 항목 제목
    'ig_desc':      8.5, # Pillow 인포그래픽 설명문·부가 텍스트
    'table_header': 9.5, # 표 헤더 행
    'table_cell':   9,   # 표 셀 본문
}


def mpl_pt(role: str, fig_width_in: float) -> float:
    """matplotlib 차트: figsize 가로 인치 기준으로, 문서 삽입 후 EFFECTIVE_PT[role]
    로 보이도록 원본 fontsize(pt)를 역산한다."""
    return round(EFFECTIVE_PT[role] * fig_width_in / REF_WIDTH_IN, 1)


def pil_pt(role: str, canvas_w_px: int) -> int:
    """Pillow 캔버스: 가로 픽셀(DPI 기준) 기준으로, 문서 삽입 후 EFFECTIVE_PT[role]
    로 보이도록 원본 폰트 크기(px)를 역산한다."""
    return max(8, round(EFFECTIVE_PT[role] * canvas_w_px / (72 * REF_WIDTH_IN)))


# ──────────────────────────────────────────────────────────────────
# 폰트 설정
# ──────────────────────────────────────────────────────────────────
_USER = os.environ.get('USERNAME', 'user')
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_CANDS = [
    # 스킬 저장소에 동봉된 폰트(리포지토리 클론만 하면 어느 PC에서도 그대로 동작) — 최우선
    os.path.join(_SCRIPT_DIR, 'assets', 'NanumGothic.ttf'),
    r'C:\Windows\Fonts\NanumGothic.ttf',
    os.path.join(r'C:\Users', _USER,
                 r'AppData\Local\Microsoft\Windows\Fonts\NanumGothic.ttf'),
    os.path.join(BASE, r'skill\assets\NanumGothic.ttf'),
]
FONT_PATH = next((p for p in _FONT_CANDS if os.path.exists(p)), None)


def setup_mpl_font():
    if FONT_PATH:
        fp = fm.FontProperties(fname=FONT_PATH)
        plt.rcParams['font.family'] = fp.get_name()
    plt.rcParams['axes.unicode_minus'] = False


def pil_font(size: int = 14) -> ImageFont.FreeTypeFont:
    for candidate in ([FONT_PATH] if FONT_PATH else []) + ['arial.ttf', 'DejaVuSans.ttf']:
        if candidate and os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                pass
    return ImageFont.load_default()


def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _relative_luminance(rgb: tuple) -> float:
    """WCAG 상대 휘도 계산 (sRGB 감마 보정 포함)."""
    def lin(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def _text_colors_for_bg(bg_rgb: tuple) -> tuple:
    """배경색 위에 얹을 (주 텍스트색, 보조 텍스트색)을 대비비 기준으로 자동 선택한다.
    PALETTE의 mint·green·orange·gray는 흰 글씨 고정 대비비가 2.2~2.8 수준으로 약한
    반면(WCAG 권장 4.5 미달) 진한 글씨는 7.5~9.7로 훨씬 낫다(navy만 반대) — 배경마다
    흰색을 고정해 쓰면 밝은 배경 위 흰 글씨가 잘 안 보이는 문제가 생긴다(실측 확인).
    두 후보(흰/검) 중 대비비가 더 높은 쪽을 그때그때 고른다."""
    L = _relative_luminance(bg_rgb)
    contrast_white = 1.05 / (L + 0.05)
    contrast_black = (L + 0.05) / 0.05
    if contrast_white >= contrast_black:
        return (255, 255, 255), (222, 222, 222)
    return (25, 25, 25), (95, 95, 95)


# ──────────────────────────────────────────────────────────────────
# 차트 카탈로그
# ──────────────────────────────────────────────────────────────────
_catalog: dict = {'charts': [], 'total_generated': 0, 'total_skipped': 0}


def _reg(chart_id: str, fname: str, section: int, title: str,
         caption: str, status: str, skip_reason: str = ''):
    _catalog['charts'].append({
        'chart_id':    chart_id,
        'filename':    fname,
        'section':     section,
        'title':       title,
        'caption':     caption,
        'status':      status,
        'skip_reason': skip_reason,
    })
    # 'reused'(원본 이미지 재활용)도 정상적으로 채워진 것이므로 생성 통계에 포함한다
    # ('generated'만 세면 재활용된 그림이 마치 누락된 것처럼 카운트된다).
    _catalog['total_generated' if status in ('generated', 'reused') else 'total_skipped'] += 1


def _save_catalog():
    with open(os.path.join(CHARTS, 'chart_catalog.json'), 'w', encoding='utf-8') as f:
        json.dump(_catalog, f, ensure_ascii=False, indent=2)


def _try_reuse_image(chart_id: str, fname: str, section: int, title: str,
                      caption: str, image_name: str | None) -> bool:
    """STEP 3에서 원본 보고서의 실제 그림(workspace/extracted/images/*)을 이 슬롯에
    쓰기로 지정했으면(그 파일명을 image_name으로 넘김) 그 그림을 그대로 복사해
    쓰고, matplotlib/Pillow로 새로 합성하지 않는다 — "본문 그림·표는 원본 이미지를
    최대한 활용하고, 없을 때만 시각화한다"는 원칙(SKILL.md STEP 4 참고)에 따른
    것이다. 파일이 없거나 image_name이 비어 있으면 False를 반환해 합성 경로로
    넘어가게 한다."""
    if not image_name:
        return False
    src_path = os.path.join(EXTRACTED_IMAGES, image_name)
    if not os.path.exists(src_path):
        return False
    dst_path = os.path.join(CHARTS, fname)
    shutil.copy(src_path, dst_path)
    _reg(chart_id, fname, section, title, caption, 'reused')
    return True


# ──────────────────────────────────────────────────────────────────
# matplotlib 공통 유틸
# ──────────────────────────────────────────────────────────────────

def _style_axes(ax, fig_width_in: float, y2=None):
    """축 눈금 라벨 크기를 figsize 폭 기준으로 정확히 맞춘다(전역 rcParams 대신
    차트별로 계산 — figsize가 다른 차트가 섞여 있으므로 전역 값 하나로는 맞지 않는다)."""
    tick_pt = mpl_pt('tick', fig_width_in)
    ax.tick_params(axis='both', labelsize=tick_pt)
    if y2 is not None:
        y2.tick_params(axis='y', labelsize=tick_pt)


def _declutter_y(vals: list, ymax: float, min_gap_frac: float = 0.05) -> list:
    """같은 x좌표에 찍히는 여러 선그래프 계열의 값이 서로 비슷하면 수치 라벨이
    겹친다 — 값 순서를 지키면서 라벨을 놓을 y좌표만 최소 간격만큼 벌린다
    (마커 자체는 실제 값 위치 그대로, 라벨 텍스트 앵커만 조정)."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    min_gap = ymax * min_gap_frac
    adj = [vals[i] for i in order]
    for k in range(1, len(adj)):
        if adj[k] - adj[k - 1] < min_gap:
            adj[k] = adj[k - 1] + min_gap
    result = [0.0] * len(vals)
    for rank, i in enumerate(order):
        result[i] = adj[rank]
    return result


def _bar_labels(ax, bars, fmt='{:.1f}', fontsize=9, rotation=0):
    """막대 위 수치 라벨. 세그먼트가 많아 막대 폭이 좁을 때(rotation=90) 라벨을
    세로로 세워 옆 막대 라벨과 가로로 겹치지 않게 한다(실측 확인 — 가로 라벨은
    좁은 막대 폭보다 글자폭이 넓어 인접 막대 라벨과 겹쳤다)."""
    for b in bars:
        h = b.get_height()
        if h and h > 0:
            ax.annotate(fmt.format(h),
                        xy=(b.get_x() + b.get_width() / 2, h),
                        xytext=(0, 3), textcoords='offset points',
                        ha='center', va='bottom', fontsize=fontsize,
                        rotation=rotation, rotation_mode='anchor')


def _savefig(fname: str) -> str:
    path = os.path.join(CHARTS, fname)
    plt.savefig(path, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close('all')
    return path


def _legend_above(fig, handles, labels, legend_pt: float, ncol: int,
                   top: float = 0.88):
    """그림 안 제목은 넣지 않는다 — 문서 삽입 후 이미지 바로 아래에 자동 채번
    캡션("그림 N. 제목 (출처: ...)")이 이미 붙으므로, 그림 안에 같은 제목을 또
    넣으면 같은 내용이 위(그림 내부)·아래(캡션) 두 번 겹쳐 보인다. 그림 안에는
    범례(계열 라벨)만, 그래프 바깥 맨 위에 작게 남긴다.
    범례는 반드시 loc='lower center'로 앵커링한다 — 'upper center'로 앵커링하면
    범례 박스가 앵커점에서 '아래로' 자라나서 세그먼트가 많아 범례가 2줄 이상이 될 때
    plot 영역을 침범해 막대·수치와 겹친다(실측 확인). 'lower center'는 앵커점에서
    '위로' 자라나므로 줄 수가 몇 줄이든 축 영역을 절대 침범하지 않는다.
    남는 여백은 _savefig의 bbox_inches='tight'가 잘라내므로 top을 넉넉히 잡아도 무방하다.
    범례는 테두리 박스로 감싼다(frameon=True) — 배경(흰색)과 테두리(연회색)로 그래프 영역과
    시각적으로 분리되어, 작은 글씨로 줄여도(EFFECTIVE_PT['legend']) 어디까지가 범례인지
    한눈에 구분된다."""
    leg = fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(0.5, top + 0.02),
                      ncol=ncol, fontsize=legend_pt, frameon=True)
    leg.get_frame().set_edgecolor(C['gray'])
    leg.get_frame().set_facecolor('white')
    leg.get_frame().set_linewidth(0.8)
    fig.subplots_adjust(top=top)


# ──────────────────────────────────────────────────────────────────
# Pillow 공통 유틸
# ──────────────────────────────────────────────────────────────────

def _wrap(text: str, max_w: int, font, draw: ImageDraw.ImageDraw) -> list:
    """단어 단위 줄 바꿈 (Pillow textbbox 사용)"""
    words = str(text).split()
    lines, cur = [], ''
    for w in words:
        test = f'{cur} {w}'.strip()
        try:
            bbox = draw.textbbox((0, 0), test, font=font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(test) * 8
        if tw <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [str(text)[:40]]


def _wrap_label(text: str, width: int = 14) -> str:
    """matplotlib 범례 라벨처럼 실측 폭을 잴 draw 컨텍스트가 없는 곳에서 쓰는
    글자수 기준 줄바꿈 — len() 슬라이스로 잘라내지 않고 여러 줄로 모두 보여준다."""
    return '\n'.join(textwrap.wrap(str(text), width)) or str(text)


def _save_pil(img: Image.Image, fname: str) -> str:
    path = os.path.join(CHARTS, fname)
    img.save(path, dpi=(DPI, DPI))
    return path


# ══════════════════════════════════════════════════════════════════
# V1_1: 전력 수요 전망 복합 차트 (막대 + 꺾은선)
# ══════════════════════════════════════════════════════════════════
def v1_1(sec1: dict, tf: str, src: str) -> bool:
    pd_  = sec1.get('power_demand_data', {})
    yrs  = pd_.get('years', [])
    incl = pd_.get('demand_incl_ai_twh', [])
    excl = pd_.get('demand_excl_ai_twh', [])
    eff  = pd_.get('efficiency_gain_pct', [])

    if not yrs or not incl:
        _reg('V1_1', 'V1_1_power_demand.png', 1, '', '', 'skipped',
             'power_demand_data 없음')
        return False

    FIG_W = 10
    x, w = np.arange(len(yrs)), 0.35
    fig, ax1 = plt.subplots(figsize=(FIG_W, 6))
    ax2 = ax1.twinx()

    b1 = ax1.bar(x - w/2, incl, w, label='AI 포함 수요 (TWh)',
                 color=C['mint'], alpha=0.9)
    b2 = ax1.bar(x + w/2, excl, w, label='AI 제외 수요 (TWh)',
                 color=C['navy'], alpha=0.9)
    data_pt = mpl_pt('data_label', FIG_W)
    # AI 포함·제외 수요 값이 비슷한 해에는 두 막대 라벨이 같은 높이 근처에 찍혀
    # 겹친다(실측 확인) — 값 순서를 지키며 라벨 y좌표만 최소 간격만큼 벌린다
    # (_declutter_y, V4_1과 동일한 방식). 막대 자체 위치·높이는 그대로 둔다.
    ymax_bar = max(incl + excl) if excl else max(incl)
    for i in range(len(yrs)):
        pts = [(incl[i], x[i] - w / 2)]
        if excl and i < len(excl):
            pts.append((excl[i], x[i] + w / 2))
        ty_list = _declutter_y([v for v, _ in pts], ymax_bar)
        for (val, xc), ty in zip(pts, ty_list):
            ax1.annotate(f'{val:.1f}', (xc, ty), xytext=(0, 3),
                         textcoords='offset points', ha='center', va='bottom',
                         fontsize=data_pt)

    if eff and len(eff) == len(yrs):
        ax2.plot(x, eff, 'o-', color=C['orange'], lw=2, ms=6,
                 label='효율 향상률 (%)')
        ax2.set_ylabel('효율 향상률 (%)', color=C['orange'],
                        fontsize=mpl_pt('axis_label', FIG_W))
        ax2.tick_params(axis='y', labelcolor=C['orange'])

    by, ey = sec1.get('base_year', yrs[0]), yrs[-1]
    ax1.set_xlabel('연도', fontsize=mpl_pt('axis_label', FIG_W))
    ax1.set_ylabel('전력 수요 (TWh)', fontsize=mpl_pt('axis_label', FIG_W))
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(y) for y in yrs])
    ax1.set_facecolor(C['light_bg'])
    ax1.grid(axis='y', alpha=0.3)
    _style_axes(ax1, FIG_W, y2=ax2)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels() if eff else ([], [])
    _legend_above(fig, h1 + h2, l1 + l2, mpl_pt('legend', FIG_W), len(h1 + h2))
    _savefig('V1_1_power_demand.png')
    _reg('V1_1', 'V1_1_power_demand.png', 1,
         f'{tf} 분야 전력 수요 전망',
         f'그림 1. 전력 수요 전망 (출처: {src})', 'generated')
    return True


# ══════════════════════════════════════════════════════════════════
# V1_2: 시나리오별 시장규모 전망
# ══════════════════════════════════════════════════════════════════
def v1_2(sec1: dict, tf: str, src: str) -> bool:
    sc      = sec1.get('scenarios', {})
    base_s  = sec1.get('base_year_size_usd_b')
    base_yr = sec1.get('base_year', '기준')
    fc_yr   = sec1.get('forecast_year', '예측')
    unit    = sec1.get('currency_unit', '$B')

    sc_defs = [
        ('낙관 (Optimistic)', 'optimistic',  PALETTE[0]),
        ('현실 (Realistic)',  'realistic',   PALETTE[1]),
        ('비관 (Pessimistic)', 'pessimistic', PALETTE[2]),
    ]
    yr_labels = [str(base_yr), str(fc_yr)]
    x = np.arange(2)

    valid = [(lbl, sc.get(k, {}), col)
             for lbl, k, col in sc_defs
             if sc.get(k, {}).get('size_usd_b') is not None]
    if not valid or base_s is None:
        _reg('V1_2', 'V1_2_market_scenarios.png', 1, '', '', 'skipped',
             '시나리오 데이터 없음')
        return False

    FIG_W = 10
    w = 0.25
    fig, ax = plt.subplots(figsize=(FIG_W, 6))
    for i, (lbl, sd, col) in enumerate(valid):
        vals = [base_s, sd['size_usd_b']]
        offset = (i - len(valid) / 2 + 0.5) * w
        bars = ax.bar(x + offset, vals, w, label=lbl, color=col, alpha=0.9)
        _bar_labels(ax, bars, fontsize=mpl_pt('data_label', FIG_W))

    ax.set_xlabel('연도', fontsize=mpl_pt('axis_label', FIG_W))
    ax.set_ylabel(f'시장규모 ({unit})', fontsize=mpl_pt('axis_label', FIG_W))
    ax.set_xticks(x)
    ax.set_xticklabels(yr_labels)
    ax.set_facecolor(C['light_bg'])
    ax.grid(axis='y', alpha=0.3)
    _style_axes(ax, FIG_W)
    handles, labels = ax.get_legend_handles_labels()
    _legend_above(fig, handles, labels, mpl_pt('legend', FIG_W), len(valid))
    _savefig('V1_2_market_scenarios.png')
    _reg('V1_2', 'V1_2_market_scenarios.png', 1,
         '시나리오별 시장규모 전망',
         f'그림 2. 시나리오별 시장규모 전망 (출처: {src})', 'generated')
    return True


# ══════════════════════════════════════════════════════════════════
# V2_1: 시장 역학 인포그래픽 (Pillow)
# ══════════════════════════════════════════════════════════════════
def v2_1(sec2: dict, src: str) -> bool:
    """항목별 상세 설명은 본문(generate_docx.py/generate_hwpx.py의 dyn_section 패턴)에
    이미 전문으로 실리므로, 그림에는 제목만 표시한다 — 그래야 항목 수가 늘어나도
    글자가 잘리거나 항목이 잘려나가는 일 없이 안정적으로 들어간다."""
    has_ch = sec2.get('has_challenges', False)
    drivers = sec2.get('drivers',     [])[:4]
    rests   = sec2.get('restraints',  [])[:4]
    challs  = sec2.get('challenges',  [])[:3] if has_ch else []
    opps    = sec2.get('opportunities', [])[:4]

    if not any([drivers, rests, opps]):
        _reg('V2_1', 'V2_1_market_dynamics.png', 2, '', '', 'skipped',
             '역학 데이터 없음')
        return False

    # 보고서에 따라 네 카테고리 중 일부(특히 저해 요인/도전 과제)가 원문에 아예
    # 없을 수 있다(예: "Opportunities/Restraints"로 묶인 절이 실제로는 기회
    # 내용만 담고 있는 경우 — 실측 확인). 데이터가 없는 카테고리를 빈 칸으로
    # 그리면 헤더만 있고 속이 빈 박스가 남으므로, has_challenges와 동일한
    # 원칙으로 항목이 하나도 없는 카테고리는 열 자체를 만들지 않는다 — 있는
    # 내용만으로 구성한다.
    col_defs = [
        c for c in [
            ('성장 동인 (Drivers)',    drivers, RGB['mint'],   '▲'),
            ('저해 요인 (Restraints)', rests,   RGB['navy'],   '▼'),
            ('도전 과제 (Challenges)', challs,  RGB['orange'], '⚡') if has_ch else None,
            ('기회 (Opportunities)',   opps,    RGB['green'],  '◆'),
        ] if c is not None and c[1]
    ]

    n_cols  = len(col_defs)
    COL_W   = 650
    W       = n_cols * COL_W + 20

    hdr_px, item_px = pil_pt('ig_header', W), pil_pt('ig_item', W)
    hdr_f, item_f = pil_font(hdr_px), pil_font(item_px)
    icon_f = pil_font(round(hdr_px * 1.3))

    LINE_H   = round(item_px * 1.55)    # 항목 제목 줄 간격(제목이 길면 여러 줄로 감쌈)
    ITEM_PAD = round(item_px * 0.55)    # 항목 박스 상하 여백
    ICON_GAP = round(hdr_px * 0.35)

    # 1차 패스: 실제 캔버스를 만들기 전에 헤더/각 컬럼에 필요한 높이를 미리 측정한다.
    # (박스 크기를 고정값으로 어림하면 폰트가 커졌을 때 내용이 잘리거나 겹친다)
    _probe = ImageDraw.Draw(Image.new('RGB', (10, 10)))
    icon_w = max(_probe.textbbox((0, 0), icon, font=icon_f)[2] for _, _, _, icon in col_defs)
    hdr_avail_w = COL_W - 29 - icon_w - ICON_GAP
    hdr_lines_n = max(len(_wrap(hdr_txt, hdr_avail_w, hdr_f, _probe)) for hdr_txt, _, _, _ in col_defs)
    HDR_LINE = round(hdr_px * 1.4)
    HDR_H = max(round(icon_f.size * 1.3), hdr_lines_n * HDR_LINE) + round(hdr_px * 0.8)

    col_heights = []
    for _, items, _, _ in col_defs:
        y = 15 + HDR_H + 15
        for item in items:
            title_lines = _wrap(f'• {item.get("title", "")}', COL_W - 34, item_f, _probe)
            item_h = ITEM_PAD * 2 + len(title_lines) * LINE_H
            y += item_h + 10
        col_heights.append(y)
    H = max(col_heights, default=HDR_H + 100) + 15

    img = Image.new('RGB', (W, H), RGB['light_bg'])
    d   = ImageDraw.Draw(img)

    for ci, (hdr_txt, items, color, icon) in enumerate(col_defs):
        cx = 10 + ci * COL_W
        hdr_primary, _ = _text_colors_for_bg(color)
        # 헤더 박스 — 아이콘 실측 폭만큼 띄운 뒤 남는 폭에서 줄바꿈한다(잘라내지 않음).
        d.rectangle([cx, 15, cx + COL_W - 8, 15 + HDR_H], fill=color)
        d.text((cx + 15, 15 + round(HDR_H * 0.5)), icon, fill=hdr_primary,
               font=icon_f, anchor='lm')
        hdr_lines = _wrap(hdr_txt, hdr_avail_w, hdr_f, d)
        hdr_y0 = 15 + round(HDR_H / 2 - len(hdr_lines) * HDR_LINE / 2)
        for li, hline in enumerate(hdr_lines):
            d.text((cx + 15 + icon_w + ICON_GAP, hdr_y0 + li * HDR_LINE), hline,
                   fill=hdr_primary, font=hdr_f)
        # 항목 박스
        y = 15 + HDR_H + 15
        for item in items:
            title_lines = _wrap(f'• {item.get("title", "")}', COL_W - 34, item_f, d)
            item_h = ITEM_PAD * 2 + len(title_lines) * LINE_H
            d.rectangle([cx + 7, y, cx + COL_W - 15, y + item_h],
                        fill=RGB['white'], outline=color, width=1)
            for li, tline in enumerate(title_lines):
                d.text((cx + 17, y + ITEM_PAD + li * LINE_H), tline,
                       fill=RGB['text'], font=item_f)
            y += item_h + 10

    _save_pil(img, 'V2_1_market_dynamics.png')
    _reg('V2_1', 'V2_1_market_dynamics.png', 2,
         '시장 역학 구조',
         f'그림 3. 시장 역학 구조 (출처: {src})', 'generated')
    return True


# ══════════════════════════════════════════════════════════════════
# V3_1: 주요 플레이어 그리드 (Pillow)
# ══════════════════════════════════════════════════════════════════
def v3_1(sec3: dict, src: str) -> bool:
    cap = f'생태계 맵 (출처: {src})'
    if _try_reuse_image('V3_1', 'V3_1_key_players.png', 3, '생태계 맵', cap,
                         sec3.get('ecosystem_map_image')):
        return True

    cats = sec3.get('key_players_by_category', [])
    if not cats:
        _reg('V3_1', 'V3_1_key_players.png', 3, '', '', 'skipped',
             '플레이어 데이터 없음')
        return False

    N_COLS = min(3, len(cats))
    N_ROWS = (len(cats) + N_COLS - 1) // N_COLS
    COL_W  = 730
    W      = N_COLS * COL_W + 20

    hdr_px, item_px = pil_pt('ig_header', W), pil_pt('ig_item', W)
    hdr_f, item_f = pil_font(hdr_px), pil_font(item_px)

    HDR_LINE = round(hdr_px * 1.4)
    ITEM_LINE = round(item_px * 1.4)
    GAP      = round(item_px * 0.35)
    TOP_PAD  = round(hdr_px * 0.5)
    ITEM_PAD = round(item_px * 0.35)

    _probe = ImageDraw.Draw(Image.new('RGB', (10, 10)))

    def _company_label(comp: dict) -> str:
        name    = str(comp.get('name', ''))
        country = str(comp.get('country', ''))
        return f'{name}  ({country})' if country else name

    # 카테고리 헤더·기업명 모두 줄바꿈 기준으로 실제 필요한 높이를 미리 측정한다
    # (잘라내지 않고 다 보여줘야 하므로, 길이에 따라 박스 높이가 늘어나야 한다).
    def _cat_height(cat: dict) -> tuple:
        hdr_lines = _wrap(str(cat.get('category', '')), COL_W - 28, hdr_f, _probe)
        hdr_h = max(1, len(hdr_lines)) * HDR_LINE + round(hdr_px * 0.6)
        comp_line_counts = []
        for comp in cat.get('companies', [])[:6]:
            lines = _wrap(_company_label(comp), COL_W - 34, item_f, _probe)
            comp_line_counts.append(max(1, len(lines)))
        comp_h = sum(n * ITEM_LINE + ITEM_PAD * 2 + GAP for n in comp_line_counts)
        return hdr_h, comp_h, comp_line_counts

    cat_metrics = [_cat_height(c) for c in cats]

    row_heights = []
    for row in range(N_ROWS):
        row_metrics = cat_metrics[row * N_COLS:(row + 1) * N_COLS]
        h = max((hh + ch for hh, ch, _ in row_metrics), default=0)
        row_heights.append(h + TOP_PAD + 15)
    H = sum(row_heights) + 20

    y_offsets = [10]
    for rh in row_heights:
        y_offsets.append(y_offsets[-1] + rh)

    img = Image.new('RGB', (W, H), RGB['light_bg'])
    d   = ImageDraw.Draw(img)

    for idx, cat in enumerate(cats):
        row, col = divmod(idx, N_COLS)
        cx, cy = 10 + col * COL_W, y_offsets[row]
        hdr_h, _, comp_line_counts = cat_metrics[idx]

        # 카테고리 헤더 (줄바꿈, 잘라내지 않음)
        d.rectangle([cx, cy, cx + COL_W - 8, cy + hdr_h], fill=RGB['navy'])
        hdr_lines = _wrap(str(cat.get('category', '')), COL_W - 28, hdr_f, d)
        for li, hline in enumerate(hdr_lines):
            d.text((cx + 14, cy + round(hdr_px * 0.3) + li * HDR_LINE), hline,
                   fill=RGB['white'], font=hdr_f)

        # 기업 목록 (긴 이름은 줄바꿈, 잘라내지 않음)
        y = cy + hdr_h + TOP_PAD
        for comp, n_lines in zip(cat.get('companies', [])[:6], comp_line_counts):
            label = _company_label(comp)
            lines = _wrap(label, COL_W - 34, item_f, d)
            box_h = n_lines * ITEM_LINE + ITEM_PAD * 2
            d.rectangle([cx + 7, y, cx + COL_W - 17, y + box_h],
                        fill=RGB['white'], outline=RGB['gray'], width=1)
            for li, tline in enumerate(lines):
                d.text((cx + 17, y + ITEM_PAD + li * ITEM_LINE), tline,
                       fill=RGB['text'], font=item_f)
            y += box_h + GAP

    _save_pil(img, 'V3_1_key_players.png')
    _reg('V3_1', 'V3_1_key_players.png', 3, '생태계 맵', cap, 'generated')
    return True


# ══════════════════════════════════════════════════════════════════
# 공통: 단계형 플로우 다이어그램 (Pillow) — 가치사슬(V3_2)·공급망(V3_3)이 공유
# ══════════════════════════════════════════════════════════════════
def _flow_diagram(stages: list, fname: str) -> None:
    N = len(stages)
    BOX_W = max(306, min(476, 2652 // N - 37))
    W = N * (BOX_W + 37) + 34

    step_px = pil_pt('ig_desc', W)      # STEP N 라벨
    name_px = pil_pt('ig_header', W)    # 단계명(한글, 가장 강조)
    en_px   = pil_pt('ig_desc', W)      # 영문명
    item_px = pil_pt('ig_desc', W)      # 대표기업·카테고리
    step_f, name_f, en_f, item_f = (pil_font(step_px), pil_font(name_px),
                                     pil_font(en_px), pil_font(item_px))

    ITEM_LINE = round(item_px * 1.5)
    NAME_LINE = round(name_px * 1.5)
    EN_LINE   = round(en_px * 1.5)
    STEP_LINE = round(step_px * 1.5)
    TOP_PAD   = round(step_px * 1.2)
    AVAIL_W   = BOX_W - 28

    _probe = ImageDraw.Draw(Image.new('RGB', (10, 10)))

    def _stage_lines(stage):
        name_lines = _wrap(str(stage.get('stage_name', '')), AVAIL_W, name_f, _probe)
        en_lines   = _wrap(str(stage.get('stage_name_en', '')), AVAIL_W, en_f, _probe)
        comp_lines = [_wrap(f'• {c}', AVAIL_W - 3, item_f, _probe)
                      for c in stage.get('representative_companies', [])[:3]]
        cat_lines  = [_wrap(f'[{c}]', AVAIL_W - 3, item_f, _probe)
                      for c in stage.get('representative_categories', [])[:2]]
        return name_lines, en_lines, comp_lines, cat_lines

    stage_metrics = [_stage_lines(s) for s in stages]

    def _stage_height(metrics):
        name_lines, en_lines, comp_lines, cat_lines = metrics
        h = STEP_LINE + len(name_lines) * NAME_LINE + len(en_lines) * EN_LINE
        h += sum(len(ls) * ITEM_LINE for ls in comp_lines)
        h += sum(len(ls) * ITEM_LINE for ls in cat_lines)
        return h

    BOX_H = max((_stage_height(m) for m in stage_metrics), default=0) + TOP_PAD
    H = BOX_H + round(TOP_PAD * 2)

    img = Image.new('RGB', (W, H), RGB['white'])
    d   = ImageDraw.Draw(img)

    for i, stage in enumerate(stages):
        cx   = 17 + i * (BOX_W + 37)
        crgb = hex_to_rgb(PALETTE[i % len(PALETTE)])
        primary, secondary = _text_colors_for_bg(crgb)
        name_lines, en_lines, comp_lines, cat_lines = stage_metrics[i]

        # 배경 박스
        d.rectangle([cx, TOP_PAD, cx + BOX_W, TOP_PAD + BOX_H],
                    fill=crgb, outline=crgb, width=2)
        y = TOP_PAD + round(TOP_PAD * 0.3)
        # STEP 번호
        d.text((cx + 14, y), f'STEP {stage.get("stage_order", i+1)}',
               fill=primary, font=step_f)
        y += STEP_LINE
        # 단계명 (한글, 줄바꿈)
        for line in name_lines:
            d.text((cx + 14, y), line, fill=primary, font=name_f)
            y += NAME_LINE
        # 영문명 (줄바꿈)
        for line in en_lines:
            d.text((cx + 14, y), line, fill=secondary, font=en_f)
            y += EN_LINE
        # 대표 기업 (줄바꿈, 잘라내지 않음)
        for lines in comp_lines:
            for li, line in enumerate(lines):
                prefix_x = cx + 17 if li == 0 else cx + 24
                d.text((prefix_x, y), line, fill=primary, font=item_f)
                y += ITEM_LINE
        # 카테고리 (줄바꿈, 잘라내지 않음)
        for lines in cat_lines:
            for li, line in enumerate(lines):
                prefix_x = cx + 17 if li == 0 else cx + 24
                d.text((prefix_x, y), line, fill=secondary, font=item_f)
                y += ITEM_LINE

        # 화살표 (마지막 제외)
        if i < N - 1:
            ax_x = cx + BOX_W + 3
            ay   = TOP_PAD + BOX_H // 2
            arrow_h = max(12, round(BOX_W * 0.06))
            d.polygon([(ax_x, ay - arrow_h), (ax_x + round(arrow_h * 1.8), ay),
                       (ax_x, ay + arrow_h)], fill=RGB['gray'])

    _save_pil(img, fname)


# ══════════════════════════════════════════════════════════════════
# V3_2: 가치사슬(Value Chain) 분석
# ══════════════════════════════════════════════════════════════════
def v3_2(sec3: dict, src: str) -> bool:
    cap = f'가치사슬 구조 (출처: {src})'
    if _try_reuse_image('V3_2', 'V3_2_value_chain.png', 3, '가치사슬 구조', cap,
                         sec3.get('value_chain_image')):
        return True

    vc = sec3.get('value_chain', [])
    if not vc:
        _reg('V3_2', 'V3_2_value_chain.png', 3, '', '', 'skipped',
             '가치사슬 데이터 없음')
        return False

    _flow_diagram(vc, 'V3_2_value_chain.png')
    _reg('V3_2', 'V3_2_value_chain.png', 3, '가치사슬 구조', cap, 'generated')
    return True


# ══════════════════════════════════════════════════════════════════
# V3_3: 공급망(Supply Chain) 분석
# ══════════════════════════════════════════════════════════════════
def v3_3(sec3: dict, src: str) -> bool:
    cap = f'공급망 구조 (출처: {src})'
    if _try_reuse_image('V3_3', 'V3_3_supply_chain.png', 3, '공급망 구조', cap,
                         sec3.get('supply_chain_image')):
        return True

    sc = sec3.get('supply_chain', [])
    if not sc:
        _reg('V3_3', 'V3_3_supply_chain.png', 3, '', '', 'skipped',
             '공급망 데이터 없음')
        return False

    _flow_diagram(sc, 'V3_3_supply_chain.png')
    _reg('V3_3', 'V3_3_supply_chain.png', 3, '공급망 구조', cap, 'generated')
    return True


# ══════════════════════════════════════════════════════════════════
# V4_1: 권역별 시장규모 묶음 막대
# ══════════════════════════════════════════════════════════════════
def v4_1(sec4: dict, tf: str, src: str, unit: str = '$B') -> bool:
    regions = sec4.get('regions', [])
    years   = sec4.get('years', [])
    glb     = sec4.get('global_size', [])

    if not regions or not years:
        _reg('V4_1', 'V4_1_regional_market.png', 4, '', '', 'skipped',
             '지역별 데이터 없음')
        return False

    n_yr  = len(years)
    series: list = []
    if glb and len(glb) >= n_yr:
        series.append(('글로벌 (Global)', glb[:n_yr], PALETTE[0]))
    for i, r in enumerate(regions[:4]):
        sz = r.get('sizes_usd_b', [])
        if sz and len(sz) >= n_yr:
            series.append((_wrap_label(r.get('name', f'지역{i+1}')), sz[:n_yr], PALETTE[i+1]))

    if not series:
        _reg('V4_1', 'V4_1_regional_market.png', 4, '', '', 'skipped', '유효 수치 없음')
        return False

    FIG_W = 12
    x = np.arange(n_yr)
    data_pt = mpl_pt('data_label', FIG_W)
    fig, ax = plt.subplots(figsize=(FIG_W, 6.5))
    # 연도가 많을 때(예: 2024~2035년 12개) 묶은 막대 + 막대마다 수치 라벨을 쓰면
    # 막대·라벨이 촘촘히 붙어 서로 겹친다 — 연 단위 시계열은 막대보다 선그래프가
    # 적합하므로 선그래프로 그리고, 라벨도 매 지점이 아니라 시작·끝점에만 달아
    # 밀집을 피한다.
    ymax = max(max(vals) for _, vals, _ in series)
    for i, (lbl, vals, col) in enumerate(series):
        ax.plot(x, vals, marker='o', lw=2.2, ms=6, color=col, label=lbl)

    # 시작점·끝점 수치 라벨: 여러 계열의 값이 같은 x에서 비슷하면 라벨이 겹치므로
    # 값 순서를 지키며 세로 위치를 최소 간격만큼 벌린다(_declutter_y).
    for xi in (0, n_yr - 1):
        col_vals = [(vals[xi], col) for _, vals, col in series]
        ty_list = _declutter_y([v for v, _ in col_vals], ymax)
        for (val, col), ty in zip(col_vals, ty_list):
            va = 'bottom' if ty < ymax * 0.92 else 'top'
            offset_pt = 6 if va == 'bottom' else -8
            ax.annotate(f'{val:.1f}', (x[xi], ty), xytext=(0, offset_pt),
                        textcoords='offset points', ha='center', va=va,
                        fontsize=data_pt, color=col)

    ax.set_xlabel('연도', fontsize=mpl_pt('axis_label', FIG_W))
    ax.set_ylabel(f'시장규모 ({unit})', fontsize=mpl_pt('axis_label', FIG_W))
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years])
    ax.set_facecolor(C['light_bg'])
    ax.grid(alpha=0.3)
    ax.set_ylim(0, ymax * 1.18)
    _style_axes(ax, FIG_W)
    handles, labels = ax.get_legend_handles_labels()
    _legend_above(fig, handles, labels, mpl_pt('legend', FIG_W), min(5, len(series)))
    _savefig('V4_1_regional_market.png')
    _reg('V4_1', 'V4_1_regional_market.png', 4,
         '지역별 시장규모',
         f'그림 6. 지역별 시장규모 (출처: {src})', 'generated')
    return True


# (V4_2: 권역별 기회·리스크 매트릭스는 더 이상 그림으로 만들지 않는다 — 바로 앞
# 섹션에서 동일한 데이터를 이미 표(table)로 삽입하고 있어 중복이었고, 표 형태의
# 데이터는 이미지가 아니라 표로 넣는 것이 원칙이다. generate_docx.py/generate_hwpx.py
# 모두 이 표만 쓰고 그림은 더 이상 호출하지 않는다.)


# ══════════════════════════════════════════════════════════════════
# V5_x: 세그먼트 묶음 막대 (공통 함수)
# ══════════════════════════════════════════════════════════════════
def v5_segment(chart_id: str, title: str, seg_data: dict,
               years: list, src: str, fig_num: int, unit: str = '$B') -> bool:
    fname = f'{chart_id}.png'
    segs  = seg_data.get('segments', [])
    n_yr  = len(years)
    valid = [(_wrap_label(s.get('name', f'S{i}'), 18), s.get('sizes', []))
             for i, s in enumerate(segs)
             if s.get('sizes') and len(s['sizes']) >= n_yr]

    if not valid:
        _reg(chart_id, fname, 5, title, '', 'skipped', '세그먼트 데이터 없음')
        return False

    FIG_W = 12
    x = np.arange(n_yr)
    w = min(0.8, 0.8 / len(valid))
    fig, ax = plt.subplots(figsize=(FIG_W, 6.5))
    ymax = max(max(vals[:n_yr]) for _, vals in valid)
    # 세그먼트가 많으면(5개 초과) 막대 폭이 좁아져 가로 라벨("42.0")이 옆 막대
    # 라벨과 겹친다(실측 확인) — 이때는 라벨을 세로로 세워 좁은 폭 안에서도
    # 겹치지 않게 하고, 세로 라벨이 차지할 위쪽 공간을 더 확보한다.
    rotate = len(valid) > 5
    for i, (name, vals) in enumerate(valid):
        offset = (i - len(valid) / 2 + 0.5) * w
        bars = ax.bar(x + offset, vals[:n_yr], w,
                      label=name, color=PALETTE[i % len(PALETTE)], alpha=0.9)
        _bar_labels(ax, bars, fontsize=mpl_pt('data_label', FIG_W),
                    rotation=90 if rotate else 0)

    ax.set_xlabel('연도', fontsize=mpl_pt('axis_label', FIG_W))
    # y축 지표명은 축 데이터에서 덮어쓸 수 있다 — 세그먼트 값이 시장규모가 아니라
    # 자본 약정액·투자액 등인 보고서에서 '시장규모'로 고정 표기하면 사실과 다르다.
    ax.set_ylabel(f'{value_label(seg_data)} ({unit})',
                  fontsize=mpl_pt('axis_label', FIG_W))
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years])
    ax.set_facecolor(C['light_bg'])
    ax.grid(axis='y', alpha=0.3)
    # 막대 위 수치 라벨이 그래프 위쪽 테두리에 붙지 않도록 여유를 준다
    # (세로 라벨은 가로 라벨보다 위쪽으로 더 많은 공간을 차지하므로 여유를 더 준다)
    ax.set_ylim(0, ymax * (1.35 if rotate else 1.18))
    _style_axes(ax, FIG_W)
    # 세그먼트가 많을 때(예: 7개) 범례가 2줄로 늘어날 수 있어 legend용 공간을
    # 넉넉히 예약한다(top=0.82) — 세그먼트가 적으면 남는 공간은 bbox_inches='tight'가
    # 잘라내므로 손해가 없다.
    ncol = min(4, len(valid))
    rows = -(-len(valid) // ncol)  # ceil
    top = 0.88 if rows <= 1 else 0.82
    handles, labels = ax.get_legend_handles_labels()
    _legend_above(fig, handles, labels, mpl_pt('legend', FIG_W), ncol, top=top)
    _savefig(fname)
    _reg(chart_id, fname, 5, title,
         f'그림 {fig_num}. {title} (출처: {src})', 'generated')
    return True


# ══════════════════════════════════════════════════════════════════
# V6_1: 기술 채택률 추이 꺾은선
# ══════════════════════════════════════════════════════════════════
def v6_1(sec5: dict, tf: str, src: str) -> bool:
    """series가 2개뿐이라고 가정하고 처음 2개만 그리면 안 된다 — 실제 보고서에는
    냉각 방식별(액체·공랭·증발·프리쿨링 등) 4개 이상 series가 들어오는 경우가 있는데,
    2개만 처리하면 나머지가 조용히 누락된다(실측 확인). 또한 y축 상한을 series[0]
    값만으로 정하면(예: 액체냉각 17~19%) 다른 series의 값이 그보다 훨씬 크거나
    작을 때(예: 공랭식 66~68%) 그 선이 축 상단 바깥으로 밀려나 화면에서 사라진
    것처럼 보인다(실측 확인 — "그래프가 사라졌다"는 버그) — 반드시 모든 series의
    값을 합쳐 y축 상한을 정한다."""
    at      = sec5.get('adoption_trend', {})
    years   = at.get('years', [])
    series  = at.get('series', [])
    valid   = [(s.get('label', f'시나리오 {i+1}'), s.get('values_pct', []))
               for i, s in enumerate(series)
               if s.get('values_pct') and len(s['values_pct']) == len(years)]

    if not years or not valid:
        _reg('V6_1', 'V6_1_adoption_trend.png', 6, '', '', 'skipped',
             '채택률 데이터 없음')
        return False

    FIG_W = 10
    data_pt = mpl_pt('data_label', FIG_W)
    fig, ax = plt.subplots(figsize=(FIG_W, 6))
    styles = ['o-', 's--', '^-.', 'd:', 'v-', 'P--']
    all_vals = [v for _, vals in valid for v in vals]
    ymax = max(all_vals) * 1.3 if all_vals else 100

    for i, (label, vals) in enumerate(valid):
        col = PALETTE[i % len(PALETTE)]
        ax.plot(years, vals, styles[i % len(styles)], color=col, lw=2, ms=6, label=label)

    # 같은 연도에서 여러 series의 값이 비슷하면 라벨이 겹치므로(예: 증발냉각·프리쿨링이
    # 둘 다 6~9% 부근) 값 순서를 지키며 라벨 y좌표만 최소 간격만큼 벌린다(_declutter_y).
    for xi, yr in enumerate(years):
        col_vals = [(vals[xi], PALETTE[i % len(PALETTE)]) for i, (_, vals) in enumerate(valid)]
        ty_list = _declutter_y([v for v, _ in col_vals], ymax)
        for (val, col), ty in zip(col_vals, ty_list):
            ax.annotate(f'{val:.1f}%', (yr, ty), xytext=(0, 9),
                        textcoords='offset points', ha='center',
                        fontsize=data_pt, color=col)

    ax.set_xlabel('연도', fontsize=mpl_pt('axis_label', FIG_W))
    ax.set_ylabel('채택률 (%)', fontsize=mpl_pt('axis_label', FIG_W))
    ax.set_facecolor(C['light_bg'])
    ax.grid(alpha=0.3)
    _style_axes(ax, FIG_W)
    ax.set_ylim(0, ymax)
    handles, labels = ax.get_legend_handles_labels()
    _legend_above(fig, handles, labels, mpl_pt('legend', FIG_W), len(handles))
    _savefig('V6_1_adoption_trend.png')
    _reg('V6_1', 'V6_1_adoption_trend.png', 6,
         '기술 채택률 추이',
         f'그림 11. 기술 채택률 전망 (출처: {src})', 'generated')
    return True


# ══════════════════════════════════════════════════════════════════
# V6_2: 기업별 특허 출원 건수 (로그 스케일 가로 막대)
# ══════════════════════════════════════════════════════════════════
def v6_2(sec6: dict, src: str) -> bool:
    pt = sec6.get('patent_trend', {})
    detail = pt.get('top_companies_detail', [])
    if not detail:
        _reg('V6_2', 'V6_2_patent_countries.png', 6, '', '', 'skipped',
             '특허 기업별 데이터 없음')
        return False

    # 지표 라벨/단위는 데이터에 따라 가변 — 원문이 특허 건수면 기본값('특허 출원 건수'/'건'),
    # 파이프라인 자산 수 등 다른 지표면 patent_trend.metric_label/metric_unit로 덮어쓴다.
    metric_label = pt.get('metric_label', '특허 출원 건수')
    metric_unit  = pt.get('metric_unit', '건')

    top = detail[:8]
    companies = [_wrap_label(d.get('company', ''), 26) for d in top][::-1]
    counts    = [d.get('count', 0) for d in top][::-1]

    FIG_W = 10
    fig, ax = plt.subplots(figsize=(FIG_W, 6))
    bars = ax.barh(companies, counts, color=C['navy'])
    ax.set_xscale('log')
    for b, v in zip(bars, counts):
        ax.annotate(f'{v:,}{metric_unit}', (b.get_width(), b.get_y() + b.get_height() / 2),
                    xytext=(6, 0), textcoords='offset points',
                    va='center', fontsize=mpl_pt('data_label', FIG_W))

    ax.set_xlabel(f'{metric_label} (로그 스케일)', fontsize=mpl_pt('axis_label', FIG_W))
    ax.set_facecolor(C['light_bg'])
    ax.grid(axis='x', alpha=0.3, which='both')
    _style_axes(ax, FIG_W)
    plt.tight_layout()
    _savefig('V6_2_patent_countries.png')
    _reg('V6_2', 'V6_2_patent_countries.png', 6,
         f'기업별 {metric_label}',
         f'기업별 {metric_label} (출처: {src})', 'generated')
    return True


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════
def main():
    os.makedirs(CHARTS, exist_ok=True)
    setup_mpl_font()

    master_path = os.path.join(STRUCTURED, 'master_dataset.json')
    if not os.path.exists(master_path):
        print('master_dataset.json 없음 — analyze_sections.py를 먼저 실행하세요.')
        sys.exit(1)

    with open(master_path, encoding='utf-8') as f:
        md = json.load(f)

    tf   = md.get('tech_field', '기술분야')
    sec1 = md.get('market_overview', {})
    sec2 = md.get('market_dynamics', {})
    sec3 = md.get('ecosystem', {})
    sec4 = md.get('regional_analysis', {})
    sec5 = md.get('segmentation', {})
    sec6 = md.get('rnd_trends', {})
    src  = sec1.get('source_report', '원본 보고서')
    unit = sec1.get('currency_unit', '$B')

    print(f'\n[STEP 4] 차트·인포그래픽 생성 — {tf}')
    print(f'  한글 폰트: {os.path.basename(FONT_PATH) if FONT_PATH else "없음 (영문 폰트 사용)"}')

    # ── V1: 시장 개요 ─────────────────────────────────────────────
    print('\n  [V1] 시장 개요 차트...')
    v1_1(sec1, tf, src)
    v1_2(sec1, tf, src)   # v1_2 내부에서 sec1['currency_unit']을 직접 읽음

    # ── V2: 시장 역학 ─────────────────────────────────────────────
    print('  [V2] 시장 역학 인포그래픽...')
    v2_1(sec2, src)

    # ── V3: 생태계 ────────────────────────────────────────────────
    print('  [V3] 공급망·가치사슬·생태계 맵 인포그래픽...')
    v3_3(sec3, src)
    v3_2(sec3, src)
    v3_1(sec3, src)

    # ── V4: 지역별 ────────────────────────────────────────────────
    print('  [V4] 지역별 분석 차트...')
    v4_1(sec4, tf, src, unit)

    # ── V5: 세그먼트 (보고서마다 실제 분류 축이 다르므로 데이터 기반으로 처리) ──
    print('  [V5] 세그먼트 차트 (4종 필수 + 3종 선택)...')
    years = sec5.get('years', [])
    MAIN_SLOTS   = ['V5_1_end_use', 'V5_2_dc_type', 'V5_3_solution', 'V5_4_rack_density']
    DETAIL_SLOTS = ['V5_5_air_sub', 'V5_6_liquid_dir', 'V5_7_immersion']

    axes = sec5.get('axes', [])
    for i, cid in enumerate(MAIN_SLOTS):
        fn = 8 + i
        axis = axes[i] if i < len(axes) else {}
        label = axis.get('label', f'세그먼트{i+1}')
        if axis.get('segments'):
            v5_segment(cid, f'{seg_title(axis, f"세그먼트{i+1}")} ({unit})',
                       axis, years, src, fn, unit)
        else:
            _reg(cid, f'{cid}.png', 5, label, '', 'skipped', '세그먼트 데이터 없음')

    detail_axes = sec5.get('detail_axes', [])
    for i, cid in enumerate(DETAIL_SLOTS):
        fn = 12 + i
        axis = detail_axes[i] if i < len(detail_axes) else {}
        segs = axis.get('segments', [])
        label = axis.get('label', f'세부분류{i+1}')
        if not segs or not isinstance(segs[0], dict):
            _reg(cid, f'{cid}.png', 5, label, '', 'skipped', '세부 세그먼트 없음')
        else:
            v5_segment(cid, f'{seg_title(axis, f"세부분류{i+1}")} ({unit})',
                       axis, years, src, fn, unit)

    # ── V6: 채택률 추이 / 특허 동향 ───────────────────────────────
    print('  [V6] 채택률 추이 차트...')
    v6_1(sec5, tf, src)
    v6_2(sec6, src)

    # 카탈로그 저장
    _save_catalog()

    # DPI 검증
    dpi_fail = []
    for entry in _catalog['charts']:
        if entry['status'] == 'generated':
            p = os.path.join(CHARTS, entry['filename'])
            if os.path.exists(p):
                try:
                    with Image.open(p) as im:
                        dpi_info = im.info.get('dpi', (DPI, DPI))
                        if dpi_info[0] < DPI:
                            dpi_fail.append(entry['filename'])
                except Exception:
                    pass

    # 로그
    log = {
        'timestamp':       datetime.now().isoformat(),
        'total_generated': _catalog['total_generated'],
        'total_skipped':   _catalog['total_skipped'],
        'dpi_fail':        dpi_fail,
        'font_used':       os.path.basename(FONT_PATH) if FONT_PATH else 'default',
        'step4_status':    'success' if _catalog['total_generated'] >= 9 else 'partial',
    }
    with open(os.path.join(LOG_DIR, 'step4_charts.json'), 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    # 필수 차트 충족 확인
    REQ = {'V1_1', 'V1_2', 'V2_1', 'V3_1', 'V3_2', 'V4_1',
           'V5_1_end_use', 'V5_2_dc_type', 'V5_3_solution', 'V5_4_rack_density'}
    gen_ids   = {c['chart_id'] for c in _catalog['charts'] if c['status'] in ('generated', 'reused')}
    missing_r = REQ - gen_ids
    skipped_s = [(c['chart_id'], c['skip_reason'][:30])
                 for c in _catalog['charts'] if c['status'] == 'skipped']

    print(f'\n✅ STEP 4 완료')
    print(f'  생성된 차트: {_catalog["total_generated"]}개')
    print(f'  재활용된 원본 이미지: 0개')
    if skipped_s:
        preview = '; '.join(f'{cid}({r})' for cid, r in skipped_s[:4])
        print(f'  생략된 차트: {_catalog["total_skipped"]}개  ({preview})')
    else:
        print(f'  생략된 차트: 0개')
    meets = 'yes' if not missing_r else f'no (미생성: {", ".join(sorted(missing_r))})'
    print(f'  필수 차트 기준 충족: {meets}')
    print(f'  한글 폰트 적용: {"yes (" + os.path.basename(FONT_PATH) + ")" if FONT_PATH else "no"}')
    print(f'\n  → 다음 단계: python generate_hwpx.py')


if __name__ == '__main__':
    main()
