"""Input file fingerprints for the step key (plans/ISSUES.md I1)."""

from nf_meta.runner.paths import input_fingerprints


def test_file_has_path_size_and_mtime(tmp_path):
    f = tmp_path / "ids.csv"
    f.write_text("SRR1\n")
    [[path, size, mtime]] = input_fingerprints({"input": str(f)})["input"]
    assert (path, size) == (str(f), 5)
    assert mtime == f.stat().st_mtime_ns


def test_directory_lists_direct_entries(tmp_path):
    (tmp_path / "a.fa").write_text(">a\n")
    (tmp_path / "sub").mkdir()
    [[path, entries]] = input_fingerprints({"refs": str(tmp_path)})["refs"]
    assert path == str(tmp_path)
    assert [e[0] for e in entries] == ["a.fa", "sub"]


def test_glob_pattern_fingerprints_each_match(tmp_path):
    for name in ("b_1.fq", "a_1.fq", "notes.txt"):
        (tmp_path / name).write_text("x")
    prints = input_fingerprints({"reads": str(tmp_path / "*_1.fq")})["reads"]
    assert [p[0] for p in prints] == [str(tmp_path / "a_1.fq"), str(tmp_path / "b_1.fq")]


def test_left_out(tmp_path):
    existing = tmp_path / "x.csv"
    existing.write_text("x")
    params = {
        "outdir": str(tmp_path),
        "url": "https://example.org/x.csv",
        "ref": "${n01:params:outdir}/x.csv",
        "missing": str(tmp_path / "nope.csv"),
        "relative": "x.csv",
        "number": 3,
        "placeholder": "<input: ids>",
    }
    assert input_fingerprints(params) == {}
