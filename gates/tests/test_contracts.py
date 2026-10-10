import pytest

BEFORE = """
def test_fr13_1_figures_are_sorted_with_every_field(output):
    figures = read(output)
    assert [item["id"] for item in figures] == [f"F{n}" for n in range(1, 14)]
    for item in figures:
        assert set(item) == {"id", "value", "recipe"}
"""


def test_fr0_35_exact_figure_contract_may_add_required_ids():
    from gates.contracts import valid_figure_extension

    assert valid_figure_extension(BEFORE, BEFORE.replace("range(1, 14)", "range(1, 15)"))
    assert valid_figure_extension(BEFORE, BEFORE)


@pytest.mark.parametrize(
    "replacement",
    [
        "range(1, 13)",
        "range(2, 15)",
        "range(1, expected_count)",
    ],
)
def test_fr0_35_rejects_smaller_or_output_derived_contract(replacement):
    from gates.contracts import valid_figure_extension

    assert not valid_figure_extension(BEFORE, BEFORE.replace("range(1, 14)", replacement))


def test_fr0_35_keeps_all_old_fields_and_assertions():
    from gates.contracts import valid_figure_extension

    after = BEFORE.replace("range(1, 14)", "range(1, 15)")
    assert not valid_figure_extension(BEFORE, after.replace(', "recipe"', ""))
    assert not valid_figure_extension(
        BEFORE, after.replace("assert set(item) ==", "assert set(item) >=")
    )


def test_fr0_35_archive_contract_adds_files_without_removal():
    from gates.contracts import valid_files_extension

    before = 'FILES = ["figures.json", "report.html", "segments.csv"]\n'
    after = before.replace('"report.html"', '"proposal.json", "report.html"')
    assert valid_files_extension(before, after)
    assert not valid_files_extension(before, after.replace('"segments.csv"', '"other.json"'))
    assert not valid_files_extension(before, after.replace('"proposal.json"', '"../private.json"'))
