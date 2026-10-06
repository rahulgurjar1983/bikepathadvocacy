from gates import generic


def test_fr0_17_region_name_in_core_code_fails(repo, capsys):
    repo.write("gates/generic-denylist.txt", "bayside\nnew south wales\n")
    repo.write("src/bikeplan/core.py", 'NAME = "Bayside"\n')
    assert generic.main([]) == 1
    assert "src/bikeplan/core.py" in capsys.readouterr().out


def test_fr0_17_multi_word_names_are_caught(repo):
    repo.write("gates/generic-denylist.txt", "new south wales\n")
    repo.write("src/bikeplan/core.py", 'STATE = "New  South Wales"\n')
    assert generic.main([]) == 1


def test_fr0_17_adapters_may_name_regions(repo):
    repo.write("gates/generic-denylist.txt", "bayside\nsydney\n")
    repo.write("src/bikeplan/adapters/au_nsw.py", 'CITY = "Sydney"\n')
    assert generic.main([]) == 0


def test_fr0_17_words_match_whole_words_only(repo):
    repo.write("gates/generic-denylist.txt", "nsw\n")
    repo.write("src/bikeplan/core.py", 'KEY = "answer"\nOTHER = "nswx"\n')
    assert generic.main([]) == 0


def test_fr0_16_missing_denylist_fails_hard(repo, capsys):
    repo.write("src/bikeplan/core.py", "x = 1\n")
    assert generic.main([]) == 2
    assert "generic-denylist.txt" in capsys.readouterr().err
