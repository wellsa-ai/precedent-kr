"""Fetch rendered precedent bodies from law.go.kr and write Markdown files.

Input:
    data/raw/{precSeq}.json

Output:
    kr/{year}/{court}/{case_no}.md

The DRF XML endpoint does not currently return precedent body content for these
records, so this stage uses Playwright against the rendered detail page.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw"
KR_DIR = ROOT_DIR / "kr"
DEFAULT_PROFILE_DIR = Path.home() / "chrome-profiles" / "precedent-kr"
KST = timezone(timedelta(hours=9))
LAW_DETAIL_URL = "https://www.law.go.kr/LSW/precInfoP.do?precSeq={prec_id}&mode=0"


@dataclass
class FetchResult:
    raw_file: Path
    output_file: Path | None = None
    status: str = "pending"
    chars: int = 0
    error: str = ""


def normalize_date(raw: str) -> str:
    """Normalize law.go.kr date strings to YYYY-MM-DD where possible."""
    if not raw:
        return ""
    digits = re.findall(r"\d+", raw)
    if len(digits) >= 3:
        return f"{digits[0]}-{int(digits[1]):02d}-{int(digits[2]):02d}"
    if len(digits) == 1 and len(digits[0]) == 8:
        s = digits[0]
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return raw


def safe_filename(text: str) -> str:
    value = re.sub(r"[\/\\:*?\"<>|]", "_", text or "").strip()
    return value or "unknown"


def clean_block(text: str | None) -> str:
    if not text:
        return ""

    text = text.replace("\r", "\n").replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]

    cleaned: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank and cleaned:
                cleaned.append("")
            blank = True
            continue
        cleaned.append(line)
        blank = False

    return "\n".join(cleaned).strip()


def clean_inline(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def normalize_related_laws(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        cleaned = clean_inline(value)
        if cleaned and cleaned not in unique:
            unique.append(cleaned)

    # law.go.kr sometimes exposes both a wrapper text and its child law links.
    filtered: list[str] = []
    for value in unique:
        if any(value != other and other in value for other in unique):
            continue
        filtered.append(value)
    return filtered


def parse_court(meta: dict[str, Any], fetched: dict[str, Any] | None = None) -> str:
    court = clean_inline(meta.get("법원명"))
    if court:
        return court

    case_no = clean_inline(meta.get("사건번호"))
    if "-" in case_no:
        candidate = case_no.split("-", 1)[0].strip()
        if candidate:
            return candidate

    match = re.match(r"^(대법원|[가-힣]+(?:고등|지방|행정|가정|회생)?법원(?:\([^)]+\))?|[가-힣]+지원)", case_no)
    if match:
        return match.group(1)

    title_case_no = clean_inline((fetched or {}).get("case_no"))
    if "-" in title_case_no:
        return title_case_no.split("-", 1)[0].strip()

    return "기타"


def detail_link(meta: dict[str, Any]) -> str:
    link = clean_inline(meta.get("판례상세링크"))
    if not link:
        return ""
    return f"https://www.law.go.kr{link}" if link.startswith("/") else link


def rendered_url(meta: dict[str, Any]) -> str:
    return LAW_DETAIL_URL.format(prec_id=meta.get("판례일련번호") or "")


def output_path(meta: dict[str, Any], fetched: dict[str, Any] | None = None, output_dir: Path = KR_DIR) -> Path:
    date = normalize_date(clean_inline(meta.get("선고일자")))
    year = (date or "0000-00-00")[:4]
    court = safe_filename(parse_court(meta, fetched))
    case_no = safe_filename(clean_inline(meta.get("사건번호")) or clean_inline((fetched or {}).get("case_no")) or str(meta.get("판례일련번호")))
    return output_dir / year / court / f"{case_no}.md"


def is_fetched_markdown(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    return "본문 미수집 단계" not in text and "## 상세내용" in text and len(text) > 500


def stale_placeholder_paths(meta: dict[str, Any], current: Path, output_dir: Path = KR_DIR) -> list[Path]:
    paths: list[Path] = []
    date = normalize_date(clean_inline(meta.get("선고일자")))
    year = (date or "0000-00-00")[:4]
    case_no = safe_filename(clean_inline(meta.get("사건번호")) or str(meta.get("판례일련번호")))
    prec_id = clean_inline(meta.get("판례일련번호"))

    for court in {"기타", safe_filename(clean_inline(meta.get("법원명")))}:
        if not court:
            continue
        candidate = output_dir / year / court / f"{case_no}.md"
        if candidate == current or not candidate.exists():
            continue
        text = candidate.read_text(encoding="utf-8")
        if prec_id and prec_id in text and "본문 미수집 단계" in text:
            paths.append(candidate)
    return paths


async def extract_page(page, meta: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
    prec_id = clean_inline(meta.get("판례일련번호"))
    url = LAW_DETAIL_URL.format(prec_id=prec_id)

    response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    status = response.status if response else None

    try:
        await page.wait_for_selector("#dcmDetailBox, #cntnWrap_html, .bo_body_cont", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        pass

    try:
        await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 15_000))
    except PlaywrightTimeoutError:
        pass

    data = await page.evaluate(
        """() => {
            const text = (el) => (el ? (el.innerText || el.textContent || '').trim() : '');
            const first = (selector) => document.querySelector(selector);
            const leftItem = (selector) => Array.from(document.querySelectorAll('.left_item'))
                .find((el) => el.querySelector(selector));

            const sections = {};
            document.querySelectorAll('.bo_body_cont .word_group').forEach((group) => {
                const heading = text(group.querySelector('h4'));
                if (!heading) return;
                let value = text(group);
                if (value.startsWith(heading)) value = value.slice(heading.length).trim();
                if (heading === '상세내용') {
                    const detail = text(document.querySelector('#cntnWrap_html'));
                    if (detail) value = detail;
                }
                sections[heading] = value;
            });

            const relatedLaws = Array.from(document.querySelectorAll('.bo_word .rel_group div, .bo_word a'))
                .map((el) => text(el))
                .filter((value) => value && value !== '관련 법령');

            return {
                page_title: document.title || '',
                body_text: text(document.body),
                title: text(first('.bo_head .title .bold')) || text(first('.bo_head .title')),
                case_no: text(first('.bo_head li strong')) || text(first('.bo_head li:nth-child(2)')),
                trial_history: text(leftItem('.cour_trial')?.querySelector('.left_item_cont')),
                reference_cases: text(leftItem('.ref_case')?.querySelector('.left_item_cont')),
                cited_cases: text(leftItem('.cite_case')?.querySelector('.left_item_cont')),
                related_laws: [...new Set(relatedLaws)],
                sections,
                detail_text: text(document.querySelector('#cntnWrap_html')),
            };
        }"""
    )
    data["http_status"] = status
    data["source_url"] = url
    return data


def make_markdown(meta: dict[str, Any], fetched: dict[str, Any]) -> str:
    prec_id = clean_inline(meta.get("판례일련번호"))
    case_name = clean_inline(meta.get("사건명")) or clean_inline(fetched.get("title"))
    case_no = clean_inline(meta.get("사건번호")) or clean_inline(fetched.get("case_no"))
    court = parse_court(meta, fetched)
    decision_date = normalize_date(clean_inline(meta.get("선고일자")))
    source_url = rendered_url(meta)
    fetched_at = datetime.now(KST).isoformat(timespec="seconds")

    sections = fetched.get("sections") or {}
    summary = clean_block(sections.get("요지"))
    judgment = clean_block(sections.get("판결내용"))
    detail = clean_block(sections.get("상세내용") or fetched.get("detail_text"))
    trial_history = clean_block(fetched.get("trial_history"))
    reference_cases = clean_block(fetched.get("reference_cases"))
    cited_cases = clean_block(fetched.get("cited_cases"))
    related_laws = normalize_related_laws(fetched.get("related_laws", []))

    frontmatter: dict[str, Any] = {
        "사건명": case_name,
        "사건번호": case_no,
        "법원": court,
        "선고일자": decision_date,
        "사건종류": clean_inline(meta.get("사건종류명")),
        "판례일련번호": prec_id,
        "데이터출처": clean_inline(meta.get("데이터출처명")),
        "상세링크": detail_link(meta),
        "원문URL": source_url,
        "수집일시": fetched_at,
    }
    if related_laws:
        frontmatter["관련법령"] = related_laws

    fm_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000)

    lines = [
        "---",
        fm_yaml.strip(),
        "---",
        "",
        f"# {case_name}",
        "",
        "## 메타",
        "",
        f"- **사건번호**: {case_no}",
        f"- **법원**: {court}",
        f"- **선고일자**: {decision_date}",
        f"- **사건종류**: {clean_inline(meta.get('사건종류명'))}",
        f"- **판례일련번호**: {prec_id}",
        f"- **원문**: [{prec_id}]({source_url})",
    ]

    if trial_history:
        lines.extend(["", "## 재판경과", "", trial_history])
    if reference_cases:
        lines.extend(["", "## 참조판례", "", reference_cases])
    if cited_cases:
        lines.extend(["", "## 인용판례", "", cited_cases])
    if related_laws:
        lines.extend(["", "## 관련 법령", ""])
        lines.extend(f"- {law}" for law in related_laws)
    if summary:
        lines.extend(["", "## 요지", "", summary])
    if judgment:
        lines.extend(["", "## 판결내용", "", judgment])
    if detail:
        lines.extend(["", "## 상세내용", "", detail])

    if not detail and not summary and not judgment:
        fallback = clean_block(fetched.get("body_text"))
        if fallback:
            lines.extend(["", "## 본문", "", fallback])

    return "\n".join(lines).rstrip() + "\n"


def load_raw_files(raw_dir: Path, ids: list[str], limit: int | None) -> list[Path]:
    if ids:
        files = [raw_dir / f"{prec_id}.json" for prec_id in ids]
    else:
        files = sorted(raw_dir.glob("*.json"))

    files = [path for path in files if path.exists()]
    if limit is not None:
        files = files[:limit]
    return files


async def fetch_all(args: argparse.Namespace) -> list[FetchResult]:
    raw_dir = Path(args.raw_dir)
    output_dir = Path(args.output_dir)
    profile_dir = Path(args.profile_dir).expanduser()
    raw_files = load_raw_files(raw_dir, args.ids, args.limit)
    results = [FetchResult(raw_file=path) for path in raw_files]

    profile_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=not args.headful,
            locale="ko-KR",
            viewport={"width": 1440, "height": 1200},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = await context.new_page()

        for result in results:
            try:
                meta = json.loads(result.raw_file.read_text(encoding="utf-8"))
                expected = output_path(meta, output_dir=output_dir)
                if is_fetched_markdown(expected) and not args.force:
                    result.output_file = expected
                    result.status = "skipped"
                    continue

                fetched = await extract_page(page, meta, args.timeout_ms)
                expected = output_path(meta, fetched=fetched, output_dir=output_dir)
                if is_fetched_markdown(expected) and not args.force:
                    result.output_file = expected
                    result.status = "skipped"
                    continue

                markdown = make_markdown(meta, fetched)
                expected.parent.mkdir(parents=True, exist_ok=True)
                expected.write_text(markdown, encoding="utf-8")
                for stale in stale_placeholder_paths(meta, expected, output_dir=output_dir):
                    stale.unlink()

                result.output_file = expected
                result.status = "fetched"
                result.chars = len(markdown)
                print(f"FETCHED {result.raw_file.stem} -> {expected} ({result.chars:,} chars)")
            except Exception as exc:  # noqa: BLE001 - batch job should keep going
                result.status = "error"
                result.error = str(exc)
                print(f"ERROR {result.raw_file.stem}: {exc}", file=sys.stderr)

            if args.delay > 0:
                await asyncio.sleep(args.delay)

        await context.close()

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch rendered precedent bodies from law.go.kr")
    parser.add_argument("--id", dest="ids", action="append", default=[], help="Precedent serial ID. Can be repeated.")
    parser.add_argument("--limit", type=int, help="Maximum number of raw records to process.")
    parser.add_argument("--force", action="store_true", help="Refetch even when Markdown already has a body.")
    parser.add_argument("--headful", action="store_true", help="Run Chromium with a visible window.")
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--output-dir", default=str(KR_DIR))
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = asyncio.run(fetch_all(args))
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    print(f"Done: {counts}")


if __name__ == "__main__":
    main()
