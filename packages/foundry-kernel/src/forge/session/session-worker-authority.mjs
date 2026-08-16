const SESSION_WORKER_AUTHORITIES = new WeakMap();

const invalidAuthority = (message) => {
  const error = new TypeError(message);
  error.code = "FORGE_INVALID_DEPENDENCY";
  return error;
};

export const bindDurableForgeSessionWorkerAuthority = (sessionPort, authority) => {
  if (SESSION_WORKER_AUTHORITIES.has(sessionPort)) {
    throw invalidAuthority("session worker authority is already bound");
  }
  SESSION_WORKER_AUTHORITIES.set(sessionPort, Object.freeze({ ...authority }));
};

export const resolveDurableForgeSessionWorkerAuthority = (sessionPort, expected) => {
  const authority = SESSION_WORKER_AUTHORITIES.get(sessionPort);
  if (authority === undefined) {
    throw invalidAuthority(
      "session must come from createDurableForgeSessionPort()",
    );
  }
  for (const key of ["stateStore", "artifactStore", "ledger", "clock"]) {
    if (authority[key] !== expected[key]) {
      return null;
    }
  }
  if (
    Object.hasOwn(expected, "classificationPort") &&
    authority.classificationPort !== expected.classificationPort
  ) {
    return null;
  }
  return Object.freeze({
    inspectOpen: authority.inspectOpen,
    prepareOpen: authority.prepareOpen,
    inspectTransition: authority.inspectTransition,
    prepareTransition: authority.prepareTransition,
  });
};
