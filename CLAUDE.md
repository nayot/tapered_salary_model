# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Interactive Streamlit tools that model a **tapered salary adjustment** for Burapha University (BUU) personnel. Given an old base (`B_old`) and a new base (`B_new`), employees below `B_new` are lifted up to `B_new`, employees between `B_new` and a "flag-cutoff" `S_max` receive a tapered top-up that decays to zero at `S_max`, and nobody is paid beyond `Max_New`. The taper curve uses a `gamma (γ)` exponent so the shape can be tuned from linear (γ=1) through convex/concave variants.

The UI and most string content are in **Thai**. Variable and function names are English; comments and labels are Thai. Keep both conventions when editing.

## Repository layout — two independent uv projects

This is not a single Python project. There are two separate uv-managed sub-projects with **different Python versions**:

- [applet/](applet/) — Python **3.12**. Standalone prototype: lets the user explore the tapering curve abstractly with snapshot/compare. No data files needed. Entry point: [applet/main.py](applet/main.py).
- [budget_analysis/](budget_analysis/) — Python **3.14**. Data-driven budget estimation against the real payroll. Two entry points:
  - [budget_analysis/budget_posid.py](budget_analysis/budget_posid.py) — drill down by single position (POS_ID) within a personnel group (GRP_ID).
  - [budget_analysis/budget_grpid.py](budget_analysis/budget_grpid.py) — aggregate across all positions / groups; produces monthly + annual budget totals.

Each project has its own `pyproject.toml`, `uv.lock`, and `.python-version`. Always run uv commands from inside the project directory whose script you are touching.

```bash
# applet (prototype curve)
cd applet && uv run streamlit run main.py

# budget analysis (real data — must be run from budget_analysis/ for the relative data/ paths)
cd budget_analysis && uv run streamlit run budget_posid.py
cd budget_analysis && uv run streamlit run budget_grpid.py
```

There is no test suite, lint config, or build step. `uv sync` inside either subdir installs deps.

## Data layout (confidential)

- `data/` at repo root is a **symlink** to `../tapered_salary_confidential/data` (a sibling repo containing real payroll data). It is git-ignored.
- The budget scripts read **relative paths** `data/new_salary_table.parquet` and `data/salary_all_posid.parquet` — they assume the current working directory is `budget_analysis/`, where a separate `data/` directory exists with the parquet files. Do not "fix" these paths to absolute without understanding both data locations.
- Parquet column names are Thai (`เงินเดือน` = salary, `ประเภทบุคลากร` = personnel-funding-type). Numeric columns may arrive as comma-formatted strings; both scripts run `clean_num` to strip commas and coerce to numeric.

## Core domain model (read this before editing any taper math)

All three scripts implement the same conceptual adjustment, but with slightly different signatures. The canonical version lives in `budget_grpid.py::calculate_adjustment`:

```
db = B_new - B_old
S_max = B_old + (pct/100) * (Max_Old - B_old)        # flag-cutoff, derived from slider %
if salary < B_new:           adj = B_new - salary    # guarantee floor: lift to Min_New
elif salary <= S_max:        adj = db * clip(1 - (salary - B_new) / (S_max - B_new), 0, 1) ** γ
else:                        adj = 0
adj = min(adj, Max_New - salary)                     # cap so new_salary never exceeds Max_New
final_adj = ceil_to_10(adj)                          # round up to nearest 10 baht
```

Key invariants — preserve them when refactoring:
- Below `B_new`: full top-up to `B_new` (no taper). This is the "guarantee" branch.
- Between `B_new` and `S_max`: taper governed by `γ`.
- Above `S_max`: zero top-up.
- New salary never exceeds `Max_New`.
- The applet prototype anchors the taper at `B_old` instead of `B_new` and lacks the floor/ceiling logic — it's intentionally simpler. Don't unify the two without checking.

Reference table (`new_salary_table.parquet`) provides `POS_ID`, `GRP_ID`, `Min_Old`, `Min_New`, `Max_Old`, `Max_New`, `Type`, `Deg_Pos`. `GRP_ID` semantics are fixed: 1=สายวิชาการ-อุดมศึกษา, 2=สายวิชาการ-ต่ำกว่าอุดมศึกษา, 3=สายสนับสนุน-ปฏิบัติการ, 4=สายสนับสนุน-ปฏิบัติงาน. `budget_grpid.py` also accepts `0 = ทั้งหมด` (all groups).

## Notes for editing the Streamlit apps

- All three scripts hold UI state in `st.session_state` and use `@st.cache_data` on `load_data()`. Mutating the loaded DataFrames in place will poison the cache for the rest of the session — always `.copy()` first (the scripts already do this; keep it).
- `budget_grpid.py` currently renders the GRP/POS summary table twice (once with annual totals, once without). That's existing behavior, not a bug you should silently dedupe — confirm with the user before consolidating.
