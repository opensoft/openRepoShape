## ADDED Requirements

### Requirement: Explicit CLI YAML confinement
Explicit project and policy YAML arguments SHALL resolve within the canonical invocation directory before any file read. An outside path SHALL refuse with exit 2 and a safely rendered path. Compiled-in defaults and internal known-path reads retain their existing contracts.

#### Scenario: Escaping input
- **WHEN** an explicit argument resolves outside cwd through an absolute path, traversal, a prefix sibling or a symlink
- **THEN** the CLI SHALL refuse before opening the target.

#### Scenario: Valid local input
- **WHEN** an explicit path resolves to a file beneath cwd
- **THEN** the existing YAML parser and validation SHALL run unchanged.
