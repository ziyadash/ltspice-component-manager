import pytest

from ltmodel import check, cli, install, scan, sources
from ltmodel.spice import parse_definitions, parse_number

NEW_NPN = ".model 2N3904 NPN(IS=6.7f BF=416 VAF=74 CJE=4.5p CJC=3.6p TF=300p)"
SUBCKT = """* opamp
.subckt MYOPAMP inp inn out vcc vee
R1 inp inn 1meg
E1 out 0 inp inn 1e5
.ends MYOPAMP
"""


def test_parse_number():
    assert parse_number("4.0m") == pytest.approx(4e-3)
    assert parse_number("10meg") == pytest.approx(1e7)
    assert parse_number("1e-4") == pytest.approx(1e-4)
    assert parse_number("-.5") == pytest.approx(-0.5)
    assert parse_number("abc") is None


def test_parse_continuation_and_params():
    d = parse_definitions(
        ".model 2N5486 NJF(Vto=-4.0\n+ Beta=4.0m Lambda=10m)\n")[0]
    assert (d.name, d.mtype) == ("2N5486", "NJF")
    assert d.number("beta") == pytest.approx(4e-3)
    assert d.number("VTO") == pytest.approx(-4.0)
    assert d.text.count("\n") == 1  # both physical lines kept


def test_parse_subckt_pins_and_text():
    d = parse_definitions(SUBCKT)[0]
    assert d.kind == "subckt" and d.pins == ["inp", "inn", "out", "vcc", "vee"]
    assert d.text.rstrip().endswith(".ends MYOPAMP")


def test_scan_finds_existing_case_insensitive(libs):
    hits = scan.scan(libs, "bc547b")
    assert len(hits) == 1 and hits[0].path.name == "standard.bjt"
    assert scan.scan(libs, "NOPE") == []


def test_check_flags_shipped_2n5486_idss(libs):
    d = scan.scan(libs, "2N5486")[0].definition
    findings = check.check(d, (8e-3, 20e-3))
    assert any("64" in f.message for f in findings)  # 4m * 16 = 64 mA
    assert not findings[-1].ok


def test_install_model_appends_backs_up_and_is_idempotent(libs):
    d = parse_definitions(NEW_NPN)[0]
    report = install.install(libs, d, "test", "community")
    text = (libs.cmp / "standard.bjt").read_text()
    assert "ltmodel:2N3904" in text and "BC547B" in text  # original kept
    assert any(a.startswith("backup") for a in report.actions)
    assert "stock `npn`" in report.hint
    with pytest.raises(FileExistsError):
        install.install(libs, d, "test", "community")
    install.install(libs, d, "test", "community", force=True)
    assert (libs.cmp / "standard.bjt").read_text().count("ltmodel:2N3904 >>>") == 1
    assert scan.scan(libs, "2N3904")


def test_dry_run_writes_nothing(libs):
    before = (libs.cmp / "standard.bjt").read_text()
    install.install(libs, parse_definitions(NEW_NPN)[0], "t", "community", dry_run=True)
    assert (libs.cmp / "standard.bjt").read_text() == before
    assert not libs.backups.exists()


def test_uninstall_restores_original(libs):
    before = (libs.cmp / "standard.bjt").read_text()
    install.install(libs, parse_definitions(NEW_NPN)[0], "t", "community")
    install.uninstall(libs, "2N3904")
    assert (libs.cmp / "standard.bjt").read_text() == before
    with pytest.raises(FileNotFoundError):
        install.uninstall(libs, "2N3904")


def test_uninstall_never_touches_foreign_models(libs):
    with pytest.raises(FileNotFoundError):
        install.uninstall(libs, "BC547B")  # shipped with LTspice, not ours
    assert scan.scan(libs, "BC547B")


def test_crlf_files_keep_crlf(libs):
    path = libs.cmp / "standard.bjt"
    path.write_bytes(path.read_text().replace("\n", "\r\n").encode())
    install.install(libs, parse_definitions(NEW_NPN)[0], "t", "community")
    raw = path.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")


def test_subckt_install_writes_lib_and_symbol(libs):
    d = parse_definitions(SUBCKT)[0]
    install.install(libs, d, "test", "vendor")
    assert (libs.sub / "MYOPAMP.lib").exists()
    asy = (libs.sym / "ltmodel" / "MYOPAMP.asy").read_text()
    assert asy.count("PIN ") == 5 and "SYMATTR ModelFile MYOPAMP.lib" in asy
    assert "PINATTR PinName vee" in asy
    install.uninstall(libs, "MYOPAMP")
    assert not (libs.sub / "MYOPAMP.lib").exists()
    assert not (libs.sym / "ltmodel" / "MYOPAMP.asy").exists()


def test_from_file_extracts_requested_model(tmp_path):
    f = tmp_path / "vendor.lib"
    f.write_text(NEW_NPN + "\n.model OTHER NPN(IS=1f)\n")
    cands = sources.from_file_or_url(str(f), "2n3904")
    assert [c.definition.name for c in cands] == ["2N3904"]
    assert cands[0].kind == "user-supplied"


def test_cli_install_skips_when_already_present(libs, capsys):
    rc = cli.main(["--lib-dir", str(libs.root), "install", "BC547B"])
    out = capsys.readouterr().out
    assert rc == 0 and "already available" in out
    assert not libs.backups.exists()


def test_cli_install_from_file_end_to_end(libs, tmp_path, capsys):
    f = tmp_path / "m.lib"
    f.write_text(NEW_NPN)
    rc = cli.main(["--lib-dir", str(libs.root), "install", "2N3904",
                   "--from", str(f), "--pick", "1", "--kind", "vendor"])
    assert rc == 0
    assert "provenance: vendor" in (libs.cmp / "standard.bjt").read_text()
    assert cli.main(["--lib-dir", str(libs.root), "find", "2N3904"]) == 0
