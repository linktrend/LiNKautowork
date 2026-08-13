"""Shared, deterministic delivery coordinator primitives."""

from .config import (
    ConfigError,
    DeliveryConfig,
    ResourceLimits,
    TestProfile,
    load_delivery_config,
)
from .state import (
    CandidateIdentity,
    DeliveryState,
    StateError,
    compute_candidate_identity,
    load_state,
    save_state,
    transition,
)

__all__ = [
    "CandidateIdentity",
    "ConfigError",
    "DeliveryConfig",
    "DeliveryState",
    "ResourceLimits",
    "StateError",
    "TestProfile",
    "compute_candidate_identity",
    "load_delivery_config",
    "load_state",
    "save_state",
    "transition",
]
