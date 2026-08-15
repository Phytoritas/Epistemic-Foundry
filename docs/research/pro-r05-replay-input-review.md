# R05 replay and typed-citation input review

Act as an independent, read-only reviewer for two small R05-local corrections.
Return only material blockers, or `NO_BLOCKER` with one short rationale.

R05 authority says operator application is replayable when the caller supplies
the child ID, `new_id` runs only when the caller declines to name the child,
and an Aporia-grounded operator must cite identifiers of questions actually
left open by a canonical ArgumentGraph.

Observed behaviors and repairs:

1. Both mutation and crossover used
   `child_genome_id or new_id(prefix)`. An explicitly supplied empty string was
   silently replaced with a random ID, contradicting the documented replay
   rule. Both paths now call:

   ```python
   def _resolve_child_id(value, *, id_prefix):
       if value is None:
           return new_id(id_prefix)
       return _require_text(value, "child_genome_id")
   ```

   Thus only absence (`None`) mints; invalid supplied values fail closed.

2. `require_aporia_citation` previously used `{str(item) for item in cited}`.
   A non-string item such as integer `1` could match a canonical open-question
   ID `"1"`. It now derives
   `{_require_text(item, "open_question_id") for item in cited}`, compares that
   typed set to `open_questions(graph)`, and returns the sorted typed IDs.

No shared schema, manifest, workflow, artifact, operator vocabulary, or output
shape changed. Review whether these corrections preserve valid callers and
match R05 replay and Aporia-binding authority, and name any material blocker.
