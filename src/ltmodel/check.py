"""Sanity checks on a model's parameters against datasheet numbers."""

from __future__ import annotations

from dataclasses import dataclass

from .spice import Definition


@dataclass
class Finding:
    ok: bool
    message: str


def _eng(value: float, unit: str) -> str:
    for scale, prefix in ((1.0, ""), (1e-3, "m"), (1e-6, "u")):
        if abs(value) >= scale:
            return f"{value / scale:.3g} {prefix}{unit}"
    return f"{value:.3g} {unit}"


def check(d: Definition, idss_range: tuple[float, float] | None = None) -> list[Finding]:
    out: list[Finding] = []
    if d.kind != "model":
        return [Finding(True, "subcircuit: no automatic checks available")]

    if d.mtype in {"NJF", "PJF"}:
        vto, beta = d.number("vto"), d.number("beta")
        if vto is None or beta is None:
            return [Finding(False, "missing Vto or Beta (LTspice defaults -2 V / 1e-4 will apply)")]
        idss = beta * vto * vto  # SPICE JFET: Id = Beta * (Vgs - Vto)^2 at Vds in saturation
        gfs = 2 * (beta * idss) ** 0.5
        out.append(Finding(True, f"IDSS = Beta*Vto^2 = {_eng(idss, 'A')}, gfs(0V) = {_eng(gfs, 'S')}"))
        if idss_range:
            lo, hi = idss_range
            ok = lo <= idss <= hi
            out.append(Finding(ok, f"IDSS {'within' if ok else 'OUTSIDE'} datasheet range "
                                   f"{_eng(lo, 'A')} to {_eng(hi, 'A')}"))
    elif d.mtype in {"NPN", "PNP"}:
        for key, label in (("bf", "Bf (gain)"), ("vaf", "Vaf (Early voltage)"),
                           ("is", "Is"), ("cje", "Cje"), ("cjc", "Cjc"), ("tf", "Tf")):
            v = d.number(key)
            out.append(Finding(v is not None,
                               f"{label} = {v:g}" if v is not None else f"{label} not set (default used)"))
    else:
        out.append(Finding(True, f"no checks for {d.mtype} models"))
    return out
