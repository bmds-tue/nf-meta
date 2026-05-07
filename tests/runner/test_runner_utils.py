import subprocess
import pytest

from nf_meta.runner.utils import (  # type: ignore[import]
    check_nextflow,
    get_installed_nextflow_version,
    check_nextflow_version,
)
from nf_meta.runner.errors import NfMetaRunnerError  # type: ignore[import]


# ---------------------------------------------------------------------------
# check_nextflow
# ---------------------------------------------------------------------------


class TestCheckNextflow:
    def test_found_returns_path(self, monkeypatch):
        monkeypatch.setattr(
            "nf_meta.runner.utils.shutil.which", lambda _: "/usr/bin/nextflow"
        )
        result = check_nextflow()
        assert result == "/usr/bin/nextflow"

    def test_not_found_raises(self, monkeypatch):
        monkeypatch.setattr("nf_meta.runner.utils.shutil.which", lambda _: None)
        with pytest.raises(NfMetaRunnerError, match="No nextflow installation found"):
            check_nextflow()


class TestGetInstalledNextflowVersion:
    def _mock_run(self, monkeypatch, stdout="", returncode=0):
        result = subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout=stdout, stderr=""
        )
        monkeypatch.setattr(
            "nf_meta.runner.utils.subprocess.run", lambda *a, **kw: result
        )

    def test_parses_standard_version(self, monkeypatch):
        self._mock_run(monkeypatch, stdout="      version 25.10.4 build 11173\n")
        assert get_installed_nextflow_version() == (25, 10, 4, 0)

    def test_parses_edge_version(self, monkeypatch):
        self._mock_run(monkeypatch, stdout="      version 25.10.4-edge build 11173\n")
        assert get_installed_nextflow_version() == (25, 10, 4, 1)

    def test_bad_returncode_raises(self, monkeypatch):
        self._mock_run(monkeypatch, stdout="error output", returncode=1)
        with pytest.raises(NfMetaRunnerError):
            get_installed_nextflow_version()

    def test_unparseable_output_raises(self, monkeypatch):
        self._mock_run(monkeypatch, stdout="some unrelated text")
        with pytest.raises(NfMetaRunnerError, match="Could not parse"):
            get_installed_nextflow_version()

    def test_file_not_found_raises(self, monkeypatch):
        def raise_fnf(*a, **kw):
            raise FileNotFoundError

        monkeypatch.setattr("nf_meta.runner.utils.subprocess.run", raise_fnf)
        with pytest.raises(NfMetaRunnerError):
            get_installed_nextflow_version()

    def test_timeout_raises(self, monkeypatch):
        def raise_timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="nextflow", timeout=30)

        monkeypatch.setattr("nf_meta.runner.utils.subprocess.run", raise_timeout)
        with pytest.raises(NfMetaRunnerError):
            get_installed_nextflow_version()


# ---------------------------------------------------------------------------
# check_nextflow_version
# ---------------------------------------------------------------------------


class TestCheckNextflowVersion:
    def _patch_installed(self, monkeypatch, version: tuple):
        monkeypatch.setattr(
            "nf_meta.runner.utils.get_installed_nextflow_version", lambda: version
        )

    def test_matching_version_returns_true(self, monkeypatch):
        self._patch_installed(monkeypatch, (25, 10, 4, 0))
        assert check_nextflow_version((25, 10, 4, 0)) is True

    def test_major_mismatch_raises(self, monkeypatch):
        self._patch_installed(monkeypatch, (24, 10, 4, 0))
        with pytest.raises(NfMetaRunnerError):
            check_nextflow_version((25, 10, 4, 0))

    def test_minor_mismatch_logs_warning_not_raises(self, monkeypatch, caplog):
        import logging

        self._patch_installed(monkeypatch, (25, 9, 4, 0))
        with caplog.at_level(logging.WARNING, logger="nf_meta.runner.utils"):
            result = check_nextflow_version((25, 10, 4, 0))
        assert result is True
        assert any("mismatch" in r.message.lower() for r in caplog.records)
