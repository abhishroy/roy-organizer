# Safety model

ROY defaults to `planning_only=true`. Scanning is read-only. Protected paths,
projects, developer configuration, company tooling, work data, kubeconfigs, and
open files are excluded. Validation fails closed on unknown open state, changed or
missing sources, collisions, protected destinations, symlinks outside the sandbox,
and unapproved operations. Early Preview execution accepts only roots resolving
under `/tmp`.
