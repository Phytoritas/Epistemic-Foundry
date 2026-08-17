import { types as utilTypes } from "node:util";

import {
  createWorkClassificationRuntimeRequest,
} from "../classifier/work-classification-worker.mjs";
import { createSessionOpenRuntimeRequest } from "./session-open-worker.mjs";
import { createSessionTransitionRuntimeRequest } from "./session-transition-worker.mjs";

const OBJECT_FREEZE = Object.freeze;
const ROUTE_NAME_KEYS = new Set([
  "classificationToolName",
  "openToolName",
  "transitionToolName",
]);
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

const requireExactKeys = (candidate, keys, label) => {
  const record = requirePlainRecord(candidate, label);
  const observed = Reflect.ownKeys(record);
  if (
    observed.length !== keys.size ||
    observed.some((key) => typeof key !== "string" || !keys.has(key))
  ) {
    fail(
      "INSTALLED_FORGE_MUTATION_INPUT_INVALID",
      `${label} fields are not canonical`,
    );
  }
  return record;
};

const normalizeRouteNames = (candidate) => {
  const names = requireExactKeys(candidate, ROUTE_NAME_KEYS, "Forge mutation route names");
  const values = {};
  for (const key of ROUTE_NAME_KEYS) {
    const value = names[key];
    if (typeof value !== "string" || value.length === 0) {
      fail(
        "INSTALLED_FORGE_MUTATION_INPUT_INVALID",
        "Forge mutation route names must be non-empty strings",
      );
    }
    values[key] = value;
  }
  if (new Set(Object.values(values)).size !== ROUTE_NAME_KEYS.size) {
    fail(
      "INSTALLED_FORGE_MUTATION_INPUT_INVALID",
      "Forge mutation route names must be unique",
    );
  }
  return OBJECT_FREEZE(values);
};

const routesFor = (routeNames) => OBJECT_FREEZE(Object.assign(Object.create(null), {
  [routeNames.classificationToolName]: OBJECT_FREEZE({
    worker: "classificationWorker",
    requestFactory: createWorkClassificationRuntimeRequest,
  }),
  [routeNames.openToolName]: OBJECT_FREEZE({
    worker: "openWorker",
    requestFactory: createSessionOpenRuntimeRequest,
  }),
  [routeNames.transitionToolName]: OBJECT_FREEZE({
    worker: "transitionWorker",
    requestFactory: createSessionTransitionRuntimeRequest,
  }),
}));

const requireContext = (candidate) =>
  requireExactKeys(candidate, CONTEXT_KEYS, "mutation dispatch context");

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

export function installedForgeMutationToolNames(routeNamesCandidate) {
  return Object.keys(routesFor(normalizeRouteNames(routeNamesCandidate)));
}

export function createInstalledForgeMutationDispatch(
  runtimeCandidate,
  routeNamesCandidate,
) {
  const runtime = requirePlainRecord(runtimeCandidate, "installed Forge runtime");
  const routes = routesFor(normalizeRouteNames(routeNamesCandidate));

  return OBJECT_FREEZE({
    execute(toolName, contextCandidate) {
      if (typeof toolName !== "string") {
        fail("INSTALLED_FORGE_MUTATION_INPUT_INVALID", "toolName must be a string");
      }
      const route = routes[toolName];
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
      if (request.tool_name !== toolName) {
        fail(
          "INSTALLED_FORGE_MUTATION_BINDING_INVALID",
          "the catalog-derived route name does not match its canonical worker request",
        );
      }
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
