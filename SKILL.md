# market-analysis — 시장분석 보고서 자동요약 스킬

영문 시장조사 보고서(PDF/HWP/HWPX/DOCX)를 입력받아
7개 섹션 + 최대 13개 차트(공급망·가치사슬·생태계 맵 포함)가 포함된 한글 **HWPX(한컴오피스) +
DOCX(워드)** 보고서를 자동 생성합니다.

---

## 사용법

```
/market-analysis
```

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

   - `base_dir`은 **슬래시(`/`)** 사용을 권장한다. 역슬래시(`\`)를 쓰려면 JSON 규칙상 `\\`로 이스케이프해야 하며,
     하나만 쓰면(`\2`, `\시` 등) JSON 파싱 오류가 난다.
   - `config.json`은 `.gitignore`에 등록되어 있어 각자의 실제 경로가 커밋되지 않는다. 보고서를 바꿀 때도
     이 5개 값만 고치면 된다 (스크립트 코드는 손댈 필요 없음).
   - 이 복사 단계를 건너뛰어 `config.json`이 없는 상태로 실행하면, `_common.get_base()`가
     `config.example.json을 config.json으로 복사한 뒤 base_dir 등 값을 채우세요`라는 안내와 함께
     `FileNotFoundError`로 중단시킨다. 위 복사 단계를 먼저 진행하면 된다.

2. 분석할 보고서 파일을 `base_dir` 아래 `input_file` 경로에 둔다 (`workspace/` 하위 폴더는
   `/market-analysis` 실행 시 자동 생성되므로 미리 만들 필요 없음).

3. Python 패키지 설치: `pip install -r requirements.txt`

나눔고딕 폰트는 `scripts/assets/NanumGothic.ttf`로 저장소에 동봉되어 있어 별도 설치 없이 어떤 PC에서도
차트에 한글이 정상 표시된다.

---

## Claude Code 실행 지침

`/market-analysis` 호출 시 Claude Code는 아래 7단계를 순서대로 수행한다.
스크립트는 모두 `config.json`의 `base_dir`을 `_common.get_base()`로 읽어 동작하므로, STEP 2 이후의
스크립트 호출에는 `--workspace` 같은 인자를 넘길 필요가 없다 (실제로 받지 않는다).

---

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

---

### STEP 1+2 — 환경 초기화 및 텍스트/이미지 추출

`scripts/extract_input.py`(텍스트, `--input`/`--tech-field`/`--project-name`/`--output-name` 인자 필요)와
`scripts/extract_images.py`(이미지, 인자 없음)를 실행한다. `workspace/` 하위 폴더 생성까지 이 스크립트가 처리한다.

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

추출 결과: `workspace/extracted/text/full_text.txt`, `sec_NN_*.txt`, `toc.json`

---

### STEP 3 — Claude Code 직접 분석 (API 키 불필요)

**`scripts/analyze_sections.py`(정규식 기반 자동 분석)는 빠른 초안용일 뿐, 정밀한 보고서에는 사용하지
말 것.** 필드명이 리포트 생성기의 실제 스키마와 어긋나는 곳이 있어 본문에 공란·TOC 잔여 텍스트가
남는다. **정밀한 보고서가 필요하면 Claude Code가 아래 절차로 직접 분석·작성한다.**

`workspace/extracted/text/full_text.txt`와 `sec_*.txt` 파일들을 Read 도구로 직접 읽어
각 섹션을 분석하고, **아래 스키마와 정확히 일치하는 키 이름으로** JSON을 생성한다
(스키마가 다르면 리포트 생성기가 해당 항목을 조용히 건너뛴다).

**생성 규칙 (모든 보고서 공통):**
- 수치(시장규모·CAGR·연도·%)는 원문 그대로 유지
- 기업명·기술명은 영문 원어 괄호 병기
- 원문에 없는 내용 생성 금지 — 불확실하면 `"원문 미확인"` 표기 (해당 필드는 자동으로 본문에서 제외됨)
- 응답은 순수 JSON만 (마크다운 코드블록 없이)
- 문체: 개조식/음슴체 (`~임`, `~함`, `~됨`, `~전망됨`) — "~습니다/합니다/됩니다" 사용 금지
- **문단(또는 불릿 항목)당 5줄(약 200자) 이내**로 작성 — 넘으면 문장 단위로 나눠 여러 개조식 항목으로 분리
  (리포트 생성기의 `_split_para()`가 안전망으로 한 번 더 잘라주지만, STEP 3 단계에서 이미 짧게 쓰는 것이 원칙)
- **세그먼트/카테고리성 데이터에서 원문이 "최대 규모"·"최고 성장률"을 명시한 항목은**, 해당 항목의
  `growth_note`(또는 대응 설명 필드)에 **"① 최대 세그먼트명+설명, ② 최고 성장률 세그먼트명+설명,
  ③ 그 성장 원인"** 3요소를 담아 작성한다 — 단순히 "(원문 명시)"만 붙이고 끝내지 않는다.
- **삽입되는 모든 표·그림에는 그 표/그림이 무엇을 보여주는지 설명하는 문장(2~3줄, 5줄 이내)을 함께
  작성한다** — 이 설명 문장 자체는 리포트 생성기 코드에 있으므로 JSON에는 원본 데이터만 정확히 채우면 됨.
- 경쟁사 점유율/랭킹 표가 있는 섹션은 **"경쟁구도 (Competitive Landscape)"** 로 명명하고, 상위 기업의
  점유율과 나머지의 분포(파편화 여부 등)를 해석하는 문장을 함께 작성한다.
- 참고 템플릿 파일(예: `output/[template] ...`)이 있으면 **글자 크기·구조(장/절 표기, 굵기 등)만**
  참조하고, 템플릿에만 있고 원문(`extracted/text/`)에서 확인되지 않는 수치·기업명·사례는 절대 포함하지
  않는다 — 반드시 원문 grep으로 대조 후 반영.

**JSON 스키마 (필드명 고정 — `market_overview` 등은 `master_dataset.json`의 최상위 키):**

```
sec1_market_overview.json  → master_dataset.json["market_overview"]
{
  "source_report": "보고서 전체 서지정보 (표지에만 쓰임, 예: 'BIS Research, Data Center Cooling Market - A Global and Regional Analysis (Analysis and Forecast: 2025-2035), April 2025')",
  "currency_unit": "원문이 실제로 시장규모를 표기하는 통화·단위 (예: 'USD$'가 원문 표기면 '$B',
    유로면 '€B' 등) — 아래 참고, 하드코딩된 고정값이 아니라 매 보고서마다 원문을 보고 채울 것",
  "base_year": 2025, "forecast_year": 2035,
  "base_year_size_usd_b": 0.0, "cagr_pct": 0.0,
  "growth_background": "성장 배경 개조식 서술 (표지 아래 본문, 5줄 이내)",
  "power_demand_data": {
    "years": [2025, 2027, ...], "demand_incl_ai_twh": [...], "demand_excl_ai_twh": [...],
    "efficiency_gain_pct": [...]
  },
  "scenarios": {
    "optimistic":  {"size_usd_b": 0.0, "cagr_pct": 0.0},
    "realistic":   {"size_usd_b": 0.0, "cagr_pct": 0.0},
    "pessimistic": {"size_usd_b": 0.0, "cagr_pct": 0.0}
  },
  "key_trends": [{"trend": "트렌드명", "description": "설명"}]
}
※ `power_demand_data`는 전력수요 관련 수치가 원문에 없으면 `{}`로 비워둘 것(그러면 해당
  그림은 자동 생략됨).
※ `currency_unit`은 원문(표지·시장 정의 등)에 실제로 쓰인 통화를 확인해서 채운다 — 대부분의
  영문 시장조사 보고서는 미국 달러(US$/USD)를 쓰므로 그 경우 `"$B"`가 되지만, 유로/파운드/엔 등
  다른 통화를 쓰는 원문이면 그 통화 기호로 채울 것(예: `"€B"`). **모든 `*_usd_b`/`sizes` 수치
  필드는 이름과 무관하게 항상 십억 단위(B, billion)로 정규화해 저장하는 내부 규칙은 그대로
  유지**하고(차트 축 스케일 계산 등 내부 일관성을 위해 필요), `currency_unit`은 그 수치를 표에
  표시할 때 붙일 통화 기호만 결정한다 — 즉 숫자 스케일은 항상 십억 단위, 통화 기호만 원문 기준으로
  가변적이다.

sec2_market_dynamics.json  → ["market_dynamics"]
{
  "drivers": [{"title": "...", "description": "..."}],
  "restraints": [{"title": "...", "description": "..."}],
  "has_challenges": false,
  "challenges": [{"title": "...", "description": "..."}],
  "opportunities": [{"title": "...", "description": "..."}]
}

sec3_ecosystem.json  → ["ecosystem"]
{
  "market_share_table": [{"company": "기업명", "share_range": "8-10%"}],
  "notable_movements": "주요 동향 개조식 서술 또는 원문 미확인",

  "supply_chain": [{"stage_order": 1, "stage_name": "단계명(한글)", "stage_name_en": "영문명",
                     "representative_companies": ["기업1", "기업2", "기업3"],
                     "representative_categories": ["카테고리1", "카테고리2"]}],
  "supply_chain_desc": "공급망 구조에 대한 실제 내용 요약 (2~3줄, 없으면 빈 문자열)",
  "supply_chain_image": "원문에 실제 공급망 그림이 있으면 그 파일명 (workspace/extracted/images/ 아래,
                          예: 'p24_img1.png') — 없으면 null. 있으면 supply_chain 합성은 생략되고
                          이 원본 그림이 그대로 삽입된다.",

  "value_chain": [{"stage_order": 1, "stage_name": "...", "stage_name_en": "...",
                    "representative_companies": [...], "representative_categories": [...]}],
  "value_chain_desc": "가치사슬 구조에 대한 실제 내용 요약 (2~3줄, 없으면 빈 문자열)",
  "value_chain_image": "원문에 실제 가치사슬 그림이 있으면 파일명, 없으면 null",

  "key_players_by_category": [{"category": "카테고리명",
                                "companies": [{"name": "기업명", "country": "국가"}]}],
  "ecosystem_map_desc": "생태계 구조(플레이어 카테고리 간 관계 등)에 대한 실제 내용 요약, 없으면 빈 문자열",
  "ecosystem_map_image": "원문에 실제 생태계 맵 그림이 있으면 파일명, 없으면 null"
}
※ market_share_table은 "경쟁구도(Competitive Landscape)" 섹션에 그대로 표로 들어가며,
  상위 3개사 점유율 + 나머지 파편화 정도를 해석하는 문장이 자동으로 붙는다.
※ **"3. 기술·솔루션 생태계"는 (1) 공급망(Supply Chain) → (2) 가치사슬(Value Chain) →
  (3) 생태계 맵(Ecosystem Map) 3개 하위 절로 고정 구성된다.** `supply_chain`/`value_chain`은
  형태가 동일한 단계형 플로우 데이터(원문에 그런 챕터가 없으면 빈 리스트 `[]`로 둘 것 — 억지로
  만들어내지 말 것), `key_players_by_category`는 생태계 맵의 폴백 데이터다.
※ **원본 이미지 재활용 원칙 (`*_image` 필드, STEP 4 "원본 이미지 활용" 절 참고)**: STEP 3
  진행 중 `workspace/extracted/images/image_catalog.json`과 실제 이미지를 확인해, 공급망/
  가치사슬/생태계 맵 각각에 대응하는 원문 그림이 있으면(페이지 위치는 파일명의 `pNNNN_imgNN`
  로 유추) 그 파일명을 `*_image` 필드에 적어 넣는다. 원문에 없으면 `null`로 두고, 그 경우에만
  `supply_chain`/`value_chain`/`key_players_by_category`의 구조화 데이터로 합성 다이어그램을
  생성한다 — 원본이 있는데 합성으로 대체하지 않는다. 재활용 후보 이미지를 직접 열어 확인할 것 —
  PDF 이미지 추출이 바운딩박스를 넓게 잡아 다이어그램 아래에 원문 본문 문단까지 함께 잘려 들어온
  경우가 실측 확인됐다(STEP 5 "세로 높이 상한" 절 참고). 그런 경우 crop한 새 파일로 저장해 `*_image`
  필드에 그 파일명을 쓸 것 — 원본 문단이 섞인 이미지를 그대로 쓰지 않는다.

sec4_regional_analysis.json  → ["regional_analysis"]
{
  "leading_region": "권역명", "fastest_growing_region": "권역명",
  "regions": [{"name": "권역명 (≤20자)",
    "short_term_opportunity": "≤30자", "short_term_risk": "≤30자",
    "long_term_opportunity": "≤30자", "long_term_risk": "≤30자"}]
}
※ 표 셀에 그대로 들어가므로 각 항목은 반드시 30자 이내로 간결하게 작성 (넘으면 잘림).

sec5_segmentation.json  → ["segmentation"]
{
  "years": [2024, 2035],
  "axes": [
    {"label": "분류축 이름 (보고서에 실제 있는 이름 그대로, 예: 최종수요 산업별)",
     "segments": [{"name": "세그먼트명", "sizes": [기준연도값, 예측연도값],
                   "cagr_pct": 0.0, "growth_note": "위 '3요소' 규칙 적용"}]},
    { ... 축 2 ... }, { ... 축 3 ... }, { ... 축 4 ... }
  ],
  "detail_axes": [
    {"label": "세부 분류축 이름 (있는 경우만)", "segments": [...]}
  ],
  "adoption_trend": {
    "label": "채택률/보급률 등 추이 지표 이름 (예: 액체냉각 기술 채택률)",
    "years": [2024, 2026, ...],
    "series": [{"label": "시나리오 A", "values_pct": [...]},
               {"label": "시나리오 B", "values_pct": [...]}]
  }
}
※ **`axes`는 최대 4개까지 순서대로 사용된다.** 원문 보고서의 세그먼트 분류가 몇 개든, 실제 그
  보고서에 있는 분류축 이름을 `label`에 그대로 쓸 것 — "최종수요 산업별/데이터센터 유형별" 같은
  이전 보고서(데이터센터 냉각) 예시를 다른 보고서에 그대로 베끼면 안 된다.
  `detail_axes`는 최대 3개, 없으면 빈 리스트. `adoption_trend`도 원문에 없으면 `{}`로 비워둘 것
  (없는 데이터를 만들어내지 않는다). **`series`는 2개로 제한되지 않는다** — 원문에 냉각 방식별
  채택률처럼 3개 이상(예: 액체냉각·공랭식·증발냉각·프리쿨링 4개)이 있으면 있는 그대로 다 채울
  것. `v6_1()`(V6_1 차트)이 `series` 개수와 무관하게 전부 그리고 y축 상한도 모든 series의
  값을 합쳐 계산하도록 되어 있다 — 예전에는 처음 2개만 그리고 y축 상한도 첫 번째 series
  기준으로만 잡아서,가장 값이 큰 series(예: 공랭식 66~68%)가 첫 series(액체냉각 17~19%) 기준
  축 범위 밖으로 밀려나 그래프에서 보이지 않게 되는 버그가 실측 확인됐다(사용자가 "그래프가
  사라졌다"고 보고). 새로 이런 다중 계열 선그래프를 추가할 때도 y축 상한은 반드시 그릴 모든
  계열의 값을 합쳐서 계산할 것 — 일부 계열만 보고 정하면 값 범위가 다른 다른 계열이 잘려나간다.

sec6_rnd_trends.json  → ["rnd_trends"]
{
  "patent_trend": {
    "description": "2~3줄 요약",
    "top_countries": ["국가1", "국가2", ...],
    "top_companies": ["기업1", "기업2", ...],
    "top_companies_detail": [{"company": "기업1", "count": 12345}, ...],
    "metric_label": "특허 출원 건수",   // (선택) 표 헤더·차트 라벨·제목에 쓰이는 지표명. 생략 시 기본 '특허 출원 건수'
    "metric_unit": "건",                 // (선택) 수치 뒤 단위. 생략 시 기본 '건'
    "top_countries_label": "주요 특허 보유국",     // (선택) 국가 목록 불릿 라벨. 생략 시 기본값
    "top_companies_label": "주요 특허 보유 기업"    // (선택) 기업 목록 불릿 라벨. 생략 시 기본값
  },
  "case_studies": [{"organization": "기관/기업", "title": "사례명", "technology": "기술", "outcome": "결과"}],
  "government_initiatives": [{"region": "권역", "initiative": "정책명", "description": "설명"}],
  "emerging_technologies": [{"tech": "기술명", "description": "설명"}]
}
※ **특허 동향의 표 + 로그스케일 막대그래프(V6_2)는 `top_companies_detail`(기업별 수치)로
  그린다.** 예전에는 `top_countries_detail`(국가별)을 썼는데, 실제 원문(BIS Research 보고서
  등)의 특허 동향 차트/표는 국가별이 아니라 **기업별** 출원 건수 비교인 경우가 많아 원문과
  다른 그래프가 나오는 문제가 있었다 — **STEP 3에서 원문의 특허 동향 차트가 실제로 국가
  단위인지 기업 단위인지 반드시 확인하고 그에 맞는 필드를 채울 것** (혼동하지 말고 원문 그대로).
  수치를 알 수 없으면 `top_companies`(이름만)만 채우고 `top_companies_detail`은 생략 — 없는
  수치를 지어내지 말 것. `top_countries`/`top_companies`(이름만)는 항상 본문에 "주요 특허
  보유국/보유 기업" 불릿으로 별도 표시되므로, 표/그래프에 안 쓰는 쪽도 이름 목록만은 채워둘 것.
※ **원문 지표가 '특허 출원 건수'가 아니면 `metric_label`/`metric_unit`으로 표 헤더·차트 라벨을
  바꿀 것 (하드코딩 아님).** 예: 원문이 특허가 아니라 'ADC 개발 파이프라인 보유 자산 수'를 기업별로
  제시하면 `metric_label`="개발 파이프라인 자산 수", `metric_unit`="개"로 채운다 — 그러면 표 헤더·차트
  x축·제목이 모두 그 지표명으로 바뀐다. 국가/기업 불릿 라벨도 `top_countries_label`/
  `top_companies_label`로 덮어쓸 수 있다(예: "주요 개발 보유국"). 네 필드 모두 생략하면 기본값(특허
  기준)이 그대로 쓰이므로, 원문이 실제 특허 데이터인 보고서에서는 채우지 않아도 된다.
※ **`case_studies`/`government_initiatives`/`emerging_technologies`는 위 스키마의 필드명을
  정확히 지킬 것 — `title`/`description`만 쓰는 실수가 두 차례 반복됐다(실측 확인).** 각각의
  올바른 필드는 `case_studies`={`organization`, `title`, `technology`, `outcome`},
  `government_initiatives`={`region`, `initiative`, `description`},
  `emerging_technologies`={`tech`, `description`}이다 — 이 중 하나라도 다른 필드명(특히
  `title`/`description`만 있는 형태)을 쓰면 리포트 생성기가 없는 필드를 빈 문자열로 읽어
  본문에 `[] 제목 — :` 같은 깨진 텍스트로 렌더링된다(예: `[{organization}] {title} — {technology}:
  {outcome}` 형식에서 `organization`/`technology`/`outcome`이 비면 대괄호와 콜론만 남는다).
  세 필드 그룹 모두 채운 뒤에는 반드시 각 항목의 키가 위 스키마와 일치하는지 다시 확인할 것.

sec7_implications.json  → ["implications"]
{
  "key_conclusions": ["개조식 결론 1", "개조식 결론 2"],
  "implications": {
    "i1_promising_tech": "...", "i2_tech_gap": "...", "i3_supply_chain": "...",
    "i4_policy": "...", "i5_kist": "..."
  },
  "data_basis_note": "데이터 근거 관련 주석 (선택)"
}
※ `implications.iN_*` 문자열 앞에 "①②③④⑤" 등 번호를 직접 붙이지 말 것 — 리포트 생성기가
  "① 유망 기술 방향" 같은 제목을 별도로 붙이므로, 붙이면 번호가 두 번 표시된다.
```

`master_dataset.json`은 위 7개 파일을 그대로 병합하고 최상위에 `tech_field`, `project_name`을 추가해 저장한다.

생성 파일: `workspace/structured/sec1_market_overview.json` ~ `sec7_implications.json`, `master_dataset.json`

---

### STEP 4 — 차트 생성

```python
subprocess.run(["python", os.path.join(skill_dir, "scripts", "generate_charts.py")], check=True)
```

**차트 폰트 크기 원칙 (중요 — 예전 방식으로 되돌리지 말 것)**: 생성된 PNG는 원본 캔버스 크기와
무관하게 문서 삽입 시 "고정 폭"으로 리사이즈된다(DOCX/HWPX 모두 본문 폭 ~6.77in — 표와 동일 폭).
그런데 차트마다 원본 캔버스 폭이 다르다 — matplotlib는 figsize가 10in/12in/15in로 제각각이고,
Pillow 인포그래픽은 캔버스가 2000~2600px로 훨씬 넓다. **모든 차트에 똑같은 pt/px 값을 쓰면
캔버스 폭 차이만큼 삽입 후 크기가 들쭉날쭉해진다** — figsize가 좁은 차트는 상대적으로 덜 축소되어
제목이 본문보다 훨씬 커 보이고, 반대로 캔버스가 넓은 Pillow 인포그래픽이나 figsize를 과도하게
키운 표는 축소율이 너무 커서 글씨가 거의 보이지 않게 된다(실제로 2026-07 보고서에서 이 문제가
발생해 수정됨).

**(참고, 현재는 해당 차트 없음) matplotlib 표를 이미지로 만들 경우 저장 후 실제 폭을 재확인할
것**: 표 형태의 데이터는 원칙적으로 이미지가 아니라 `b.table()`로 넣으므로(아래 "표 형태의
데이터는 그림이 아니라 실제 표로" 참고) 이 패턴이 필요한 경우는 이제 거의 없지만, 부득이 정말
시각적 차트(추세선 등)를 matplotlib 표와 결합해 만들어야 한다면 기록해둔다: `ax.table(...)
.auto_set_column_width()`는 셀 내용에 맞춰 열 폭을 늘릴 수 있어, 저장된 PNG의 실제 폭이 지정한
figsize보다 넓어지는 경우가 있다(제목이 길거나 셀 텍스트가 많을 때). 그러면 폰트 계산에 쓴 명목
figsize가 실제보다 좁아 보여 글자가 다시 작아진다 — (예전 V4_2가 그랬다) 한 번 저장한 뒤
`Image.open()`으로 실제 폭을 재보고, 명목값과
8% 이상 차이 나면 그 실측 폭으로 폰트를 다시 계산해 한 번 더 저장하는 2단계 패턴을 쓸 것. 또한
표·그림 내부 제목에 출처 문구를 넣지 말 것 — 출처는 표지(첫 페이지 요약)에만 싣고 본문의
그림·표에는 넣지 않는 것이 원칙이며, 긴 출처 문구 자체가 이 문제를 유발하는 가장 흔한 원인이다.

**해결책**: `generate_charts.py` 상단의 `mpl_pt(role, fig_width_in)` / `pil_pt(role, canvas_w_px)`
헬퍼가 "삽입 후 몇 pt로 보이길 원하는가"(`EFFECTIVE_PT` 딕셔너리, 본문 10pt·캡션 9pt와 조화되도록
9~12pt 수준으로 설정됨)를 그 차트의 실제 원본 폭 기준으로 역산해 원본 fontsize를 반환한다. **새 차트를
추가하거나 기존 차트를 수정할 때도 하드코딩된 pt/px 값 대신 반드시 이 두 헬퍼를 통해 크기를 정할 것.**
Pillow 인포그래픽(V2_1/V3_1/V3_2)은 폰트 크기가 캔버스 폭에 따라 달라지므로, 박스 높이·줄 간격 등
레이아웃 치수도 폰트 크기에서 역산하고(고정값 금지), 실제 캔버스를 만들기 전에 필요한 높이를 먼저
측정하는 2단계 방식을 쓴다(그렇지 않으면 폰트가 커졌을 때 내용이 잘리거나 다음 항목과 겹친다).

**그림 안 글자는 절대 잘리거나 생략되면 안 된다 (중요)**: 회사명·단계명·항목 제목처럼 길이가
들쭉날쭉한 라벨을 `len()`으로 자르거나(`text[:20]`) 말줄임표로 축약하지 말 것 — 대신 `_wrap()`
(Pillow, 실측 폭 기준) 또는 `_wrap_label()`/`textwrap.wrap()`(matplotlib 범례·표처럼 실측 draw
컨텍스트가 없는 곳, 글자수 기준)으로 항상 여러 줄로 감싸고, 그만큼 박스 높이·행 높이를 늘려서
전체 내용이 다 보이게 한다. V3_1/V3_2/V3_3은 항목마다 필요한 줄 수를 먼저 측정해 박스 높이를
동적으로 정한다.

**차트 제목·범례·데이터가 서로 겹치면 안 된다 (중요 — 실측으로 발견된 문제들)**: 시계열·세그먼트
차트에서 아래 패턴들이 실제로 겹침을 유발했으므로 새 차트를 추가하거나 기존 차트를 고칠 때도
반드시 지킬 것.
- **연도가 많은 시계열은 막대가 아니라 선그래프로**: 12개년처럼 연도 수가 많은 시계열을 계열별
  묶은 막대 + 막대마다 수치 라벨로 그리면 막대·라벨이 촘촘히 겹친다(V4_1이 그랬다). 연 단위
  추세는 `ax.plot()` 선그래프로 그리고, 수치 라벨도 매 지점이 아니라 시작·끝점에만 단다.
- **같은 x에서 값이 비슷한 여러 계열의 라벨은 `_declutter_y()`로 세로 위치를 벌린다**: 선그래프
  시작·끝점에서 여러 지역/계열의 값이 비슷하면(예: 8.6, 8.5, 6.8) 라벨 텍스트가 겹친다 —
  `_declutter_y(vals, ymax)`가 값 순서를 지키면서 라벨 y좌표만 최소 간격(ymax의 5%)만큼 벌려
  겹치지 않게 한다(마커 자체 위치는 실제 값 그대로). 선그래프뿐 아니라 묶은 막대 그래프에서도
  같은 문제가 생긴다 — V1_1(AI 포함/제외 전력 수요)처럼 같은 연도의 두 막대 값이 비슷하면 막대
  위 수치 라벨이 겹치므로, 연도별로 그 해의 막대 값들을 모아 `_declutter_y()`에 통과시킨 뒤
  나온 y좌표를 `ax.annotate()`의 `xy=`로 쓴다(막대 높이 자체는 그대로 둔다).
- **막대 위 수치 라벨은 세그먼트가 많으면(5개 초과) 세로로 세운다**: 세그먼트 축(V5_x)에서
  세그먼트가 많아지면 막대 폭이 좁아져 가로 라벨("42.0")이 옆 막대 라벨과 가로로 겹친다 —
  `_bar_labels(..., rotation=90)`로 세로로 세우고, `ax.set_ylim()` 위쪽 여유도 가로 라벨보다
  더 크게(`ymax*1.35` 등) 잡아 세로 라벨이 위 테두리에 잘리지 않게 한다.
- **차트 이미지 안에는 제목을 넣지 않는다 — 범례만 그래프 바깥 맨 위에, 작게 남긴다
  (`ax.set_title`/`fig.suptitle` 금지)**: 문서 삽입 시 `generate_docx.py`/`generate_hwpx.py`가
  이미지 바로 아래에 자동 채번 캡션("그림 N. 제목")을 이미 붙이므로, 그림 안에 같은 제목을
  `ax.set_title()`/`fig.suptitle()`로 또 넣으면 같은 문구가 그림 위(안)·아래(캡션) 두 번
  겹쳐 보인다 — 그림 안의 "위 제목"은 제거하고, 아래 캡션(표·그림 번호·이름)은 그대로 둔다.
  범례(계열 라벨)가 있는 차트는 `_legend_above(fig, handles, labels, legend_pt, ncol, top=...)`를
  쓸 것 — `fig.legend(loc='lower center', ...)`를 `fig.subplots_adjust(top=...)`으로 예약한 축
  영역 바로 위에 작게(EFFECTIVE_PT['legend']=7.5pt) 앉힌다.
  예전에는 `ax.set_title(pad=..)` + `ax.legend(bbox_to_anchor=..)`를 함께 썼는데 둘 다 "축 상단
  기준 상대좌표"라 실제 렌더링 시 제목과 범례 글자가 겹치는 경우가 실측으로 확인됐던 것도 이
  방식을 쓰지 않는 이유 중 하나다. 범례는 `frameon=True` + `leg.get_frame().set_edgecolor(C['gray'])`로
  테두리 박스를 둘러 어디까지가 범례인지 그래프 배경과 시각적으로 분리되게 한다 — 글자 크기·박스
  여부를 바꿀 때는 `EFFECTIVE_PT['legend']`와 `_legend_above()`의 `frameon=True` 설정만 고치면
  `_legend_above()`를 쓰는 모든 차트(V1_1/V1_2/V4_1/V5_x/V6_1)에 한 번에 반영된다 — 차트별로
  따로 고치지 말 것.
  **범례는 반드시 `loc='lower center'`로 앵커링해야 한다** — `loc='upper center'`로 앵커링하면
  범례 박스가 앵커점에서 "아래로" 자라나서 세그먼트가 많아 범례가 2줄 이상이 될 때 축 영역(막대·
  수치)을 침범한다(V5_1/V5_2처럼 세그먼트 7개인 차트에서 실측 확인). `loc='lower center'`는
  앵커점에서 "위로" 자라나므로 줄 수가 몇 줄이든 축 영역을 절대 침범하지 않는다. 범례 줄 수가
  많을 것으로 예상되면(`ncol`로 나눈 행 수가 2 이상) `top`을 더 작게(더 넉넉히 예약) 잡을 것 —
  남는 여백은 `_savefig`의 `bbox_inches='tight'`가 알아서 잘라내므로 손해가 없다. 범례가 없는
  단일 계열 차트(V6_2 등)는 제목만 제거하면 되고 `_legend_above()`를 쓸 필요가 없다.

**색이 있는 박스 위 글자는 배경 밝기에 맞춰 자동으로 고른다 (중요)**: `_flow_diagram()`(V3_2/
V3_3)과 V2_1 헤더는 `PALETTE`(mint·navy·green·orange·gray)를 배경색으로 순환해 쓰는데, 예전에는
글자색을 흰색으로 고정해서 mint·green·orange·gray처럼 밝은 배경 위에서 대비가 약해(WCAG 대비비
계산상 2.2~2.8, 권장 4.5 미달) 글자가 잘 안 보이는 문제가 있었다(navy만 흰 글씨가 실제로 잘
맞는 배경이었다). `_text_colors_for_bg(bg_rgb)`가 배경의 상대 휘도를 계산해 흰 글씨/어두운 글씨
중 대비비가 더 높은 쪽을 그때그때 골라준다 — 새로운 색이 있는 배경에 글자를 얹을 때도 색을
하드코딩하지 말고 반드시 이 헬퍼를 통해 주 텍스트색·보조 텍스트색을 정할 것.

**그림에는 요약만, 상세 설명은 본문에 (중요)**: V2_1(시장 역학 인포그래픽)은 각 항목의 **제목만**
표시하고 설명 문장은 넣지 않는다 — 상세 설명은 `generate_docx.py`/`generate_hwpx.py`의
`dyn_section()` 패턴으로 소제목(성장 동인/저해 요인/...) 아래 항목별 전체 bullet로 이미 싣고 있다.
그림 안에 설명까지 욱여넣으면 항목 수가 늘어날 때 글자가 잘리거나 항목 자체가 밀려나기 쉬우므로,
"그림 = 구조 요약, 본문 = 전체 설명" 역할 분담을 유지할 것. 새로운 카드형/인포그래픽 차트를 추가할
때도 이 원칙을 따른다.

**데이터가 없는 카테고리는 빈 칸으로 그리지 말고 열 자체를 뺀다 (중요 — 있는 내용만으로 구성)**:
V2_1의 4개 카테고리(성장 동인/저해 요인/도전 과제/기회) 중 일부가 원문에 아예 없을 수 있다 —
예를 들어 Technavio 계열 보고서의 "Market opportunities/restraints"처럼 절 제목은 두 종류를
같이 걸어 놓았지만 본문은 기회(Opportunities) 내용만 있고 저해 요인(Restraints) 서술이 전혀
없는 경우가 실측 확인됐다. `has_challenges`가 false일 때 도전 과제 열 자체를 만들지 않는 것과
동일한 원칙으로, `drivers`/`restraints`/`opportunities`도 항목이 하나도 없으면(`[]`) 그 열을
아예 만들지 않는다(`v2_1()`의 `col_defs` 리스트 컴프리헨션이 항목 없는 카테고리를 자동으로
제외하고, `n_cols`도 실제 남은 열 개수로 계산한다) — 헤더만 있고 속이 빈 박스를 만들지 말 것.
새로운 다중 카테고리 인포그래픽을 추가할 때도 이 원칙(데이터가 있는 카테고리만 그린다)을 따른다.
같은 원칙이 본문 소제목에도 적용된다 — `generate_docx.py`/`generate_hwpx.py`의 "3. 기술·솔루션
생태계" 절은 공급망/가치사슬/생태계 맵 3개 하위 소제목(`b.h2(...)`)을 예전에는 데이터 유무와 무관
하게 항상 냈는데, 원문에 재활용할 이미지도 없고 합성용 구조화 데이터(`supply_chain` 등)도 없으면
`img()`가 조용히 아무것도 그리지 않아 **소제목만 있고 그 아래가 완전히 빈 절**이 남는 문제가
실측 확인됐다(예: 공급망 챕터가 아예 없는 보고서). 지금은 각 소제목을 `if sec3.get('*_image')
or sec3.get('supply_chain'/'value_chain'/'key_players_by_category'):`로 감싸 실제로 그릴
내용이 있을 때만 낸다 — 새로운 절을 추가할 때도 소제목과 그 아래 그림/데이터의 유무를 함께
확인할 것.

수정 후 실제로 잘 보이는지 확인하려면, 차트 PNG를 문서 삽입 폭(`DOCX_WIDTH_IN`/`HWPX_WIDTH_IN`)에
맞춰 리사이즈한 뒤 10pt 본문·9pt 캡션 샘플 텍스트와 나란히 배치해 비교하는 방식으로 검증한다(코드만
보고 "23pt니까 크겠지" 식으로 판단하면 이번과 같은 착시에 다시 빠진다).

세그먼트 차트(V5_1~V5_4, V5_5~V5_7)는 STEP 3에서 채운 `segmentation.axes`/`detail_axes` 리스트를
그대로 순서대로 사용하므로, 보고서마다 분류축 개수·이름이 달라져도 코드 수정 없이 동작한다.

**본문 그림·표는 원본 이미지를 최대한 활용하고, 없을 때만 합성한다 (중요 원칙)**: `extract_images.py`
가 원본 보고서에서 뽑아둔 그림들이 `workspace/extracted/images/`에 있고 `image_catalog.json`에
목록화되어 있다. STEP 3에서 특정 그림 슬롯(공급망/가치사슬/생태계 맵 등)에 대응하는 원문 그림이
실제로 있으면, matplotlib/Pillow로 새로 합성하지 말고 그 원본 파일명을 구조화 JSON의 `*_image`
필드(예: `supply_chain_image`)에 적어 넣는다. `generate_charts.py`의 `_try_reuse_image()` 헬퍼가
그 필드를 보고 원본을 그대로 복사해 쓰며(카탈로그 status는 `reused`), 필드가 비어 있을 때만 그
아래의 합성 로직(구조화 데이터 기반 다이어그램)이 실행된다. 새 그림 슬롯을 추가할 때도 이 순서
(reuse 시도 → 실패 시 합성)를 지킬 것 — 원본이 있는데 굳이 다시 그리면 원문의 실제 정보(정확한
수치·로고·화살표 관계 등)를 잃는다.

**표 형태의 데이터는 그림(이미지)이 아니라 실제 표로 넣는다 (중요 원칙)**: 지역별 기회·리스크
매트릭스처럼 순수 표 데이터를 matplotlib `ax.table()`로 그려 PNG 이미지로 삽입하는 방식(V4_2가
그랬다)은 쓰지 않는다 — 텍스트 선택·접근성이 떨어지고, 문서 삽입 폭에 맞춰 다시 리사이즈되며
글자 크기가 틀어지는 문제가 반복적으로 발생했다. 게다가 같은 데이터를 표(`b.table()`)로도 함께
넣으면 완전히 중복된다. **같은 데이터를 표로 이미 넣고 있다면 그 옆에 이미지 버전을 또 넣지 말고,
표 하나만 남길 것.** 지역별 데이터처럼 이미 `b.table()`로 표시하고 있는 데이터를 위해 새로 차트
함수를 만들 필요는 없다 — 정말 "표로 담기 어려운" 시각화(추세선, 막대 비교 등)만 그림으로 만든다.

**그림·표 캡션은 자동 채번된다 (중요 — 하드코딩 금지)**: `DocxBuilder.image()`/`.table()`과
`HWPXBuilder.image()`/`.table()`은 호출될 때마다 내부 카운터(`fig_n`/`tbl_n`)를 증가시켜
"그림 N. 제목" / "표 N. 제목" 캡션을 자동으로 만든다. `build_report()` 안에서
`img('V3_2', '가치사슬 구조')`처럼 **번호 없는 제목만** 넘길 것 — `f'그림 4. ...'`처럼 번호를
직접 문자열에 넣으면 다른 그림이 추가/삭제돼 순서가 바뀔 때 번호가 어긋난다(실제로 공급망 분석
절을 추가하면서 뒤따르는 모든 그림 번호가 밀리는 문제가 있었다).

**출처는 표지(첫 페이지 요약)에만 싣는다 (중요 — 원칙)**: `image()`/`table()`에는 `source`
인자가 없다 — 본문 섹션 1 상단이나 그림·표 캡션 하단에 "(출처: ...)"를 반복해서 붙이지 않는다.
표지의 "원본 출처: {source_report} ({publish_year})" 한 줄만 출처를 표기하는 유일한 곳이다.
새 그림·표를 추가할 때 `source`/`src_cite` 같은 인자를 다시 만들어 넘기지 말 것.

**설명(desc)은 실제 내용이 있을 때만 넣는다 (중요)**: `img()`/`table()`의 `desc` 인자는 그
그림·표가 "무엇을 보여주는지"를 다른 말로 반복하는 문장이 아니라, 구체적 수치·경향처럼 그
자체로 새로운 정보를 담고 있을 때만 채운다(예: "AI 포함 시나리오는 2025년 120TWh에서 2035년
400TWh로 증가"). STEP 3가 채운 데이터에서 실제로 계산 가능한 값이 없으면 desc를 빈 문자열로
두고, `img()`/`table()`은 desc가 비어 있으면 그 문장을 조용히 생략한다 — "이 그림은 ~을 비교한
그림임" 같은 제목 재진술용 캡션 문장을 새로 만들지 말 것.

**desc에 처리 기준·방법론 설명을 쓰지 않는다 (중요 — 원칙)**: desc는 그 표·그림이 담은 실제
데이터에 대한 해석만 담아야 한다 — "이 데이터를 어떻게 만들었는지/왜 이런 형태인지"를 설명하는
문장은 쓰지 않는다. 실측 확인된 잘못된 예:
- `"상세 설명은 아래 항목별 서술을 참고."` (문서 내 다른 위치를 가리키는 안내 문구)
- `"로봇 기업별 단계 매핑은 원문에 제시되지 않아 단계별 대표 카테고리만 반영함."` (원문에 없어서
  어떻게 대체했는지 설명하는 방법론 노트)
- `"AI 휴머노이드 로봇 기업별 생태계 역할을 구분하는 별도 다이어그램은 원문에 제시되지 않음. 대신
  ...으로 재구성함."` (마찬가지로 합성 로직 자체를 설명하는 문장)

이런 문장은 독자에게 필요한 "이 표/그림이 무엇을 말하는가"가 아니라 "우리가 이 표/그림을 어떻게
만들었는가"를 설명하므로 본문에 나오면 안 된다. 대체할 만한 새 데이터(구체적 수치·비교 등)가 없으면
그냥 desc를 빈 문자열로 두고 완전히 생략할 것 — 위 "실제 내용이 있을 때만 넣는다" 원칙과 같은
이유다. STEP 3 작성 중에도 `*_desc` 필드에 "원문에 없어서", "~는 원문에 제시되지 않음", "재구성함"
같은 방법론 설명을 적지 말 것.

**표·그림 해석/요약은 길이가 아니라 내용으로 판단한다 (중요 — 원칙, 글자수 하드캡 금지)**: 한때
`_cap_text()`로 desc/growth_note/특허 설명을 전부 3줄(약 120자)로 강제 절단한 적이 있었는데,
길이만 보고 자르면 실제로 의미 있는 내용(예: 세그먼트가 여러 개일 때 세그먼트별 근거)까지 중간에
잘려나가는 문제가 있어 폐기됐다(사용자 피드백). 지금은 다시 위 "실제 내용이 있을 때만 넣는다"
원칙만 적용한다 — 글자수 상한을 코드로 강제하지 않고, `_split_para()`(문단당 5줄/약 200자)로
문장 경계에서 자연스럽게 여러 문단으로 나눌 뿐이다. 새로운 표·그림 해석 텍스트를 추가할 때도
임의로 글자수를 잘라내는 헬퍼를 다시 만들지 말 것 — 대신 STEP 3 작성 시점에 애초에 "무엇을
보여주는지"만 간결하게 쓰도록(3요소 규칙 등 필요한 경우는 예외) 유도하는 것이 맞는 접근이다.

**표·그림의 반복되는 단위는 표 우측 상단/그림 축에만 대표로 표시한다 (중요 — 원칙)**: 금액·시장
규모처럼 모든 셀(또는 모든 데이터 라벨)에 같은 단위($B 등)가 반복되는 경우, 셀·라벨 안에는 숫자만
쓰고 단위는 한 번만 대표로 표시한다. **그림(matplotlib 차트)도 데이터 라벨에는 절대 단위를 넣지
않는다** — `v1_2()`(시나리오별 시장규모 그림)가 한때 `_bar_labels(..., fmt='${:.1f}B')`로 막대마다
"$1.0B" 식으로 단위를 중복 표기한 적이 있었는데(실측 확인, 사용자가 "그림1 그래프 안에 $이
표기되어 있다"고 보고), 다른 차트(V4_1/V5_x)는 처음부터 `_bar_labels`의 기본 서식(`fmt='{:.1f}'`,
단위 없는 숫자)만 썼으므로 v1_2도 동일하게 단위 없는 서식으로 맞췄다 — 단위는 y축 라벨
("시장규모 ({단위})")에만 표시한다. 새 차트를 추가할 때도 `_bar_labels`/`ax.annotate` 등 데이터
라벨 서식(`fmt=`)에 통화 기호·단위 문자열을 절대 넣지 말 것 — 숫자만 나오는 기본값을 그대로 쓴다.

표는 `DocxBuilder.table()`/`HWPXBuilder.table()`에 `unit` 인자를 추가해, 넘기면 표 바로 위에
"(단위: {unit})"을 우측 정렬로 한 줄 표시하고 각 셀에는 숫자만 넣는다(`build_report()`의
"시나리오별 시장규모 전망" 표가 이 패턴을 씀 — 셀 값은 `f'${...}B'` 대신 `f'{...}'`만 쓴다). HWPX는
우측 정렬 문단을 위해 `hwpx_template/Contents/header.xml`에 `paraPr id="23"`(`align
horizontal="RIGHT"`, id=20 캡션과 동일한 margin/lineSpacing)를 새로 추가했다 — 기존
paraPr(0=JUSTIFY, 20=CENTER, 21=LEFT 제목, 22=LEFT 본문/셀) 중 우측 정렬은 없었으므로 새로 만든
것이다. **새 `paraPr`를 추가할 때는 반드시 목록 맨 끝(마지막 기존 id 바로 다음, `</hh:paraProperties>`
직전)에 추가하고 `<hh:paraProperties itemCnt="N">`의 `N`도 실제 개수에 맞게 갱신할 것** — 처음엔
id=20과 21 사이(목록 중간)에 끼워 넣고 `itemCnt`도 갱신하지 않아, 위치 기반으로 다른 `paraPrIDRef`
매핑이 밀리면서 본문 제목(`h1()`/`h2()`, `paraPrIDRef="21"`)이 의도치 않게 우측 정렬로 보이는
버그가 실측 확인됐다(사용자가 "본문 내 제목들이 오른쪽으로 붙어 있다"고 보고) — `id` 속성이 아니라
목록 내 위치(순번)로 해석하는 경로가 있다고 봐야 하므로, 항상 끝에 추가 + `itemCnt` 동기화 둘 다
지킬 것. 새로운 표에 반복 단위가 있으면 `unit` 인자를 쓸 것 — 셀마다 단위 문자열을 직접 붙이지
않는다.

**`unit`/축 라벨 값은 스크립트에 하드코딩하지 않고 STEP 3 데이터에서 읽는다 (중요 — 원칙, `$B`는
고정값이 아님)**: 표의 `unit` 인자와 차트의 y축 라벨(`시장규모 ({unit})`) 모두 `'$B'`처럼 문자열을
직접 박아넣지 말고 `sec1.get('currency_unit', '$B')`(`generate_charts.py`는 `main()`에서
`unit = sec1.get('currency_unit', '$B')`로 한 번 읽어 `v1_2()`/`v4_1()`/`v5_segment()`에
인자로 넘긴다)로 STEP 3가 채운 `currency_unit` 필드를 읽어써야 한다 — `$B`는 미국 달러로 표기된
보고서(대부분의 영문 시장조사 보고서)에서 흔히 나오는 값일 뿐, 원문이 유로·파운드·엔 등 다른
통화를 쓰면 `currency_unit`도 그에 맞게 달라진다(STEP 3 스키마의 `currency_unit` 필드 설명 참고).
새로운 표·차트에 통화 단위를 표시할 때도 같은 방식으로 `sec1.get('currency_unit', '$B')`를
재사용할 것 — 통화 기호를 코드에 직접 쓰지 않는다.

출력: `workspace/charts/*.png`, `chart_catalog.json`

---

### STEP 5 — HWPX + DOCX 보고서 동시 생성

```python
subprocess.run(["python", os.path.join(skill_dir, "scripts", "generate_reports.py")], check=True)
# 필요시 한 형식만: generate_reports.py --only hwpx  /  --only docx
```

내부적으로 `generate_hwpx.py`(HWPX) → `validate_output_hwpx.py`, `generate_docx.py`(DOCX) →
`validate_output_docx.py` 순서로 실행되며 각각 생성+검증까지 마친다.

**페이지 여백·본문 폭 표준 (중요 — 두 포맷 동일하게 유지)**: A4 기준 위·아래 2.54cm, 좌·우 1.9cm
여백을 쓴다(`generate_docx.py`의 `MARGIN_*_CM`, `generate_hwpx.py`의 `MARGIN_TOP_BOTTOM`/
`MARGIN_LEFT_RIGHT`). **표(table)와 그림(image)은 항상 이 본문 폭에 정확히 꽉 채워 삽입한다** —
DOCX는 `CONTENT_WIDTH_IN`, HWPX는 `CONTENT_WIDTH`를 이미지·표 양쪽에 동일하게 사용할 것(예전에는
HWPX 이미지만 0.85배로 줄여 표보다 좁게 삽입되던 버그가 있었다). DOCX에서 표 폭을 강제하려면
`table.autofit=False`만으로는 부족하고, `tblPr`에 이미 들어있는 기본 `<w:tblW type="auto" w="0"/>`
요소를 찾아 값을 덮어써야 한다(그냥 새 `tblW`를 append하면 같은 태그가 중복 삽입되어 문서가 손상된
것으로 인식될 수 있다 — `generate_docx.py`의 `table()` 메서드 참고).

**단, 세로 높이에는 공통 상한이 있다 (`MAX_IMAGE_HEIGHT_IN`/`MAX_IMAGE_HEIGHT`, 4.5in)**: 위 "본문
폭에 꽉 채운다"는 원칙은 matplotlib/Pillow로 직접 생성하는 차트에는 그대로 유지되지만(이 차트들은
figsize를 3.5~4.5in 높이 범위로 설계해두었으므로 폭에 맞추면 자연스럽게 이 범위 안에 들어온다),
원본 보고서에서 재활용하는 이미지(`*_image` 필드, "원본 이미지 활용" 절 참고)는 정사각형에 가까운
경우가 있어(예: 4단계 가치사슬 다이어그램 974×924px) 본문 폭에 그대로 맞추면 세로로 5.5in 이상
길어져 다른 그림보다 눈에 띄게 커 보이는 문제가 실측 확인됐다(사용자 피드백). `DocxBuilder.image()`/
`HWPXBuilder.image()`는 실제 이미지 종횡비를 읽어, 본문 폭 그대로 삽입했을 때 높이가 4.5in를
넘으면 그때만 높이를 4.5in로 고정하고 폭을 비례 축소한다(이미지 문단은 이미 가운데 정렬이므로
폭이 좁아져도 자동으로 중앙에 위치함, HWPX는 `treatAsChar=1`이라 문단 정렬이 그대로 적용됨) — 정상
범위인 차트는 전혀 영향받지 않고, 종횡비가 유별난 재활용 이미지만 자동으로 작아진다. 이것은
Round A에서 되돌린 "차트 밀도별 3단계 폭 규격화"(third/half/full 임의 분류, 비일관적이라 반려됨)와
다른 원칙이다 — 여기서는 모든 그림이 동일한 규칙(폭 우선, 세로 상한 초과 시에만 예외)을 따르므로
차트마다 다른 분류를 매기지 않는다. 원본 보고서에서 추출한 이미지에 다이어그램과 무관한 본문
문단이 함께 잘려 들어온 경우(PDF 이미지 추출이 바운딩박스를 넓게 잡아 생기는 문제, 실측 확인)는
`workspace/extracted/images/`의 원본을 Pillow로 열어 불필요한 부분을 crop한 새 파일(예:
`p0036_img01_cropped.png`)로 저장하고 `*_image` 필드를 그 파일명으로 갱신할 것 — 원본 파일 자체를
덮어쓰지 말고 별도 파일로 남긴다.

여백을 바꾸면 `generate_docx.py`(`CONTENT_WIDTH_IN`), `generate_hwpx.py`(`CONTENT_WIDTH`),
`generate_charts.py`(`DOCX_WIDTH_IN`/`HWPX_WIDTH_IN`) **세 곳을 반드시 함께 갱신**할 것 — 이 값이
어긋나면 차트 폰트 크기 역산(`mpl_pt`/`pil_pt`)이 실제 삽입 폭과 맞지 않게 되어 STEP 4의 크기 문제가
재발한다.

**HWPX 정렬 정책**: 일반 본문(`normal()`/`bullet()`)과 표 셀(`table()`)은 모두 **LEFT**
(`paraPr id="22"`, 본 스킬이 템플릿에 추가— `id=0`과 여백·줄간격은 같고 정렬만 다름)를 쓴다.
제목(`h1()`/`h2()`)은 `paraPr id="21"`(LEFT)을 쓰고, 캡션은 `paraPr id="20"`(CENTER)을 쓴다.
표 위 단위 표시(`table(..., unit=...)`)는 `paraPr id="23"`(RIGHT, 본 스킬이 id=20을 복제해 추가)를
쓴다. `paraPrIDRef`에 `0`(JUSTIFY, 옛 기본값)을 다시 쓰지 말 것 — 아래 이유로 더 이상 필요 없다.

**HWPX 본문 문단 간 간격 (중요 — 밀도가 높아 답답해 보이는 문제)**: `paraPr id="22"`(본문/표 셀
LEFT 정렬)는 `hh:margin`의 `hc:next`를 `300`(HWPUNIT)으로 설정해 각 문단(글머리표 포함) 뒤에
약간의 세로 여백을 준다 — 이 값이 `0`이면 문단마다 줄간격(160%)만 적용되고 문단 사이 추가 간격이
전혀 없어 bullet 목록이 촘촘하게 붙어 보인다(실측 확인, 사용자 피드백으로 발견). `hc:prev`는
그대로 `0`을 유지할 것 — `next`와 `prev`를 동시에 올리면 인접 문단 사이 간격이 두 배로 겹쳐
계산된다. 값을 더 키우고 싶다면 `hp:case`/`hp:default` 두 블록 모두(문자 단위가 다른 두 경로) 함께
바꿔야 실제로 적용된다.

**HWPX 본문 오른쪽 여백이 안 채워지는 문제 (중요 — 근본 원인 실측 확인 + 해결됨)**: HWPX의 각
문단은 `hp:linesegarray`에 줄 수·줄 폭(`horzsize`)·글자 시작 위치(`textpos`)를 우리가 직접
계산해 써넣는다(`_estimate_lines()`/`_add_lineseg()`/`_wrap_lines()`). **pyhwpx로 한컴오피스를
직접 자동화해 실측한 결과, 한컴오피스는 문서를 열 때 이 linesegarray 값을 그대로 신뢰해 표시하고
재계산하지 않는다** — 즉 우리가 계산한 줄바꿈 위치가 곧 실제로 보이는 줄바꿈 위치다. 예전에는
"10pt·특정 폭에서 한글 40자/줄"이라는 글자수 어림값으로 줄 수를 추정했는데, 이 어림값이 실제
폭보다 작게 잡혀 있어(그리고 영문·숫자가 섞이면 문자당 폭이 달라 더 안 맞았다) 왼쪽 정렬
문단이 오른쪽 끝까지 못 미치고 일찍 줄바꿈되는 문제가 있었다. **지금은 글자수 어림값 대신
`generate_charts.py`가 Pillow 차트에서 이미 하는 것과 동일하게, 실제 폰트(`assets/NanumGothic.ttf`
— 본문 폰트인 함초롬바탕과 100% 동일하진 않지만 CJK 고정폭 특성이 비슷해 신뢰할 만한 근사치를
준다)로 텍스트 폭을 직접 측정해(`_wrap_lines()`) 줄바꿈 지점을 계산한다.** 이 방식은 좌우 정렬
어느 쪽을 쓰든 유효하므로(측정이 정확하면 굳이 JUSTIFY로 우회하지 않아도 된다), 요청대로 LEFT
정렬을 유지하면서 오른쪽 여백 문제를 해결했다. 새 단락 유형을 추가할 때도 글자수 어림값을
부활시키지 말고 `_wrap_lines()`/`_estimate_lines()`를 그대로 쓸 것.

**HWPX "판독불가" 오류 방지 원칙 (중요)**: HWPX는 단순 XML이 아니라 KS X 6101(OWPML) 스펙을 따라야
하며, `mimetype`(무압축·zip 최상단) + `version.xml` + `Contents/{header.xml, section0.xml, content.hpf}` +
`META-INF/{container.xml, container.rdf, manifest.xml}` 구조를 정확히 갖춰야 한컴오피스가 판독한다.
임의 스키마로 손수 XML을 만들면 반드시 판독불가가 발생하므로, `scripts/hwpx_template/`의 정적 파트를
그대로 복사하고 `section0.xml`·`content.hpf`만 동적으로 생성하는 현재 방식을 유지할 것.

**HWPX 본문 글씨가 겹쳐 보이는 문제 방지 (중요)**: HWPX의 각 문단은 실제 줄바꿈 수만큼
`hp:linesegarray/hp:lineseg`를 선언해야 한다. 1줄짜리 lineseg만 넣으면 여러 줄로 줄바꿈되는 문단의
세로 공간이 부족해 다음 문단과 겹쳐 보인다. `HWPXBuilder._add_lineseg()`가 실제 폰트 측정
(`_wrap_lines()`)으로 줄 수를 구해 그만큼 lineseg를 자동 생성하므로, 새 단락 유형을 추가할 때도
반드시 `_add_lineseg(p, height, text, width)`를 텍스트와 함께 호출할 것 (텍스트 없이 호출하면
다시 1줄로 간주되어 겹침 버그가 재발한다). 표 셀도 동일한 이유로 각 셀 문단에 lineseg를 넣고,
행 높이를 셀 내용의 최대 줄 수에 맞춰 동적으로 계산한다 (`table()` 메서드 참고).

**HWPX 그림이 세로로 눌리거나 늘어나 보이는 문제 방지 (중요)**: `HWPXBuilder.image()`는 예전에
`w=14400, h=7200`(2:1 고정 비율) 기본값을 항상 써서, 실제 PNG가 2:1이 아니면(대부분의 차트가
그렇다) 억지로 그 비율에 맞춰 늘이거나 눌러 삽입했다 — 이 때문에 그림 안 글씨가 비정상적으로
커 보이거나 뭉개져 보였다(실측 확인된 버그). 지금은 `w`/`h`를 넘기지 않으면(기본값 0)
`BinData`에 이미 복사된 실제 PNG 파일을 열어 진짜 종횡비를 읽어 쓴다 — 새로 이미지를 삽입하는
코드를 추가할 때도 실제 파일 크기를 무시한 임의 비율을 쓰지 말 것.

**글자 크기 계층** (`hwpx_template/Contents/header.xml`의 charPr 기준):

| 스타일 | charPr id | 크기 |
|---|---|---|
| 제목1 (장 제목) | 7 | 18pt bold navy |
| 제목2 (절 제목) | 8 | 13pt bold navy |
| 볼드 본문 | 9 | 10pt bold |
| 캡션 | 10 | 11pt gray |
| 본문/불릿 | 0 | 10pt |

**캡션 크기는 HWPX만 11pt (DOCX는 9pt 그대로, 중요)**: 표·그림 캡션("표 N. 제목"/"그림 N. 제목")
글자 크기가 사용자 요청으로 9pt→11pt로 조정됐는데, 이 변경은 **HWPX 전용**이다 —
`hwpx_template/Contents/header.xml`의 `charPr id="10"`(`height="900"`→`"1100"`)과
`generate_hwpx.py`의 `caption()`(`_text_paragraph(text, 10, 20, 900)`→`...1100)`, `height`
인자가 lineseg 줄 수 계산에도 쓰이므로 charPr XML의 `height`와 반드시 같은 값을 유지할 것) 두 곳을
함께 바꿔야 적용된다. `generate_docx.py`의 `DocxBuilder.caption()`(`run.font.size = Pt(9)`)은
그대로 둔다 — 두 포맷의 캡션 크기를 항상 동일하게 맞춰야 한다고 오해해 DOCX도 같이 올리지 말 것.

`HWPXBuilder.normal()`/`.bullet()`은 `_split_para()`로 문단을 자동 분할해 1개당 5줄(약 200자)을
넘지 않게 만든다 — STEP 3에서 이미 짧게 써도, 원문 인용 등으로 문단이 길어지는 경우의 안전망 역할.
`generate_docx.py`도 동일한 `_split_para()`를 갖고 있어 DOCX도 같은 규칙을 따른다.

**표·그림 설명 규칙**: `img()`/`b.table()` 호출 직후 그 표/그림이 무엇을 보여주는지 1문장(≤5줄)
설명을 `b.normal(...)`로 삽입한다 (이미 모든 표·그림에 적용되어 있으니, 새 표·그림을 추가할 때도
이 패턴을 유지할 것).

출력: `workspace/output/{OUTPUT_NAME}.hwpx`, `.docx`

---

### STEP 6 — 품질 검증

`generate_reports.py`가 STEP 5에서 이미 검증까지 수행한다 (별도 실행 불필요). 검증 항목은
`validate_output_hwpx.py`/`validate_output_docx.py`의 C00~C10 (패키지 구조·7개 섹션·시장규모·CAGR·
출처·시사점 5개·표 2개 이상·이미지 9개 이상·캡션·이미지 참조 일치·표지 정보).

합격 기준: C00(패키지 구조)은 반드시 통과, 나머지 구조검증 8/10 이상.

---

### STEP 7 — 배포

```python
subprocess.run(["python", os.path.join(skill_dir, "scripts", "finalize_report.py")], check=True)
# 중간 파일까지 정리하려면: finalize_report.py --cleanup
```

검증 통과 시 `skill/output/`(= `BASE/skill/output/`)으로 HWPX·DOCX를 복사하고 실행 리포트(md)를 생성한다.

**주의**: 배포 대상 파일이 한글/워드에서 열려 있으면 복사가 `PermissionError`로 실패한다. 해당 프로그램을
닫은 뒤 `finalize_report.py`만 다시 실행하면 된다 (STEP 5부터 다시 돌릴 필요 없음).

---

## 다른 PC·다른 보고서에서 재사용하기 (이식성)

이 스킬은 아래 원칙으로 설계되어, 리포지토리를 클론한 뒤 `config.json`만 채우면 **다른 PC·다른
보고서에서도 동일한 구성(7개 섹션, 최대 12개 차트, 경쟁구도·특허 동향 표+그림, 5줄 이내 개조식 문체,
글씨 겹침 없는 HWPX)의 보고서가 나오도록** 되어 있다.

- **경로 하드코딩 없음**: 모든 스크립트가 `_common.get_base()`로 `config.json`의 `base_dir`을 읽는다.
- **폰트 동봉**: `scripts/assets/NanumGothic.ttf`가 저장소에 포함되어 있어, 시스템에 나눔고딕이
  없는 PC에서도 차트에 한글이 깨지지 않는다.
- **세그먼트 축 하드코딩 없음**: STEP 3에서 채우는 `segmentation.axes[].label`이 그대로 섹션
  제목·차트 제목에 쓰이므로, 전혀 다른 산업의 보고서(예: 배터리, 반도체 등)를 넣어도 "데이터센터
  유형별" 같은 엉뚱한 제목이 남지 않는다.
- **분석 로직은 Claude가 매번 수행**: STEP 3는 스크립트가 아니라 Claude Code가 STEP 3 스키마에
  맞춰 원문을 읽고 채우므로, 어떤 보고서든 같은 스키마·같은 품질 규칙(음슴체, 5줄 제한, 표/그림
  설명, 경쟁구도 해석 등)이 그대로 적용된다. **다만 보고서 내용 자체(구체적 수치·사례)는 원문에
  따라 달라지는 것이 정상이다** — "동일한 프레임"은 구조·문체·검증 기준이 동일하다는 뜻이다.

새 PC에서 처음 쓸 때 체크리스트:
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
