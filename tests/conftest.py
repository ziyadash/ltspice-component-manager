import pytest

from ltmodel.paths import LibDirs

STANDARD_JFT = (
    ".model 2N5484 NJF(Is=.25p Vto=-1.5 Beta=3.0m Lambda=10m Cgs=4p Cgd=4p mfg=Siliconix)\n"
    ".model 2N5486 NJF(Is=.25p Alpha=1e-4 Vk= 80 Vto=-4.0 Vtotc=-3m Beta=4.0m Lambda=10m\n"
    "+ Betatce=-.5 Rd=10 Rs=10 Cgs=4p Cgd=4p Kf=3e-17 mfg=Siliconix)\n"
)
STANDARD_BJT = (
    "* comment line\n"
    ".model BC547B NPN(IS=2.39E-14 BF=294.3 VAF=63.2 CJE=1.358E-11 mfg=NXP)\n"
)


@pytest.fixture
def libs(tmp_path):
    root = tmp_path / "lib"
    (root / "cmp").mkdir(parents=True)
    (root / "sub").mkdir()
    (root / "sym").mkdir()
    (root / "cmp" / "standard.jft").write_text(STANDARD_JFT)
    (root / "cmp" / "standard.bjt").write_text(STANDARD_BJT)
    return LibDirs(root)
