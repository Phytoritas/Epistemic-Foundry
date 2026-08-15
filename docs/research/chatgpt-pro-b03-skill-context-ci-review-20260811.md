DECISION: CHANGES_REQUIRED

BLOCKER: `ci_matrix_lint.py` tests each required command only as a substring of concatenated `run` text; `run: echo "uv run --locked --group skill-context pytest tests -p no:cacheprovider"` therefore passes validation without executing pytest.

MINIMUM_REPAIR: Compare every required command by exact equality against stripped, non-empty lines from the workflow's `run` scalars instead of using substring membership.

RATIONALE: The final `uv run --locked --group skill-context pytest ...` is semantically sound: that invocation updates the project environment from the locked resolution while explicitly including `skill-context`, and `uv run` uses an inexact sync by default, so the intervening ungrouped `uv run` commands do not cancel or remove the group. The blocker is confined to B03-local enforcement.
