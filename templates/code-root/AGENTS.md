This is the **code leg** of {{PROJECT_NAME}} (`{{PROJECT_ID}}`): the implementation
and its tests.

**The project's rules are not here.** They are in the assembly root
`{{ASSEMBLY_REPOSITORY}}`, in `AGENTS-shape.md` — read that before touching anything
that spans the legs. This leg is mounted there at `{{CODE_PATH}}/`, and the other leg,
`{{SPEC_REPOSITORY}}`, beside it at `../{{SPEC_PATH}}/`, once the root is cloned with
`--recurse-submodules`.

Working here is ordinary — an ordinary repository on an ordinary branch. What
advancing this leg does NOT do is advance the project: that is ONE commit in
`{{ASSEMBLY_REPOSITORY}}` moving the gitlink, `contracts/code-pin.yaml` and every
workflow `@<sha>` for this leg together.

Being the code leg confers no authority over the implementation. The split is
navigation.
