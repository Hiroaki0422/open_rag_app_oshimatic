"""Atomic, immutable local artifact storage."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from rag_app.domain.errors import ArtifactConflictError, ArtifactIntegrityError
from rag_app.domain.experiments import ExperimentManifest
from rag_app.domain.identifiers import canonical_json_bytes, content_digest
from rag_app.domain.runs import ArtifactReference


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put_manifest(self, manifest: ExperimentManifest) -> ArtifactReference:
        payload = canonical_json_bytes(manifest)
        checksum = content_digest("artifact", "v1", payload)
        relative = Path("manifests") / f"{checksum.value.rsplit(':', 1)[1]}.json"
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            if destination.read_bytes() != payload:
                raise ArtifactConflictError(f"artifact address already exists: {relative}")
        else:
            fd, temporary_name = tempfile.mkstemp(prefix=".manifest-", dir=destination.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(fd, "wb") as output:
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                try:
                    os.link(temporary, destination)
                except FileExistsError:
                    if destination.read_bytes() != payload:
                        raise ArtifactConflictError(
                            f"artifact address already exists: {relative}"
                        ) from None
            finally:
                temporary.unlink(missing_ok=True)

        return ArtifactReference(
            uri=f"local://{relative.as_posix()}",
            checksum=checksum,
            byte_length=len(payload),
        )

    def read(self, reference: ArtifactReference) -> bytes:
        prefix = "local://"
        if not reference.uri.startswith(prefix):
            raise ArtifactIntegrityError("unsupported artifact URI")
        relative = Path(reference.uri.removeprefix(prefix))
        if relative.is_absolute() or ".." in relative.parts:
            raise ArtifactIntegrityError("artifact URI escapes the configured root")
        payload = (self.root / relative).read_bytes()
        actual = content_digest("artifact", "v1", payload)
        if actual != reference.checksum or len(payload) != reference.byte_length:
            raise ArtifactIntegrityError("artifact checksum or length mismatch")
        return payload

    def health(self) -> tuple[bool, str | None]:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            if not os.access(self.root, os.W_OK):
                return False, "artifact root is not writable"
        except OSError as exc:
            return False, str(exc)
        return True, None
