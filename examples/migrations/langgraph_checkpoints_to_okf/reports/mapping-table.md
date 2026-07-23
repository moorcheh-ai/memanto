# Mapping table

| LangGraph source | OKF / Memanto target | Fidelity note |
| --- | --- | --- |
| `memories[].id` | OKF `title`, `x_memanto.id` | Stable source identity is preserved. |
| `memories[].type` | OKF `type`, `x_memanto.type` | Unknown types fall back to `observation`. |
| `memories[].content` | Markdown body | Human-readable portable memory text. |
| `memories[].confidence` | `x_memanto.confidence` | Numeric confidence round-trips. |
| `memories[].tags` | OKF `tags` | Source tags stay filterable. |
| checkpoint ids | OKF `resource` plus provenance footer | Lineage stays auditable. |
| evidence turn | provenance footer | Recall claims point back to source data. |
