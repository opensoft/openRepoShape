## Why

Sonar pythonsecurity:S8707 follows explicit CLI project and policy arguments to unrestricted YAML reads in neutral wallet's pinned shape tooling. Agent-invoked inputs must not escape the invocation directory through traversal or symlinks.

## What Changes

- Canonicalize explicit project/policy paths and refuse paths outside the invocation directory before reading them.
- Preserve compiled-in default policy paths and internal manifest/pin readers.
- Document that operators select an external project by invoking from its directory.
- Exercise traversal, absolute outside paths, prefix siblings and symlink escapes.

## Capabilities

### New Capabilities
- cli-yaml-read-boundary: Invocation-directory confinement for explicit project/policy YAML arguments.

### Modified Capabilities
None.

## Impact

Naming CLI and assembly manifest CLI, shared boundary helper and regression tests. Authorized by Brett Heap's openXwallet #73 repair instruction on 2026-11-16. Existing identifiers, validation rules and refusal codes remain intact;
accepted explicit paths are canonicalized before diagnostics; only explicit outside-directory reads are refused. Speckit feature 001 owns implementation tasks.
