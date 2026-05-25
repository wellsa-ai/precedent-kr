# fetch_body.py validation

Date: 2026-05-25 KST

## Commands

```bash
python3 -m py_compile pipeline/fetch_body.py
python3 pipeline/fetch_body.py --id 618727 --force
python3 pipeline/fetch_body.py --limit 10 --force
```

## Results

- Single-case smoke test passed: `618727` -> `kr/2026/대법원/대법원-2026-두-30252.md` (`1,546` chars).
- 10-case batch test passed: `613735`, `616055`, `616277`, `616279`, `616689`, `616749`, `616997`, `616999`, `617019`, `617021`.
- Fetched Markdown count after validation: `11`.
- Body size range: min `1,110` chars, max `8,956` chars.
- Extracted sections include `재판경과`, `관련 법령`, `요지`, `판결내용`, `상세내용`.
- Placeholder files under `kr/2026/기타/` were replaced by parsed court paths such as `kr/2026/대법원/`, `kr/2026/인천지방법원/`, `kr/2026/성남지원/`.

## Notes

- Source page: `https://www.law.go.kr/LSW/precInfoP.do?precSeq={ID}&mode=0`
- The script uses an isolated Chromium profile: `~/chrome-profiles/precedent-kr`.
- Related-law wrapper text is filtered so only individual law references remain.
