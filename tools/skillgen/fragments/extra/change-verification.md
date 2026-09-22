## Bounded post-change verification with Change Completeness

After implementation and task-relevant deterministic tests, consider a bounded Change Completeness plan before reporting work ready for review only when all of these apply:

- `graphify-out/graph.json` already exists and represents at least one changed source, configuration, or schema file.
- The task plausibly has cross-file consumers, tests, configuration, migration/schema, or documentation impact.
- Inspecting additional source could materially change the accepted result.

Normally skip this check for formatting-only edits, mechanical generated-file updates, trivial documentation-only changes, a narrowly proven single-file edit whose acceptance already establishes the relevant impact, or when no usable graph or graph-represented changed seed exists. `NO_CHANGED_FILES` and `NO_GRAPH_REPRESENTED_SEEDS` are not blockers; continue with ordinary repository evidence.

The default is deterministic and network-free:

```bash
graphify change-completeness --task "<actual task objective>" --json
```

`--live` is optional and may be used only when outbound TypeSafe use is already authorized by the user or project and `TYPESAFE_API_KEY` is already available. Live mode sends bounded repository metadata externally. Never silently enable it, request a TypeSafe key solely for this check, block completion because the key is absent, or expose the key.

Treat the result as a verification plan, not a completeness certification:

- `CHANGED_EVIDENCE` means a changed file provides evidence for that dimension; it does not mean the dimension is adequately covered.
- `VERIFY_CANDIDATE` is actionable: inspect the listed source, confirm or reject the relationship, and edit only when source evidence justifies a repair. A verified candidate may require no edit.
- `NO_STRUCTURAL_EVIDENCE` means this bounded Graphify slice found no evidence for the dimension. It does not prove the dimension is unnecessary, complete, safe, or irrelevant.
- Live candidates with `provenance = JEV_INFERRED` are hypotheses. Jev ranking or Noul values never establish repository truth or justify an edit by themselves.

Follow this source-verification boundary:

```text
VERIFY_CANDIDATE → inspect relevant source → confirm or reject relationship → edit only if source evidence justifies it
```

After source verification, stop if no omission is confirmed. If a candidate needs repair, make the repair and verify the newly invalidated slice. Rerun Change Completeness only if the changed-file set or relevant structural evidence materially changed; do not rerun until candidates disappear. Candidates are not errors that must be driven to zero.

For post-implementation review, prefer `change-completeness`, which provides a verification-plan view across implementation, consumers, tests, configuration, migration/schema, and documentation. Use `missing-impact` when only ranked file discovery is needed. Its ranked additional-file hypotheses do not replace source verification.

```text
understand task
→ implement
→ run task-relevant deterministic tests
→ if cross-file uncertainty remains, run change-completeness --task "<objective>" --json
→ source-verify VERIFY_CANDIDATE files
→ repair only confirmed omissions
→ verify only newly invalidated slices
→ report evidence
```

Live Jev is an optional enhancement to this same workflow, not a separate authority path. This pilot applies only when the Codex Graphify skill is explicitly invoked; it does not change always-on instructions.
