// H04-0001 capability-probe contract harness.
//
// H04 declares two required checks, `hook_feature_probe_test` and
// `hook_degraded_mode_test`.  Both are authored as the product test suites in
// the manifest write scope tests/compatibility/hooks/ (hook-feature-probe.test.mjs
// with eleven cases and hook-degraded-mode.test.mjs with seven cases).  This
// attempt-directory harness maps those two required checks onto one shared
// `node --test` invocation by side-effect-importing the two product suites, so a
// single `node --test artifacts/work_packages/H04/attempts/0001/
// h04-capability-probe-tests.mjs` runs all eighteen cases against the bounded
// capability-probe module packages/plugin-host/src/capability-probe/
// capability-probe.mjs.  The evidence builder splits the eighteen-case JUnit into
// the two required checks by testcase-name prefix.  The import specifiers inside
// each product suite resolve relative to that suite's own location, so importing
// them here does not change which source module is exercised.

import "../../../../../tests/compatibility/hooks/hook-feature-probe.test.mjs";
import "../../../../../tests/compatibility/hooks/hook-degraded-mode.test.mjs";
