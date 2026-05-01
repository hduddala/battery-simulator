# battery_sim

Shaman **I / II** battery energy simulator: JSON scenarios → time-series SOC, CSV, and structured JSON results.

This folder is intended to be **its own Git repository** (push only this directory).

## Quick start

```bash
cd battery_sim
python3 battery_simulator.py --overwrite
```

Regression check:

```bash
python3 battery_simulator.py --verify
```

Spec-complete **two-hop** scenario:

```bash
python3 battery_simulator.py --scenario scenario_spec_complete.json --out-dir output_spec --overwrite
```

Optional virtualenv (recommended for isolation, not required — stdlib only):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

## Contents

| File | Purpose |
|------|---------|
| `battery_simulator.py` | Engine + CLI |
| `scenario.json` | Default 72 h demo (single relay hop) |
| `scenario_spec_complete.json` | 96 h, two relays, fuller §2-style inputs |
| `SIMULATOR.md` | Equations, variable mapping, where outputs live |
| **`docs/`** | Ivonne’s **`variables_equations.md`** & **`simulation_loop.md`** (copied from `battery sim/Ivonne/docs/`) + index |

Outputs land under `output/` or `--out-dir` (ignored by git — regenerate anytime).

## Documentation

- **`SIMULATOR.md`** — canonical naming for this repo (`P_mic`, `scenario.json`, CLI).
- **`docs/README.md`** — index linking **`variables_equations.md`** (Ivonne notation + equations) and **`simulation_loop.md`** (loop design).

## Git / push

From **inside** this folder:

```bash
git init
git add battery_simulator.py scenario.json scenario_spec_complete.json SIMULATOR.md README.md .gitignore docs/
git commit -m "Initial battery simulator bundle"
git remote add origin <your-repo-url>
git push -u origin main
```

Do **not** commit `.venv/`, `output/`, or `output_spec/` — they are listed in `.gitignore`.
