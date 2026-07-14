# market-analysis

영문 시장조사 보고서 한글 HWPX·DOCX 자동요약 스킬

원하는 PDF/HWP/HWPX/DOCX 보고서를 업로드하면, 내용을 자동으로 분석하고 한글 개조식(음슴체)으로
요약한 뒤, **한컴오피스에서 열리는 `.hwpx`**와 **워드에서 열리는 `.docx`** 보고서를 동시에 만들어줍니다.

---

## 🚀 새 PC 셋업 (5분)

```bash
# 1. 스킬 클론
git clone https://github.com/lheajin7/market-analysis-skill.git ~/.claude/skills/market-analysis
cd ~/.claude/skills/market-analysis

# 2. 패키지 설치
pip install -r requirements.txt

# 3. 설정 파일 생성 (⚠️ 필수 — config.json은 저장소에 없습니다)
cp config.example.json config.json
```

**4.** `config.json`을 열어 5개 값을 본인 환경에 맞게 수정합니다:

```json
{
  "input_file":   "report.pdf",
  "tech_field":   "이차전지",
  "project_name": "이차전지 기술개발 시장분석",
  "output_name":  "시장분석_이차전지",
  "base_dir":     "C:/Users/본인계정/my-projects/battery"
}
```

**5.** 분석할 보고서를 `base_dir` 아래 `input_file` 경로에 두고, Claude Code에서 실행:

```
/market-analysis
```

끝입니다. `workspace/`와 `skill/output/` 폴더는 실행 시 자동 생성되며, 결과물 `.hwpx`·`.docx`가
`skill/output/`에 저장됩니다.

### 셋업 시 자주 걸리는 3가지

| 증상 | 원인 | 해결 |
|------|------|------|
| `FileNotFoundError: config.json이 없습니다` | 3단계를 건너뜀 | `cp config.example.json config.json` |
| `❌ 지원하지 않는 형식: md` | **입력은 PDF·HWP·HWPX·DOCX 4종만 지원** | 원문을 PDF나 DOCX로 변환 |
| JSON 파싱 오류 | `base_dir`에 역슬래시(`\`)를 하나만 씀 | 슬래시(`/`) 사용 권장. 역슬래시는 `\\`로 이스케이프 |

> **`config.json`은 저장소에 커밋되지 않습니다** (`.gitignore` 등록). 각자의 실제 경로·과제명이
> 원격에 올라가지 않으므로, PC마다 이 파일만 따로 만들어 쓰면 됩니다. 코드·문서·한글 폰트는
> 저장소에서 그대로 공유됩니다 — 나눔고딕이 동봉되어 있어 폰트 설치도 불필요합니다.

---

## 주요 기능

- 어떤 보고서든 OK: PDF, HWP, HWPX, DOCX 모두 지원합니다.
- 7개 섹션 자동 구성: 시장 개요·역학·생태계(경쟁구도 포함)·지역·세그먼트·R&D(특허 동향 포함)·시사점.
- 차트 자동 생성: matplotlib/Pillow로 최대 13개 차트(공급망·가치사슬·생태계 맵 포함, 문서 삽입 시 축소되어도 읽히도록 큰 폰트 적용)를 자동 생성합니다.
- 원본 그림 재활용: 원문에 공급망·가치사슬·생태계 맵 그림이 있으면 새로 합성하지 않고 원본을 그대로 삽입합니다.
- 개조식/음슴체 출력: `~임`, `~됨`, `~전망됨` 형식의 보고서용 한글 문체로 작성합니다.
- 표·그림마다 2~3줄 해설 자동 삽입.
- 세그먼트 분류축이 보고서마다 달라도(예: 산업별/유형별/솔루션별 등 무엇이든) 자동으로 대응합니다.
- 지표명도 보고서에 맞춰 자동 대응: 세그먼트 수치가 시장규모가 아니라 자본 약정액·투자액이거나,
  R&D 지표가 특허가 아닌 다른 것이어도 축·표 헤더·절 제목이 원문 지표명으로 표기됩니다.
- API 키 불필요: Claude Code가 직접 텍스트를 읽고 분석합니다. 외부 API 비용 없음.
- 한글 폰트 동봉: 저장소 자체에 나눔고딕을 포함해, 어떤 PC에서도 별도 설치 없이 차트에 한글이 표시됩니다.
- config.json으로 설정: 분석할 보고서 경로와 기술분야명만 바꾸면 바로 실행됩니다.

---

## config.json 설정값 상세

위 셋업 4단계에서 채우는 5개 값입니다. 새 보고서로 바꿀 때도 이 값들만 고치면 됩니다 —
스크립트 코드는 건드릴 필요 없습니다.

| 항목 | 설명 |
|------|------|
| `input_file` | 분석할 보고서 경로 (`base_dir` 기준 **상대경로**). PDF·HWP·HWPX·DOCX만 지원 |
| `tech_field` | 기술분야명 — 보고서 제목·섹션 제목에 사용됨 |
| `project_name` | 과제명 — 표지에 표시됨 |
| `output_name` | 출력 파일명 (예: `시장분석_데이터센터냉각`) |
| `base_dir` | 프로젝트 루트 폴더 (보고서 파일과 `workspace/`, `skill/output/`이 여기 생성됨) |

`input_file`은 `base_dir` 기준 상대경로이므로 아래 둘 다 유효합니다:

```json
"input_file": "report.pdf"                    // base_dir 바로 아래
"input_file": "workspace/input/report.pdf"    // 하위 폴더 안
```

---

## 사용법

Claude Code에서:

```
/market-analysis
```

---

## 원격 저장소 (클론 · 저장)

이 스킬은 GitHub 원격 저장소로 관리됩니다: **https://github.com/lheajin7/market-analysis-skill**

### 내려받기 (클론)

```bash
git clone https://github.com/lheajin7/market-analysis-skill.git ~/.claude/skills/market-analysis
```

### 변경사항 저장하기 (커밋 · 푸시)

스킬을 수정한 뒤 원격 저장소에 반영하려면:

```bash
cd ~/.claude/skills/market-analysis
git add -A
git commit -m "변경 내용 요약"
git push
```

> **주의:** `config.json`은 `.gitignore`에 등록되어 있어 `git add -A`를 해도 커밋되지 않습니다.
> 각자의 실제 경로·과제명 등 개인 설정이 원격에 올라가지 않으므로, 안심하고 `git add -A`를 사용해도 됩니다.

새 PC를 처음 연결할 때는 최초 1회 사용자 정보를 설정합니다:

```bash
git config user.name  "이름"
git config user.email "메일주소"
```

---

## 실행 흐름

```
STEP 0    config.json 읽기
STEP 1+2  환경 초기화 + 텍스트·이미지 추출 (PDF/HWP/HWPX/DOCX → sec_*.txt, 원본 이미지)
STEP 3    Claude Code 직접 분석 → 섹션별 JSON 생성 (references/step3-schema.md의 스키마·문체 규칙 적용)
STEP 4    차트 생성 (최대 13개 PNG — 원문 그림이 있으면 재활용, 없으면 합성)
STEP 5    HWPX + DOCX 보고서 동시 생성 (generate_reports.py)
STEP 6    품질 검증 (구조 C00~C10, generate_reports.py에 포함됨)
STEP 7    output/ 배포 + 실행 리포트(md) 생성 (finalize_report.py)
```

각 단계별 상세 규칙은 `SKILL.md`와 `references/`에 나뉘어 있습니다 — 아래 "문서 구조" 참고.

---

## 파일 구조

```
market-analysis/
├── SKILL.md              # 스킬 정의 — 7단계 실행 흐름 (Claude가 /market-analysis 실행 시 읽는 파일)
├── references/           # 상세 규칙 — 필요한 시점에만 읽힘 (아래 "문서 구조" 참고)
│   ├── step3-schema.md       # STEP 3 JSON 스키마·작성 규칙 (매 실행 필수)
│   ├── chart-design.md       # 차트 설계 원칙 (generate_charts.py 수정 시)
│   └── document-format.md    # HWPX·DOCX 포맷 원칙 (문서 생성기 수정 시)
├── README.md
├── config.example.json   # 설정 템플릿 (커밋됨)
├── config.json           # 사용자 실제 설정 (.gitignore — 커밋 안 됨)
├── requirements.txt
├── .gitignore
└── scripts/
    ├── _common.py               # config.json → base_dir 로더 + 세그먼트 제목/지표명 규칙 (공용)
    ├── extract_input.py         # 텍스트 추출 (STEP 1+2)
    ├── extract_images.py        # 이미지 추출 (STEP 1+2)
    ├── generate_charts.py       # 차트 생성 (STEP 4)
    ├── generate_hwpx.py         # HWPX 생성 (STEP 5)
    ├── generate_docx.py         # DOCX 생성 (STEP 5)
    ├── generate_reports.py      # HWPX+DOCX 동시 생성·검증 오케스트레이터
    ├── validate_output_hwpx.py  # HWPX 품질 검증 (STEP 6)
    ├── validate_output_docx.py  # DOCX 품질 검증 (STEP 6)
    ├── finalize_report.py       # 최종 배포 (STEP 7)
    ├── hwpx_template/           # 실제 OWPML 정적 파트 (mimetype/version.xml/header.xml 등)
    └── assets/
        └── NanumGothic.ttf      # 동봉 한글 폰트 (SIL Open Font License)
```

---

## 문서 구조 (`SKILL.md` + `references/`)

`SKILL.md`는 스킬 실행 시 **매번 통째로 컨텍스트에 로드**됩니다. 그래서 여기에는 7단계 실행 흐름만
남기고, 상세 규칙은 `references/` 아래로 분리해 **필요한 시점에만 읽도록** 했습니다.

| 문서 | 내용 | 언제 읽히나 |
|------|------|------------|
| `SKILL.md` | 7단계 실행 흐름, config 설정, 이식성 | 스킬 실행 시 항상 |
| `references/step3-schema.md` | 섹션별 JSON 스키마, 문체·작성 규칙, 선택 필드 | **STEP 3 (매 실행)** |
| `references/chart-design.md` | 폰트 크기 역산, 제목·범례 겹침 방지, 원본 이미지 재활용, 단위 하드코딩 금지 | `generate_charts.py` 수정 시 |
| `references/document-format.md` | 여백·본문 폭, 캡션 자동 채번, HWPX linesegarray·"판독불가" 방지 | HWPX·DOCX 생성기 수정 시 |

- **보고서를 생성하기만** 한다면 `SKILL.md` + `step3-schema.md`만 관여합니다.
- 차트·문서 생성기 코드를 **고칠 때만** 나머지 두 문서가 읽힙니다. 두 문서에 적힌 원칙은 대부분
  실측으로 발견된 버그(글씨 겹침, 범례가 막대를 가림, 한컴오피스 판독불가 등)에서 나온 것이므로,
  해당 코드를 수정하기 전에 반드시 확인하세요.

---

## 필요 환경

필수:

- Python 3.8 이상
- `pip install -r requirements.txt`
- Claude Code + `/market-analysis` 스킬 설치

선택:

- `poppler` — PDF 이미지 추출 품질 향상 시 필요. [다운로드](https://github.com/oschwartz10612/poppler-windows/releases) 후 PATH 등록
- 한컴오피스 / MS Word — 결과물 확인용 (없어도 생성 자체는 됨)

---

## 이식성 (다른 PC·다른 보고서에서도 동일 품질)

- 절대경로 하드코딩 없음 — `config.json`의 `base_dir`만 맞추면 어떤 PC에서도 동작합니다.
- 한글 폰트가 저장소에 동봉되어 있어 시스템 폰트 설치 여부와 무관합니다.
- 세그먼트 분류축(산업별/유형별/솔루션별 등)이 보고서마다 달라도 자동으로 대응합니다 — 코드에
  특정 보고서의 카테고리명이 하드코딩되어 있지 않습니다.
- **지표명·통화 단위도 하드코딩되어 있지 않습니다.** 세그먼트 수치가 시장규모가 아니거나(자본
  약정액·투자액 등), R&D 지표가 특허가 아니거나, 통화가 달러가 아니어도(유로·엔 등) 원문의 지표명과
  통화 기호가 차트 축·표 헤더·절 제목에 그대로 반영됩니다. 해당 선택 필드는
  `references/step3-schema.md`를 참고하세요 (`value_label`, `market_share_metric`,
  `market_share_desc`, `section_title`, `metric_label`, `currency_unit`).
- STEP 3의 분석·문체·검증 규칙은 `references/step3-schema.md`에 고정되어 있어, Claude Code가 어떤
  보고서를 분석하든 동일한 스키마·품질 기준(음슴체, 5줄 제한, 표/그림 설명, 경쟁구도 해석 등)을
  적용합니다. 다만 보고서의 구체적 수치·사례 자체는 원문 내용에 따라 달라지는 것이 정상입니다.

---

## 라이선스

MIT License — 자유롭게 사용·수정·배포 가능.
단, 분석에 사용한 원본 시장조사 보고서의 저작권은 각 발행사에 귀속됩니다.
나눔고딕 폰트는 SIL Open Font License 1.1을 따릅니다.
