This is the **spec leg** of {{PROJECT_NAME}} (`{{PROJECT_ID}}`): requirements, decisions
and acceptance criteria.

**The project's rules are not here.** They are in the assembly root
`{{ASSEMBLY_REPOSITORY}}`, in `AGENTS-shape.md` — read that before touching anything
that spans the legs. This leg is mounted there at `{{SPEC_PATH}}/`, and the other leg,
`{{CODE_REPOSITORY}}`, beside it at `../{{CODE_PATH}}/`, once the root is cloned with
`--recurse-submodules`.

Working here is ordinary — an ordinary repository on an ordinary branch. What
advancing this leg does NOT do is advance the project: that is ONE commit in
`{{ASSEMBLY_REPOSITORY}}` moving the gitlink, `contracts/spec-pin.yaml` and every
workflow `@<sha>` for this leg together.

Being the spec leg confers no authority over specifications. The split is
navigation.
