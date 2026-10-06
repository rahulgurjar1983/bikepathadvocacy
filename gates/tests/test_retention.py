from gates import retention


def test_fr0_3_dropped_test_fails(mini, capsys):
    base = mini.head()
    mini.write("tests/test_core.py", "from minipkg.core import one\n")
    mini.commit("drop test_one")
    assert retention.main(["--base", base]) == 1
    out = capsys.readouterr()
    assert "test_one" in out.out + out.err


def test_fr0_3_retires_trailer_allows_a_drop(mini):
    base = mini.head()
    mini.write("tests/test_core.py", "from minipkg.core import one\n")
    mini.commit("drop test_one\n\nRetires: P1.1")
    assert retention.main(["--base", base]) == 0


def test_fr0_3_rename_keeps_tests(mini):
    base = mini.head()
    mini.git("mv", "tests/test_core.py", "tests/test_core_moved.py")
    mini.commit("rename test file")
    assert retention.main(["--base", base]) == 0


def test_fr0_3_body_edit_passes(mini):
    base = mini.head()
    mini.write(
        "tests/test_core.py",
        """
        from minipkg.core import one


        def test_one():
            assert one() + 1 == 2
        """,
    )
    mini.commit("edit test body")
    assert retention.main(["--base", base]) == 0


def test_fr0_3_deleted_file_fails(mini):
    base = mini.head()
    mini.git("rm", "-q", "tests/test_core.py")
    mini.commit("delete test file")
    assert retention.main(["--base", base]) == 1


def test_fr0_3_class_methods_are_tracked(mini):
    mini.write(
        "tests/test_class.py",
        """
        class TestOne:
            def test_a(self):
                assert True

            def test_b(self):
                assert True
        """,
    )
    base = mini.commit("class tests")
    mini.write(
        "tests/test_class.py",
        """
        class TestOne:
            def test_a(self):
                assert True
        """,
    )
    mini.commit("drop a method")
    assert retention.main(["--base", base]) == 1


def test_fr0_3_new_tests_pass(mini):
    base = mini.head()
    mini.append("tests/test_core.py", "\n\ndef test_more():\n    assert one() == 1\n")
    mini.commit("add test")
    assert retention.main(["--base", base]) == 0
