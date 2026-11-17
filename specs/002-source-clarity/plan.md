# Plan

Base: published main 833f75564c6ed4b622c3d504f66a84ccdf2537c8, tree-equivalent to the consumer's pinned source 0be1f3b8ff48b4c063a40b1adfc2859a8cb169a9. All four source files were verified byte-identical to the selected openWallet consumer before editing.

Extract the unquoted scalar's next-state calculation and unavailable-chain warning formatting into private helpers. Preserve exact public outputs and referent-property behavior. Name the status tuple descriptively, factor repeated literals into constants, and make the nine existing implicit no-op case defaults explicit.

Validation: calibrated Sonar local analysis reproduces both complexity-21 findings and the naming collision on the before library, then returns zero findings on the candidate library. Differential probes retain 82,742 quote/flow results, 432 chain-warning results and five referent-state observations. Constant-expanded ASTs for both templates are identical. These are focused evidence, not full source acceptance.

Run the complete existing provider suite and workflow lint, obtain exact-head independent review and unchanged required CI, then land normally. Check consumer per-file verdicts before the standard update; preserve unrelated bytes and artifact/release identities. The parent assembly must consume the published provider, retain all existing conformance assertions, and verify actual main and original keys.
