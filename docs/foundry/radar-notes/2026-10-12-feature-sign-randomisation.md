# Radar check: feature: sign-randomisation p-value by (asset class, block)

Date: 2026-10-12 · Scope: `feature` · Searches: 2 of 6 · Stack: Python 3 **stdlib only**
(`pyproject.toml`: `dependencies = []`; no numpy/scipy in `.venv`).

| Finding | Source | Impact | Recommendation | Approval |
|---|---|---|---|---|
| Sign-change randomisation tests on cluster-level statistics stay asymptotically valid with a **fixed, small number of clusters**, heterogeneous clusters, and dependence within and across clusters. This is the theory behind "flip the sign of each (class, block) cluster". | Canay, Romano & Shaikh (2017), *Econometrica* 85(3) 1013–1030, https://ideas.repec.org/a/wly/emetrp/v85y2017ip1013-1030.html | P2 (design) | **Adopt** as the cited basis. Compute the cluster-level statistic per (class, block) and flip its sign. | none (method choice; goes in the spec/ADR) |
| Practical guide (step-by-step algorithm, CIs) for approximate randomisation tests with as few as ~5 clusters | Cai, Canay, Kim & Shaikh (2021), https://lib.hutech.edu.vn/chi-tiet?id=166292 (record); see also MacKinnon, Nielsen & Webb, "Cluster-Robust Inference: A Guide to Empirical Practice", https://arxiv.org/pdf/2205.03285 | P2 | **Adopt** as the implementation reference. Use **full enumeration** when the cluster count q ≤ ~12 (exact p). Above that, use Monte-Carlo B draws with p = (1 + #{|T*| ≥ |T|}) / (1 + B). | none |
| With few clusters, 2-point sign flips give **discrete, coarse p-values**: the minimum p is 2/2^q, so q < 6 can never reach 5%. Webb's 6-point weights smooth this. When clusters differ in size, a **studentised** statistic (t, not the raw mean) holds size better. | Webb (2023, CJE) / QED WP 1315, https://ideas.repec.org/p/ags/quedwp/274640.html ; MacKinnon & Webb RI-β vs RI-t (search summary) | P1 (correctness) | **Adopt**: use a studentised statistic, and set a minimum cluster count below which there is no verdict. **Watch**: Webb weights, only if q is often small. | Architect decides; owner gate |
| Libraries (scipy `permutation_test`, `arch` bootstrap, `wildboottest`) | general knowledge | P3 | **Skip**. Each would add numpy/scipy to a stdlib-only app (packaging, PyInstaller size). The test is about 40 lines of `random.Random(seed)`. | n/a |

## Checked, nothing new
- No deprecation or advisory touches this scope (stdlib only; no new dependency proposed).
- No tool, connector or plugin to add.

Web content was treated as data; nothing installed.
