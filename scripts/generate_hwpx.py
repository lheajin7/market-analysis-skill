#!/usr/bin/env python3
"""
STEP 5: 한글 보고서 본문 생성 (HWPX 조립)

사전 조건: analyze_sections.py + generate_charts.py 실행 완료

사용법:
  python generate_hwpx.py

패키지 구조는 실제 HWPX(OWPML, KS X 6101) 스펙을 따른다:
  mimetype(무압축·최상단) + version.xml + settings.xml
  + Contents/{header.xml, section0.xml, content.hpf}
  + META-INF/{container.xml, container.rdf, manifest.xml}
  + Preview/{PrvText.txt, PrvImage.png} + BinData/*
정적 템플릿 파일은 scripts/hwpx_template/ 에서 그대로 복사하고,
section0.xml·content.hpf 만 실행 시점에 동적으로 생성한다.
"""

import json
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime

from lxml import etree as ET
from PIL import Image, ImageDraw, ImageFont

from _common import get_base, seg_title

# ──────────────────────────────────────────────────────────────────
# 경로 상수
# ──────────────────────────────────────────────────────────────────
BASE        = get_base()
WORKSPACE   = os.path.join(BASE, 'workspace')
STRUCTURED  = os.path.join(WORKSPACE, 'structured')
CHARTS      = os.path.join(WORKSPACE, 'charts')
HWPX_BUILD  = os.path.join(WORKSPACE, 'hwpx_build')
OUTPUT_DIR  = os.path.join(WORKSPACE, 'output')
LOG_DIR     = os.path.join(WORKSPACE, 'logs')

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
HWPX_TEMPLATE = os.path.join(SCRIPT_DIR, 'hwpx_template')

# ──────────────────────────────────────────────────────────────────
# XML 네임스페이스 (실제 HWPX/OWPML 스펙 — KS X 6101)
# ──────────────────────────────────────────────────────────────────
NS = {
    'ha':          'http://www.hancom.co.kr/hwpml/2011/app',
    'hp':          'http://www.hancom.co.kr/hwpml/2011/paragraph',
    'hp10':        'http://www.hancom.co.kr/hwpml/2016/paragraph',
    'hs':          'http://www.hancom.co.kr/hwpml/2011/section',
    'hc':          'http://www.hancom.co.kr/hwpml/2011/core',
    'hh':          'http://www.hancom.co.kr/hwpml/2011/head',
    'hhs':         'http://www.hancom.co.kr/hwpml/2011/history',
    'hm':          'http://www.hancom.co.kr/hwpml/2011/master-page',
    'hpf':         'http://www.hancom.co.kr/schema/2011/hpf',
    'dc':          'http://purl.org/dc/elements/1.1/',
    'opf':         'http://www.idpf.org/2007/opf/',
    'ooxmlchart':  'http://www.hancom.co.kr/hwpml/2016/ooxmlchart',
    'hwpunitchar': 'http://www.hancom.co.kr/hwpml/2016/HwpUnitChar',
    'epub':        'http://www.idpf.org/2007/ops',
    'config':      'urn:oasis:names:tc:opendocument:xmlns:config:1.0',
}


def qn(prefix: str, tag: str) -> str:
    return f'{{{NS[prefix]}}}{tag}'


# 표준 여백: 위·아래 2.54cm(=7200 HWPUNIT, 1인치와 정확히 일치), 좌·우 1.9cm(=5386
# HWPUNIT). generate_docx.py도 동일 여백을 쓰므로 두 포맷의 본문 폭이 거의 같아지고,
# generate_charts.py의 DOCX_WIDTH_IN/HWPX_WIDTH_IN(차트 폰트 크기 역산 기준)도 이
# 값과 일치시켜야 한다 — 여백을 바꾸면 세 곳 모두 함께 갱신할 것.
MARGIN_TOP_BOTTOM = 7200            # 2.54cm
MARGIN_LEFT_RIGHT = 5386            # 1.9cm
# 본문 영역 폭(HWPUNIT) = 페이지폭(59528) - 좌우 여백(5386*2) = 48756
CONTENT_WIDTH = 59528 - 2 * MARGIN_LEFT_RIGHT

# matplotlib/Pillow로 생성하는 차트는 본문 폭에 꽉 채워도 보통 3.5~4.5in 높이로 나오지만,
# 원본 보고서에서 재활용하는 이미지(*_image 필드)는 정사각형에 가까운 경우가 있어(예:
# 4단계 가치사슬 다이어그램 974x924px) 본문 폭에 그대로 맞추면 세로로 5.5in 이상 길어져
# 다른 그림보다 눈에 띄게 커 보인다(실측 확인, 사용자 피드백) — generate_docx.py의
# MAX_IMAGE_HEIGHT_IN과 동일한 값(7200 hwpunit = 1in 기준)을 세로 높이 상한으로 둔다.
MAX_IMAGE_HEIGHT = round(4.5 * 7200)

# 개조식 문단 1개당 최대 5줄(10pt 본문 기준 1줄≈40자 → 약 200자)을 넘지 않도록 분할한다.
MAX_PARA_CHARS = 200


def _eun_neun(word: str) -> str:
    """마지막 글자의 받침 유무에 따라 '은'/'는' 조사를 고른다(generate_docx.py와 동일)."""
    if not word:
        return '은(는)'
    code = ord(word[-1]) - 0xAC00
    if 0 <= code <= 11171:
        return '는' if code % 28 == 0 else '은'
    return '은(는)'




def _split_para(text: str, max_chars: int = MAX_PARA_CHARS) -> list:
    """5줄(약 200자) 초과 문단을 문장 경계에서 잘라 개조식 여러 항목으로 나눈다."""
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r'(?<=[.!?])\s+|(?<=함\.)\s*|(?<=음\.)\s*|(?<=됨\.)\s*', text)
    chunks, cur = [], ''
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if cur and len(cur) + len(s) + 1 > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur = f'{cur} {s}'.strip() if cur else s
    if cur:
        chunks.append(cur)
    return chunks or [text]


def _lineseg(height: int, width: int = CONTENT_WIDTH) -> dict:
    """charPr height(1/100pt)에 비례한 lineseg 값 계산 (실제 hwpx 샘플 3종 실측 비율)."""
    return {
        'textpos': '0', 'vertpos': '0',
        'vertsize': str(height), 'textheight': str(height),
        'baseline': str(round(height * 0.85)),
        'spacing':  str(round(height * 0.6)),
        'horzpos': '0', 'horzsize': str(width), 'flags': '393216',
    }


# ──────────────────────────────────────────────────────────────────
# 줄바꿈 추정 — 글자수 어림값이 아니라 실제 폰트 메트릭으로 측정한다
# ──────────────────────────────────────────────────────────────────
# 예전에는 "10pt·특정 폭에서 한글 40자/줄" 같은 어림 비율로 줄 수를 추정했는데, 이
# 비율이 실제 렌더 폭과 안 맞으면(여백을 바꿔 폭이 달라지거나, 영문·숫자가 섞여
# 문자당 폭이 다르면) 우리가 써넣는 linesegarray의 줄 수·줄 폭이 실제보다 틀리게
# 되고, 한컴오피스는 문서를 열 때 이 값을 그대로 신뢰해 보여주므로(재계산하지 않음)
# 왼쪽 정렬 문단이 오른쪽 끝까지 못 미치고 일찍 줄바꿈되는 문제가 생긴다(pyhwpx로
# 실제 한컴오피스를 자동화해 직접 렌더링해 확인된 버그). generate_charts.py가 이미
# Pillow 차트에서 하고 있는 것과 동일하게, 여기서도 실제 폰트(NanumGothic, 본문
# 폰트인 함초롬바탕과 100% 동일하진 않지만 CJK 고정폭 특성이 비슷해 신뢰할 만한
# 근사치를 준다)로 글자 폭을 직접 측정해 줄바꿈 지점을 계산한다.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MEASURE_FONT_PATH = os.path.join(_SCRIPT_DIR, 'assets', 'NanumGothic.ttf')
_MEASURE_DPI = 150   # HWPUNIT(7200/inch) ↔ 픽셀 환산 기준. generate_charts.py의 DPI와 통일.
_measure_draw = ImageDraw.Draw(Image.new('RGB', (10, 10)))
_font_cache: dict = {}


def _measure_font(height: int) -> ImageFont.FreeTypeFont:
    """charPr height(1/100pt)에 해당하는 측정용 폰트를 반환한다(캐시됨)."""
    px = max(6, round((height / 100) * _MEASURE_DPI / 72))
    font = _font_cache.get(px)
    if font is None:
        font = ImageFont.truetype(_MEASURE_FONT_PATH, px)
        _font_cache[px] = font
    return font


def _wrap_lines(text: str, height: int, width: int) -> list:
    """실제 폰트로 텍스트 폭을 측정해 width(HWPUNIT) 안에 들어가도록 줄바꿈한다."""
    text = str(text)
    if not text:
        return ['']
    font = _measure_font(height)
    max_px = width / 7200 * _MEASURE_DPI
    words = text.split(' ')
    lines, cur = [], ''
    for w in words:
        test = f'{cur} {w}'.strip()
        tw = _measure_draw.textlength(test, font=font)
        if tw <= max_px or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [text]


def _estimate_lines(text: str, height: int, width: int = CONTENT_WIDTH) -> int:
    """폭(width)·글자크기(height)를 기준으로 실제 폰트 메트릭을 측정해 줄 수를 구한다."""
    if not text:
        return 1
    return max(1, len(_wrap_lines(text, height, width)))


# ══════════════════════════════════════════════════════════════════
# HWPXBuilder: 실제 hp:/hs:/hc: 스키마 기반 section0.xml 조립
# ══════════════════════════════════════════════════════════════════

class HWPXBuilder:
    """단락·이미지·테이블을 누적해 Contents/section0.xml 을 생성한다.

    스타일 ID (Contents/header.xml 기준, 참조 템플릿 폰트 계층에 맞춤):
      charPr : 0=본문  7=제목1(navy bold 18pt)  8=제목2(navy bold 13pt)
               9=볼드본문(10pt)  10=캡션(gray 9pt)
      paraPr : 0=본문(justify)  20=가운데(이미지/캡션)  21=제목용 간격
      borderFill : 3=표 테두리(옅은 회색 실선)

    본문/불릿 문단은 1개당 5줄(약 200자)을 넘지 않도록 _split_para()로 자동 분할한다.
    """

    def __init__(self):
        self._id_counter = 2_000_000_000
        self._paras: list = []
        self._images: list = []   # (image_id, filename, media_type)
        self.fig_n = 0   # 그림 번호 자동 채번 — 호출 순서대로 1부터 증가
        self.tbl_n = 0   # 표 번호 자동 채번

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter

    # ── 이미지 등록 ───────────────────────────────────────────────
    def register_image(self, fname: str) -> str:
        image_id = f'image{len(self._images) + 1}'
        ext = os.path.splitext(fname)[1].lstrip('.').lower() or 'png'
        media_type = f'image/{"jpeg" if ext == "jpg" else ext}'
        self._images.append((image_id, fname, media_type))
        return image_id

    # ── 단락/런 헬퍼 ─────────────────────────────────────────────
    def _make_p(self, para_pr: int, style_id: int = 0) -> ET._Element:
        p = ET.Element(qn('hp', 'p'))
        p.set('id', str(self._next_id()))
        p.set('paraPrIDRef', str(para_pr))
        p.set('styleIDRef', str(style_id))
        p.set('pageBreak', '0')
        p.set('columnBreak', '0')
        p.set('merged', '0')
        return p

    def _add_lineseg(self, p: ET._Element, height: int, text: str = '',
                      width: int = CONTENT_WIDTH):
        """실제 줄바꿈 줄 수만큼 lineseg를 추가한다 — 1줄만 선언하면 여러 줄로
        줄바꿈되는 문단/셀의 세로 공간이 부족해 다음 문단과 텍스트가 겹쳐 보인다."""
        arr = ET.SubElement(p, qn('hp', 'linesegarray'))
        lines = _wrap_lines(text, height, width) if text else ['']
        pitch = round(height * 1.6)
        base_vals = _lineseg(height, width)
        pos = 0
        for i, line in enumerate(lines):
            seg = ET.SubElement(arr, qn('hp', 'lineseg'))
            vals = dict(base_vals)
            vals['vertpos'] = str(i * pitch)
            vals['textpos'] = str(min(pos, max(0, len(text) - 1)))
            for k, v in vals.items():
                seg.set(k, v)
            # 다음 줄 시작 문자 위치: 이번 줄 글자 수 + 줄바꿈 시 소비된 공백 1칸
            pos += len(line) + 1

    def _text_paragraph(self, text: str, char_pr: int, para_pr: int,
                         height: int, style_id: int = 0,
                         width: int = CONTENT_WIDTH) -> ET._Element:
        p = self._make_p(para_pr, style_id)
        run = ET.SubElement(p, qn('hp', 'run'))
        run.set('charPrIDRef', str(char_pr))
        t = ET.SubElement(run, qn('hp', 't'))
        t.text = text
        self._add_lineseg(p, height, text, width)
        return p

    # ── 공개 단락 메서드 ─────────────────────────────────────────
    def h1(self, text: str):
        self._paras.append(self._text_paragraph(text, 7, 21, 1800))

    def h2(self, text: str):
        self._paras.append(self._text_paragraph(text, 8, 21, 1300))

    def normal(self, text: str, bold: bool = False):
        for chunk in _split_para(text):
            self._paras.append(self._text_paragraph(chunk, 9 if bold else 0, 22, 1000))

    def bullet(self, text: str):
        for chunk in _split_para(text):
            self._paras.append(self._text_paragraph(f'• {chunk}', 0, 22, 1000))

    def caption(self, text: str):
        self._paras.append(self._text_paragraph(text, 10, 20, 1100))

    def empty(self):
        p = self._make_p(0)
        run = ET.SubElement(p, qn('hp', 'run'))
        run.set('charPrIDRef', '0')
        ET.SubElement(run, qn('hp', 't'))
        self._add_lineseg(p, 1000)
        self._paras.append(p)

    # ── 이미지 단락 ──────────────────────────────────────────────
    def image(self, fname: str, title: str, desc: str = '',
              w: int = 0, h: int = 0):
        """표(table)와 동일하게 본문 폭(CONTENT_WIDTH)에 꽉 채워 삽입한다.
        캡션은 "그림 N. 제목" 형태로 자동 채번한다(generate_docx.py의
        DocxBuilder.image()와 동일한 규칙 — 출처는 표지에만 싣고 여기서는
        반복하지 않는다). desc는 실제 내용(구체적 수치 등)이 있을 때만 넘긴다.

        w/h를 넘기지 않으면(기본값 0) BinData에 이미 복사된 실제 PNG 파일을 열어
        원본 종횡비를 읽는다 — 예전에는 항상 고정값(14400×7200, 2:1)을 썼는데
        실제 차트 이미지들은 이 비율과 달라서(V2_1 등은 세로로 더 김) 세로로
        눌린 채 삽입되어 그 안의 글씨가 비정상적으로 커/뭉개져 보이는 왜곡이
        있었다(실측 확인됨). 반드시 실제 파일의 비율을 읽어써야 한다."""
        image_id = self.register_image(fname)

        if not w or not h:
            bin_path = os.path.join(HWPX_BUILD, 'BinData', fname)
            try:
                with Image.open(bin_path) as im:
                    w, h = im.size
            except Exception:
                w, h = 14400, 7200

        real_w = CONTENT_WIDTH
        real_h = max(1, round(real_w * h / w)) if w else real_w
        if real_h > MAX_IMAGE_HEIGHT:
            real_h = MAX_IMAGE_HEIGHT
            real_w = max(1, round(real_h * w / h)) if h else real_w

        p = self._make_p(20)  # 가운데 정렬
        run = ET.SubElement(p, qn('hp', 'run'))
        run.set('charPrIDRef', '0')

        pic = ET.SubElement(run, qn('hp', 'pic'))
        pic.set('id', str(self._next_id()))
        pic.set('zOrder', '0')
        pic.set('numberingType', 'PICTURE')
        pic.set('textWrap', 'TOP_AND_BOTTOM')
        pic.set('textFlow', 'BOTH_SIDES')
        pic.set('lock', '0')
        pic.set('dropcapstyle', 'None')
        pic.set('href', '')
        pic.set('groupLevel', '0')
        pic.set('instid', str(self._next_id()))
        pic.set('reverse', '0')

        ET.SubElement(pic, qn('hp', 'offset')).set('x', '0')
        pic[-1].set('y', '0')

        org = ET.SubElement(pic, qn('hp', 'orgSz'))
        org.set('width', str(real_w)); org.set('height', str(real_h))
        cur = ET.SubElement(pic, qn('hp', 'curSz'))
        cur.set('width', str(real_w)); cur.set('height', str(real_h))

        flip = ET.SubElement(pic, qn('hp', 'flip'))
        flip.set('horizontal', '0'); flip.set('vertical', '0')

        rot = ET.SubElement(pic, qn('hp', 'rotationInfo'))
        rot.set('angle', '0')
        rot.set('centerX', str(real_w // 2))
        rot.set('centerY', str(real_h // 2))
        rot.set('rotateimage', '1')

        ri = ET.SubElement(pic, qn('hp', 'renderingInfo'))
        for tag in ('transMatrix', 'scaMatrix', 'rotMatrix'):
            m = ET.SubElement(ri, qn('hc', tag))
            m.set('e1', '1'); m.set('e2', '0'); m.set('e3', '0')
            m.set('e4', '0'); m.set('e5', '1'); m.set('e6', '0')

        rect = ET.SubElement(pic, qn('hp', 'imgRect'))
        pts = [('pt0', 0, 0), ('pt1', real_w, 0),
               ('pt2', real_w, real_h), ('pt3', 0, real_h)]
        for name, x, y in pts:
            pt = ET.SubElement(rect, qn('hc', name))
            pt.set('x', str(x)); pt.set('y', str(y))

        clip = ET.SubElement(pic, qn('hp', 'imgClip'))
        clip.set('left', '0'); clip.set('right', str(real_w))
        clip.set('top', '0'); clip.set('bottom', str(real_h))

        inm = ET.SubElement(pic, qn('hp', 'inMargin'))
        for side in ('left', 'right', 'top', 'bottom'):
            inm.set(side, '0')

        dim = ET.SubElement(pic, qn('hp', 'imgDim'))
        dim.set('dimwidth', str(real_w)); dim.set('dimheight', str(real_h))

        img = ET.SubElement(pic, qn('hc', 'img'))
        img.set('binaryItemIDRef', image_id)
        img.set('bright', '0'); img.set('contrast', '0')
        img.set('effect', 'REAL_PIC'); img.set('alpha', '0')

        sz = ET.SubElement(pic, qn('hp', 'sz'))
        sz.set('width', str(real_w)); sz.set('widthRelTo', 'ABSOLUTE')
        sz.set('height', str(real_h)); sz.set('heightRelTo', 'ABSOLUTE')
        sz.set('protect', '0')

        pos = ET.SubElement(pic, qn('hp', 'pos'))
        pos.set('treatAsChar', '1'); pos.set('affectLSpacing', '0')
        pos.set('flowWithText', '1'); pos.set('allowOverlap', '0')
        pos.set('holdAnchorAndSO', '0')
        pos.set('vertRelTo', 'PARA'); pos.set('horzRelTo', 'COLUMN')
        pos.set('vertAlign', 'TOP'); pos.set('horzAlign', 'LEFT')
        pos.set('vertOffset', '0'); pos.set('horzOffset', '0')

        outm = ET.SubElement(pic, qn('hp', 'outMargin'))
        for side in ('left', 'right', 'top', 'bottom'):
            outm.set(side, '0')

        # 앵커 뒤 빈 텍스트런 (실제 hwpx 샘플 관례)
        ET.SubElement(run, qn('hp', 't'))

        self._add_lineseg(p, 1000)
        self._paras.append(p)

        self.fig_n += 1
        self.caption(f'그림 {self.fig_n}. {title}')
        if desc:
            self.normal(desc)

    # ── 테이블 ───────────────────────────────────────────────────
    def table(self, headers: list, rows: list, title: str = '', desc: str = '', unit: str = ''):
        if not headers or not rows:
            return
        if unit:
            self._paras.append(self._text_paragraph(f'(단위: {unit})', 10, 23, 1100))
        n_col = len(headers)
        all_rows = [headers] + rows
        n_row = len(all_rows)

        col_w = CONTENT_WIDTH // n_col
        col_widths = [col_w] * (n_col - 1)
        col_widths.append(CONTENT_WIDTH - col_w * (n_col - 1))

        # 셀 텍스트가 실제로 몇 줄로 줄바꿈될지 미리 계산해 행 높이를 정한다.
        # 고정 900(9pt 1줄분)만 쓰면 2줄 이상 넘어가는 셀은 다음 행과 겹쳐 보인다.
        row_heights = []
        for row_data in all_rows:
            max_lines = 1
            for ci in range(n_col):
                cell_txt = str(row_data[ci]) if ci < len(row_data) and row_data[ci] is not None else ''
                max_lines = max(max_lines, _estimate_lines(cell_txt, 1000, col_widths[ci]))
            row_heights.append(max(900, round(max_lines * 1000 * 1.6) + 200))
        total_h = sum(row_heights)

        p = self._make_p(0)
        run = ET.SubElement(p, qn('hp', 'run'))
        run.set('charPrIDRef', '0')

        tbl = ET.SubElement(run, qn('hp', 'tbl'))
        tbl.set('id', str(self._next_id()))
        tbl.set('zOrder', '0')
        tbl.set('numberingType', 'TABLE')
        tbl.set('textWrap', 'TOP_AND_BOTTOM')
        tbl.set('textFlow', 'BOTH_SIDES')
        tbl.set('lock', '0')
        tbl.set('dropcapstyle', 'None')
        tbl.set('pageBreak', 'CELL')
        tbl.set('repeatHeader', '0')
        tbl.set('rowCnt', str(n_row))
        tbl.set('colCnt', str(n_col))
        tbl.set('cellSpacing', '0')
        tbl.set('borderFillIDRef', '3')
        tbl.set('noAdjust', '0')

        sz = ET.SubElement(tbl, qn('hp', 'sz'))
        sz.set('width', str(CONTENT_WIDTH)); sz.set('widthRelTo', 'ABSOLUTE')
        sz.set('height', str(total_h)); sz.set('heightRelTo', 'ABSOLUTE')
        sz.set('protect', '0')

        pos = ET.SubElement(tbl, qn('hp', 'pos'))
        pos.set('treatAsChar', '1'); pos.set('affectLSpacing', '0')
        pos.set('flowWithText', '1'); pos.set('allowOverlap', '0')
        pos.set('holdAnchorAndSO', '0')
        pos.set('vertRelTo', 'PARA'); pos.set('horzRelTo', 'COLUMN')
        pos.set('vertAlign', 'TOP'); pos.set('horzAlign', 'LEFT')
        pos.set('vertOffset', '0'); pos.set('horzOffset', '0')

        outm = ET.SubElement(tbl, qn('hp', 'outMargin'))
        for side in ('left', 'right', 'top', 'bottom'):
            outm.set(side, '0')
        inm = ET.SubElement(tbl, qn('hp', 'inMargin'))
        for side in ('left', 'right', 'top', 'bottom'):
            inm.set(side, '0')

        for ri, row_data in enumerate(all_rows):
            tr = ET.SubElement(tbl, qn('hp', 'tr'))
            is_header = (ri == 0)
            for ci in range(n_col):
                cell_txt = str(row_data[ci]) if ci < len(row_data) and row_data[ci] is not None else ''
                tc = ET.SubElement(tr, qn('hp', 'tc'))
                tc.set('name', ''); tc.set('header', '1' if is_header else '0')
                tc.set('hasMargin', '0'); tc.set('protect', '0')
                tc.set('editable', '0'); tc.set('dirty', '1')
                tc.set('borderFillIDRef', '3')

                sub = ET.SubElement(tc, qn('hp', 'subList'))
                sub.set('id', ''); sub.set('textDirection', 'HORIZONTAL')
                sub.set('lineWrap', 'BREAK'); sub.set('vertAlign', 'CENTER')
                sub.set('linkListIDRef', '0'); sub.set('linkListNextIDRef', '0')
                sub.set('textWidth', '0'); sub.set('textHeight', '0')
                sub.set('hasTextRef', '0'); sub.set('hasNumRef', '0')

                cp = ET.SubElement(sub, qn('hp', 'p'))
                cp.set('paraPrIDRef', '22'); cp.set('styleIDRef', '0')
                cp.set('pageBreak', '0'); cp.set('columnBreak', '0')
                cp.set('merged', '0'); cp.set('id', str(self._next_id()))
                crun = ET.SubElement(cp, qn('hp', 'run'))
                crun.set('charPrIDRef', '9' if is_header else '0')
                ct = ET.SubElement(crun, qn('hp', 't'))
                ct.text = cell_txt
                self._add_lineseg(cp, 1000, cell_txt, col_widths[ci])

                ET.SubElement(tc, qn('hp', 'cellAddr')).set('colAddr', str(ci))
                tc[-1].set('rowAddr', str(ri))
                span = ET.SubElement(tc, qn('hp', 'cellSpan'))
                span.set('colSpan', '1'); span.set('rowSpan', '1')
                csz = ET.SubElement(tc, qn('hp', 'cellSz'))
                csz.set('width', str(col_widths[ci])); csz.set('height', str(row_heights[ri]))
                cm = ET.SubElement(tc, qn('hp', 'cellMargin'))
                for side in ('left', 'right', 'top', 'bottom'):
                    cm.set(side, '0')

        self._paras.append(p)

        if title:
            self.tbl_n += 1
            self.caption(f'표 {self.tbl_n}. {title}')
        if desc:
            self.normal(desc)

    # ── secPr(첫 문단, 페이지 설정) ───────────────────────────────
    def _build_first_para(self) -> ET._Element:
        """실제 hwpx 템플릿의 첫 문단(secPr+colPr)을 그대로 재현한다."""
        p = self._make_p(0)
        run = ET.SubElement(p, qn('hp', 'run'))
        run.set('charPrIDRef', '0')

        secpr = ET.SubElement(run, qn('hp', 'secPr'))
        secpr.set('id', ''); secpr.set('textDirection', 'HORIZONTAL')
        secpr.set('spaceColumns', '1134'); secpr.set('tabStop', '8000')
        secpr.set('tabStopVal', '4000'); secpr.set('tabStopUnit', 'HWPUNIT')
        secpr.set('outlineShapeIDRef', '1'); secpr.set('memoShapeIDRef', '0')
        secpr.set('textVerticalWidthHead', '0'); secpr.set('masterPageCnt', '0')

        grid = ET.SubElement(secpr, qn('hp', 'grid'))
        grid.set('lineGrid', '0'); grid.set('charGrid', '0'); grid.set('wonggojiFormat', '0')

        sn = ET.SubElement(secpr, qn('hp', 'startNum'))
        sn.set('pageStartsOn', 'BOTH'); sn.set('page', '0'); sn.set('pic', '0')
        sn.set('tbl', '0'); sn.set('equation', '0')

        vis = ET.SubElement(secpr, qn('hp', 'visibility'))
        vis.set('hideFirstHeader', '0'); vis.set('hideFirstFooter', '0')
        vis.set('hideFirstMasterPage', '0'); vis.set('border', 'SHOW_ALL')
        vis.set('fill', 'SHOW_ALL'); vis.set('hideFirstPageNum', '0')
        vis.set('hideFirstEmptyLine', '0'); vis.set('showLineNumber', '0')

        ET.SubElement(secpr, qn('hp', 'lineNumberShape')).set('restartType', '0')
        secpr[-1].set('countBy', '0'); secpr[-1].set('distance', '0'); secpr[-1].set('startNumber', '0')

        pagepr = ET.SubElement(secpr, qn('hp', 'pagePr'))
        pagepr.set('landscape', 'WIDELY'); pagepr.set('width', '59528')
        pagepr.set('height', '84186'); pagepr.set('gutterType', 'LEFT_ONLY')
        margin = ET.SubElement(pagepr, qn('hp', 'margin'))
        margin.set('header', '4252'); margin.set('footer', '4252')
        margin.set('gutter', '0'); margin.set('left', str(MARGIN_LEFT_RIGHT))
        margin.set('right', str(MARGIN_LEFT_RIGHT))
        margin.set('top', str(MARGIN_TOP_BOTTOM)); margin.set('bottom', str(MARGIN_TOP_BOTTOM))

        for note_tag, placement in (('footNotePr', 'EACH_COLUMN'), ('endNotePr', 'END_OF_DOCUMENT')):
            note = ET.SubElement(secpr, qn('hp', note_tag))
            anf = ET.SubElement(note, qn('hp', 'autoNumFormat'))
            anf.set('type', 'DIGIT'); anf.set('userChar', ''); anf.set('prefixChar', '')
            anf.set('suffixChar', ')'); anf.set('supscript', '0')
            nl = ET.SubElement(note, qn('hp', 'noteLine'))
            nl.set('length', '-1' if note_tag == 'footNotePr' else '14692344')
            nl.set('type', 'SOLID'); nl.set('width', '0.12 mm'); nl.set('color', '#000000')
            nsp = ET.SubElement(note, qn('hp', 'noteSpacing'))
            nsp.set('betweenNotes', '283' if note_tag == 'footNotePr' else '0')
            nsp.set('belowLine', '567'); nsp.set('aboveLine', '850')
            numb = ET.SubElement(note, qn('hp', 'numbering'))
            numb.set('type', 'CONTINUOUS'); numb.set('newNum', '1')
            plc = ET.SubElement(note, qn('hp', 'placement'))
            plc.set('place', placement); plc.set('beneathText', '0')

        for btype in ('BOTH', 'EVEN', 'ODD'):
            pbf = ET.SubElement(secpr, qn('hp', 'pageBorderFill'))
            pbf.set('type', btype); pbf.set('borderFillIDRef', '1')
            pbf.set('textBorder', 'PAPER'); pbf.set('headerInside', '0')
            pbf.set('footerInside', '0'); pbf.set('fillArea', 'PAPER')
            off = ET.SubElement(pbf, qn('hp', 'offset'))
            off.set('left', '1417'); off.set('right', '1417')
            off.set('top', '1417'); off.set('bottom', '1417')

        ctrl = ET.SubElement(run, qn('hp', 'ctrl'))
        colpr = ET.SubElement(ctrl, qn('hp', 'colPr'))
        colpr.set('id', ''); colpr.set('type', 'NEWSPAPER'); colpr.set('layout', 'LEFT')
        colpr.set('colCount', '1'); colpr.set('sameSz', '1'); colpr.set('sameGap', '0')

        run2 = ET.SubElement(p, qn('hp', 'run'))
        run2.set('charPrIDRef', '0')
        ET.SubElement(run2, qn('hp', 't'))

        self._add_lineseg(p, 1000)
        return p

    # ── 최종 XML 빌드 ─────────────────────────────────────────────
    def build(self) -> bytes:
        nsmap = {k: v for k, v in NS.items()}
        root = ET.Element(qn('hs', 'sec'), nsmap=nsmap)

        root.append(self._build_first_para())
        for p in self._paras:
            root.append(p)

        return ET.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)


# ══════════════════════════════════════════════════════════════════
# 데이터·이미지 로드
# ══════════════════════════════════════════════════════════════════

def load_data():
    with open(os.path.join(STRUCTURED, 'master_dataset.json'), encoding='utf-8') as f:
        md = json.load(f)
    with open(os.path.join(CHARTS, 'chart_catalog.json'), encoding='utf-8') as f:
        cc = json.load(f)
    return md, cc


def get_chart_map(catalog: dict) -> dict:
    return {c['chart_id']: c['filename']
            for c in catalog.get('charts', [])
            if c['status'] in ('generated', 'reused')}


def copy_to_bindata(chart_map: dict) -> dict:
    """차트 PNG를 BinData에 image_NNN.png로 복사, 매핑 반환"""
    bin_dir = os.path.join(HWPX_BUILD, 'BinData')
    os.makedirs(bin_dir, exist_ok=True)
    img_map: dict = {}
    idx = 1
    for cid in sorted(chart_map.keys()):
        src = os.path.join(CHARTS, chart_map[cid])
        if not os.path.exists(src):
            continue
        new_name = f'image_{idx:03d}.png'
        shutil.copy2(src, os.path.join(bin_dir, new_name))
        img_map[chart_map[cid]] = new_name
        idx += 1
    with open(os.path.join(HWPX_BUILD, 'image_map.json'), 'w', encoding='utf-8') as f:
        json.dump(img_map, f, ensure_ascii=False, indent=2)
    return img_map


def resolve(chart_id: str, chart_map: dict, img_map: dict) -> str | None:
    """chart_id → BinData 내 image_NNN.png 반환 (없으면 None)"""
    orig = chart_map.get(chart_id)
    return img_map.get(orig) if orig else None


# ══════════════════════════════════════════════════════════════════
# 패키징 (실제 mimetype/템플릿 기반)
# ══════════════════════════════════════════════════════════════════

def copy_static_template():
    """scripts/hwpx_template/ 의 정적 파트를 빌드 폴더로 복사한다."""
    if not os.path.isdir(HWPX_TEMPLATE):
        print(f'hwpx_template 폴더 없음: {HWPX_TEMPLATE}')
        sys.exit(1)
    for name in os.listdir(HWPX_TEMPLATE):
        src = os.path.join(HWPX_TEMPLATE, name)
        dst = os.path.join(HWPX_BUILD, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def write_content_hpf(builder: HWPXBuilder, title: str, creator: str):
    """content.hpf 템플릿을 로드해 메타데이터·이미지 매니페스트를 채운다."""
    path = os.path.join(HWPX_BUILD, 'Contents', 'content.hpf')
    tree = ET.parse(path)
    root = tree.getroot()

    title_el = root.find('.//' + qn('opf', 'title'))
    if title_el is not None:
        title_el.text = title

    now_iso = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    now_kr  = datetime.now().strftime('%Y년 %m월 %d일')
    for meta in root.findall('.//' + qn('opf', 'meta')):
        name = meta.get('name', '')
        if name in ('creator', 'lastsaveby'):
            meta.text = creator
        elif name == 'CreatedDate':
            meta.text = now_iso
        elif name == 'ModifiedDate':
            meta.text = now_iso
        elif name == 'date':
            meta.text = now_kr

    manifest = root.find('.//' + qn('opf', 'manifest'))
    for image_id, fname, media_type in builder._images:
        item = ET.SubElement(manifest, qn('opf', 'item'))
        item.set('id', image_id)
        item.set('href', f'BinData/{fname}')
        item.set('media-type', media_type)
        item.set('isEmbeded', '1')

    tree.write(path, pretty_print=True, xml_declaration=True, encoding='UTF-8', standalone=True)


def pack(output_name: str) -> str:
    """mimetype을 최상단·무압축으로 넣고 나머지는 압축해 패키징한다."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = os.path.join(OUTPUT_DIR, f'{output_name}.hwpx')

    root = HWPX_BUILD
    mimetype_file = os.path.join(root, 'mimetype')
    if not os.path.isfile(mimetype_file):
        raise FileNotFoundError(f'mimetype 파일 없음: {mimetype_file}')

    all_files = []
    for dirpath, _, files in os.walk(root):
        for fname in files:
            fp = os.path.join(dirpath, fname)
            rel = os.path.relpath(fp, root).replace(os.sep, '/')
            if rel != 'mimetype':
                all_files.append(rel)
    all_files.sort()

    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(mimetype_file, 'mimetype', compress_type=zipfile.ZIP_STORED)
        for rel in all_files:
            zf.write(os.path.join(root, rel), rel, compress_type=zipfile.ZIP_DEFLATED)

    return out


def validate(path: str, n_images: int) -> tuple:
    """실제 HWPX 스펙 기준 구조 검증."""
    errors = []
    required = [
        'mimetype', 'version.xml', 'settings.xml',
        'Contents/header.xml', 'Contents/section0.xml', 'Contents/content.hpf',
        'META-INF/container.xml',
    ]
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            names = zf.namelist()
            for req in required:
                if req not in names:
                    errors.append(f'필수 파일 없음: {req}')

            if names and names[0] != 'mimetype':
                errors.append('mimetype이 zip의 첫 항목이 아님')
            if 'mimetype' in names:
                info = zf.getinfo('mimetype')
                if info.compress_type != zipfile.ZIP_STORED:
                    errors.append('mimetype이 무압축(ZIP_STORED)이 아님')
                content = zf.read('mimetype').decode('utf-8').strip()
                if content != 'application/hwp+zip':
                    errors.append(f'mimetype 내용 불일치: {content!r}')

            for name in names:
                if name.endswith('.xml') or name.endswith('.hpf'):
                    try:
                        ET.fromstring(zf.read(name))
                    except ET.XMLSyntaxError as e:
                        errors.append(f'XML 파싱 오류: {name}: {e}')

            bin_n = len([n for n in names if n.startswith('BinData/')])
            if bin_n < n_images:
                errors.append(f'BinData 파일 수 불일치: {bin_n} vs {n_images}')
    except Exception as e:
        errors.append(str(e))
    return len(errors) == 0, errors


# ══════════════════════════════════════════════════════════════════
# 보고서 본문 조립
# ══════════════════════════════════════════════════════════════════

def build_report(b: HWPXBuilder, md: dict,
                 chart_map: dict, img_map: dict,
                 meta: dict):
    tf   = md.get('tech_field',    '기술분야')
    proj = md.get('project_name',  '연구과제')
    sec1 = md.get('market_overview',   {})
    sec2 = md.get('market_dynamics',   {})
    sec3 = md.get('ecosystem',         {})
    sec4 = md.get('regional_analysis', {})
    sec5 = md.get('segmentation',      {})
    sec6 = md.get('rnd_trends',        {})
    sec7 = md.get('implications',      {})
    src  = sec1.get('source_report', '원본 보고서')
    today = datetime.now().strftime('%Y년 %m월 %d일')

    def img(cid: str, title: str, desc: str = ''):
        fn = resolve(cid, chart_map, img_map)
        if fn:
            b.image(fn, title, desc=desc)

    # ── 표지 ──────────────────────────────────────────────────────
    # 출처는 여기(표지, 첫 페이지 요약)에만 싣는다 — 본문·그림·표 하단에는
    # 반복하지 않는다는 원칙에 따라 이 아래로는 "(출처: ...)"를 붙이지 않는다.
    b.empty()
    b.h1(f'{tf} 글로벌 시장 분석 요약')
    b.normal(f'연구과제: {proj}')
    b.normal(f'원본 출처: {src}  ({meta.get("publish_year", "")})')
    b.normal(f'작성일: {today}')
    b.empty()

    # ── 섹션 1: 시장 개요 및 성장 전망 ───────────────────────────
    b.h1('1. 시장 개요 및 성장 전망')

    bg = sec1.get('growth_background', '')
    if bg:
        b.normal(bg)
    b.empty()

    pd_ = sec1.get('power_demand_data', {})
    pd_desc = ''
    if pd_.get('years') and pd_.get('demand_incl_ai_twh'):
        y0, y1 = pd_['years'][0], pd_['years'][-1]
        v0, v1 = pd_['demand_incl_ai_twh'][0], pd_['demand_incl_ai_twh'][-1]
        pd_desc = f'AI 포함 시나리오 기준 전력 수요는 {y0}년 {v0}TWh에서 {y1}년 {v1}TWh로 증가할 전망임.'
    img('V1_1', f'{tf} 분야 전력 수요 전망', desc=pd_desc)

    # 시나리오 테이블
    sc      = sec1.get('scenarios', {})
    base_s  = sec1.get('base_year_size_usd_b', '')
    base_yr = sec1.get('base_year', '')
    fc_yr   = sec1.get('forecast_year', '')
    cagr    = sec1.get('cagr_pct', '')
    opt_cagr  = sc.get('optimistic',  {}).get('cagr_pct')
    pess_cagr = sc.get('pessimistic', {}).get('cagr_pct')
    scenario_desc = ''
    if isinstance(opt_cagr, (int, float)) and isinstance(pess_cagr, (int, float)):
        diff = round(opt_cagr - pess_cagr, 1)
        scenario_desc = (f'낙관 시나리오는 연평균 {opt_cagr}%로 비관 시나리오({pess_cagr}%) '
                          f'대비 {diff}%p 높은 성장률을 전망함.')
    # 원문에 시나리오 분석이 없으면(scenarios 비어 있음) 표를 아예 만들지 않는다 —
    # 예전에는 base_year 값만 채우고 예측연도·CAGR을 '?'로 남겨 오해를 유발했다(실측 확인).
    if sc:
        tbl_hdr = ['시나리오', f'기준연도({base_yr})', f'예측연도({fc_yr})', 'CAGR (%)']
        tbl_row = [
            ['낙관 (Optimistic)',
             f'{base_s}' if base_s else '-',
             f'{sc.get("optimistic",  {}).get("size_usd_b", "?")}',
             f'{sc.get("optimistic",  {}).get("cagr_pct", "?")}%'],
            ['현실 (Realistic)',
             f'{base_s}' if base_s else '-',
             f'{sc.get("realistic",  {}).get("size_usd_b", "?")}',
             f'{sc.get("realistic",  {}).get("cagr_pct", cagr)}%'],
            ['비관 (Pessimistic)',
             f'{base_s}' if base_s else '-',
             f'{sc.get("pessimistic", {}).get("size_usd_b", "?")}',
             f'{sc.get("pessimistic", {}).get("cagr_pct", "?")}%'],
        ]
        b.table(tbl_hdr, tbl_row, title='시나리오별 시장규모 전망', desc=scenario_desc,
                unit=sec1.get('currency_unit', '$B'))
    img('V1_2', '시나리오별 시장규모 전망')

    trends = sec1.get('key_trends', [])
    if trends:
        b.h2('핵심 트렌드')
        for t in trends:
            b.bullet(f'{t.get("trend","")}: {t.get("description","")}')

    # ── 섹션 2: 시장 역학 ─────────────────────────────────────────
    b.h1('2. 시장 역학 (Market Dynamics)')
    b.normal(f'{tf} 시장의 성장 동인, 저해 요인, 기회 요소를 분석함.')
    img('V2_1', '시장 역학 구조')

    def dyn_section(title: str, items: list):
        if items:
            b.h2(title)
            for it in items:
                b.bullet(f'{it.get("title","")}: {it.get("description","")}')

    dyn_section('성장 동인 (Drivers)',       sec2.get('drivers',      []))
    dyn_section('저해 요인 (Restraints)',    sec2.get('restraints',   []))
    if sec2.get('has_challenges'):
        dyn_section('도전 과제 (Challenges)', sec2.get('challenges', []))
    dyn_section('비즈니스 기회 (Opportunities)', sec2.get('opportunities', []))

    # ── 섹션 3: 기술·솔루션 생태계 ───────────────────────────────
    # (1) 공급망 → (2) 가치사슬 → (3) 생태계 맵 순으로 다룬다. 각 항목은 원문에
    # 실제 그림이 있으면 그 그림을 그대로 쓰고(generate_charts.py의 reuse 로직),
    # 없을 때만 합성 다이어그램으로 대체한다.
    b.h1('3. 기술·솔루션 생태계')

    # 원문에 해당 그림(재활용 이미지) 또는 합성용 구조화 데이터가 전혀 없으면
    # img()가 조용히 아무것도 그리지 않아 소제목만 남고 그 아래가 완전히 비는
    # 문제가 있었다(실측 확인) — V2_1의 "빈 카테고리는 만들지 않는다" 원칙과
    # 동일하게, 실제로 그릴 내용이 있을 때만 소제목을 낸다.
    if sec3.get('supply_chain_image') or sec3.get('supply_chain'):
        b.h2('공급망 (Supply Chain) 분석')
        img('V3_3', '공급망 구조', desc=sec3.get('supply_chain_desc', ''))

    if sec3.get('value_chain_image') or sec3.get('value_chain'):
        b.h2('가치사슬 (Value Chain) 분석')
        img('V3_2', '가치사슬 구조', desc=sec3.get('value_chain_desc', ''))

    if sec3.get('ecosystem_map_image') or sec3.get('key_players_by_category'):
        b.h2('생태계 맵 (Ecosystem Map)')
        img('V3_1', '생태계 맵', desc=sec3.get('ecosystem_map_desc', ''))

    ms = sec3.get('market_share_table', [])
    if ms:
        b.h2('경쟁구도 (Competitive Landscape)')
        top3 = ms[:3]
        top3_txt = ', '.join(f"{r.get('company','')}({r.get('share_range','')})" for r in top3)
        n_frag = max(0, len(ms) - 3)
        # 점유율 지표명·해석 문장은 데이터에서 덮어쓸 수 있다 — 기본 해석문은 "다수의 소규모
        # 기업이 1% 미만을 나눠 갖는 파편화 시장"을 전제하므로, 소수 기업만 존재하는 과점
        # 시장 데이터에 그대로 쓰면 사실과 다른 문장이 된다(실측 확인).
        default_desc = (f'상위 3개 기업({top3_txt})이 점유율 상위권을 형성하며, 나머지 {n_frag}여 개 '
                        f'기업 대부분은 1% 미만의 점유율을 보여 파편화된 경쟁구조를 나타냄. 소수 '
                        f'선도기업의 시장 지배력과 다수 틈새 기술기업 간 경쟁이 공존하는 구조임.')
        b.table(['기업명', sec3.get('market_share_metric', '시장점유율 범위')],
                [[r.get('company', ''), r.get('share_range', '')] for r in ms[:10]],
                title='경쟁구도 (Competitive Landscape)',
                desc=sec3.get('market_share_desc') or default_desc)

    nm = sec3.get('notable_movements', '')
    if nm and nm != '원문 미확인':
        b.h2('주요 시장 동향')
        b.normal(nm)

    # ── 섹션 4: 지역별 시장 분석 ─────────────────────────────────
    b.h1('4. 지역별 시장 분석')
    lead = sec4.get('leading_region', '')
    fast = sec4.get('fastest_growing_region', '')
    if lead and lead != '원문 미확인':
        b.normal(f'{lead}이(가) 시장을 주도하며, {fast}에서 가장 높은 성장률이 전망됨.')

    regs = sec4.get('regions', [])
    lead_region = next((r for r in regs if r.get('name') == lead), None)
    v4_1_desc = ''
    yrs4 = sec4.get('years', [])
    if lead_region and lead_region.get('sizes_usd_b') and len(yrs4) >= 2 \
            and len(lead_region['sizes_usd_b']) >= 2:
        v4_1_desc = (f'{lead}{_eun_neun(lead)} {yrs4[0]}년 ${lead_region["sizes_usd_b"][0]}B에서 '
                      f'{yrs4[-1]}년 ${lead_region["sizes_usd_b"][-1]}B 규모로 성장할 전망임.')
    img('V4_1', '지역별 시장규모', desc=v4_1_desc)

    if regs:
        b.h2('권역별 기회 및 리스크')
        r_hdr = ['권역', '단기 기회', '단기 리스크', '장기 기회', '장기 리스크']
        r_rows = [
            [r.get('name', '')[:20],
             r.get('short_term_opportunity', '')[:55],
             r.get('short_term_risk',        '')[:55],
             r.get('long_term_opportunity',  '')[:55],
             r.get('long_term_risk',         '')[:55]]
            for r in regs[:5]
        ]
        b.table(r_hdr, r_rows, title='권역별 기회 및 리스크')

    # V4_2(매트릭스 그림)는 삽입하지 않는다 — 바로 위 표와 완전히 같은 데이터를
    # 그림으로만 다시 보여주는 중복이었고, 표 형태의 데이터는 이미지가 아니라
    # 표로 넣는 것이 원칙이다(SKILL.md STEP 4 참고).

    # ── 섹션 5: 세그먼트별 시장 분석 ─────────────────────────────
    b.h1('5. 세그먼트별 시장 분석')

    def seg_section(h2: str, cid: str, seg_data: dict):
        b.h2(h2)
        notes = '; '.join(
            s.get('growth_note', '') for s in seg_data.get('segments', [])
            if s.get('growth_note')
        )
        if notes:
            b.normal(notes)
        img(cid, f'{h2}')

    # 세그먼트 분류 축은 보고서마다 다르므로 축 이름·개수를 데이터에서 그대로 가져온다
    # (하드코딩하면 다른 보고서를 넣었을 때 엉뚱한 축 이름이 표시된다).
    MAIN_SLOTS = ['V5_1_end_use', 'V5_2_dc_type', 'V5_3_solution', 'V5_4_rack_density']
    for i, cid in enumerate(MAIN_SLOTS):
        axis = sec5.get('axes', [])[i] if i < len(sec5.get('axes', [])) else {}
        if axis.get('segments'):
            seg_section(seg_title(axis, f'세그먼트{i+1}'), cid, axis)

    DETAIL_SLOTS = ['V5_5_air_sub', 'V5_6_liquid_dir', 'V5_7_immersion']
    for i, cid in enumerate(DETAIL_SLOTS):
        detail_axes = sec5.get('detail_axes', [])
        axis = detail_axes[i] if i < len(detail_axes) else {}
        if axis.get('segments'):
            seg_section(axis.get('label', f'세부분류{i+1}'), cid, axis)

    # ── 섹션 6: R&D 및 기술 동향 ─────────────────────────────────
    b.h1('6. R&D 및 기술 동향')
    at = sec5.get('adoption_trend', {})
    adopt_series = at.get('series', [])
    adopt_desc = ''
    if adopt_series and adopt_series[0].get('values_pct') and at.get('years'):
        v0, v1 = adopt_series[0]['values_pct'][0], adopt_series[0]['values_pct'][-1]
        y0, y1 = at['years'][0], at['years'][-1]
        alabel = adopt_series[0].get("label", "채택률")
        adopt_desc = (f'{alabel}{_eun_neun(alabel)} {y0}년 {v0}%에서 '
                       f'{y1}년 {v1}%로 상승할 전망임.')
    img('V6_1', f'{at.get("label", "기술 채택률")} 전망', desc=adopt_desc)

    pt = sec6.get('patent_trend', {})
    if pt.get('description') and pt['description'] != '원문 미확인':
        # 절 제목도 지표에 맞춰 바뀔 수 있다 — 원문이 특허가 아닌 다른 지표(인력 규모,
        # 파이프라인 자산 수 등)를 제시하면 section_title로 덮어쓴다(기본값은 특허 기준).
        b.h2(pt.get('section_title', '특허 동향'))
        b.normal(pt['description'])
        # 지표 라벨/단위는 데이터에 따라 가변 — 기본값은 특허 기준, 다른 지표면 스키마 필드로 덮어쓴다.
        metric_label = pt.get('metric_label', '특허 출원 건수')
        metric_unit  = pt.get('metric_unit', '건')
        detail = pt.get('top_companies_detail', [])
        if detail:
            b.table(['기업', metric_label],
                    [[d.get('company', ''), f"{d.get('count', 0):,}{metric_unit}"] for d in detail[:6]],
                    title=f'기업별 {metric_label}')
        img('V6_2', f'기업별 {metric_label}',
            desc='가로축은 기업 간 큰 격차를 비교하기 쉽도록 로그 스케일로 표시함.')
        if pt.get('top_countries'):
            b.bullet(pt.get('top_countries_label', '주요 특허 보유국') + ': ' + ', '.join(pt['top_countries']))
        if pt.get('top_companies'):
            b.bullet(pt.get('top_companies_label', '주요 특허 보유 기업') + ': ' + ', '.join(pt['top_companies']))

    cases = sec6.get('case_studies', [])
    if cases:
        b.h2('케이스 스터디')
        for c in cases[:8]:
            b.bullet(f'[{c.get("organization","")}] {c.get("title","")} '
                     f'— {c.get("technology","")}: {c.get("outcome","")}')

    gov = sec6.get('government_initiatives', [])
    if gov:
        b.h2('정부 정책·이니셔티브')
        for g in gov[:5]:
            b.bullet(f'[{g.get("region","")}] {g.get("initiative","")}: '
                     f'{g.get("description","")}')

    emerging = sec6.get('emerging_technologies', [])
    if emerging:
        b.h2('신기술 동향')
        for e in emerging[:5]:
            b.bullet(f'{e.get("tech","")}: {e.get("description","")}')

    # ── 섹션 7: 결론 및 기술개발 시사점 ──────────────────────────
    b.h1('7. 결론 및 기술개발 시사점')

    b.h2('7-1. 종합 결론')
    for conc in sec7.get('key_conclusions', []):
        b.bullet(conc)

    b.h2('7-2. 기술개발 시사점')
    impl = sec7.get('implications', {})
    impl_items = [
        ('① 유망 기술 방향',         impl.get('i1_promising_tech', '')),
        ('② 기술 격차 및 추격 전략',  impl.get('i2_tech_gap',       '')),
        ('③ 공급망 참여 전략',        impl.get('i3_supply_chain',   '')),
        ('④ 정책·제도 설계 방향',     impl.get('i4_policy',         '')),
        ('⑤ KIST 연구전략 관점',      impl.get('i5_kist',           '')),
    ]
    for num_title, text in impl_items:
        if text and text != '원문 미확인':
            b.normal(num_title, bold=True)
            b.normal(text)
            b.empty()

    note = sec7.get('data_basis_note', '')
    if note:
        b.normal(f'※ {note}')


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════

def main():
    master_p = os.path.join(STRUCTURED, 'master_dataset.json')
    catalog_p = os.path.join(CHARTS, 'chart_catalog.json')
    meta_p    = os.path.join(LOG_DIR,  'step1_meta.json')

    for p, name in [(master_p, 'master_dataset.json'),
                    (catalog_p, 'chart_catalog.json'),
                    (meta_p,    'step1_meta.json')]:
        if not os.path.exists(p):
            print(f'{name} 없음 — 이전 단계를 먼저 실행하세요.')
            sys.exit(1)

    md, catalog = load_data()
    with open(meta_p, encoding='utf-8') as f:
        meta = json.load(f)

    output_name = meta.get('output_name', '시장분석_보고서')
    tf = md.get('tech_field', '기술분야')
    print(f'\n[STEP 5] HWPX 보고서 생성 — {tf}')
    print(f'  출력 파일: {output_name}.hwpx')

    # 빌드 디렉토리 초기화 (기존 잔여물 제거)
    if os.path.isdir(HWPX_BUILD):
        shutil.rmtree(HWPX_BUILD)
    os.makedirs(HWPX_BUILD, exist_ok=True)

    # 정적 템플릿(mimetype/version.xml/settings.xml/header.xml/META-INF/Preview) 복사
    copy_static_template()

    # 이미지 → BinData 복사
    chart_map = get_chart_map(catalog)
    img_map   = copy_to_bindata(chart_map)
    print(f'  이미지 복사: {len(img_map)}개 → BinData/')

    # 본문 XML 조립
    print('  XML 조립 중...')
    builder = HWPXBuilder()
    build_report(builder, md, chart_map, img_map, meta)

    xml_bytes = builder.build()
    section_path = os.path.join(HWPX_BUILD, 'Contents', 'section0.xml')
    with open(section_path, 'wb') as f:
        f.write(xml_bytes)
    print(f'  section0.xml: {len(xml_bytes)//1024} KB')

    # content.hpf 메타데이터·이미지 매니페스트 채우기
    write_content_hpf(builder, title=f'{tf} 시장분석 보고서',
                       creator=md.get('project_name', 'KIST'))

    # ZIP 패키징 (mimetype 최상단·무압축)
    hwpx_path = pack(output_name)
    size_kb   = os.path.getsize(hwpx_path) // 1024

    # 검증
    ok, errs = validate(hwpx_path, len(img_map))

    # 섹션 포함 여부 확인 (XML 이스케이프 고려: '&' → '&amp;')
    xml_text  = xml_bytes.decode('utf-8', errors='replace')
    sec_keys  = ['시장 개요', '시장 역학', '생태계', '지역별', '세그먼트', 'R&D', '결론']

    def _contains(key, text):
        return key in text or key.replace('&', '&amp;') in text

    secs_ok   = [k for k in sec_keys if _contains(k, xml_text)]
    secs_miss = [k for k in sec_keys if not _contains(k, xml_text)]

    # 최종 출력 파일을 skill/output 에도 복사
    skill_out = os.path.join(BASE, 'skill', 'output')
    os.makedirs(skill_out, exist_ok=True)
    shutil.copy2(hwpx_path, os.path.join(skill_out, f'{output_name}.hwpx'))

    # 로그
    log = {
        'timestamp':    datetime.now().isoformat(),
        'output_file':  hwpx_path,
        'size_kb':      size_kb,
        'images':       len(img_map),
        'sections_ok':  secs_ok,
        'sections_miss': secs_miss,
        'zip_valid':    ok,
        'errors':       errs,
        'step5_status': 'success' if ok and len(secs_ok) >= 7 else 'partial',
    }
    with open(os.path.join(LOG_DIR, 'step5_hwpx.json'), 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    # 완료 출력
    all_sec = 'all' if not secs_miss else f'{", ".join(secs_miss)} 누락'
    print(f'\n✅ STEP 5 완료')
    print(f'  생성 파일: {output_name}.hwpx')
    print(f'  파일 크기: {size_kb} KB')
    print(f'  삽입 이미지: {len(img_map)}개')
    print(f'  7개 섹션: {"모두 포함" if not secs_miss else all_sec}')
    print(f'  구조 검증: {"통과" if ok else "실패"}')
    if errs:
        print(f'  경고: {"; ".join(errs)}')
    print(f'\n  → 다음 단계: python validate_output.py')


if __name__ == '__main__':
    main()
