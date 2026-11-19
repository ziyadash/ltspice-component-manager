# ltmodel

Look up a component by name, check whether LTspice already has a model for it,
and if not, fetch one and install it (model, plus a symbol where needed) into
the right LTspice folders.

```bash
uv run ltmodel find BC547B            # is it already in LTspice?
uv run ltmodel install BF862          # search GitHub, list candidates
uv run ltmodel install BF862 --pick 3 # install candidate 3
uv run ltmodel install X --from ~/Downloads/x.lib   # a vendor file you downloaded
uv run ltmodel check 2N5486 --idss 8m 20m           # sanity-check parameters
uv run ltmodel uninstall BF862
```

Add `--dry-run` to any install/uninstall to see what would change without writing.

## What it does

1. **Scan** `lib/cmp` and `lib/sub` for a `.model` or `.subckt` with that name.
   If it exists, `install` stops (use `--force` to override).
2. **Fetch** from a file or URL you give with `--from`, or by searching public
   GitHub files (needs the [`gh`](https://cli.github.com) CLI, logged in).
   Candidates are listed and you choose one; nothing is installed unseen.
3. **Install**
   - Discrete `.model` (NPN/PNP/NJF/PJF/NMOS/PMOS/D): appended to LTspice's
     `standard.bjt` / `.jft` / `.mos` / `.dio`, so the stock symbol finds it by
     name. Just place the generic `npn`/`njf`... symbol and set its Value.
   - `.subckt`: written to `lib/sub/NAME.lib` with a generated symbol in
     `lib/sym/ltmodel/NAME.asy` (pins in netlist order; press F2 and browse to
     the `ltmodel` folder).
   LTspice's "Pick New Transistor" dialog builds its Manufacturer / Vceo / Ic
   columns from `mfg=`, `Vceo=` and `Icrating=` in the model. `install` adds
   `mfg=` (defaults to the provenance tag, e.g. `community`, so the picker shows
   how far to trust it) and, if you pass `--vceo 45 --icrating 100m`, the
   ratings. Existing values in a model are never overwritten and ratings are
   never invented. Use `--mfg onsemi` to set the manufacturer yourself.
4. **Provenance**: every install gets `source` / `provenance` / date comment
   lines. Tags: `vendor`, `community`, `derived`, `user-supplied`.

Safety: files are backed up to `lib/.ltmodel-backups/` before any change,
installs are wrapped in marker comments, and `uninstall` removes only what
ltmodel put there. Updating LTspice may overwrite the `standard.*` files, in
which case just re-run `install`.

## Library location

Auto-detected on macOS (`~/Library/Application Support/LTspice/lib`) and
Windows (`~/AppData/Local/LTspice/lib`, `~/Documents/LTspiceXVII/lib`).
Override with `--lib-dir` or `$LTSPICE_LIB`. `ltmodel where` shows what it found.

## Caveats

- Community models are unverified. Use `ltmodel check`: for JFETs it computes
  IDSS = Beta * Vto^2 and compares with a datasheet range. This caught
  LTspice's own 2N5486 model, which works out to about 64 mA against a
  datasheet 8-20 mA.
- Manufacturer sites (e.g. Nexperia) block scripted downloads, so for vendor
  models download the file in a browser and use `--from`.
- The generated subcircuit symbols are plain rectangles; they aren't tailored
  to the part.

## Development

```bash
uv run --with pytest python -m pytest
```

## Examples

`examples/2n5486_derived.lib` has datasheet-derived 2N5486 JFET models (nominal
plus low/high IDSS corners) as a sample `--from` file.
