# Precedent KR

> 대한민국 법원 판례를 Git으로 관리합니다.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![data](https://img.shields.io/badge/data-Markdown-blue)](kr/) [![source](https://img.shields.io/badge/source-법제처_DRF_OpenAPI-orange)](https://open.law.go.kr)

대한민국 법원 판례를 Markdown + YAML frontmatter로 변환하여 Git 저장소에서 관리합니다. 각 판례는 **선고일자(또는 결정일자)** 를 Git commit date 로 갖고, 사건명·법원·사건번호·판결요지·참조조문·참조판례를 메타데이터로 보관합니다.

[legalize-kr](https://github.com/legalize-kr/legalize-kr)이 법률을, [regulate-kr](https://github.com/wellsa-ai/regulate-kr) 이 행정규칙을, **precedent-kr** 이 판례를 담당합니다.

## 왜 필요한가?

법률·행정규칙이 "기준" 이라면, **판례는 그 기준이 실제 어떻게 적용되었는지의 살아있는 해석** 입니다.

```
형법 제307조 (명예훼손)
  └─ 대법원 2019도XXX 판결 (공인의 비판적 표현 위법성 조각)
       └─ 대법원 2024다XXXX 판결 (SNS 게시 표현의 위법성 판단 기준)
```

법률 + 행정규칙 + 판례가 모두 Git 으로 관리되어야 **개정·해석 변화의 전체 흐름** 을 추적할 수 있습니다.

## 빠른 시작

```bash
git clone https://github.com/wellsa-ai/precedent-kr.git
cd precedent-kr

# 특정 판례 보기 (예시 경로)
cat kr/2024/대법원/2024다12345.md

# 특정 법령을 참조한 판례 검색
grep -rl "형법 제307조" kr/

# 선고일자 순 판례 이력
git log --format="%ai %s" -- kr/2024/
```

## 구조

```
kr/{선고연도}/{법원}/
  {사건번호}.md            # 판례 본문 (요지 + 본문)
  ...
```

## 메타데이터 (YAML Frontmatter)

```yaml
---
사건명: "명예훼손"
사건번호: "2024다12345"
법원: "대법원"
선고일자: "2024-06-15"
재판부: "제2부"
사건종류: "민사"
참조조문:
  - "형법 제307조"
  - "형법 제310조"
참조판례:
  - "대법원 2019도XXXX"
출처: "https://www.law.go.kr/판례/(2024다12345)"
---
```

## 자동 업데이트

매일 [국가법령정보센터 DRF API](https://open.law.go.kr) 의 `target=prec` 를 체크하여 신규·정정 판례가 있으면 자동으로 커밋합니다.

- `pipeline/cron_update.sh` — 매일 06:00 KST (신규 판례 체크)
- `pipeline/cron_full_sweep.sh` — 매일 23:30 KST (전체 풀 스윕)

## 관련 프로젝트

| 프로젝트 | 대상 | 설명 |
|---|---|---|
| [legalize-kr](https://github.com/legalize-kr/legalize-kr) | 법률·시행령 | 대한민국 법령을 Git으로 관리 |
| [regulate-kr](https://github.com/wellsa-ai/regulate-kr) | 행정규칙·고시 | 전 부처 행정규칙(고시)을 Git으로 관리 |
| **precedent-kr** (이 저장소) | 법원 판례 | 대한민국 법원 판례를 Git으로 관리 |
| [interpretation-kr](https://github.com/wellsa-ai/interpretation-kr) | 법령해석례 | 법제처 법령해석례 (예정) |
| [constitution-kr](https://github.com/wellsa-ai/constitution-kr) | 헌재결정례 | 헌법재판소 결정례 (예정) |
| [localrule-kr](https://github.com/wellsa-ai/localrule-kr) | 자치법규 | 지자체 자치법규 (예정) |
| [treaty-kr](https://github.com/wellsa-ai/treaty-kr) | 조약 | 대한민국 조약 (예정) |

## 활용 사례

- **법률 검색 보강**: 법령·행정규칙 검색 결과에 관련 판례 동시 노출
- **판례 RAG**: 자연어 질의 → 관련 판례 추출 (예: [MiniLex](https://minilex.wellsa.ai))
- **법학 교육·연구**: Git history 로 판례 흐름 학습
- **법무 실무**: 특정 조문이 시간에 따라 어떻게 해석되어 왔는지 추적

## 데이터 출처

모든 판례 데이터는 [국가법령정보센터 DRF API](https://open.law.go.kr) 에서 가져옵니다. 판례 원문은 대한민국 정부 공공저작물로 자유롭게 이용 가능합니다.

## 라이선스

- 판례 원문: 공공저작물 (대한민국 정부)
- 저장소 구조·파이프라인 코드: MIT

## 기여

이슈, PR 환영합니다. [이슈](https://github.com/wellsa-ai/precedent-kr/issues) 에 남겨주세요.
