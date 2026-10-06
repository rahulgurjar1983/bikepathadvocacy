import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path

from gates.common import ToolMissing, fail_hard, git

try:
    import textstat
except ImportError:
    textstat = None

GLOSSARY = Path("GLOSSARY.md")
ALLOWLIST = Path(".readability-allow")
MIN_WORDS = 30
NEUTRAL = "thing"
GLOSSARY_LINE = re.compile(r"^\s*[-*]\s+\*\*(?P<term>[^*]+)\*\*\s*[—:-]\s*(?P<expl>.+?)\s*$")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
SUFFIXES = (
    ("ies", "y"),
    ("es", ""),
    ("s", ""),
    ("ed", ""),
    ("ed", "e"),
    ("d", ""),
    ("ing", ""),
    ("ing", "e"),
    ("er", ""),
    ("est", ""),
    ("ly", ""),
)
DALE_CHALL_GRADES = ((4.9, 4), (5.9, 5), (6.9, 7), (7.9, 9), (8.9, 11), (9.9, 13))


def parse_glossary(path: Path = GLOSSARY) -> list[tuple[str, str]]:
    if not path.is_file():
        return []
    entries: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = GLOSSARY_LINE.match(line)
        if match:
            entries.append((match["term"].strip(), match["expl"].strip()))
    return entries


def neutralizer(terms: list[str]) -> Callable[[str], str]:
    if not terms:
        return lambda text: text
    parts = [
        r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?:e?s|ed|ing)?(?![A-Za-z])"
        for term in sorted(terms, key=len, reverse=True)
    ]
    pattern = re.compile("|".join(parts), re.IGNORECASE)
    return lambda text: pattern.sub(NEUTRAL, text)


def strip_to_prose(markdown: str) -> str:
    markdown = re.sub(r"\A---\n.*?\n---\n", "", markdown, flags=re.DOTALL)
    markdown = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)
    markdown = re.sub(r"~~~.*?~~~", " ", markdown, flags=re.DOTALL)
    lines: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("|") or re.match(r"^[-:| ]+$", stripped):
            continue
        if stripped.startswith(("#", ">")):
            stripped = stripped.lstrip("#> ").strip()
        stripped = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", stripped)
        lines.append(stripped)
    text = "\n".join(lines)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[*_~]{1,3}", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def easy(word: str) -> bool:
    return not textstat.is_difficult_word(word.lower(), syllable_threshold=0)


def familiar(word: str) -> str:
    low = word.lower()
    if easy(low):
        return word
    for suffix, replacement in SUFFIXES:
        if low.endswith(suffix) and len(low) > len(suffix) + 1:
            stem = low[: -len(suffix)] + replacement
            if easy(stem):
                return stem
    return word


def familiarize(text: str) -> str:
    return WORD.sub(lambda match: familiar(match.group(0)), text)


def dale_chall_grade(score: float) -> int:
    for ceiling, grade in DALE_CHALL_GRADES:
        if score <= ceiling:
            return grade
    return 16


def grades(prose: str) -> dict[str, float]:
    return {
        "flesch_kincaid": textstat.flesch_kincaid_grade(prose),
        "gunning_fog": textstat.gunning_fog(prose),
        "dale_chall": dale_chall_grade(textstat.dale_chall_readability_score(familiarize(prose))),
        "text_standard": textstat.text_standard(prose, float_output=True),
    }


def out_of_band(scores: dict[str, float], low: int, high: int) -> list[str]:
    return [name for name, value in scores.items() if (low > 0 and value < low) or value > high]


def is_acronym(term: str) -> bool:
    return (
        term.isupper()
        or any(char.isupper() for char in term[1:])
        or any(char.isdigit() for char in term)
        or "/" in term
    )


def glossary_problems(
    entries: list[tuple[str, str]], neutralize: Callable[[str], str], low: int, high: int
) -> list[str]:
    problems: list[str] = []
    for term, _ in entries:
        if len(term.split()) == 1 and not is_acronym(term) and easy(term):
            problems.append(f"glossary term '{term}' is an easy word; reword the page instead")
    body = neutralize(". ".join(explanation for _, explanation in entries))
    if textstat.lexicon_count(body, removepunct=True) >= MIN_WORDS:
        bad = out_of_band(grades(body), low, high)
        if bad:
            problems.append(f"glossary explanations read too hard: {', '.join(bad)}")
    return problems


def allowlist() -> set[str]:
    if not ALLOWLIST.is_file():
        return set()
    return {line.strip() for line in ALLOWLIST.read_text().splitlines() if line.strip()}


def changed_markdown(base: str) -> list[str]:
    out = git("diff", "--name-only", "--diff-filter=ACMR", base, "HEAD", "--", "*.md")
    return sorted(line for line in out.splitlines() if line)


def tracked_markdown() -> list[str]:
    out = git("ls-files", "--cached", "--others", "--exclude-standard", "--", "*.md")
    return sorted({line for line in out.splitlines() if line})


def score(
    name: str, raw: str, neutralize: Callable[[str], str], low: int, high: int
) -> tuple[bool, str]:
    prose = neutralize(strip_to_prose(raw))
    words = textstat.lexicon_count(prose, removepunct=True)
    if words < MIN_WORDS:
        return True, f"skip {name}  [{words} words]"
    values = grades(prose)
    text = (
        f"FK={values['flesch_kincaid']:.1f} FOG={values['gunning_fog']:.1f} "
        f"DC={values['dale_chall']} TS={values['text_standard']:.1f}"
    )
    bad = out_of_band(values, low, high)
    if bad:
        return False, f"FAIL {name}  [{text}  too hard: {', '.join(bad)}]"
    return True, f"ok   {name}  [{text}]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gates.readability")
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--changed", metavar="BASE")
    parser.add_argument("--reply", metavar="FILE")
    parser.add_argument("--min", type=int, default=0)
    parser.add_argument("--max", type=int, default=11)
    args = parser.parse_args(argv)
    if textstat is None:
        return fail_hard("readability", "textstat is required; run uv sync")
    entries = parse_glossary()
    neutralize = neutralizer([term for term, _ in entries])
    problems = glossary_problems(entries, neutralize, args.min, args.max)
    for problem in problems:
        print(f"FAIL {GLOSSARY}  [{problem}]")
    if args.reply:
        raw = (
            sys.stdin.read() if args.reply == "-" else Path(args.reply).read_text(encoding="utf-8")
        )
        passed, message = score("reply", raw, neutralize, args.min, args.max)
        print(message)
        return 0 if passed and not problems else 1
    try:
        files = changed_markdown(args.changed) if args.changed else args.paths or tracked_markdown()
    except ToolMissing as exc:
        return fail_hard("readability", str(exc))
    skipped = allowlist()
    failures = len(problems)
    for name in files:
        path = Path(name)
        if name in skipped or not path.is_file():
            continue
        passed, message = score(
            name, path.read_text(encoding="utf-8"), neutralize, args.min, args.max
        )
        print(message)
        failures += 0 if passed else 1
    print(f"readability: {failures} failure(s); every page must read at grade {args.max} or lower")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
