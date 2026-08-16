# Quality Policies

The files in this directory are the versioned decision contracts for the
control plane.

- `visual-baselines.json` defines responsive profiles, states, renderer
  identity, and pixel-comparison tolerances.
- `accessibility.json` defines the evaluated WCAG tags, responsive matrix, and
  blocking versus advisory impacts.
- `accessibility-exceptions.json` records narrowly scoped, owned, justified,
  and time-bounded exceptions. It intentionally starts empty.

A policy change is a quality-contract change. Review it together with its test
evidence and, when applicable, a newly proposed visual baseline set.
