---
name: market-analysis
description: "영문 시장조사 보고서(PDF/HWP/HWPX/DOCX)를 분석해 7개 섹션 + 최대 13개 차트(공급망·가치사슬·생태계 맵 포함)가 담긴 한글 개조식 HWPX(한컴오피스)·DOCX(워드) 보고서를 자동 생성. 텍스트/이미지 추출 → Claude 직접 분석 → 차트 생성 → 문서 생성 → 검증 → 배포 7단계 파이프라인. 트리거: '시장분석', '시장보고서 요약', '마켓 리포트', 'market analysis', 'market-analysis'."
user-invocable: true
---

# market-analysis — 시장분석 보고서 자동요약 스킬

영문 시장조사 보고서(PDF/HWP/HWPX/DOCX)를 입력받아 7개 섹션 + 최대 13개 차트(공급망·가치사슬·
생태계 맵 포함)가 포함된 한글 **HWPX(한컴오피스) + DOCX(워드)** 보고서를 자동 생성합니다.

## 사용법

```
/market-analysis
```

---

## 참고 문서 (`references/`)

SKILL.md는 **실행 흐름**만 담는다. 상세 규칙은 필요한 시점에 아래 파일을 Read할 것.

| 파일 | 언제 읽나 |
|---|---|
| **`references/step3-schema.md`** | **STEP 3 수행 전 반드시 (매 실행 필수)** — 구조화 JSON 스키마·생성 규칙 전문 |
| `references/chart-design.md` | `generate_charts.py`를 **수정**할 때만 — 폰트 역산·겹침 방지·원본 이미지 재활용 원칙 |
| `references/document-format.md` | `generate_hwpx.py`/`generate_docx.py`/`hwpx_template/`을 **수정**할 때만 — 여백·캡션·HWPX linesegarray·판독불가 방지 |

보고서를 생성하기만 할 때는 `step3-schema.md`만 읽으면 된다.

---

## 실행 전 준비 (최초 1회, PC마다)

1. `config.example.json`을 `config.json`으로 복사한 뒤 5개 값을 수정:

```json
{
  "input_file": "report.pdf",
  "tech_field": "기술분야명 (예: 데이터센터 냉각)",
  "project_name": "과제명",
  "output_name": "시장분석_기술분야",
  "base_dir": "C:/Users/본인계정/원하는/프로젝트/폴더"
}
```

   - `base_dir`은 **슬래시(`/`)** 사용을 권장한다. 역슬래시(`\`)를 쓰려면 JSON 규칙상 `\\`로
     이스케이프해야 하며, 하나만 쓰면(`\2`, `\시` 등) JSON 파싱 오류가 난다.
   - `config.json`은 `.gitignore`에 등록되어 있어 각자의 실제 경로가 커밋되지 않는다. 보고서를 바꿀
     때도 이 5개 값만 고치면 된다 (스크립트 코드는 손댈 필요 없음).
   - `config.json` 없이 실행하면 `_common.get_base()`가 안내 메시지와 함께 `FileNotFoundError`로
     중단시킨다 — 위 복사 단계를 먼저 진행하면 된다.

2. 분석할 보고서 파일을 `base_dir` 아래 `input_file` 경로에 둔다 (`workspace/` 하위 폴더는
   `/market-analysis` 실행 시 자동 생성되므로 미리 만들 필요 없음).

3. Python 패키지 설치: `pip install -r requirements.txt`

나눔고딕 폰트는 `scripts/assets/NanumGothic.ttf`로 저장소에 동봉되어 있어 별도 설치 없이 어떤
PC에서도 차트에 한글이 정상 표시된다.

---

## Claude Code 실행 지침

`/market-analysis` 호출 시 아래 7단계를 순서대로 수행한다. 스크립트는 모두 `config.json`의
`base_dir`을 `_common.get_base()`로 읽어 동작하므로, STEP 2 이후의 스크립트 호출에는 `--workspace`
같은 인자를 넘길 필요가 없다 (실제로 받지 않는다).

### STEP 0 — config.json 읽기

```python
import json, os

skill_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(skill_dir, "config.json"), encoding="utf-8") as f:
    cfg = json.load(f)

BASE         = cfg["base_dir"]
INPUT_FILE   = os.path.join(BASE, cfg["input_file"])
TECH_FIELD   = cfg["tech_field"]
PROJECT_NAME = cfg["project_name"]
OUTPUT_NAME  = cfg["output_name"]
WORKSPACE    = os.path.join(BASE, "workspace")
SKILL_OUT    = os.path.join(BASE, "skill", "output")
```

### STEP 1+2 — 환경 초기화 및 텍스트/이미지 추출

`scripts/extract_input.py`(텍스트, 인자 필요)와 `scripts/extract_images.py`(이미지, 인자 없음)를
실행한다. `workspace/` 하위 폴더 생성까지 이 스크립트가 처리한다.

```python
import subprocess
subprocess.run([
    "python", os.path.join(skill_dir, "scripts", "extract_input.py"),
    "--input", INPUT_FILE,
    "--tech-field", TECH_FIELD,
    "--project-name", PROJECT_NAME,
    "--output-name", OUTPUT_NAME,
], check=True)
subprocess.run(["python", os.path.join(skill_dir, "scripts", "extract_images.py")], check=True)
```

추출 결과: `workspace/extracted/text/full_text.txt`, `sec_NN_*.txt`, `toc.json`,
`workspace/extracted/images/`, `image_catalog.json`

### STEP 3 — Claude Code 직접 분석 (API 키 불필요)

> **먼저 `references/step3-schema.md`를 Read할 것.** 스키마·생성 규칙 전문이 그 파일에 있다.

`workspace/extracted/text/`의 텍스트를 Read로 직접 읽어 7개 섹션을 분석하고, 스키마와 **정확히
일치하는 키 이름으로** JSON을 생성한다 (스키마가 다르면 리포트 생성기가 해당 항목을 조용히 건너뛴다).

핵심 원칙 (상세는 `step3-schema.md`):
- 원문에 없는 내용 생성 금지 — 불확실하면 `"원문 미확인"`
- 문체는 개조식/음슴체(`~임`, `~함`, `~됨`), 문단당 5줄(약 200자) 이내
- 수치는 원문 그대로, 기업명·기술명은 영문 원어 병기
- 공급망·가치사슬·생태계 맵은 **원문 그림이 있으면 `*_image` 필드로 재활용**하고, 없을 때만 합성
- `scripts/analyze_sections.py`(정규식 자동 분석)는 초안용일 뿐 — 정밀 보고서에는 쓰지 말 것

생성 파일: `workspace/structured/sec1_market_overview.json` ~ `sec7_implications.json`,
`master_dataset.json`

### STEP 4 — 차트 생성

```python
subprocess.run(["python", os.path.join(skill_dir, "scripts", "generate_charts.py")], check=True)
```

STEP 3에서 채운 `segmentation.axes`/`detail_axes`를 그대로 사용하므로 보고서마다 분류축 개수·이름이
달라져도 코드 수정 없이 동작한다.

> 차트 코드를 **수정**해야 한다면 먼저 `references/chart-design.md`를 Read할 것 — 폰트 크기 역산
> (`mpl_pt`/`pil_pt`), 제목·범례 겹침 방지, 원본 이미지 재활용, 단위 하드코딩 금지 등 실측으로
> 확립된 원칙들이 있다. 그냥 실행만 할 때는 읽지 않아도 된다.

출력: `workspace/charts/*.png`, `chart_catalog.json`

### STEP 5 — HWPX + DOCX 보고서 동시 생성

```python
subprocess.run(["python", os.path.join(skill_dir, "scripts", "generate_reports.py")], check=True)
# 필요시 한 형식만: generate_reports.py --only hwpx  /  --only docx
```

내부적으로 `generate_hwpx.py` → `validate_output_hwpx.py`, `generate_docx.py` →
`validate_output_docx.py` 순서로 실행되며 각각 생성+검증까지 마친다.

> 문서 생성기나 `hwpx_template/`을 **수정**해야 한다면 먼저 `references/document-format.md`를
> Read할 것 — 여백·본문 폭, 캡션 자동 채번, HWPX linesegarray(글씨 겹침·오른쪽 여백), "판독불가"
> 방지 등 실측으로 확립된 원칙들이 있다. 그냥 실행만 할 때는 읽지 않아도 된다.

출력: `workspace/output/{OUTPUT_NAME}.hwpx`, `.docx`

### STEP 6 — 품질 검증

`generate_reports.py`가 STEP 5에서 이미 검증까지 수행한다 (별도 실행 불필요). 검증 항목은
`validate_output_hwpx.py`/`validate_output_docx.py`의 C00~C10 (패키지 구조·7개 섹션·시장규모·CAGR·
출처·시사점 5개·표 2개 이상·이미지 9개 이상·캡션·이미지 참조 일치·표지 정보).

합격 기준: **C00(패키지 구조)은 반드시 통과, 나머지 구조검증 8/10 이상.**

### STEP 7 — 배포

```python
subprocess.run(["python", os.path.join(skill_dir, "scripts", "finalize_report.py")], check=True)
# 중간 파일까지 정리하려면: finalize_report.py --cleanup
```

검증 통과 시 `skill/output/`(= `BASE/skill/output/`)으로 HWPX·DOCX를 복사하고 실행 리포트(md)를 생성한다.

**주의**: 배포 대상 파일이 한글/워드에서 열려 있으면 복사가 `PermissionError`로 실패한다. 해당
프로그램을 닫은 뒤 `finalize_report.py`만 다시 실행하면 된다 (STEP 5부터 다시 돌릴 필요 없음).

---

## 다른 PC·다른 보고서에서 재사용하기 (이식성)

리포지토리를 클론한 뒤 `config.json`만 채우면 **다른 PC·다른 보고서에서도 동일한 구성**(7개 섹션,
경쟁구도·특허 동향 표+그림, 5줄 이내 개조식 문체, 글씨 겹침 없는 HWPX)의 보고서가 나온다.

- **경로 하드코딩 없음**: 모든 스크립트가 `_common.get_base()`로 `config.json`의 `base_dir`을 읽는다.
- **폰트 동봉**: `scripts/assets/NanumGothic.ttf`가 저장소에 포함되어 있어, 시스템에 나눔고딕이 없는
  PC에서도 차트에 한글이 깨지지 않는다.
- **세그먼트 축·지표명 하드코딩 없음**: STEP 3에서 채우는 `segmentation.axes[].label`과
  `value_label`이 그대로 절 제목·차트 축에 쓰이므로(`_common.seg_title()`), 전혀 다른 산업의
  보고서(배터리·반도체 등)를 넣어도 "데이터센터 유형별" 같은 엉뚱한 제목이 남지 않는다.
- **분석 로직은 Claude가 매번 수행**: STEP 3는 스크립트가 아니라 Claude Code가 스키마에 맞춰 원문을
  읽고 채우므로, 어떤 보고서든 같은 스키마·같은 품질 규칙이 적용된다. **다만 보고서 내용 자체(구체적
  수치·사례)는 원문에 따라 달라지는 것이 정상이다** — "동일한 프레임"은 구조·문체·검증 기준이
  동일하다는 뜻이다.

새 PC 체크리스트:
1. `git clone` → `~/.claude/skills/market-analysis`
2. `pip install -r requirements.txt`
3. `cp config.example.json config.json` 후 5개 값 수정 (`base_dir`은 슬래시 `/` 권장)
4. 분석할 보고서를 `base_dir/input_file` 경로에 배치
5. Claude Code에서 `/market-analysis` 실행

---

## 필요 패키지

```bash
pip install -r requirements.txt
```

(`pdfplumber`, `olefile`, `pyhwp`, `lxml`, `matplotlib`, `Pillow`, `numpy`, `python-docx`)

선택: `poppler` — PDF 이미지 추출 품질 향상 시 필요.

## 컬러 팔레트

mint `#2EC4B6` / navy `#1A3A5C` / green `#4CAF50` / orange `#FF7043` / gray `#90A4AE`
