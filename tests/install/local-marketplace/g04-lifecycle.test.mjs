import assert from "node:assert/strict";
import test from "node:test";

import { runLocalMarketplaceLifecycle } from "./lifecycle-harness.mjs";

test("fresh_install_test and clean_uninstall_test: isolated local marketplace lifecycle", () => {
  const result = runLocalMarketplaceLifecycle();

  assert.equal(result.final_status, "PASS");
  assert.equal(result.isolation.isolated_user_profile, true);
  assert.equal(result.isolation.personal_marketplace_visible, false);
  assert.equal(result.fresh_install_test.marketplace_add, "PASS");
  assert.equal(result.fresh_install_test.plugin_install, "PASS");
  assert.equal(result.fresh_install_test.installed_cache_copy, "PASS");
  assert.equal(result.fresh_install_test.missing_paths.length, 0);
  assert.equal(result.fresh_install_test.extra_paths.length, 0);
  assert.equal(result.fresh_install_test.hash_mismatches.length, 0);
  assert.equal(result.fresh_install_test.disable_state_observed, true);
  assert.equal(result.fresh_install_test.reenable_state_observed, true);
  assert.equal(result.fresh_install_test.marketplace_source_detached, true);
  assert.equal(result.fresh_install_test.installed_cache_survived_source_detachment, true);
  assert.equal(result.fresh_install_test.installed_plugin_listed_after_source_detachment, true);

  assert.equal(result.path_less_boundary.invocation_used_absolute_installed_dispatcher, true);
  assert.equal(result.path_less_boundary.path_environment_empty, true);
  assert.equal(result.path_less_boundary.repository_checkout_fallback_count, 0);
  assert.equal(result.path_less_boundary.command_success_claimed, false);

  assert.equal(result.clean_uninstall_test.plugin_remove, "PASS");
  assert.equal(result.clean_uninstall_test.installed_cache_residue_count, 0);
  assert.equal(result.clean_uninstall_test.installed_config_residue_count, 0);
  assert.equal(result.clean_uninstall_test.marketplace_remove, "PASS");
  assert.equal(result.clean_uninstall_test.marketplace_config_residue_count, 0);
  assert.equal(result.commands.every((command) => command.semantic_result === "PASS"), true);
  assert.equal(result.commands.some((command) => "stdout" in command), false);
  assert.equal(result.commands.some((command) => "stderr" in command), false);
});
