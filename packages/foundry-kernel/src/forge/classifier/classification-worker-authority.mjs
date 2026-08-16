const CLASSIFICATION_WORKER_AUTHORITIES = new WeakMap();

const invalidAuthority = (message) => {
  const error = new TypeError(message);
  error.code = "INVALID_DEPENDENCY";
  return error;
};

export const bindClassificationWorkerAuthority = (committer, authority) => {
  if (CLASSIFICATION_WORKER_AUTHORITIES.has(committer)) {
    throw invalidAuthority("classification worker authority is already bound");
  }
  CLASSIFICATION_WORKER_AUTHORITIES.set(committer, Object.freeze({ ...authority }));
};

export const resolveClassificationWorkerAuthority = (committer, expected) => {
  const authority = CLASSIFICATION_WORKER_AUTHORITIES.get(committer);
  if (authority === undefined) {
    throw invalidAuthority(
      "classification must come from createClassificationCommitter()",
    );
  }
  for (const key of ["stateStore", "artifactStore", "ledger", "clock"]) {
    if (authority[key] !== expected[key]) {
      return null;
    }
  }
  return Object.freeze({
    prepareClassification: authority.prepareClassification,
  });
};
