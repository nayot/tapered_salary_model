# Budget Analysis — Burapha University Salary Adjustment Model

Streamlit tools for estimating the budget impact of a tapered salary adjustment applied to BUU personnel. Two independent entry points share the same underlying model but serve different analytical purposes.

## Entry points

| Script | Purpose |
|---|---|
| `budget_posid.py` | Single-position (POS_ID) drill-down. Shows the taper curve, histogram of employee salaries, and per-person adjustment. |
| `budget_grpid.py` | Group-level aggregate. Covers one or all personnel groups, with multi-year budget projection and export to Excel/PDF. |

Run either from inside `budget_analysis/`:

```bash
cd budget_analysis
uv run streamlit run budget_grpid.py
uv run streamlit run budget_posid.py
```

---

## Data

Two Parquet files are required, both read from `data/` relative to `budget_analysis/`:

### `new_salary_table.parquet` — Position salary cylinders (42 rows)

Each row defines one salary cylinder:

| Column | Meaning |
|---|---|
| `POS_ID` | Unique position identifier (1–42) |
| `GRP_ID` | Personnel group (1–4) |
| `Type` | Group label (Thai) |
| `Deg_Pos` | Position + degree label, e.g. `อาจารย์ - ปริญญาเอก` |
| `Min_Old` | Old minimum salary (floor before adjustment) |
| `Max_Old` | Old maximum salary (used to derive flag-cutoff S_max) |
| `Min_New` | New minimum salary (guarantee floor after adjustment) |
| `Max_New` | New maximum salary (hard ceiling — salary never exceeds this) |

### `salary_all_checked_posid.parquet` — Employee payroll

One row per employee. Key columns used by the model:

| Column | Meaning |
|---|---|
| `เงินเดือน` | Current monthly salary |
| `POS_ID` | Links to `new_salary_table` |
| `GRP_ID` | Personnel group |
| `ประเภทบุคลากร` | Funding type (government subsidy / own revenue) |
| `สังกัดคณะ` | Faculty / unit affiliation |
| `วันที่เกษียณอายุ` | Retirement date (used for projection turnover) |

Numeric columns may arrive as comma-formatted strings; both scripts run `clean_num` to strip commas and coerce to float on load.

---

## Personnel groups

| GRP_ID | Thai label | Description |
|---|---|---|
| 1 | สายวิชาการ (ระดับอุดมศึกษา) | Academic — higher education (อาจารย์ through ศาสตราจารย์) |
| 2 | สายวิชาการ (ระดับต่ำกว่าอุดมศึกษา) | Academic — below higher education |
| 3 | สายสนับสนุนวิชาการ (ปฏิบัติการ) | Academic support — professional level |
| 4 | สายสนับสนุนวิชาการ (ปฏิบัติงาน) | Academic support — operational level |

`budget_grpid.py` also accepts `GRP_ID = 0` (all groups combined).

---

## Taper adjustment formula

For an employee with current salary `s` in a cylinder defined by `(Min_Old, Max_Old, Min_New, Max_New)`:

```
δ       = Min_New − Min_Old           # base raise (floor shift)
S_max   = Min_Old + (pct/100) × (Max_Old − Min_Old)   # flag-cutoff

if s < Min_New:
    adj = Min_New − s                 # guarantee: lift to new floor

elif s ≤ S_max:
    ratio = clip(1 − (s − Min_New) / (S_max − Min_New), 0, 1)
    adj   = δ × ratio^γ              # tapered top-up

else:
    adj = 0                           # above flag-cutoff: no adjustment

adj = min(adj, Max_New − s)          # hard ceiling
adj = ceil_to_10(adj)                # round up to nearest 10 baht
```

### Key invariants
- **Below Min_New**: employee is lifted exactly to `Min_New` (full gap, no taper).
- **Between Min_New and S_max**: taper governed by γ. γ=1 → linear decay; γ<1 → concave (generous to mid-range); γ>1 → convex (quickly drops to zero).
- **Above S_max**: zero top-up.
- **New salary ≤ Max_New** always.

---

## Tunable parameters

| Parameter | Slider range | Default | Effect |
|---|---|---|---|
| `s_max_pct` | 0–120% | 100% | Sets S_max as a % of the old salary range. 100% = full old cylinder; >100% extends the taper region beyond the old ceiling. |
| `γ` (gamma) | 0.1–5.0 | 1.0 | Shape of the taper curve. |
| Annual raise % | 0–10% | 4% | Compound raise applied to base salaries each projection year. |
| Projection years | 1–20 | 10 | How many future years to simulate. |

---

## Fund contributions

In addition to direct salary, the model optionally includes employer contributions to four funds (all toggleable):

| Fund | Rate | Ceiling / flat |
|---|---|---|
| ประกันสังคม (Social Security) | 5% default | Monthly SS capped per statutory schedule: ≤2028 → 875 ฿/month; 2029–2031 → 1,000 ฿/month; ≥2032 → 1,150 ฿/month |
| กองทุนสำรองเลี้ยงชีพ (Provident Fund) | 5% default | No cap (% of salary) |
| กองทุนสวัสดิการ (Welfare Fund) | Flat | 10,000 ฿/person/year |
| กองทุนบูรพามั่นคง (BUU Stability Fund) | 0.5% default | No cap |

Rates are adjustable in the sidebar; the SS ceiling schedule is hardcoded from the statutory projection.

---

## Multi-year projection model (`budget_grpid.py`)

The projection starts from the current year and steps forward one year at a time.

### Each year:

1. **Annual raise** — Each employee's base salary grows by `raise_factor = 1 + annual_raise_pct/100`, capped at their position's `Max_New`. Once a salary reaches `Max_New` it is frozen there.

2. **Retirement & replacement** — Employees whose `วันที่เกษียณอายุ` falls in the simulated year are removed. Each is replaced by a new hire entering at `Min_New` of the lowest-`Min_New` position in their group (GRP_ID), filtered by degree:
   - GRP 1 & 2: entry at the PhD-level minimum (`Deg_Pos` contains `เอก`)
   - GRP 3: entry at bachelor level (`Deg_Pos` contains `ตรี`)
   - GRP 4: entry at the group minimum (no degree filter)

3. **Adjustment** — The taper formula is re-applied to existing employees' grown base salaries. Replacement salaries grow each year at the same raise rate but receive no initial taper adjustment.

4. **Fund totals** — SS, PF, WF, BM are computed on actual paid salaries (base + adjustment) for all employees in that year.

### Three projection scenarios

| Scenario | Description | Chart style |
|---|---|---|
| **Lower** | Current `Max_New` ceilings per position | Dotted green |
| **Upper** | GRP 1 ceilings extended to 145,000 (GRP 1 group max); GRP 2 to 117,000 (GRP 2 group max). GRP 3/4 unchanged. | Dotted red with light-red shading between lower and upper |
| **Average** | Midpoint of lower and upper | Solid red |
| **Baseline** | No adjustment applied (`skip_adj=True`); shows what budget would be with raises only and no salary top-up | Solid grey (optional, sidebar toggle) |

The shaded band between lower and upper represents the plausible budget range depending on how far GRP 1/2 employees ultimately progress within their extended cylinders.

---

## Assumptions and limitations

- **Headcount is held constant** — each retiree is replaced 1-for-1 at the entry salary of their group. The model does not simulate hiring freezes, over-hiring, or voluntary attrition.
- **Annual raise is uniform** — all employees receive the same percentage raise regardless of position, seniority, or performance. The raise is applied to the base salary, not the post-adjustment salary.
- **Adjustment is recalculated annually** — the taper formula runs each year on the grown base salary, so employees who receive a top-up in year 0 may receive a smaller or zero top-up in later years as their salary approaches S_max.
- **Fund rates are fixed** — SS, PF, and BM percentages and the welfare flat amount are assumed constant over the projection horizon except for the statutory SS ceiling step-ups.
- **Replacement salaries are not tapered** — new hires enter at `Min_New` and grow purely from annual raises; they do not receive an initial adjustment.
- **`Max_New` is the absolute ceiling** in all scenarios. Even in the upper scenario, the extended group-level ceiling is the maximum; no salary can grow beyond it.
- **Data is a static snapshot** — the model does not account for mid-year promotions, position reclassification, or changes to the salary table.
