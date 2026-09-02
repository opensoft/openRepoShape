# {{PROJECT}}-code

The **code leg** of the `{{PROJECT_ID}}` project: the implementation and its
tests. The requirements it implements live in
[`{{SPEC_REPOSITORY}}`](https://github.com/{{SPEC_REPOSITORY}}).

**Clone the assembly root, not this repository.** This leg is mounted as a
submodule at `{{CODE_PATH}}/` inside
[`{{ASSEMBLY_REPOSITORY}}`](https://github.com/{{ASSEMBLY_REPOSITORY}}), which
is what pins the commit of this repository that the project currently is:

```sh
git clone --recurse-submodules {{ASSEMBLY_CLONE_URL}}
cd {{PROJECT}}
make bootstrap
```

Working here directly is fine — it is an ordinary repository with an ordinary
branch. What advancing this leg does NOT do is advance the project: that is a
commit in the assembly root moving the gitlink, `contracts/code-pin.yaml` and
any workflow `@<sha>` reference together.

Being the code leg confers no authority over the implementation. The split is
navigation; authority travels in grants, and a project that keeps spec and
code in one repository is reviewed identically.

Topic: `{{TOPIC}}`.
