"""Domain failures with stable, machine-readable reason codes."""


class DomainError(ValueError):
    reason_code = "domain.invalid"


class InvalidRunTransitionError(DomainError):
    reason_code = "run.invalid_transition"


class RunNotFoundError(DomainError):
    reason_code = "run.not_found"


class IdempotencyConflictError(DomainError):
    reason_code = "run.idempotency_conflict"


class ArtifactConflictError(DomainError):
    reason_code = "artifact.immutable_conflict"


class ArtifactIntegrityError(DomainError):
    reason_code = "artifact.integrity_failure"
