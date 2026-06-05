# Tapered Salary Model — BUU

Interactive Streamlit tools for modelling a **tapered salary adjustment** for Burapha University (BUU) personnel under the revised salary table. Given the old and new minimum bases for each position, the model lifts under-base employees to the new minimum, applies a tunable taper across the mid-band, and caps everyone at the new maximum.

The user interface is in Thai. This README is in English for setup; the in-app captions you will see while running the tools are Thai.

## Repository contents

| Path | Purpose | Python | Needs payroll data? |
| --- | --- | --- | --- |
| [applet/](applet/) | Curve-shape playground. Explore how `γ` and `S_max` affect the taper, capture snapshots, compare. | 3.12 | No |
| [budget_analysis/budget_posid.py](budget_analysis/budget_posid.py) | Single-position budget drill-down — pick one `GRP_ID` + `POS_ID`, see the per-employee adjustment and total monthly cost. | 3.14 | Yes |
| [budget_analysis/budget_grpid.py](budget_analysis/budget_grpid.py) | Whole-group / whole-university budget — pick a group (or "all") and a funding source, see monthly and annual totals plus a box-plot of adjustments. | 3.14 | Yes |

The two sub-projects are independent: each has its own `pyproject.toml`, `uv.lock`, and `.python-version`. There is no top-level Python project.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (handles Python versions and dependencies)
- For `budget_analysis/`: the parquet data files described in [Data](#data) below. Without them the apps will display "ไม่พบไฟล์ข้อมูล" and stop.

## Quick start

### 1. Curve playground (no data needed)

```bash
cd applet
uv sync
uv run streamlit run main.py
```

Then visit the URL Streamlit prints (default <http://localhost:8501>).

Sidebar controls:
- **ฐานเดิม / ฐานใหม่ (B_old, B_new)** — old and new base salary.
- **จุดตัดชายธง (S_max)** — the salary at which the top-up tapers to zero.
- **ความโค้ง (γ)** — taper curvature. `γ=1` is linear; `γ<1` keeps top-ups higher for longer; `γ>1` decays faster.
- **Capture กราฟปัจจุบัน** — save the current curve as a dashed reference so you can A/B different `γ`/`S_max` combinations.

The bottom **Individual Simulator** lets you type a single salary and see the resulting top-up and new salary (rounded up to the nearest 10 baht).

### 2. Single-position budget (budget_posid)

```bash
cd budget_analysis
uv sync
uv run streamlit run budget_posid.py
```

Important: you must run this from inside `budget_analysis/` because the script reads `data/new_salary_table.parquet` and `data/salary_all_posid.parquet` as **relative paths**.

Sidebar workflow:
1. Pick a personnel group **GRP_ID** (1–4, see [Group codes](#group-codes)).
2. Pick a funding source — ทั้งหมด, เงินอุดหนุนรัฐบาล, or เงินรายได้ส่วนงาน.
3. Pick a position **POS_ID** within that group. `Min_Old`, `Min_New`, `Max_Old`, `Max_New` are read from the reference table automatically.
4. Set the **flag-cutoff %** (where `S_max` sits between `B_old` and `Max_Old`) and **γ**.

Main view: a histogram of current salaries for that position overlaid with the proposed top-up curve, plus the total monthly budget required, the count of employees being lifted into the new floor, and the count whose new salary hits `Max_New`. There is also a per-employee simulator.

### 3. Whole-group budget (budget_grpid)

```bash
cd budget_analysis
uv run streamlit run budget_grpid.py
```

Use this for university-wide or per-group budget envelopes. Selecting `0: ทั้งหมด` aggregates across all four groups. Output includes:

- Monthly total + projected annual total (×12).
- Average top-up per person.
- A summary table — by group when "all" is selected, or by position when a single group is selected — showing headcount, monthly, and annual totals.
- A box plot of the distribution of top-ups.
- **Employer fund contributions** — four additional budget lines can be toggled and rate-configured in the sidebar:
  - เงินสมทบกองทุนประกันสังคม (Social Security): default 5 %, monthly ceiling steps up by CE year (≤ 2028: 875 THB, 2029–2031: 1 000 THB, ≥ 2032: 1 150 THB).
  - เงินสมทบกองทุนสำรองเลี้ยงชีพ (Provident Fund): default 5 %.
  - เงินสมทบกองทุนสวัสดิการ (Welfare Fund): fixed 10 000 THB / person / year.
  - เงินสมทบกองทุนบูรพามั่นคง (Burapha Fund): default 0.5 %.
- **Fund breakdown table** at Year 0 — salary + each selected fund, monthly and annual.
- **Multi-year projection** with a grand total column (salary + all checked funds). Projection models annual raises and retirement/replacement.
- **Baseline "what-if" overlay** — toggle "แสดงกราฟฐาน" to add a solid grey reference line showing the total budget *without* any tapered adjustment; the gap to the red adjusted-total line is shaded.
- **Export buttons** — download the projection table and Year-0 breakdown as `.xlsx` (two sheets) or `.pdf` (Thai font, A4 landscape).

## Adjustment formula

For each employee with current salary `s` working in position with `(B_old, B_new, Max_Old, Max_New)`:

```
S_max  = B_old + (pct/100) * (Max_Old - B_old)    # from the slider
ΔB     = B_new - B_old

if s < B_new:        adj = B_new - s              # guarantee: lift to new minimum
elif s ≤ S_max:      adj = ΔB · clip(1 − (s − B_new)/(S_max − B_new), 0, 1)^γ
else:                adj = 0

adj = min(adj, Max_New − s)                       # never exceed Max_New
final_adj = ceil(adj / 10) * 10                   # round up to nearest 10 baht
```

The curve playground in `applet/` anchors the taper at `B_old` instead of `B_new` and omits the floor/ceiling logic — it is a teaching prototype for the shape only, not a budget tool.

## Group codes

| GRP_ID | Meaning |
| --- | --- |
| 1 | สายวิชาการ (อุดมศึกษา) — Academic, higher-education |
| 2 | สายวิชาการ (ต่ำกว่าอุดมศึกษา) — Academic, sub-higher-education |
| 3 | สายสนับสนุน (ปฏิบัติการ) — Support, professional |
| 4 | สายสนับสนุน (ปฏิบัติงาน) — Support, operational |
| 0 | ทั้งหมด — All groups (only valid in `budget_grpid.py`) |

## Data

Both budget apps need two parquet files in `budget_analysis/data/`:

- `new_salary_table.parquet` — reference table with columns `POS_ID`, `GRP_ID`, `Min_Old`, `Min_New`, `Max_Old`, `Max_New`, `Type`, `Deg_Pos`.
- `salary_all_posid.parquet` — payroll snapshot with columns `เงินเดือน` (salary), `POS_ID`, `GRP_ID`, `ประเภทบุคลากร` (personnel/funding type, must contain "รัฐบาล" or "รายได้" for the funding-source filter to work).

Numeric columns may arrive as comma-formatted strings; the loader strips commas and coerces them automatically.

The top-level `data/` directory is a symlink to a sibling confidential repository and is git-ignored. The parquet files actually consumed by the apps live inside `budget_analysis/data/`.

## Troubleshooting

- **"ไม่พบไฟล์ข้อมูล"** — the parquet files are missing or you ran the script from the wrong directory. `cd budget_analysis` first.
- **Python version mismatch** — each subdir has its own `.python-version`. Run `uv sync` from inside the subdir; uv will install the right interpreter.
- **Streamlit shows stale numbers after editing data** — clear the cache (sidebar menu → "Clear cache") or restart the server. The loader is wrapped in `@st.cache_data`.
