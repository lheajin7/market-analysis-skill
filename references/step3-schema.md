# STEP 3 — 구조화 JSON 스키마 (매 실행 필수)

`workspace/extracted/text/full_text.txt`와 `sec_*.txt`를 Read로 직접 읽어 각 섹션을 분석하고,
**아래 스키마와 정확히 일치하는 키 이름으로** JSON을 생성한다.
스키마가 다르면 리포트 생성기가 해당 항목을 조용히 건너뛴다.

> `scripts/analyze_sections.py`(정규식 기반 자동 분석)는 빠른 초안용일 뿐, 정밀한 보고서에는
> 사용하지 말 것 — 필드명이 리포트 생성기의 실제 스키마와 어긋나는 곳이 있어 본문에 공란·TOC
> 잔여 텍스트가 남는다.

생성 파일: `workspace/structured/sec1_market_overview.json` ~ `sec7_implications.json`,
`master_dataset.json`(7개 파일 병합 + 최상위에 `tech_field`, `project_name` 추가).

---

## 생성 규칙 (모든 보고서 공통)

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

### desc·설명 필드에 방법론을 쓰지 말 것

`*_desc`/`growth_note` 등 설명 필드는 **그 표·그림이 담은 실제 데이터에 대한 해석만** 담는다.
"이 데이터를 어떻게 만들었는지/왜 이런 형태인지"를 설명하는 문장은 쓰지 않는다.
실측 확인된 잘못된 예:

- `"상세 설명은 아래 항목별 서술을 참고."` (문서 내 다른 위치를 가리키는 안내 문구)
- `"로봇 기업별 단계 매핑은 원문에 제시되지 않아 단계별 대표 카테고리만 반영함."` (방법론 노트)
- `"...별도 다이어그램은 원문에 제시되지 않음. 대신 ...으로 재구성함."` (합성 로직 설명)

대체할 만한 새 데이터(구체적 수치·비교 등)가 없으면 그냥 **빈 문자열로 두고 완전히 생략**할 것 —
리포트 생성기는 desc가 비어 있으면 그 문장을 조용히 건너뛴다. "원문에 없어서", "~는 원문에
제시되지 않음", "재구성함" 같은 표현을 설명 필드에 적지 말 것.

---

## sec1_market_overview.json → `master_dataset.json["market_overview"]`

```
{
  "source_report": "보고서 전체 서지정보 (표지에만 쓰임, 예: 'BIS Research, Data Center Cooling Market - A Global and Regional Analysis (Analysis and Forecast: 2025-2035), April 2025')",
  "currency_unit": "원문이 실제로 시장규모를 표기하는 통화·단위 (예: 'USD$'가 원문 표기면 '$B',
    유로면 '€B' 등) — 하드코딩된 고정값이 아니라 매 보고서마다 원문을 보고 채울 것",
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
```

- `power_demand_data`는 전력수요 관련 수치가 원문에 없으면 `{}`로 비워둘 것(그러면 해당 그림은 자동 생략됨).
- `currency_unit`은 원문(표지·시장 정의 등)에 실제로 쓰인 통화를 확인해서 채운다. 대부분의 영문 시장조사
  보고서는 미국 달러(US$/USD)를 쓰므로 그 경우 `"$B"`가 되지만, 유로/파운드/엔 등 다른 통화를 쓰는
  원문이면 그 통화 기호로 채울 것(예: `"€B"`).
  **모든 `*_usd_b`/`sizes` 수치 필드는 이름과 무관하게 항상 십억 단위(B, billion)로 정규화해 저장하는
  내부 규칙은 그대로 유지**하고(차트 축 스케일 계산 등 내부 일관성을 위해 필요), `currency_unit`은 그
  수치를 표에 표시할 때 붙일 통화 기호만 결정한다 — 즉 숫자 스케일은 항상 십억 단위, 통화 기호만
  원문 기준으로 가변적이다.

---

## sec2_market_dynamics.json → `["market_dynamics"]`

```
{
  "drivers": [{"title": "...", "description": "..."}],
  "restraints": [{"title": "...", "description": "..."}],
  "has_challenges": false,
  "challenges": [{"title": "...", "description": "..."}],
  "opportunities": [{"title": "...", "description": "..."}]
}
```

- 원문에 해당 카테고리 서술이 아예 없으면 빈 리스트 `[]`로 둘 것 — 항목이 없는 카테고리는 인포그래픽
  (V2_1)에서 **열 자체가 생성되지 않는다**. 헤더만 있고 속이 빈 박스를 만들지 않기 위한 의도된 동작이다.

---

## sec3_ecosystem.json → `["ecosystem"]`

```
{
  "market_share_table": [{"company": "기업명", "share_range": "8-10%"}],
  "market_share_metric": "시장점유율 범위",   // (선택) 표의 2번째 열 헤더. 생략 시 기본 '시장점유율 범위'
  "market_share_desc": "경쟁구도 해석 문장",   // (선택) 표 해석 문장. 생략 시 아래 기본 문장 자동 생성
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
```

### `market_share_metric` / `market_share_desc` (둘 다 선택)

`market_share_table`은 "경쟁구도(Competitive Landscape)" 표로 그대로 들어간다.

- `market_share_metric`: 표의 2번째 열 헤더. 원문이 점유율(%)이 아닌 다른 지표(예: "누적 투자액",
  "출하량 순위")를 제시하면 이 필드로 덮어쓴다. 생략 시 `'시장점유율 범위'`.
- `market_share_desc`: 표 아래 해석 문장. **생략하면 "상위 3개사가 상위권을 형성하며, 나머지 N여 개
  기업 대부분은 1% 미만의 점유율을 보여 파편화된 경쟁구조"라는 기본 문장이 자동 생성된다.**
  이 기본 문장은 *다수의 소규모 기업이 1% 미만을 나눠 갖는 파편화 시장*을 전제하므로, **소수 기업만
  존재하는 과점 시장이면 사실과 다른 문장이 된다** — 그런 보고서에서는 반드시 `market_share_desc`에
  실제 구조를 직접 써 넣을 것.

### `*_image` — 원본 이미지 재활용 원칙

STEP 3 진행 중 `workspace/extracted/images/image_catalog.json`과 실제 이미지를 확인해,
공급망/가치사슬/생태계 맵 각각에 대응하는 원문 그림이 있으면(페이지 위치는 파일명의 `pNNNN_imgNN`로
유추) 그 파일명을 `*_image` 필드에 적는다. 원문에 없으면 `null`로 두고, **그 경우에만**
`supply_chain`/`value_chain`/`key_players_by_category`의 구조화 데이터로 합성 다이어그램이 생성된다 —
원본이 있는데 합성으로 대체하지 않는다.

재활용 후보 이미지는 **직접 열어 확인할 것** — PDF 이미지 추출이 바운딩박스를 넓게 잡아 다이어그램
아래에 원문 본문 문단까지 함께 잘려 들어온 경우가 실측 확인됐다. 그런 경우 Pillow로 crop한 새 파일
(예: `p0036_img01_cropped.png`)로 저장하고 `*_image`에 그 파일명을 쓸 것 — 원본 파일 자체를 덮어쓰지
말고 별도 파일로 남긴다.

### 절 구성

**"3. 기술·솔루션 생태계"는 (1) 공급망 → (2) 가치사슬 → (3) 생태계 맵 3개 하위 절로 구성된다.**
`supply_chain`/`value_chain`은 형태가 동일한 단계형 플로우 데이터로, **원문에 그런 챕터가 없으면
빈 리스트 `[]`로 둘 것 — 억지로 만들어내지 말 것.** `key_players_by_category`는 생태계 맵의 폴백
데이터다. 세 하위 절은 각각 그릴 내용(원본 이미지 또는 구조화 데이터)이 실제로 있을 때만 출력되므로,
빈 리스트로 두면 소제목째 생략된다.

---

## sec4_regional_analysis.json → `["regional_analysis"]`

```
{
  "leading_region": "권역명", "fastest_growing_region": "권역명",
  "regions": [{"name": "권역명 (≤20자)",
    "short_term_opportunity": "≤30자", "short_term_risk": "≤30자",
    "long_term_opportunity": "≤30자", "long_term_risk": "≤30자"}]
}
```

- 표 셀에 그대로 들어가므로 각 항목은 반드시 **30자 이내**로 간결하게 작성 (넘으면 잘림).

---

## sec5_segmentation.json → `["segmentation"]`

```
{
  "years": [2024, 2035],
  "axes": [
    {"label": "분류축 이름 (보고서에 실제 있는 이름 그대로, 예: 최종수요 산업별)",
     "value_label": "시장규모",   // (선택) 이 축의 수치가 무엇인지. 생략 시 기본 '시장규모'
     "segments": [{"name": "세그먼트명", "sizes": [기준연도값, 예측연도값],
                   "cagr_pct": 0.0, "growth_note": "위 '3요소' 규칙 적용"}]},
    { ... 축 2 ... }, { ... 축 3 ... }, { ... 축 4 ... }
  ],
  "detail_axes": [
    {"label": "세부 분류축 이름 (있는 경우만)", "value_label": "...", "segments": [...]}
  ],
  "adoption_trend": {
    "label": "채택률/보급률 등 추이 지표 이름 (예: 액체냉각 기술 채택률)",
    "years": [2024, 2026, ...],
    "series": [{"label": "시나리오 A", "values_pct": [...]},
               {"label": "시나리오 B", "values_pct": [...]}]
  }
}
```

### `axes` / `detail_axes`

**`axes`는 최대 4개까지 순서대로 사용된다.** 원문 보고서의 세그먼트 분류가 몇 개든, 실제 그 보고서에
있는 분류축 이름을 `label`에 그대로 쓸 것 — "최종수요 산업별/데이터센터 유형별" 같은 이전 보고서
(데이터센터 냉각) 예시를 다른 보고서에 그대로 베끼면 안 된다. `detail_axes`는 최대 3개, 없으면 빈 리스트.

### `value_label` (선택) — 수치가 시장규모가 아닐 때

`value_label`은 그 축의 수치가 **무엇인지**를 정하며, 차트 y축 라벨과 본문 절 제목에 함께 쓰인다
(`_common.seg_title()`/`value_label()`이 세 생성기에서 공유). 생략 시 `'시장규모'`.

세그먼트 값이 시장규모가 아닌 보고서(예: 자본 약정액·투자액·출하량)에서 이 필드를 비워두면 y축과
절 제목이 **"시장규모"로 잘못 표기된다** — 그런 경우 반드시 채울 것.

절 제목 규칙: `label`이 이미 `'규모'`로 끝나면 지표명을 덧붙이지 않는다
("자본 약정 규모 시장규모"처럼 같은 말이 두 번 나오는 제목 방지).

| `label` | `value_label` | 결과 제목 | y축 |
|---|---|---|---|
| `최종수요 산업별` | (생략) | 최종수요 산업별 시장규모 | 시장규모 ($B) |
| `투자 단계별` | `자본 약정액` | 투자 단계별 자본 약정액 | 자본 약정액 ($B) |
| `자본 약정 규모` | `자본 약정액` | 자본 약정 규모 | 자본 약정액 ($B) |

### `adoption_trend`

원문에 없으면 `{}`로 비워둘 것 (없는 데이터를 만들어내지 않는다).
**`series`는 2개로 제한되지 않는다** — 원문에 냉각 방식별 채택률처럼 3개 이상(예: 액체냉각·공랭식·
증발냉각·프리쿨링 4개)이 있으면 있는 그대로 다 채울 것. `v6_1()`이 `series` 개수와 무관하게 전부
그리고 y축 상한도 모든 series 값을 합쳐 계산한다.

---

## sec6_rnd_trends.json → `["rnd_trends"]`

```
{
  "patent_trend": {
    "description": "2~3줄 요약",
    "top_countries": ["국가1", "국가2", ...],
    "top_companies": ["기업1", "기업2", ...],
    "top_companies_detail": [{"company": "기업1", "count": 12345}, ...],
    "section_title": "특허 동향",         // (선택) 절 제목. 생략 시 기본 '특허 동향'
    "metric_label": "특허 출원 건수",      // (선택) 표 헤더·차트 라벨·제목의 지표명. 생략 시 기본값
    "metric_unit": "건",                  // (선택) 수치 뒤 단위. 생략 시 기본 '건'
    "top_countries_label": "주요 특허 보유국",    // (선택) 국가 목록 불릿 라벨. 생략 시 기본값
    "top_companies_label": "주요 특허 보유 기업"  // (선택) 기업 목록 불릿 라벨. 생략 시 기본값
  },
  "case_studies": [{"organization": "기관/기업", "title": "사례명", "technology": "기술", "outcome": "결과"}],
  "government_initiatives": [{"region": "권역", "initiative": "정책명", "description": "설명"}],
  "emerging_technologies": [{"tech": "기술명", "description": "설명"}]
}
```

### 국가별인지 기업별인지 반드시 원문을 확인할 것

**특허 동향의 표 + 로그스케일 막대그래프(V6_2)는 `top_companies_detail`(기업별 수치)로 그린다.**
예전에는 `top_countries_detail`(국가별)을 썼는데, 실제 원문(BIS Research 보고서 등)의 특허 동향
차트/표는 국가별이 아니라 **기업별** 출원 건수 비교인 경우가 많아 원문과 다른 그래프가 나오는 문제가
있었다 — STEP 3에서 원문 차트가 국가 단위인지 기업 단위인지 반드시 확인하고 그에 맞는 필드를 채울 것.

수치를 알 수 없으면 `top_companies`(이름만)만 채우고 `top_companies_detail`은 생략 — 없는 수치를
지어내지 말 것. `top_countries`/`top_companies`(이름만)는 항상 본문에 불릿으로 별도 표시되므로,
표/그래프에 안 쓰는 쪽도 이름 목록만은 채워둘 것.

### 지표가 '특허'가 아닐 때 — `section_title`/`metric_label`/`metric_unit`

원문 지표가 특허 출원 건수가 아니면 아래 선택 필드로 절 제목·표 헤더·차트 라벨을 모두 덮어쓸 수 있다
(코드에 하드코딩돼 있지 않음). 예를 들어 원문이 'ADC 개발 파이프라인 보유 자산 수'를 기업별로 제시하면:

```json
"section_title": "개발 파이프라인 동향",
"metric_label": "개발 파이프라인 자산 수",
"metric_unit": "개",
"top_companies_label": "주요 개발 파이프라인 보유 기업"
```

다섯 필드 모두 생략하면 기본값(특허 기준)이 그대로 쓰이므로, 원문이 실제 특허 데이터인 보고서에서는
채우지 않아도 된다.

### 필드명을 정확히 지킬 것 (실측 확인된 반복 실수)

`case_studies`/`government_initiatives`/`emerging_technologies`에 **`title`/`description`만 쓰는
실수가 두 차례 반복됐다.** 올바른 필드는 각각:

- `case_studies` = {`organization`, `title`, `technology`, `outcome`}
- `government_initiatives` = {`region`, `initiative`, `description`}
- `emerging_technologies` = {`tech`, `description`}

하나라도 다른 필드명을 쓰면 리포트 생성기가 없는 필드를 빈 문자열로 읽어 본문에 `[] 제목 — :` 같은
깨진 텍스트로 렌더링된다(`[{organization}] {title} — {technology}: {outcome}` 형식에서 값이 비면
대괄호와 콜론만 남는다). 세 필드 그룹을 채운 뒤 반드시 키를 다시 대조할 것.

---

## sec7_implications.json → `["implications"]`

```
{
  "key_conclusions": ["개조식 결론 1", "개조식 결론 2"],
  "implications": {
    "i1_promising_tech": "...", "i2_tech_gap": "...", "i3_supply_chain": "...",
    "i4_policy": "...", "i5_kist": "..."
  },
  "data_basis_note": "데이터 근거 관련 주석 (선택)"
}
```

- `implications.iN_*` 문자열 앞에 "①②③④⑤" 등 번호를 직접 붙이지 말 것 — 리포트 생성기가
  "① 유망 기술 방향" 같은 제목을 별도로 붙이므로, 붙이면 번호가 두 번 표시된다.
