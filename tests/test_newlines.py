"""CRLF and lone-CR files load with LF only (v0.1.1): the GUI preview drew every CR as a music-note glyph
and the CR went into the EPUB paragraphs."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import detect  # noqa: E402

CR, LF = chr(13), chr(10)


def _write(tmp_path, name, data: bytes):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_crlf_cp949_loads_as_lf(tmp_path):
    src = CR.join(["김소월 시선" + LF, LF, "제1장 진달래꽃" + LF, "나 보기가 역겨워" + LF]).replace(LF + CR, CR + LF)
    path = _write(tmp_path, "crlf.txt", src.encode("cp949"))
    text, det, bad = detect.read_file(path)
    assert CR not in text
    assert text == LF.join(["김소월 시선", "", "제1장 진달래꽃", "나 보기가 역겨워", ""])
    assert bad == 0


def test_lone_cr_utf8_loads_as_lf(tmp_path):
    path = _write(tmp_path, "cr.txt", ("line one" + CR + "line two" + CR).encode("utf-8"))
    text, _, _ = detect.read_file(path)
    assert text == "line one" + LF + "line two" + LF


def test_lf_file_is_unchanged(tmp_path):
    path = _write(tmp_path, "lf.txt", ("a" + LF + "b" + LF).encode("utf-8"))
    text, _, _ = detect.read_file(path)
    assert text == "a" + LF + "b" + LF
