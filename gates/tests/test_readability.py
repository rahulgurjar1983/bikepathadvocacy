import os
import subprocess
import sys
from pathlib import Path

import textstat

from gates import readability

ROOT = Path(__file__).resolve().parents[2]

PLAIN = (
    "We ride to school on a safe path. The path is wide and calm. Kids and old people "
    "like it. Cars stay on the road. We can see the park from the path. It is a good "
    "way to get to school each day. The town wants more paths like this one."
)

HARD = (
    "Notwithstanding considerable infrastructural heterogeneity, multimodal transportation "
    "interventions necessitate comprehensive intergovernmental coordination, particularly "
    "regarding prioritisation methodologies, quantitative evaluation frameworks, and "
    "longitudinal performance monitoring across jurisdictional administrative boundaries. "
    "Consequently, institutional stakeholders systematically underestimate implementation "
    "complexity."
)

MADE_UP = (
    "Zorblaxification helps zorblaxification on the street. We like zorblaxification and "
    "more zorblaxification. Zorblaxification makes the road calm with zorblaxification. "
    "Kids love zorblaxification and zorblaxification. Old people want zorblaxification "
    "after zorblaxification. The town will add zorblaxification to zorblaxification."
)

PLURALS = (
    "Homes need roads. Schools need paths. Shops need streets. Boys and girls walk to "
    "schools. Cars park on roads. Trees line the streets. Birds sing in trees. Dogs run "
    "in parks. Cats sleep on walls. Friends meet at shops. Days are long. Nights are "
    "cool. Farms grow apples."
)


def test_fr0_6_plain_text_passes(repo):
    repo.write("doc.md", PLAIN)
    assert readability.main(["doc.md"]) == 0


def test_fr0_6_hard_text_fails(repo, capsys):
    repo.write("doc.md", HARD)
    assert readability.main(["doc.md"]) == 1
    assert "FAIL doc.md" in capsys.readouterr().out


def test_fr0_6_glossary_terms_are_swapped_out(repo):
    repo.write("doc.md", MADE_UP)
    assert readability.main(["doc.md"]) == 1
    repo.write("GLOSSARY.md", "- **zorblaxification** — a made-up word for tests.\n")
    assert readability.main(["doc.md"]) == 0


def test_fr0_6_easy_glossary_term_fails(repo, capsys):
    repo.write("doc.md", PLAIN)
    repo.write("GLOSSARY.md", "- **road** — where cars go.\n")
    assert readability.main(["doc.md"]) == 1
    assert "road" in capsys.readouterr().out


def test_fr0_6_acronym_glossary_term_passes(repo):
    repo.write("doc.md", PLAIN)
    repo.write("GLOSSARY.md", "- **LTS** — a score of how hard a street feels on a bike.\n")
    assert readability.main(["doc.md"]) == 0


def test_fr0_6_hard_glossary_explanations_fail(repo):
    repo.write("doc.md", PLAIN)
    repo.write("GLOSSARY.md", f"- **zorblaxification** — {HARD}\n")
    assert readability.main(["doc.md"]) == 1


def test_fr0_6_short_files_are_skipped(repo):
    repo.write("doc.md", "Notwithstanding heterogeneity.\n")
    assert readability.main(["doc.md"]) == 0


def test_fr0_6_exempt_files_are_skipped(repo):
    repo.write("hard.md", HARD)
    repo.write(".readability-allow", "hard.md\n")
    assert readability.main(["hard.md"]) == 0


def test_fr0_6_changed_mode_scores_only_changed_files(repo):
    repo.write("hard.md", HARD)
    base = repo.commit("base")
    repo.branch("loop/docs")
    repo.write("plain.md", PLAIN)
    repo.commit("add plain doc")
    assert readability.main(["--changed", base]) == 0
    repo.append("hard.md", " More words.")
    repo.commit("touch hard doc")
    assert readability.main(["--changed", base]) == 1


def test_fr0_6_all_mode_scores_every_tracked_file(repo):
    repo.write("plain.md", PLAIN)
    repo.write("docs/hard.md", HARD)
    repo.commit("docs")
    assert readability.main([]) == 1


def test_fr0_6_code_tables_and_links_are_left_out(repo):
    repo.write(
        "doc.md",
        f"{PLAIN}\n\n```\n{HARD}\n```\n\n| {HARD} |\n|---|\n\n"
        f"See [the guide](https://example.org/{'x' * 40}) and `{HARD}`.\n",
    )
    assert readability.main(["doc.md"]) == 0


def test_fr0_6_plural_forms_of_easy_words_count_as_easy(repo):
    raw = readability.dale_chall_grade(textstat.dale_chall_readability_score(PLURALS))
    assert raw > 11
    repo.write("doc.md", PLURALS)
    assert readability.main(["doc.md"]) == 0


def test_fr0_6_reply_mode_scores_text(repo, tmp_path):
    good = tmp_path / "good.md"
    good.write_text(PLAIN)
    bad = tmp_path / "bad.md"
    bad.write_text(HARD)
    assert readability.main(["--reply", str(good)]) == 0
    assert readability.main(["--reply", str(bad)]) == 1


def test_fr0_6_check_reply_script_runs_the_same_gate(tmp_path):
    good = tmp_path / "good.md"
    good.write_text(PLAIN)
    bad = tmp_path / "bad.md"
    bad.write_text(HARD)
    script = str(ROOT / "scripts" / "check-reply.sh")
    ok = subprocess.run(["bash", script, str(good)], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    fail = subprocess.run(["bash", script], input=HARD, capture_output=True, text=True)
    assert fail.returncode == 1, fail.stdout + fail.stderr


def test_fr0_16_missing_textstat_fails_hard(repo):
    repo.write("doc.md", PLAIN)
    code = (
        "import runpy, sys\n"
        "sys.modules['textstat'] = None\n"
        "sys.argv = ['readability', 'doc.md']\n"
        "runpy.run_module('gates.readability', run_name='__main__')\n"
    )
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=repo.path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 2
    assert "textstat" in result.stderr
