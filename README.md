# market-analysis

영문 시장조사 보고서 한글 HWPX·DOCX 자동요약 스킬

원하는 PDF/HWP/HWPX/DOCX 보고서를 업로드하면, 내용을 자동으로 분석하고 한글 개조식(음슴체)으로
요약한 뒤, **한컴오피스에서 열리는 `.hwpx`**와 **워드에서 열리는 `.docx`** 보고서를 동시에 만들어줍니다.

---

## 주요 기능

- 어떤 보고서든 OK: PDF, HWP, HWPX, DOCX 모두 지원합니다.
- 7개 섹션 자동 구성: 시장 개요·역학·생태계(경쟁구도 포함)·지역·세그먼트·R&D(특허 동향 포함)·시사점.
- 차트 자동 생성: matplotlib/Pillow로 최대 12개 차트(문서 삽입 시 축소되어도 읽히도록 큰 폰트 적용)를 자동 생성합니다.
- 개조식/음슴체 출력: `~임`, `~됨`, `~전망됨` 형식의 보고서용 한글 문체로 작성합니다.
- 표·그림마다 2~3줄 해설 자동 삽입.
- 세그먼트 분류축이 보고서마다 달라도(예: 산업별/유형별/솔루션별 등 무엇이든) 자동으로 대응합니다.
- API 키 불필요: Claude Code가 직접 텍스트를 읽고 분석합니다. 외부 API 비용 없음.
- 한글 폰트 동봉: 저장소 자체에 나눔고딕을 포함해, 어떤 PC에서도 별도 설치 없이 차트에 한글이 표시됩니다.
- config.json으로 설정: 분석할 보고서 경로와 기술분야명만 바꾸면 바로 실행됩니다.

---

## 설치 방법

### 1단계: 스킬 복사

```bash
git clone https://github.com/lheajin7/market-analysis-skill.git ~/.claude/skills/market-analysis
```

### 2단계: Python 패키지 설치

```bash
cd ~/.claude/skills/market-analysis
pip install -r requirements.txt
```

### 3단계: 설정 파일 준비

```bash
cp config.example.json config.json
```

`config.json`을 열어 아래 5개 값을 본인 환경에 맞게 수정합니다 (`base_dir`은 슬래시 `/` 사용 권장 —
역슬래시를 쓰려면 JSON 규칙상 `\\`로 이스케이프해야 합니다):

| 항목 | 설명 |
|------|------|
| `input_file` | 분석할 보고서 경로 (`base_dir` 기준 상대경로) |
| `tech_field` | 기술분야명 — 보고서 제목·섹션 제목에 사용됨 |
| `project_name` | 과제명 — 표지에 표시됨 |
| `output_name` | 출력 파일명 (예: `시장분석_데이터센터냉각`) |
| `base_dir` | 프로젝트 루트 폴더 (보고서 파일과 `workspace/`, `skill/output/`이 여기 생성됨) |

`config.json`은 `.gitignore`에 등록되어 있어, 각자의 실제 경로가 실수로 커밋되지 않습니다. 새 보고서로
바꿀 때도 이 파일 5개 값만 고치면 됩니다 — 스크립트 코드는 건드릴 필요 없습니다.

분석할 보고서 파일은 `base_dir` 아래 `input_file` 경로에 두면 됩니다 (`workspace/` 하위 폴더는
실행 시 자동 생성됩니다).

---

## 사용법

Claude Code에서:

```
/market-analysis
```

---

## 실행 흐름

```
STEP 0    config.json 읽기
STEP 1+2  환경 초기화 + 텍스트·이미지 추출 (PDF/HWP/HWPX/DOCX → sec_*.txt)
STEP 3    Claude Code 직접 분석 → 섹션별 JSON 생성 (SKILL.md의 스키마·문체 규칙 적용)
STEP 4    차트 생성 (최대 12개 PNG)
STEP 5    HWPX + DOCX 보고서 동시 생성 (generate_reports.py)
STEP 6    품질 검증 (구조 C00~C10, generate_reports.py에 포함됨)
STEP 7    output/ 배포 + 실행 리포트(md) 생성 (finalize_report.py)
```

자세한 각 단계별 규칙(JSON 스키마, 문체, 표/그림 설명 규칙, HWPX 겹침 방지 등)은 `SKILL.md`를 참고하세요.

---

## 파일 구조

```
market-analysis/
├── SKILL.md              # 스킬 정의 (Claude가 /market-analysis 실행 시 읽는 파일)
├── README.md
├── config.example.json   # 설정 템플릿 (커밋됨)
├── config.json           # 사용자 실제 설정 (.gitignore — 커밋 안 됨)
├── requirements.txt
├── .gitignore
└── scripts/
    ├── _common.py               # config.json → base_dir 로더 (모든 스크립트가 공용으로 사용)
    ├── extract_input.py         # 텍스트 추출 (STEP 1+2)
    ├── extract_images.py        # 이미지 추출 (STEP 1+2)
    ├── analyze_sections.py      # 규칙 기반 자동 분석 — 빠른 초안용, 정밀 보고서엔 미권장 (STEP 3 대안)
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
- STEP 3의 분석·문체·검증 규칙은 `SKILL.md`에 고정되어 있어, Claude Code가 어떤 보고서를 분석하든
  동일한 스키마·품질 기준(음슴체, 5줄 제한, 표/그림 설명, 경쟁구도 해석 등)을 적용합니다. 다만
  보고서의 구체적 수치·사례 자체는 원문 내용에 따라 달라지는 것이 정상입니다.

---

## 라이선스

MIT License — 자유롭게 사용·수정·배포 가능.
단, 분석에 사용한 원본 시장조사 보고서의 저작권은 각 발행사에 귀속됩니다.
나눔고딕 폰트는 SIL Open Font License 1.1을 따릅니다.
