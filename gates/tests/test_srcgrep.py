from gates import srcgrep


def test_fr0_5_source_path_in_a_test_fails(repo, capsys):
    repo.write(
        "tests/test_x.py",
        """
        def test_x():
            assert "def" in open("src/bikeplan/core.py").read()
        """,
    )
    assert srcgrep.main([]) == 1
    assert "tests/test_x.py" in capsys.readouterr().out


def test_fr0_5_inspect_getsource_fails(repo):
    repo.write(
        "tests/test_x.py",
        """
        import inspect

        import bikeplan


        def test_x():
            assert inspect.getsource(bikeplan)
        """,
    )
    assert srcgrep.main([]) == 1


def test_fr0_5_module_file_read_fails(repo):
    repo.write(
        "tests/test_x.py",
        """
        from pathlib import Path

        import bikeplan.core as core


        def test_x():
            assert Path(core.__file__).read_text()
        """,
    )
    assert srcgrep.main([]) == 1


def test_fr0_5_from_import_module_file_read_fails(repo):
    repo.write(
        "tests/test_x.py",
        """
        from pathlib import Path

        from bikeplan import core


        def test_x():
            assert Path(core.__file__).read_text()
        """,
    )
    assert srcgrep.main([]) == 1


def test_fr0_5_normal_test_passes(repo):
    repo.write(
        "tests/test_x.py",
        """
        from bikeplan.core import f


        def test_x():
            assert f() == 1
            assert "tests/fixtures/tiny.osm"
        """,
    )
    assert srcgrep.main([]) == 0


def test_fr0_5_package_option_names_the_product(repo):
    repo.write(
        "tests/test_x.py",
        """
        import minipkg


        def test_x():
            assert minipkg.__file__
        """,
    )
    assert srcgrep.main([]) == 0
    assert srcgrep.main(["--package", "minipkg"]) == 1
