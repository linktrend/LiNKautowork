"""Installer error types mapped to stable exit codes."""

from __future__ import annotations

from .constants import (
    EXIT_CONFLICT,
    EXIT_DRIFT,
    EXIT_ERROR,
    EXIT_INVALID_PACKAGE,
    EXIT_ROLLBACK_FAILURE,
)


class InstallerError(Exception):
    """Base installer failure."""

    exit_code = EXIT_ERROR

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidPackageError(InstallerError):
    exit_code = EXIT_INVALID_PACKAGE


class ConflictError(InstallerError):
    exit_code = EXIT_CONFLICT


class DriftError(InstallerError):
    exit_code = EXIT_DRIFT


class RollbackError(InstallerError):
    exit_code = EXIT_ROLLBACK_FAILURE
