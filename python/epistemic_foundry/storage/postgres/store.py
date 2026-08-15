"""Tenant-scoped PostgreSQL implementation of the D01 revision primitive.

The store owns no driver dependency. A caller supplies a factory returning a
new dedicated synchronous PostgreSQL DB-API connection. The connection is put
in autocommit mode so every operation can establish an explicit transaction,
bind tenant/workspace settings with ``set_config(..., true)``, and leave no
session-scoped tenant state behind.
"""

from __future__ import annotations

import inspect
import json
import math
import types
from collections.abc import Callable, Mapping
from threading import RLock, get_ident
from typing import Any, Protocol, TypeVar


SCHEMA_VERSION = 1
MAX_REVISION = 9_007_199_254_740_991
CONTRACT_ID = "epistemic-foundry-postgres-team-store/v1"
IDENTIFIER_ENCODING = "utf16be-lowerhex-v1"
_IDENTIFIER_PREFIX = "u16be:"
_LOWER_HEX_DIGITS = frozenset("0123456789abcdef")

_EXPECTED_SCOPE_FUNCTION_DEFINITION = """
CREATE OR REPLACE FUNCTION epistemic_foundry.scope_is_authorized(
    requested_tenant text,
    requested_workspace text
)
RETURNS boolean
LANGUAGE sql
STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog'
AS $function$
    SELECT EXISTS (
        SELECT 1
          FROM epistemic_foundry.principal_scopes AS scope
         WHERE scope.principal_name = session_user::name
           AND scope.tenant_id = requested_tenant
           AND scope.workspace_id = requested_workspace
    )
$function$
"""

_EXPECTED_WRITER_LOCK_FUNCTION_DEFINITION = """
CREATE OR REPLACE FUNCTION epistemic_foundry.acquire_writer_lock(
    requested_tenant text,
    requested_workspace text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog'
AS $function$
BEGIN
    IF NULLIF(
        current_setting('epistemic_foundry.tenant_id', true),
        ''
    ) IS DISTINCT FROM requested_tenant
       OR NULLIF(
           current_setting('epistemic_foundry.workspace_id', true),
           ''
       ) IS DISTINCT FROM requested_workspace
       OR NOT epistemic_foundry.scope_is_authorized(
           requested_tenant,
           requested_workspace
       ) THEN
        RAISE EXCEPTION 'writer lock scope is not authorized'
            USING ERRCODE = '42501';
    END IF;

    LOCK TABLE epistemic_foundry.revisioned_records
        IN SHARE ROW EXCLUSIVE MODE;
    RETURN true;
END
$function$
"""

_EXPECTED_CREATE_FUNCTION_DEFINITION = """
CREATE OR REPLACE FUNCTION epistemic_foundry.create_revisioned_record(
    requested_tenant text,
    requested_workspace text,
    requested_record_type text,
    requested_record_id text,
    requested_value_json json
)
RETURNS TABLE(
    record_type text,
    record_id text,
    revision bigint,
    value_json json,
    created boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog'
AS $function$
BEGIN
    LOCK TABLE epistemic_foundry.revisioned_records
        IN SHARE ROW EXCLUSIVE MODE;

    IF EXISTS (
        SELECT 1
          FROM epistemic_foundry.revisioned_records AS target
         WHERE target.tenant_id = requested_tenant
           AND target.workspace_id = requested_workspace
           AND target.record_type = requested_record_type
           AND target.record_id = requested_record_id
    ) THEN
        RETURN QUERY
        SELECT target.record_type,
               target.record_id,
               target.revision,
               target.value_json,
               false
          FROM epistemic_foundry.revisioned_records AS target
         WHERE target.tenant_id = requested_tenant
           AND target.workspace_id = requested_workspace
           AND target.record_type = requested_record_type
           AND target.record_id = requested_record_id;
        RETURN;
    END IF;

    RETURN QUERY
    INSERT INTO epistemic_foundry.revisioned_records AS target
        (tenant_id, workspace_id, record_type, record_id, revision, value_json)
    VALUES (
        requested_tenant,
        requested_workspace,
        requested_record_type,
        requested_record_id,
        0,
        requested_value_json
    )
    RETURNING target.record_type,
              target.record_id,
              target.revision,
              target.value_json,
              true;
END
$function$
"""

_EXPECTED_CAS_FUNCTION_DEFINITION = """
CREATE OR REPLACE FUNCTION epistemic_foundry.compare_and_swap_revision(
    requested_tenant text,
    requested_workspace text,
    requested_record_type text,
    requested_record_id text,
    requested_expected_revision bigint,
    requested_value_json json
)
RETURNS TABLE(record_type text, record_id text, revision bigint, value_json json)
LANGUAGE sql
SECURITY DEFINER
SET search_path TO 'pg_catalog'
AS $function$
    UPDATE epistemic_foundry.revisioned_records AS target
       SET revision = target.revision + 1,
           value_json = requested_value_json
     WHERE target.tenant_id = NULLIF(requested_tenant, '')
       AND target.workspace_id = NULLIF(requested_workspace, '')
       AND target.record_type = requested_record_type
       AND target.record_id = requested_record_id
       AND target.revision = requested_expected_revision
       AND target.revision < 9007199254740991
    RETURNING target.record_type, target.record_id, target.revision, target.value_json
$function$
"""


class _Cursor(Protocol):
    rowcount: int

    def execute(self, query: str, params: object = ...) -> Any: ...

    def fetchone(self) -> object: ...

    def fetchall(self) -> list[object]: ...

    def close(self) -> None: ...


class _Connection(Protocol):
    autocommit: bool
    closed: bool

    def cursor(self) -> _Cursor: ...

    def close(self) -> None: ...


class _StoreMode:
    ACTIVE = "ACTIVE"
    SAFE_MODE = "SAFE_MODE"


POSTGRES_STORE_MODE = _StoreMode()


class PostgresStateStoreError(RuntimeError):
    """Typed failure from the PostgreSQL state boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details) if details is not None else None


def _fail(
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> None:
    raise PostgresStateStoreError(code, message, details)


def _require_nonempty_string(value: object, label: str) -> str:
    if type(value) is not str or not value or "\x00" in value:
        _fail("INVALID_INPUT", f"{label} must be a non-empty NUL-free string")
    return value


def _require_record_identifier(value: object, label: str) -> str:
    if type(value) is not str or not value:
        _fail("INVALID_INPUT", f"{label} must be a non-empty string")
    return value


def _encode_identifier(value: str) -> str:
    """Encode JavaScript-string UTF-16 code units as canonical PostgreSQL text."""

    return _IDENTIFIER_PREFIX + value.encode("utf-16-be", errors="surrogatepass").hex()


def _decode_identifier(value: object, label: str) -> str:
    if type(value) is not str or not value.startswith(_IDENTIFIER_PREFIX):
        _fail(
            "POSTGRES_PERSISTED_IDENTIFIER_INVALID",
            f"persisted {label} does not use the canonical identifier encoding",
        )
    encoded = value[len(_IDENTIFIER_PREFIX) :]
    if (
        not encoded
        or len(encoded) % 4 != 0
        or any(character not in _LOWER_HEX_DIGITS for character in encoded)
    ):
        _fail(
            "POSTGRES_PERSISTED_IDENTIFIER_INVALID",
            f"persisted {label} does not use the canonical identifier encoding",
        )
    try:
        decoded = bytes.fromhex(encoded).decode("utf-16-be", errors="surrogatepass")
    except (UnicodeDecodeError, ValueError) as error:
        raise PostgresStateStoreError(
            "POSTGRES_PERSISTED_IDENTIFIER_INVALID",
            f"persisted {label} cannot be decoded",
        ) from error
    if not decoded or _encode_identifier(decoded) != value:
        _fail(
            "POSTGRES_PERSISTED_IDENTIFIER_INVALID",
            f"persisted {label} is not canonically encoded",
        )
    return decoded


def _parse_json_integer(token: str) -> int:
    if token == "-0":
        _fail("INVALID_RECORD_VALUE", "persisted value contains a negative-zero number")
    return int(token)


def _require_revision(value: object, label: str = "revision") -> int:
    if type(value) is not int or value < 0 or value > MAX_REVISION:
        _fail(
            "INVALID_REVISION",
            f"{label} must be an integer between 0 and {MAX_REVISION}",
        )
    return value


def _validate_json_value(
    value: object,
    path: str = "value",
    ancestors: set[int] | None = None,
) -> None:
    if value is None or type(value) in (str, bool):
        return
    if type(value) is int:
        try:
            number = float(value)
        except OverflowError:
            number = math.inf
        if not math.isfinite(number) or int(number) != value:
            _fail(
                "INVALID_RECORD_VALUE",
                f"{path} contains an integer that is not exactly representable as an IEEE-754 number",
            )
        return
    if type(value) is float:
        if not math.isfinite(value) or (value == 0.0 and math.copysign(1.0, value) < 0):
            _fail("INVALID_RECORD_VALUE", f"{path} contains a non-finite or negative-zero number")
        return
    if type(value) not in (dict, list):
        _fail("INVALID_RECORD_VALUE", f"{path} contains a non-JSON value")

    if ancestors is None:
        ancestors = set()
    identity = id(value)
    if identity in ancestors:
        _fail("INVALID_RECORD_VALUE", f"{path} contains a cyclic reference")
    ancestors.add(identity)
    try:
        if type(value) is list:
            for index, item in enumerate(value):
                _validate_json_value(item, f"{path}[{index}]", ancestors)
            return
        for key, item in value.items():
            if type(key) is not str:
                _fail("INVALID_RECORD_VALUE", f"{path} contains a non-string key")
            _validate_json_value(item, f"{path}.{key}", ancestors)
    finally:
        ancestors.remove(identity)


def _encode_json(value: object) -> str:
    _validate_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def _sqlstate(error: BaseException) -> str | None:
    value = getattr(error, "sqlstate", None)
    return value if type(value) is str else None


_SQL_OPERATOR_CHARACTERS = frozenset("+-*/<>=~!@#%^&|`?")


def _normalize_sql(
    value: object,
    *,
    _normalize_dollar_body: bool = True,
) -> str:
    """Canonicalize catalog-rendered SQL without changing quoted values.

    PostgreSQL changes insignificant layout when it renders catalog objects,
    so the fingerprint compares lexical tokens rather than source bytes.
    Quoted identifiers and string-literal contents remain byte-sensitive.  A
    function's outer dollar-quoted body is SQL source and is tokenized once;
    nested dollar-quoted values inside that body remain literal data.
    """

    text = str(value)
    tokens: list[str] = []
    index = 0
    length = len(text)

    while index < length:
        character = text[index]
        if character.isspace():
            index += 1
            continue

        if character in {"'", '"'}:
            quote = character
            end = index + 1
            while end < length:
                if text[end] != quote:
                    end += 1
                    continue
                if end + 1 < length and text[end + 1] == quote:
                    end += 2
                    continue
                end += 1
                break
            tokens.append(text[index:end])
            index = end
            continue

        if character == "$":
            delimiter_end = text.find("$", index + 1)
            if delimiter_end != -1:
                tag = text[index + 1 : delimiter_end]
                if not tag or (
                    (tag[0].isalpha() or tag[0] == "_")
                    and all(part.isalnum() or part == "_" for part in tag[1:])
                ):
                    delimiter = text[index : delimiter_end + 1]
                    body_end = text.find(delimiter, delimiter_end + 1)
                    if body_end != -1:
                        body = text[delimiter_end + 1 : body_end]
                        if _normalize_dollar_body:
                            body = _normalize_sql(
                                body,
                                _normalize_dollar_body=False,
                            )
                        tokens.append(f"$body${body}$body$")
                        index = body_end + len(delimiter)
                        continue

        if character.isalnum() or character == "_" or ord(character) >= 128:
            end = index + 1
            while end < length:
                part = text[end]
                if not (part.isalnum() or part == "_" or ord(part) >= 128):
                    break
                end += 1
            tokens.append(text[index:end].lower())
            index = end
            continue

        if character in _SQL_OPERATOR_CHARACTERS:
            end = index + 1
            while end < length and text[end] in _SQL_OPERATOR_CHARACTERS:
                end += 1
            tokens.append(text[index:end])
            index = end
            continue

        tokens.append(character)
        index += 1

    return "\x1f".join(tokens)


_T = TypeVar("_T")


class PostgresStateStore:
    """Synchronous tenant/workspace-scoped PostgreSQL state store."""

    def __init__(
        self,
        connection: _Connection,
        tenant_id: str,
        workspace_id: str,
    ) -> None:
        self._connection = connection
        self._tenant_id = tenant_id
        self._workspace_id = workspace_id
        self._mode = POSTGRES_STORE_MODE.ACTIVE
        self._safe_mode_reason: dict[str, object] | None = None
        self._closed = False
        self._transaction_active = False
        self._transaction_owner_thread_id: int | None = None
        self._operation_lock = RLock()

    @classmethod
    def open(
        cls,
        connection_factory: Callable[[], _Connection],
        tenant_id: str,
        workspace_id: str,
    ) -> "PostgresStateStore":
        if not callable(connection_factory):
            _fail("INVALID_INPUT", "connection_factory must be callable")
        tenant = _require_nonempty_string(tenant_id, "tenant_id")
        workspace = _require_nonempty_string(workspace_id, "workspace_id")
        connection: _Connection | None = None
        try:
            connection = connection_factory()
            connection.autocommit = True
            store = cls(connection, tenant, workspace)
            store._validate_runtime_principal(contract_objects=False)
            contract = store._validate_schema_contract()
            if not contract["ok"]:
                store._enter_safe_mode(str(contract["code"]), contract.get("details"))
                return store
            store._validate_runtime_principal()
            try:
                store._run_scoped_transaction(lambda: None)
            except PostgresStateStoreError:
                if store.mode != POSTGRES_STORE_MODE.SAFE_MODE:
                    raise
            return store
        except PostgresStateStoreError:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            raise
        except Exception as error:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            raise PostgresStateStoreError(
                "POSTGRES_UNAVAILABLE",
                "PostgreSQL connection or initialization failed",
                {"sqlstate": _sqlstate(error), "cause": type(error).__name__},
            ) from error

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def schema_version(self) -> int:
        return SCHEMA_VERSION

    @property
    def safe_mode_reason(self) -> dict[str, object] | None:
        return dict(self._safe_mode_reason) if self._safe_mode_reason is not None else None

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def workspace_id(self) -> str:
        return self._workspace_id

    def health(self) -> dict[str, object]:
        return {
            "mode": self._mode,
            "backend": "postgresql",
            "schemaVersion": SCHEMA_VERSION,
            "tenantId": self._tenant_id,
            "workspaceId": self._workspace_id,
            "safeModeReason": self.safe_mode_reason,
            "closed": self._closed,
        }

    def transaction(self, callback: Callable[["PostgresStateStore"], _T]) -> _T:
        self._assert_mutable()
        if not callable(callback):
            _fail("INVALID_INPUT", "transaction callback must be callable")
        if self._transaction_active:
            if self._transaction_owner_thread_id != get_ident():
                _fail(
                    "CONCURRENT_TRANSACTION_ACCESS_DENIED",
                    "an explicit transaction may only be used by its callback thread",
                )
            _fail("NESTED_TRANSACTION_DENIED", "nested transactions are not supported")

        def invoke() -> _T:
            result = callback(self)
            if inspect.isawaitable(result):
                if (
                    type(result) is types.CoroutineType
                    and inspect.getcoroutinestate(result) == inspect.CORO_CREATED
                ):
                    result.close()
                _fail("ASYNC_TRANSACTION_DENIED", "transaction callbacks must be synchronous")
            return result

        try:
            return self._run_scoped_transaction(invoke, explicit=True, writer=True)
        except PostgresStateStoreError as error:
            if error.code == "ASYNC_TRANSACTION_DENIED":
                self._enter_safe_mode(
                    error.code,
                    {"rollback": "confirmed", "escapedContinuationDenied": True},
                )
            raise

    def create_revisioned_record(
        self,
        *,
        record_type: str,
        record_id: str,
        value: object,
    ) -> dict[str, object]:
        self._assert_mutable()
        record_type = _require_record_identifier(record_type, "record_type")
        record_id = _require_record_identifier(record_id, "record_id")
        stored_record_type = _encode_identifier(record_type)
        stored_record_id = _encode_identifier(record_id)
        encoded = _encode_json(value)

        def create() -> dict[str, object]:
            rows = self._fetchall(
                """
                SELECT record_type, record_id, revision, value_json::text, created
                  FROM epistemic_foundry.create_revisioned_record(
                      %s, %s, %s, %s, %s::json
                  )
                """,
                (
                    self._tenant_id,
                    self._workspace_id,
                    stored_record_type,
                    stored_record_id,
                    encoded,
                ),
            )
            if len(rows) != 1:
                details = {"rowCount": len(rows), "operation": "create"}
                self._enter_safe_mode("POSTGRES_RESULT_INVALID", details)
                raise PostgresStateStoreError(
                    "POSTGRES_RESULT_INVALID",
                    "create function returned an invalid result cardinality",
                    details,
                )
            row = rows[0]
            if row[4] is False:
                _fail(
                    "RECORD_ALREADY_EXISTS",
                    "revisioned record already exists",
                    {"recordType": record_type, "recordId": record_id},
                )
            if row[4] is not True:
                _fail("POSTGRES_RESULT_INVALID", "INSERT returned no record")
            return self._decode_record(row[:4])

        return self._within_scope(create, writer=True)

    def read_revisioned_record(
        self,
        record_type: str,
        record_id: str,
    ) -> dict[str, object] | None:
        self._assert_readable()
        record_type = _require_record_identifier(record_type, "record_type")
        record_id = _require_record_identifier(record_id, "record_id")
        stored_record_type = _encode_identifier(record_type)
        stored_record_id = _encode_identifier(record_id)

        def read() -> dict[str, object] | None:
            return self._read(stored_record_type, stored_record_id)

        return self._within_scope(read, writer=False)

    def compare_and_swap_revision(
        self,
        *,
        record_type: str,
        record_id: str,
        expected_revision: int,
        value: object,
    ) -> dict[str, object]:
        self._assert_mutable()
        record_type = _require_record_identifier(record_type, "record_type")
        record_id = _require_record_identifier(record_id, "record_id")
        stored_record_type = _encode_identifier(record_type)
        stored_record_id = _encode_identifier(record_id)
        expected = _require_revision(expected_revision, "expected_revision")
        encoded = _encode_json(value)

        def update() -> dict[str, object]:
            rows = self._fetchall(
                """
                SELECT record_type, record_id, revision, value_json::text
                  FROM epistemic_foundry.compare_and_swap_revision(
                      %s, %s, %s, %s, %s, %s::json
                  )
                """,
                (
                    self._tenant_id,
                    self._workspace_id,
                    stored_record_type,
                    stored_record_id,
                    expected,
                    encoded,
                ),
            )
            if len(rows) > 1:
                details = {"rowCount": len(rows), "operation": "compare-and-swap"}
                self._enter_safe_mode("POSTGRES_RESULT_INVALID", details)
                raise PostgresStateStoreError(
                    "POSTGRES_RESULT_INVALID",
                    "compare-and-swap returned an invalid result cardinality",
                    details,
                )
            row = None if not rows else rows[0]
            if row is not None:
                record = self._decode_record(row)
                return {
                    "ok": True,
                    "status": "UPDATED",
                    "previousRevision": expected,
                    "currentRevision": record["revision"],
                    "record": record,
                }

            record = self._read(stored_record_type, stored_record_id)
            if record is None:
                return {
                    "ok": False,
                    "status": "RECORD_NOT_FOUND",
                    "code": "RECORD_NOT_FOUND",
                    "expectedRevision": expected,
                    "currentRevision": None,
                    "record": None,
                }
            if record["revision"] == expected == MAX_REVISION:
                _fail(
                    "REVISION_EXHAUSTED",
                    "revision cannot be incremented beyond the safe integer limit",
                    {
                        "recordType": record_type,
                        "recordId": record_id,
                        "revision": expected,
                    },
                )
            return {
                "ok": False,
                "status": "STALE_REVISION",
                "code": "STALE_REVISION",
                "expectedRevision": expected,
                "currentRevision": record["revision"],
                "record": record,
            }

        return self._within_scope(update, writer=True)

    def check_integrity(self) -> dict[str, object]:
        with self._operation_lock:
            self._assert_available()
            try:
                if self._transaction_active:
                    if self._transaction_owner_thread_id != get_ident():
                        _fail(
                            "CONCURRENT_TRANSACTION_ACCESS_DENIED",
                            "an explicit transaction may only be used by its callback thread",
                        )
                    self._assert_bound_scope_context()
                self._validate_runtime_principal(contract_objects=False)
                result = self._validate_schema_contract()
                if result["ok"]:
                    self._validate_runtime_principal()
                    result = (
                        self._validate_persisted_records()
                        if self._transaction_active
                        else self._run_scoped_transaction(self._validate_persisted_records)
                    )
            except PostgresStateStoreError as error:
                result = {
                    "ok": False,
                    "code": error.code,
                    "details": error.details,
                }
            except Exception as error:
                result = {
                    "ok": False,
                    "code": "POSTGRES_INTEGRITY_FAILED",
                    "details": {
                        "sqlstate": _sqlstate(error),
                        "cause": type(error).__name__,
                    },
                }
            if not result["ok"]:
                self._enter_safe_mode(
                    str(result.get("code", "POSTGRES_INTEGRITY_FAILED")),
                    result.get("details"),
                )
            return {
                "ok": bool(result["ok"]),
                "mode": self._mode,
                "details": result.get("details"),
            }

    def close(self) -> None:
        with self._operation_lock:
            if self._closed:
                return
            try:
                self._connection.close()
            finally:
                self._closed = True
                self._transaction_active = False
                self._transaction_owner_thread_id = None

    def _within_scope(self, operation: Callable[[], _T], *, writer: bool) -> _T:
        if self._transaction_active:
            if self._transaction_owner_thread_id != get_ident():
                _fail(
                    "CONCURRENT_TRANSACTION_ACCESS_DENIED",
                    "an explicit transaction may only be used by its callback thread",
                )
            self._assert_bound_scope_context()
            return operation()
        return self._run_scoped_transaction(operation, writer=writer)

    def _run_scoped_transaction(
        self,
        operation: Callable[[], _T],
        *,
        explicit: bool = False,
        writer: bool = False,
    ) -> _T:
        with self._operation_lock:
            return self._run_scoped_transaction_locked(
                operation,
                explicit=explicit,
                writer=writer,
            )

    def _run_scoped_transaction_locked(
        self,
        operation: Callable[[], _T],
        *,
        explicit: bool,
        writer: bool,
    ) -> _T:
        self._assert_available()
        started = False
        try:
            self._execute("BEGIN")
            started = True
            self._transaction_active = explicit
            self._transaction_owner_thread_id = get_ident() if explicit else None
            self._bind_scope_context()
            self._assert_schema_contract()
            self._validate_runtime_principal()
            self._assert_scope_authorized()
            if writer:
                self._acquire_writer_lock()
            self._validate_persisted_records()
            result = operation()
            self._assert_available()
            self._assert_bound_scope_context()
            self._execute("COMMIT")
            started = False
            return result
        except Exception as error:
            rollback_confirmed = False
            if started:
                try:
                    self._execute("ROLLBACK")
                    rollback_confirmed = True
                except Exception as rollback_error:
                    details = {
                        "cause": type(error).__name__,
                        "rollbackCause": type(rollback_error).__name__,
                        "sqlstate": _sqlstate(error),
                    }
                    self._enter_safe_mode("POSTGRES_TRANSACTION_OUTCOME_UNCERTAIN", details)
                    raise PostgresStateStoreError(
                        "POSTGRES_TRANSACTION_OUTCOME_UNCERTAIN",
                        "transaction failed and rollback could not be confirmed",
                        details,
                    ) from error
            if isinstance(error, PostgresStateStoreError):
                if error.code == "ASYNC_TRANSACTION_DENIED" and not rollback_confirmed:
                    self._enter_safe_mode(
                        "POSTGRES_TRANSACTION_OUTCOME_UNCERTAIN",
                        {"cause": error.code, "rollback": "unconfirmed"},
                    )
                if error.code in {
                    "PRIVILEGED_PRINCIPAL_DENIED",
                    "POSTGRES_PRINCIPAL_PRIVILEGE_MISMATCH",
                    "POSTGRES_PRINCIPAL_ROLE_MEMBERSHIP_DENIED",
                    "ROLE_SWITCH_DENIED",
                }:
                    self._enter_safe_mode(error.code, error.details)
                raise
            if _sqlstate(error) is not None and _sqlstate(error).startswith("XX"):
                details = {"sqlstate": _sqlstate(error), "cause": type(error).__name__}
                self._enter_safe_mode("POSTGRES_INTEGRITY_FAILED", details)
                raise PostgresStateStoreError(
                    "POSTGRES_INTEGRITY_FAILED",
                    "PostgreSQL reported an internal integrity failure",
                    details,
                ) from error
            raise
        finally:
            if explicit:
                self._transaction_active = False
                self._transaction_owner_thread_id = None

    def _bind_scope_context(self) -> None:
        row = self._fetchone(
            """
            SELECT set_config('epistemic_foundry.tenant_id', %s, true),
                   set_config('epistemic_foundry.workspace_id', %s, true),
                   current_user::text,
                   session_user::text
            """,
            (self._tenant_id, self._workspace_id),
        )
        if row is None or tuple(row[:2]) != (self._tenant_id, self._workspace_id):
            _fail("TENANT_CONTEXT_BINDING_FAILED", "transaction-local tenant context was not bound")
        if row[2] != row[3]:
            _fail(
                "ROLE_SWITCH_DENIED",
                "current_user must equal immutable session_user on a runtime connection",
                {"currentUser": row[2], "sessionUser": row[3]},
            )
        self._validate_runtime_principal(contract_objects=False)

    def _assert_bound_scope_context(self) -> None:
        row = self._fetchone(
            """
            SELECT current_setting('epistemic_foundry.tenant_id', true),
                   current_setting('epistemic_foundry.workspace_id', true),
                   current_user::text,
                   session_user::text
            """
        )
        actual = None if row is None else tuple(row)
        expected = (
            self._tenant_id,
            self._workspace_id,
            None if row is None else row[3],
            None if row is None else row[3],
        )
        if actual != expected:
            _fail(
                "BOUND_SCOPE_CONTEXT_CHANGED",
                "transaction-local tenant/workspace or principal context changed",
                {
                    "expectedTenantId": self._tenant_id,
                    "expectedWorkspaceId": self._workspace_id,
                    "actualTenantId": None if row is None else row[0],
                    "actualWorkspaceId": None if row is None else row[1],
                    "currentUserMatchesSessionUser": (
                        False if row is None else row[2] == row[3]
                    ),
                },
            )
        self._validate_runtime_principal(contract_objects=False)

    def _assert_scope_authorized(self) -> None:
        row = self._fetchone(
            "SELECT epistemic_foundry.scope_is_authorized(%s, %s)",
            (self._tenant_id, self._workspace_id),
        )
        if row is None or row[0] is not True:
            _fail(
                "SCOPE_NOT_AUTHORIZED",
                "session principal is not authorized for the requested tenant/workspace",
                {"tenantId": self._tenant_id, "workspaceId": self._workspace_id},
            )

    def _acquire_writer_lock(self) -> None:
        row = self._fetchone(
            "SELECT epistemic_foundry.acquire_writer_lock(%s, %s)",
            (self._tenant_id, self._workspace_id),
        )
        if row is None or row[0] is not True:
            _fail(
                "POSTGRES_WRITER_LOCK_FAILED",
                "PostgreSQL writer serialization lock was not acquired",
                {"tenantId": self._tenant_id, "workspaceId": self._workspace_id},
            )

    def _validate_runtime_principal(self, *, contract_objects: bool = True) -> None:
        row = self._fetchone(
            """
            SELECT r.rolsuper, r.rolbypassrls, r.rolcreaterole,
                   r.rolcreatedb, r.rolreplication, r.rolcanlogin,
                   current_user::text, session_user::text
              FROM pg_catalog.pg_roles AS r
             WHERE r.rolname = session_user
            """
        )
        if row is None:
            _fail("POSTGRES_PRINCIPAL_INVALID", "session principal is not visible in pg_roles")
        if any(value is True for value in row[0:5]) or row[5] is not True:
            _fail(
                "PRIVILEGED_PRINCIPAL_DENIED",
                "runtime state access requires an unprivileged login principal",
                {
                    "superuser": bool(row[0]),
                    "bypassRls": bool(row[1]),
                    "createRole": bool(row[2]),
                    "createDatabase": bool(row[3]),
                    "replication": bool(row[4]),
                    "canLogin": bool(row[5]),
                },
            )
        if row[6] != row[7]:
            _fail("ROLE_SWITCH_DENIED", "runtime connections may not use SET ROLE")

        role_memberships = self._fetchall(
            """
            SELECT granted_role.rolname
              FROM pg_catalog.pg_auth_members AS membership
              JOIN pg_catalog.pg_roles AS member_role
                ON member_role.oid = membership.member
              JOIN pg_catalog.pg_roles AS granted_role
                ON granted_role.oid = membership.roleid
             WHERE member_role.rolname = session_user
             ORDER BY granted_role.rolname
            """
        )
        if role_memberships:
            _fail(
                "POSTGRES_PRINCIPAL_ROLE_MEMBERSHIP_DENIED",
                "runtime principals must receive direct grants and have no role memberships",
                {"grantedRoles": [str(membership[0]) for membership in role_memberships]},
            )
        if not contract_objects:
            return

        schema_row = self._fetchone(
            """
            SELECT pg_catalog.has_schema_privilege(
                       session_user, n.oid, 'USAGE'
                   ),
                   pg_catalog.has_schema_privilege(
                       session_user, n.oid, 'CREATE'
                   ),
                   pg_catalog.pg_has_role(
                       session_user, n.nspowner, 'MEMBER'
                   )
              FROM pg_catalog.pg_namespace AS n
             WHERE n.nspname = 'epistemic_foundry'
            """
        )
        expected_schema_privileges = (True, False, False)
        if schema_row is None or tuple(schema_row) != expected_schema_privileges:
            _fail(
                "POSTGRES_PRINCIPAL_PRIVILEGE_MISMATCH",
                "runtime schema privileges do not match the team-store contract",
                {
                    "component": "schema",
                    "expected": list(expected_schema_privileges),
                    "actual": None if schema_row is None else list(schema_row),
                },
            )

        table_rows = self._fetchall(
            """
            SELECT c.relname,
                   pg_catalog.pg_has_role(
                       session_user, c.relowner, 'MEMBER'
                   ),
                   pg_catalog.has_table_privilege(
                       session_user, c.oid, 'SELECT'
                   ),
                   pg_catalog.has_table_privilege(
                       session_user, c.oid, 'INSERT'
                   ),
                   pg_catalog.has_table_privilege(
                       session_user, c.oid, 'UPDATE'
                   ),
                   pg_catalog.has_table_privilege(
                       session_user, c.oid, 'DELETE'
                   ),
                   pg_catalog.has_table_privilege(
                       session_user, c.oid, 'TRUNCATE'
                   ),
                   pg_catalog.has_table_privilege(
                       session_user, c.oid, 'REFERENCES'
                   ),
                   pg_catalog.has_table_privilege(
                       session_user, c.oid, 'TRIGGER'
                   )
              FROM pg_catalog.pg_class AS c
              JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
             WHERE n.nspname = 'epistemic_foundry'
               AND c.relname IN (
                   'store_metadata', 'principal_scopes', 'revisioned_records'
               )
             ORDER BY c.relname
            """
        )
        actual_table_privileges = [tuple(row) for row in table_rows]
        expected_table_privileges = [
            ("principal_scopes", False, False, False, False, False, False, False, False),
            ("revisioned_records", False, True, False, False, False, False, False, False),
            ("store_metadata", False, True, False, False, False, False, False, False),
        ]
        if actual_table_privileges != expected_table_privileges:
            _fail(
                "POSTGRES_PRINCIPAL_PRIVILEGE_MISMATCH",
                "runtime table privileges do not match the team-store contract",
                {
                    "component": "tables",
                    "expected": expected_table_privileges,
                    "actual": actual_table_privileges,
                },
            )

        column_rows = self._fetchall(
            """
            SELECT c.relname,
                   a.attname,
                   pg_catalog.has_column_privilege(
                       session_user, c.oid, a.attnum, 'SELECT'
                   ),
                   pg_catalog.has_column_privilege(
                       session_user, c.oid, a.attnum, 'INSERT'
                   ),
                   pg_catalog.has_column_privilege(
                       session_user, c.oid, a.attnum, 'UPDATE'
                   ),
                   pg_catalog.has_column_privilege(
                       session_user, c.oid, a.attnum, 'REFERENCES'
                   )
              FROM pg_catalog.pg_class AS c
              JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
              JOIN pg_catalog.pg_attribute AS a ON a.attrelid = c.oid
             WHERE n.nspname = 'epistemic_foundry'
               AND c.relname IN (
                   'store_metadata', 'principal_scopes', 'revisioned_records'
               )
               AND a.attnum > 0
               AND NOT a.attisdropped
             ORDER BY c.relname, a.attnum
            """
        )
        actual_column_privileges = [tuple(row) for row in column_rows]
        expected_column_privileges = [
            ("principal_scopes", "principal_name", False, False, False, False),
            ("principal_scopes", "tenant_id", False, False, False, False),
            ("principal_scopes", "workspace_id", False, False, False, False),
            ("principal_scopes", "granted_at", False, False, False, False),
            ("revisioned_records", "tenant_id", True, False, False, False),
            ("revisioned_records", "workspace_id", True, False, False, False),
            ("revisioned_records", "record_type", True, False, False, False),
            ("revisioned_records", "record_id", True, False, False, False),
            ("revisioned_records", "revision", True, False, False, False),
            ("revisioned_records", "value_json", True, False, False, False),
            ("store_metadata", "key", True, False, False, False),
            ("store_metadata", "value", True, False, False, False),
        ]
        if actual_column_privileges != expected_column_privileges:
            _fail(
                "POSTGRES_PRINCIPAL_PRIVILEGE_MISMATCH",
                "runtime column privileges do not match the team-store contract",
                {
                    "component": "columns",
                    "expected": expected_column_privileges,
                    "actual": actual_column_privileges,
                },
            )

        function_rows = self._fetchall(
            """
            SELECT p.proname,
                   pg_catalog.pg_get_function_identity_arguments(p.oid),
                   pg_catalog.pg_has_role(
                       session_user, p.proowner, 'MEMBER'
                   ),
                   pg_catalog.has_function_privilege(
                       session_user, p.oid, 'EXECUTE'
                   )
             FROM pg_catalog.pg_proc AS p
              JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
             WHERE n.nspname = 'epistemic_foundry'
             ORDER BY p.proname,
                      pg_catalog.pg_get_function_identity_arguments(p.oid)
            """
        )
        actual_function_privileges = [tuple(row) for row in function_rows]
        expected_function_privileges = [
            (
                "acquire_writer_lock",
                "requested_tenant text, requested_workspace text",
                False,
                True,
            ),
            (
                "compare_and_swap_revision",
                "requested_tenant text, requested_workspace text, "
                "requested_record_type text, requested_record_id text, "
                "requested_expected_revision bigint, requested_value_json json",
                False,
                True,
            ),
            (
                "create_revisioned_record",
                "requested_tenant text, requested_workspace text, "
                "requested_record_type text, requested_record_id text, "
                "requested_value_json json",
                False,
                True,
            ),
            (
                "scope_is_authorized",
                "requested_tenant text, requested_workspace text",
                False,
                True,
            ),
        ]
        if actual_function_privileges != expected_function_privileges:
            _fail(
                "POSTGRES_PRINCIPAL_PRIVILEGE_MISMATCH",
                "runtime function privileges do not match the team-store contract",
                {
                    "component": "functions",
                    "expected": expected_function_privileges,
                    "actual": actual_function_privileges,
                },
            )

    def _assert_schema_contract(self) -> None:
        contract = self._validate_schema_contract()
        if contract["ok"]:
            return
        code = str(contract.get("code", "POSTGRES_SCHEMA_UNAVAILABLE"))
        details = contract.get("details")
        self._enter_safe_mode(code, details)
        raise PostgresStateStoreError(
            code,
            "PostgreSQL team-store schema no longer matches the canonical contract",
            details if isinstance(details, Mapping) else None,
        )

    def _validate_schema_contract(self) -> dict[str, object]:
        try:
            metadata_rows = self._fetchall(
                "SELECT key, value FROM epistemic_foundry.store_metadata ORDER BY key"
            )
            metadata = {str(row[0]): str(row[1]) for row in metadata_rows}
            expected_metadata = {
                "contract_id": CONTRACT_ID,
                "identity_collation": "pg_catalog.C-deterministic",
                "identifier_encoding": IDENTIFIER_ENCODING,
                "identity_uniqueness": "serialized-exact-match-no-length-limited-index",
                "isolation_policy": "principal+tenant+workspace+transaction-local-context",
                "revision_ceiling": str(MAX_REVISION),
                "revision_genesis": "0",
                "schema_version": str(SCHEMA_VERSION),
            }
            if metadata.get("schema_version") != str(SCHEMA_VERSION):
                return {
                    "ok": False,
                    "code": "POSTGRES_SCHEMA_VERSION_MISMATCH",
                    "details": {
                        "expected": str(SCHEMA_VERSION),
                        "actual": metadata.get("schema_version"),
                    },
                }
            if metadata != expected_metadata:
                return {
                    "ok": False,
                    "code": "POSTGRES_SCHEMA_METADATA_MISMATCH",
                    "details": {"expected": expected_metadata, "actual": metadata},
                }

            schema_acl_rows = self._fetchall(
                """
                SELECT COALESCE(grantee_role.rolname, 'PUBLIC'),
                       grantee_role.rolsuper,
                       grantee_role.rolbypassrls,
                       grantee_role.rolcreaterole,
                       grantee_role.rolcreatedb,
                       grantee_role.rolreplication,
                       grantee_role.rolcanlogin,
                       acl.privilege_type,
                       acl.is_grantable
                  FROM pg_catalog.pg_namespace AS namespace
                  CROSS JOIN LATERAL pg_catalog.aclexplode(
                      COALESCE(
                          namespace.nspacl,
                          pg_catalog.acldefault('n', namespace.nspowner)
                      )
                  ) AS acl
                  LEFT JOIN pg_catalog.pg_roles AS grantee_role
                    ON grantee_role.oid = acl.grantee
                 WHERE namespace.nspname = 'epistemic_foundry'
                   AND acl.grantee <> namespace.nspowner
                 ORDER BY COALESCE(grantee_role.rolname, 'PUBLIC'),
                          acl.privilege_type
                """
            )
            invalid_schema_acl = [
                tuple(row)
                for row in schema_acl_rows
                if row[0] == "PUBLIC"
                or any(value is True for value in row[1:6])
                or row[6] is not True
                or row[7] != "USAGE"
                or row[8] is not False
            ]

            table_acl_rows = self._fetchall(
                """
                SELECT relation.relname,
                       COALESCE(grantee_role.rolname, 'PUBLIC'),
                       grantee_role.rolsuper,
                       grantee_role.rolbypassrls,
                       grantee_role.rolcreaterole,
                       grantee_role.rolcreatedb,
                       grantee_role.rolreplication,
                       grantee_role.rolcanlogin,
                       acl.privilege_type,
                       acl.is_grantable
                  FROM pg_catalog.pg_class AS relation
                  JOIN pg_catalog.pg_namespace AS namespace
                    ON namespace.oid = relation.relnamespace
                  CROSS JOIN LATERAL pg_catalog.aclexplode(
                      COALESCE(
                          relation.relacl,
                          pg_catalog.acldefault('r', relation.relowner)
                      )
                  ) AS acl
                  LEFT JOIN pg_catalog.pg_roles AS grantee_role
                    ON grantee_role.oid = acl.grantee
                 WHERE namespace.nspname = 'epistemic_foundry'
                   AND relation.relname IN (
                       'store_metadata', 'principal_scopes', 'revisioned_records'
                   )
                   AND acl.grantee <> relation.relowner
                 ORDER BY relation.relname,
                          COALESCE(grantee_role.rolname, 'PUBLIC'),
                          acl.privilege_type
                """
            )
            invalid_table_acl = [
                tuple(row)
                for row in table_acl_rows
                if row[1] == "PUBLIC"
                or any(value is True for value in row[2:7])
                or row[7] is not True
                or row[8] != "SELECT"
                or row[0] == "principal_scopes"
                or row[9] is not False
            ]

            column_acl_rows = self._fetchall(
                """
                SELECT relation.relname,
                       attribute.attname,
                       COALESCE(grantee_role.rolname, 'PUBLIC'),
                       acl.privilege_type,
                       acl.is_grantable
                  FROM pg_catalog.pg_class AS relation
                  JOIN pg_catalog.pg_namespace AS namespace
                    ON namespace.oid = relation.relnamespace
                  JOIN pg_catalog.pg_attribute AS attribute
                    ON attribute.attrelid = relation.oid
                  CROSS JOIN LATERAL pg_catalog.aclexplode(
                      COALESCE(
                          attribute.attacl,
                          pg_catalog.acldefault('c', relation.relowner)
                      )
                  ) AS acl
                  LEFT JOIN pg_catalog.pg_roles AS grantee_role
                    ON grantee_role.oid = acl.grantee
                 WHERE namespace.nspname = 'epistemic_foundry'
                   AND relation.relname IN (
                       'store_metadata', 'principal_scopes', 'revisioned_records'
                   )
                   AND attribute.attnum > 0
                   AND NOT attribute.attisdropped
                   AND acl.grantee <> relation.relowner
                 ORDER BY relation.relname,
                          attribute.attnum,
                          COALESCE(grantee_role.rolname, 'PUBLIC'),
                          acl.privilege_type
                """
            )

            function_acl_rows = self._fetchall(
                """
                SELECT function_definition.proname,
                       pg_catalog.pg_get_function_identity_arguments(
                           function_definition.oid
                       ),
                       COALESCE(grantee_role.rolname, 'PUBLIC'),
                       grantee_role.rolsuper,
                       grantee_role.rolbypassrls,
                       grantee_role.rolcreaterole,
                       grantee_role.rolcreatedb,
                       grantee_role.rolreplication,
                       grantee_role.rolcanlogin,
                       acl.privilege_type,
                       acl.is_grantable
                  FROM pg_catalog.pg_proc AS function_definition
                  JOIN pg_catalog.pg_namespace AS namespace
                    ON namespace.oid = function_definition.pronamespace
                  CROSS JOIN LATERAL pg_catalog.aclexplode(
                      COALESCE(
                          function_definition.proacl,
                          pg_catalog.acldefault('f', function_definition.proowner)
                      )
                  ) AS acl
                 LEFT JOIN pg_catalog.pg_roles AS grantee_role
                    ON grantee_role.oid = acl.grantee
                 WHERE namespace.nspname = 'epistemic_foundry'
                   AND function_definition.proname IN (
                       'acquire_writer_lock',
                       'compare_and_swap_revision',
                       'create_revisioned_record',
                       'scope_is_authorized'
                   )
                   AND acl.grantee <> function_definition.proowner
                 ORDER BY function_definition.proname,
                          pg_catalog.pg_get_function_identity_arguments(
                              function_definition.oid
                          ),
                          COALESCE(grantee_role.rolname, 'PUBLIC'),
                          acl.privilege_type
                """
            )
            invalid_function_acl = [
                tuple(row)
                for row in function_acl_rows
                if row[2] == "PUBLIC"
                or any(value is True for value in row[3:8])
                or row[8] is not True
                or row[9] != "EXECUTE"
                or row[10] is not False
            ]
            if (
                invalid_schema_acl
                or invalid_table_acl
                or column_acl_rows
                or invalid_function_acl
            ):
                return {
                    "ok": False,
                    "code": "POSTGRES_SCHEMA_ACL_MISMATCH",
                    "details": {
                        "schema": invalid_schema_acl,
                        "tables": invalid_table_acl,
                        "columns": [tuple(row) for row in column_acl_rows],
                        "functions": invalid_function_acl,
                    },
                }

            relation_rows = self._fetchall(
                """
                SELECT c.relname, c.relkind::text, c.relpersistence::text,
                       c.relrowsecurity, c.relforcerowsecurity,
                       c.relowner = n.nspowner,
                       owner.rolsuper, owner.rolbypassrls
                  FROM pg_catalog.pg_class AS c
                  JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                  JOIN pg_catalog.pg_roles AS owner ON owner.oid = n.nspowner
                 WHERE n.nspname = 'epistemic_foundry'
                   AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
                 ORDER BY c.relname
                """
            )
            actual_relations = [tuple(row) for row in relation_rows]
            expected_relations = [
                ("principal_scopes", "r", "p", False, False, True, False, False),
                ("revisioned_records", "r", "p", True, True, True, False, False),
                ("store_metadata", "r", "p", False, False, True, False, False),
            ]
            if actual_relations != expected_relations:
                revisioned_relation = next(
                    (
                        relation
                        for relation in actual_relations
                        if relation[0] == "revisioned_records"
                    ),
                    None,
                )
                if (
                    revisioned_relation is None
                    or revisioned_relation[3:5] != (True, True)
                ):
                    return {
                        "ok": False,
                        "code": "POSTGRES_RLS_CONFIGURATION_MISMATCH",
                        "details": {
                            "expected": [True, True],
                            "actual": (
                                None
                                if revisioned_relation is None
                                else list(revisioned_relation[3:5])
                            ),
                        },
                    }
                return {
                    "ok": False,
                    "code": "POSTGRES_SCHEMA_RELATION_MISMATCH",
                    "details": {"expected": expected_relations, "actual": actual_relations},
                }

            column_rows = self._fetchall(
                """
                SELECT c.relname, a.attname,
                       pg_catalog.format_type(a.atttypid, a.atttypmod),
                       a.attnotnull,
                       pg_catalog.pg_get_expr(d.adbin, d.adrelid),
                       a.attidentity::text, a.attgenerated::text,
                       collation_namespace.nspname,
                       collation_definition.collname,
                       collation_definition.collprovider::text,
                       collation_definition.collisdeterministic,
                       a.attnum
                  FROM pg_catalog.pg_class AS c
                  JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                  JOIN pg_catalog.pg_attribute AS a ON a.attrelid = c.oid
                  LEFT JOIN pg_catalog.pg_attrdef AS d
                    ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                  LEFT JOIN pg_catalog.pg_collation AS collation_definition
                    ON collation_definition.oid = a.attcollation
                  LEFT JOIN pg_catalog.pg_namespace AS collation_namespace
                    ON collation_namespace.oid = collation_definition.collnamespace
                 WHERE n.nspname = 'epistemic_foundry'
                   AND c.relname IN ('store_metadata', 'principal_scopes', 'revisioned_records')
                   AND c.relkind = 'r'
                   AND a.attnum > 0
                   AND NOT a.attisdropped
                 ORDER BY c.relname, a.attnum
                """
            )
            actual_columns = [tuple(row[:11]) for row in column_rows]
            c_collation = ("pg_catalog", "C", "c", True)
            no_collation = (None, None, None, None)
            expected_columns = [
                (
                    "principal_scopes",
                    "principal_name",
                    "name",
                    True,
                    None,
                    "",
                    "",
                    *c_collation,
                ),
                (
                    "principal_scopes",
                    "tenant_id",
                    "text",
                    True,
                    None,
                    "",
                    "",
                    *c_collation,
                ),
                (
                    "principal_scopes",
                    "workspace_id",
                    "text",
                    True,
                    None,
                    "",
                    "",
                    *c_collation,
                ),
                (
                    "principal_scopes",
                    "granted_at",
                    "timestamp with time zone",
                    True,
                    "statement_timestamp()",
                    "",
                    "",
                    *no_collation,
                ),
                (
                    "revisioned_records",
                    "tenant_id",
                    "text",
                    True,
                    None,
                    "",
                    "",
                    *c_collation,
                ),
                (
                    "revisioned_records",
                    "workspace_id",
                    "text",
                    True,
                    None,
                    "",
                    "",
                    *c_collation,
                ),
                (
                    "revisioned_records",
                    "record_type",
                    "text",
                    True,
                    None,
                    "",
                    "",
                    *c_collation,
                ),
                (
                    "revisioned_records",
                    "record_id",
                    "text",
                    True,
                    None,
                    "",
                    "",
                    *c_collation,
                ),
                (
                    "revisioned_records",
                    "revision",
                    "bigint",
                    True,
                    None,
                    "",
                    "",
                    *no_collation,
                ),
                (
                    "revisioned_records",
                    "value_json",
                    "json",
                    True,
                    None,
                    "",
                    "",
                    *no_collation,
                ),
                (
                    "store_metadata",
                    "key",
                    "text",
                    True,
                    None,
                    "",
                    "",
                    *c_collation,
                ),
                (
                    "store_metadata",
                    "value",
                    "text",
                    True,
                    None,
                    "",
                    "",
                    *c_collation,
                ),
            ]
            if actual_columns != expected_columns:
                return {
                    "ok": False,
                    "code": "POSTGRES_SCHEMA_COLUMN_MISMATCH",
                    "details": {"expected": expected_columns, "actual": actual_columns},
                }

            constraint_rows = self._fetchall(
                """
                SELECT c.relname, con.conname, con.contype::text,
                       con.convalidated,
                       pg_catalog.pg_get_constraintdef(con.oid, true)
                  FROM pg_catalog.pg_constraint AS con
                  JOIN pg_catalog.pg_class AS c ON c.oid = con.conrelid
                  JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'epistemic_foundry'
                 ORDER BY c.relname, con.conname
                """
            )
            actual_constraints = [
                (row[0], row[1], row[2], row[3], _normalize_sql(row[4]))
                for row in constraint_rows
            ]
            expected_constraints = [
                (
                    "principal_scopes",
                    "principal_scopes_pk",
                    "p",
                    True,
                    _normalize_sql(
                        "PRIMARY KEY (principal_name, tenant_id, workspace_id)"
                    ),
                ),
                (
                    "principal_scopes",
                    "principal_scopes_principal_nonempty",
                    "c",
                    True,
                    _normalize_sql("CHECK (principal_name <> ''::name)"),
                ),
                (
                    "principal_scopes",
                    "principal_scopes_tenant_nonempty",
                    "c",
                    True,
                    _normalize_sql("CHECK (tenant_id <> ''::text)"),
                ),
                (
                    "principal_scopes",
                    "principal_scopes_workspace_nonempty",
                    "c",
                    True,
                    _normalize_sql("CHECK (workspace_id <> ''::text)"),
                ),
                (
                    "revisioned_records",
                    "revisioned_records_id_encoding",
                    "c",
                    True,
                    _normalize_sql(
                        "CHECK (record_id ~ '^u16be:([0-9a-f]{4})+$'::text)"
                    ),
                ),
                (
                    "revisioned_records",
                    "revisioned_records_id_nonempty",
                    "c",
                    True,
                    _normalize_sql("CHECK (record_id <> ''::text)"),
                ),
                (
                    "revisioned_records",
                    "revisioned_records_revision_range",
                    "c",
                    True,
                    _normalize_sql(
                        "CHECK (revision >= 0 AND "
                        "revision <= '9007199254740991'::bigint)"
                    ),
                ),
                (
                    "revisioned_records",
                    "revisioned_records_tenant_nonempty",
                    "c",
                    True,
                    _normalize_sql("CHECK (tenant_id <> ''::text)"),
                ),
                (
                    "revisioned_records",
                    "revisioned_records_type_encoding",
                    "c",
                    True,
                    _normalize_sql(
                        "CHECK (record_type ~ '^u16be:([0-9a-f]{4})+$'::text)"
                    ),
                ),
                (
                    "revisioned_records",
                    "revisioned_records_type_nonempty",
                    "c",
                    True,
                    _normalize_sql("CHECK (record_type <> ''::text)"),
                ),
                (
                    "revisioned_records",
                    "revisioned_records_workspace_nonempty",
                    "c",
                    True,
                    _normalize_sql("CHECK (workspace_id <> ''::text)"),
                ),
                (
                    "store_metadata",
                    "store_metadata_pkey",
                    "p",
                    True,
                    _normalize_sql("PRIMARY KEY (key)"),
                ),
            ]
            if actual_constraints != expected_constraints:
                return {
                    "ok": False,
                    "code": "POSTGRES_SCHEMA_CONSTRAINT_MISMATCH",
                    "details": {"expected": expected_constraints, "actual": actual_constraints},
                }

            index_rows = self._fetchall(
                """
                SELECT table_relation.relname,
                       index_relation.relname,
                       index_state.indisunique,
                       index_state.indisprimary,
                       index_state.indisvalid,
                       index_state.indisready,
                       pg_catalog.pg_get_indexdef(index_relation.oid)
                  FROM pg_catalog.pg_index AS index_state
                  JOIN pg_catalog.pg_class AS table_relation
                    ON table_relation.oid = index_state.indrelid
                  JOIN pg_catalog.pg_class AS index_relation
                    ON index_relation.oid = index_state.indexrelid
                  JOIN pg_catalog.pg_namespace AS namespace
                    ON namespace.oid = table_relation.relnamespace
                 WHERE namespace.nspname = 'epistemic_foundry'
                   AND table_relation.relname IN (
                       'store_metadata', 'principal_scopes', 'revisioned_records'
                   )
                 ORDER BY table_relation.relname, index_relation.relname
                """
            )
            actual_indexes = [
                (*tuple(row[:6]), _normalize_sql(row[6])) for row in index_rows
            ]
            expected_indexes = [
                (
                    "principal_scopes",
                    "principal_scopes_pk",
                    True,
                    True,
                    True,
                    True,
                    _normalize_sql(
                        "CREATE UNIQUE INDEX principal_scopes_pk ON "
                        "epistemic_foundry.principal_scopes USING btree "
                        "(principal_name, tenant_id, workspace_id)"
                    ),
                ),
                (
                    "store_metadata",
                    "store_metadata_pkey",
                    True,
                    True,
                    True,
                    True,
                    _normalize_sql(
                        "CREATE UNIQUE INDEX store_metadata_pkey ON "
                        "epistemic_foundry.store_metadata USING btree (key)"
                    ),
                ),
            ]
            if actual_indexes != expected_indexes:
                return {
                    "ok": False,
                    "code": "POSTGRES_SCHEMA_INDEX_MISMATCH",
                    "details": {"expected": expected_indexes, "actual": actual_indexes},
                }

            policy_rows = self._fetchall(
                """
                SELECT c.relname, p.polname, p.polcmd::text, p.polpermissive,
                       p.polroles,
                       pg_catalog.pg_get_expr(p.polqual, p.polrelid),
                       pg_catalog.pg_get_expr(p.polwithcheck, p.polrelid)
                  FROM pg_catalog.pg_policy AS p
                  JOIN pg_catalog.pg_class AS c ON c.oid = p.polrelid
                  JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'epistemic_foundry'
                   AND c.relname = 'revisioned_records'
                 ORDER BY p.polname
                """
            )
            actual_policies = [
                (
                    row[0],
                    row[1],
                    row[2],
                    row[3],
                    list(row[4]),
                    _normalize_sql(row[5]),
                    _normalize_sql(row[6]),
                )
                for row in policy_rows
            ]
            policy_expression = _normalize_sql(
                """
                ((tenant_id = NULLIF(
                    current_setting('epistemic_foundry.tenant_id'::text, true),
                    ''::text
                )) AND (workspace_id = NULLIF(
                    current_setting('epistemic_foundry.workspace_id'::text, true),
                    ''::text
                )) AND epistemic_foundry.scope_is_authorized(
                    tenant_id, workspace_id
                ))
                """
            )
            expected_policies = [
                (
                    "revisioned_records",
                    "tenant_workspace_isolation",
                    "*",
                    True,
                    [0],
                    policy_expression,
                    policy_expression,
                )
            ]
            if actual_policies != expected_policies:
                return {
                    "ok": False,
                    "code": "POSTGRES_RLS_POLICY_MISMATCH",
                    "details": {"expected": expected_policies, "actual": actual_policies},
                }

            trigger_rows = self._fetchall(
                """
                SELECT c.relname, t.tgname
                  FROM pg_catalog.pg_trigger AS t
                  JOIN pg_catalog.pg_class AS c ON c.oid = t.tgrelid
                  JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'epistemic_foundry'
                   AND NOT t.tgisinternal
                 ORDER BY c.relname, t.tgname
                """
            )
            if trigger_rows:
                return {
                    "ok": False,
                    "code": "POSTGRES_SCHEMA_TRIGGER_MISMATCH",
                    "details": {"expected": [], "actual": [tuple(row) for row in trigger_rows]},
                }

            function_rows = self._fetchall(
                """
                SELECT p.prosecdef, p.provolatile, p.proconfig,
                       pg_catalog.pg_get_function_identity_arguments(p.oid),
                       pg_catalog.pg_get_function_result(p.oid),
                       p.proisstrict, p.proleakproof, p.proparallel::text,
                       p.proowner = n.nspowner,
                       NOT EXISTS (
                           SELECT 1
                             FROM pg_catalog.aclexplode(
                                 COALESCE(
                                     p.proacl,
                                     pg_catalog.acldefault('f', p.proowner)
                                 )
                             ) AS acl
                            WHERE acl.grantee = 0
                              AND acl.privilege_type = 'EXECUTE'
                       ),
                       pg_catalog.pg_get_functiondef(p.oid)
                  FROM pg_catalog.pg_proc AS p
                  JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'epistemic_foundry'
                 ORDER BY p.proname,
                          pg_catalog.pg_get_function_identity_arguments(p.oid)
                """
            )
            actual_functions = [
                (
                    row[0],
                    row[1],
                    list(row[2]) if row[2] is not None else None,
                    row[3],
                    row[4],
                    row[5],
                    row[6],
                    row[7],
                    row[8],
                    row[9],
                    _normalize_sql(row[10]),
                )
                for row in function_rows
            ]
            expected_functions = [
                (
                    True,
                    "v",
                    ["search_path=pg_catalog"],
                    "requested_tenant text, requested_workspace text",
                    "boolean",
                    False,
                    False,
                    "u",
                    True,
                    True,
                    _normalize_sql(_EXPECTED_WRITER_LOCK_FUNCTION_DEFINITION),
                ),
                (
                    True,
                    "v",
                    ["search_path=pg_catalog"],
                    "requested_tenant text, requested_workspace text, "
                    "requested_record_type text, requested_record_id text, "
                    "requested_expected_revision bigint, requested_value_json json",
                    "TABLE(record_type text, record_id text, revision bigint, "
                    "value_json json)",
                    False,
                    False,
                    "u",
                    True,
                    True,
                    _normalize_sql(_EXPECTED_CAS_FUNCTION_DEFINITION),
                ),
                (
                    True,
                    "v",
                    ["search_path=pg_catalog"],
                    "requested_tenant text, requested_workspace text, "
                    "requested_record_type text, requested_record_id text, "
                    "requested_value_json json",
                    "TABLE(record_type text, record_id text, revision bigint, "
                    "value_json json, created boolean)",
                    False,
                    False,
                    "u",
                    True,
                    True,
                    _normalize_sql(_EXPECTED_CREATE_FUNCTION_DEFINITION),
                ),
                (
                    True,
                    "s",
                    ["search_path=pg_catalog"],
                    "requested_tenant text, requested_workspace text",
                    "boolean",
                    False,
                    False,
                    "u",
                    True,
                    True,
                    _normalize_sql(_EXPECTED_SCOPE_FUNCTION_DEFINITION),
                )
            ]
            if actual_functions != expected_functions:
                return {
                    "ok": False,
                    "code": "POSTGRES_RLS_FUNCTION_MISMATCH",
                    "details": {"expected": expected_functions, "actual": actual_functions},
                }

            return {"ok": True, "details": {"schemaVersion": SCHEMA_VERSION}}
        except Exception as error:
            return {
                "ok": False,
                "code": "POSTGRES_SCHEMA_UNAVAILABLE",
                "details": {"sqlstate": _sqlstate(error), "cause": type(error).__name__},
            }

    def _validate_persisted_records(self) -> dict[str, object]:
        rows = self._fetchall(
            """
            SELECT record_type, record_id, revision, value_json::text
              FROM epistemic_foundry.revisioned_records
             ORDER BY record_type, record_id
            """
        )
        identities: set[tuple[object, object]] = set()
        for row in rows:
            identity = (row[0], row[1])
            if identity in identities:
                details = {
                    "recordType": row[0],
                    "recordId": row[1],
                    "scope": "current tenant/workspace",
                }
                self._enter_safe_mode("POSTGRES_PERSISTED_IDENTITY_DUPLICATE", details)
                raise PostgresStateStoreError(
                    "POSTGRES_PERSISTED_IDENTITY_DUPLICATE",
                    "persisted PostgreSQL records contain a duplicate logical identity",
                    details,
                )
            identities.add(identity)
            self._decode_record(row)
        return {
            "ok": True,
            "details": {
                "scope": "current tenant/workspace",
                "recordCount": len(rows),
            },
        }

    def _read(self, record_type: str, record_id: str) -> dict[str, object] | None:
        rows = self._fetchall(
            """
            SELECT record_type, record_id, revision, value_json::text
              FROM epistemic_foundry.revisioned_records
             WHERE tenant_id = %s
               AND workspace_id = %s
               AND record_type = %s
               AND record_id = %s
            """,
            (self._tenant_id, self._workspace_id, record_type, record_id),
        )
        if len(rows) > 1:
            details = {
                "recordType": record_type,
                "recordId": record_id,
                "rowCount": len(rows),
            }
            self._enter_safe_mode("POSTGRES_PERSISTED_IDENTITY_DUPLICATE", details)
            raise PostgresStateStoreError(
                "POSTGRES_PERSISTED_IDENTITY_DUPLICATE",
                "persisted PostgreSQL records contain a duplicate logical identity",
                details,
            )
        return None if not rows else self._decode_record(rows[0])

    def _decode_record(self, row: object) -> dict[str, object]:
        record_type: object = None
        record_id: object = None
        try:
            values = tuple(row)
            if len(values) != 4 or type(values[0]) is not str or type(values[1]) is not str:
                raise ValueError("invalid record row shape")
            record_type, record_id = values[0], values[1]
            revision = _require_revision(values[2], "persisted revision")
            record_type = _decode_identifier(values[0], "record_type")
            record_id = _decode_identifier(values[1], "record_id")
            if type(values[3]) is not str:
                _fail("INVALID_RECORD_VALUE", "persisted value must be JSON text")
            decoded = json.loads(values[3], parse_int=_parse_json_integer)
            _validate_json_value(decoded, "persisted value")
            if values[3] != _encode_json(decoded):
                _fail("INVALID_RECORD_VALUE", "persisted value is not canonical JSON")
            return {
                "recordType": record_type,
                "recordId": record_id,
                "revision": revision,
                "value": decoded,
            }
        except PostgresStateStoreError as error:
            code = (
                "POSTGRES_PERSISTED_REVISION_INVALID"
                if error.code == "INVALID_REVISION"
                else (
                    "POSTGRES_PERSISTED_IDENTIFIER_INVALID"
                    if error.code == "POSTGRES_PERSISTED_IDENTIFIER_INVALID"
                    else "POSTGRES_PERSISTED_JSON_INVALID"
                )
            )
            details = {
                "recordType": record_type,
                "recordId": record_id,
                "cause": error.code,
            }
            self._enter_safe_mode(code, details)
            raise PostgresStateStoreError(
                code,
                "persisted PostgreSQL record violates the canonical state contract",
                details,
            ) from error
        except Exception as error:
            details = {
                "recordType": record_type,
                "recordId": record_id,
                "cause": type(error).__name__,
            }
            self._enter_safe_mode("POSTGRES_RESULT_INVALID", details)
            raise PostgresStateStoreError(
                "POSTGRES_RESULT_INVALID",
                "PostgreSQL returned an invalid revisioned-record shape",
                details,
            ) from error

    def _execute(self, query: str, params: object = ()) -> int:
        cursor = self._connection.cursor()
        try:
            cursor.execute(query, params)
            return int(cursor.rowcount)
        finally:
            cursor.close()

    def _fetchone(self, query: str, params: object = ()) -> object | None:
        cursor = self._connection.cursor()
        try:
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            cursor.close()

    def _fetchall(self, query: str, params: object = ()) -> list[object]:
        cursor = self._connection.cursor()
        try:
            cursor.execute(query, params)
            return list(cursor.fetchall())
        finally:
            cursor.close()

    def _assert_available(self) -> None:
        if self._mode == POSTGRES_STORE_MODE.SAFE_MODE:
            _fail(
                "STORE_SAFE_MODE",
                "PostgreSQL state store is in SAFE_MODE",
                self._safe_mode_reason,
            )
        if self._closed or bool(getattr(self._connection, "closed", False)):
            _fail("STORE_CLOSED", "PostgreSQL state store is closed")

    def _assert_readable(self) -> None:
        self._assert_available()

    def _assert_mutable(self) -> None:
        self._assert_readable()

    def _enter_safe_mode(
        self,
        code: str,
        details: object = None,
    ) -> None:
        self._mode = POSTGRES_STORE_MODE.SAFE_MODE
        self._safe_mode_reason = {"code": code, "details": details}


def open_postgres_state_store(
    connection_factory: Callable[[], _Connection],
    tenant_id: str,
    workspace_id: str,
) -> PostgresStateStore:
    return PostgresStateStore.open(connection_factory, tenant_id, workspace_id)
