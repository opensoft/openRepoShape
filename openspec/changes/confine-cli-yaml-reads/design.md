## Context

Explicit YAML arguments may be supplied by an agent. The original two taint paths reach load_yaml without confinement. Internal callers also deliberately read published plans and pins outside a cwd; changing their generic parser would conflate trust boundaries.

## Goals / Non-Goals

Constrain explicit project/policy inputs at the CLI boundary while retaining internal readers and compiled-in defaults. No new read-root bypass, suppression or permission expansion is introduced.

## Decisions

Resolve the path and invocation cwd canonically, then require equality or separator-delimited descent before returning the validated absolute path. Reject outside absolute paths, traversal, prefix siblings and symlink escapes. Validate before opening or decoding. Name refusals through shown_path and preserve exit 2.
For external projects, invoke from the project directory (or a deliberately chosen encompassing workspace). This narrows explicit file selection and is documented as security behavior; it does not change manifest or naming rules.

## Risks / Trade-offs

Existing invocations that select outside YAML must choose their working directory explicitly. Regression tests for valid external temp projects must launch from that workspace; outside-path refusal tests always set cwd explicitly. Races remain subject to normal filesystem ownership, but symlinks are resolved before validation.

## Migration Plan

Land upstream with tests and publish via ordinary shape update; never patch a consumer copy or manually change its digest. Preserve history and unchanged validation rules.

## Open Questions

None for implementation. Exact consuming provenance and acceptance are recorded by wallet #73.
