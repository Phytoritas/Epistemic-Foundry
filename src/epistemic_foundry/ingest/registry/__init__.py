"""K01 immutable document-registration public boundary."""

from .errors import *  # noqa: F403
from .hash import (
    canonicalize_identifier_hints,
    compute_registration_hash,
    compute_request_hash,
    seal_registration_payload,
    seal_request_payload,
    verify_registration_payload,
    verify_request_payload,
)
from .lineage import (
    assert_registration_immutable,
    validate_registration_lineage,
    validate_registration_predecessor,
)
from .models import (
    ActionIntentEvidence,
    ArtifactPublication,
    ArtifactReceiptEvidence,
    ArtifactReservation,
    CasOutcome,
    CommittedRegistration,
    DocumentRegistration,
    DocumentRegistrationRequest,
    EffectReceiptEvidence,
    EffectReservation,
    LeaseAuthorization,
    LedgerPublication,
    LedgerReservation,
    RegistrationReservation,
    ResolvedArtifact,
    SourcePublication,
)
from .repository import RegistrationPorts
from .service import (
    REGISTER_SOURCE_ACTION_TYPE,
    REGISTER_SOURCE_REQUIRED_CAPABILITIES,
    register_document,
)

__all__ = [
    "ActionIntentEvidence",
    "ArtifactPublication",
    "ArtifactReceiptEvidence",
    "ArtifactReservation",
    "CasOutcome",
    "CommittedRegistration",
    "DocumentRegistration",
    "DocumentRegistrationRequest",
    "EffectReceiptEvidence",
    "EffectReservation",
    "LeaseAuthorization",
    "LedgerPublication",
    "LedgerReservation",
    "RegistrationPorts",
    "RegistrationReservation",
    "ResolvedArtifact",
    "SourcePublication",
    "assert_registration_immutable",
    "canonicalize_identifier_hints",
    "compute_registration_hash",
    "compute_request_hash",
    "register_document",
    "REGISTER_SOURCE_ACTION_TYPE",
    "REGISTER_SOURCE_REQUIRED_CAPABILITIES",
    "seal_registration_payload",
    "seal_request_payload",
    "validate_registration_lineage",
    "validate_registration_predecessor",
    "verify_registration_payload",
    "verify_request_payload",
]
