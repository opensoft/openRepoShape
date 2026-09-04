Read AGENTS-shape.md first — the rules of this repository's shape.

This is the assembly root of **{{PROJECT_NAME}}** (`{{PROJECT_ID}}`): the repository an
engineer clones. It holds `project.yaml`, the pins and the gate, and it mounts
the two legs.

| role | repository | path |
|---|---|---|
| assembly | `{{ASSEMBLY_REPOSITORY}}` | `.` |
| spec | `{{SPEC_REPOSITORY}}` | `{{SPEC_PATH}}/` |
| code | `{{CODE_REPOSITORY}}` | `{{CODE_PATH}}/` |

Everything below this line is {{PROJECT_NAME}}'s own. The shape wrote the block above
once and does not pin this file, so how this project is built, tested, reviewed
and released belongs here and nothing upstream will overwrite it.
