# `lanes/log/` — the per-lane object logs (lane-collision-protocol Amendment 7)

One append-only file per lane, `<lane>.md`, written only by `lanes-edit.sh`
(`opensoft/openRepoTools`) — its `log`, `claim` and `release` subcommands;
`who` reads them. The grammar, the verbs and the row format are in
`../README-lanes.md`.
