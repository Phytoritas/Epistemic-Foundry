import { types as utilTypes } from "node:util";

import {
  createWorkClassificationRuntimeRequest,
} from "../classifier/work-classification-worker.mjs";
import { createSessionOpenRuntimeRequest } from "./session-open-worker.mjs";
import { createSessionTransitionRuntimeRequest } from "./session-transition-worker.mjs";

const OBJECT_FREEZE = Object.freeze;

const ROUTES = OBJECT_FREEZE({
  "foundry.work.classify": OBJECT_FREEZE({
    worker: "classificationWorker",
    requestFactory: createWorkClassificationRuntimeRequest,
  }),
  "foundry.session.open": OBJECT_FREEZE({
    worker: "openWorker",
    requestFactory: createSessionOpenRuntimeRequest,
  }),
  "foundry.session.transition": OBJECT_FREEZE({
    worker: "transitionWorker",
    requestFactory: createSessionTransitionRuntimeRequest,
  }),
});

const CONTEXT_KEYS = new Set([
  "auth",
  "validatedArguments",
  "requestId",
  "generatedAt",
]);

export class InstalledForgeMutationDispatchError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "InstalledForgeMutationDispatchError";
    this.code = code;
  }
}

const fail = (code, message) => {
  throw new InstalledForgeMutationDispatchError(code, message);
};

const requirePlainRecord = (candidate, label) => {
  if (
    candidate === null ||
    typeof candidate !== "object" ||
    Array.isArray(candidate) ||
    utilTypes.isProxy(candidate)
  ) {
    fail("INSTALLED_FORGE_MUTATION_INPUT_INVALID", `${label} must be a plain object`);
  }
  const prototype = Object.getPrototypeOf(candidate);
  if (prototype !== Object.prototype && prototype !== null) {
    fail("INSTALLED_FORGE_MUTATION_INPUT_INVALID", `${label} must be a plain object`);
  }
  return candidate;
};

const requireContext = (candidate) => {
  const context = requirePlainRecord(candidate, "mutation dispatch context");
  const keys = Reflect.ownKeys(context);
  if (
    keys.length !== CONTEXT_KEYS.size ||
    keys.some((key) => typeof key !== "string" || !CONTEXT_KEYS.has(key))
  ) {
    fail(
      "INSTALLED_FORGE_MUTATION_INPUT_INVALID",
      "mutation dispatch context fields are not canonical",
    );
  }
  return context;
};

const requireWorker = (runtime, route) => {
  const worker = runtime[route.worker];
  if (worker === null || worker === undefined) {
    fail(
      "INSTALLED_FORGE_MUTATION_UNAVAILABLE",
      `${route.worker} is unavailable in the installed Forge runtime`,
    );
  }
  if (
    worker === null ||
    typeof worker !== "object" ||
    Array.isArray(worker) ||
    utilTypes.isProxy(worker) ||
    typeof worker.execute !== "function"
  ) {
    fail(
      "INSTALLED_FORGE_MUTATION_RUNTIME_INVALID",
      `${route.worker} does not expose the canonical execute port`,
    );
  }
  return worker;
};

export function installedForgeMutationToolNames() {
  return Object.keys(ROUTES);
}

export function createInstalledForgeMutationDispatch(runtimeCandidate) {
  const runtime = requirePlainRecord(runtimeCandidate, "installed Forge runtime");

  return OBJECT_FREEZE({
    execute(toolName, contextCandidate) {
      if (typeof toolName !== "string") {
        fail("INSTALLED_FORGE_MUTATION_INPUT_INVALID", "toolName must be a string");
      }
      const route = ROUTES[toolName];
      if (route === undefined) {
        fail(
          "INSTALLED_FORGE_MUTATION_UNAVAILABLE",
          "the installed Forge runtime does not back this mutation tool",
        );
      }
      const context = requireContext(contextCandidate);
      const worker = requireWorker(runtime, route);
      const request = route.requestFactory({
        auth: context.auth,
        validatedArguments: context.validatedArguments,
        requestId: context.requestId,
        generatedAt: context.generatedAt,
      });
      const result = worker.execute(request);
      if (
        result !== null &&
        ["object", "function"].includes(typeof result) &&
        "then" in result
      ) {
        fail(
          "INSTALLED_FORGE_MUTATION_RUNTIME_INVALID",
          "installed Forge mutation workers must be synchronous",
        );
      }
      return result;
    },
  });
}
