from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import SplitResult, urlsplit


IG_DEMO_BASE_URL = "https://demo-api.ig.com/gateway/deal"
IG_LIVE_BASE_URL = "https://api.ig.com/gateway/deal"


class BrokerEnvironment(str, Enum):
    DEMO = "DEMO"
    LIVE = "LIVE"


class BrokerEndpointClassification(str, Enum):
    IG_DEMO_GATEWAY = "IG_DEMO_GATEWAY"
    IG_LIVE_GATEWAY = "IG_LIVE_GATEWAY"
    TEST_ONLY_CUSTOM = "TEST_ONLY_CUSTOM"


@dataclass(frozen=True, slots=True)
class ClassifiedBrokerEndpoint:
    environment: BrokerEnvironment
    endpoint_classification: BrokerEndpointClassification
    base_url: str


@dataclass(frozen=True, slots=True)
class _NormalizedUrlParts:
    scheme: str
    host: str
    port: int
    path: str


def classify_ig_api_base_url(raw_url: str) -> ClassifiedBrokerEndpoint:
    parsed = _parse_and_validate_https_url(raw_url)
    normalized = _normalize_url_parts(parsed)

    for base_url, environment, classification in _CANONICAL_ENDPOINTS:
        if normalized == _normalize_url_parts(urlsplit(base_url)):
            return ClassifiedBrokerEndpoint(
                environment=environment,
                endpoint_classification=classification,
                base_url=base_url,
            )

    raise ValueError(
        "IG_API_BASE_URL must exactly match the canonical IG demo or live gateway."
    )


def normalize_test_broker_base_url(raw_url: str) -> str:
    parsed = _parse_and_validate_https_url(raw_url)
    normalized = _normalize_url_parts(parsed)
    default_port = 443
    netloc = normalized.host
    if normalized.port != default_port:
        netloc = f"{netloc}:{normalized.port}"
    return f"{normalized.scheme}://{netloc}{normalized.path}"


def _parse_and_validate_https_url(raw_url: str) -> SplitResult:
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ValueError("IG_API_BASE_URL must be a non-empty HTTPS URL.")

    parsed = urlsplit(raw_url.strip())
    if parsed.scheme.lower() != "https":
        raise ValueError("IG_API_BASE_URL must use HTTPS.")
    if parsed.username or parsed.password:
        raise ValueError("IG_API_BASE_URL must not include embedded credentials.")
    if parsed.hostname is None:
        raise ValueError("IG_API_BASE_URL must include a hostname.")
    if parsed.query or parsed.fragment:
        raise ValueError("IG_API_BASE_URL must not include query or fragment values.")
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise ValueError("IG_API_BASE_URL contains an invalid port.")
    if not parsed.path:
        raise ValueError("IG_API_BASE_URL must include the IG gateway path.")
    return parsed


def _normalize_url_parts(parsed: SplitResult) -> _NormalizedUrlParts:
    normalized_path = parsed.path.rstrip("/") or "/"
    return _NormalizedUrlParts(
        scheme=parsed.scheme.lower(),
        host=parsed.hostname.lower() if parsed.hostname else "",
        port=parsed.port or 443,
        path=normalized_path,
    )


_CANONICAL_ENDPOINTS = (
    (
        IG_DEMO_BASE_URL,
        BrokerEnvironment.DEMO,
        BrokerEndpointClassification.IG_DEMO_GATEWAY,
    ),
    (
        IG_LIVE_BASE_URL,
        BrokerEnvironment.LIVE,
        BrokerEndpointClassification.IG_LIVE_GATEWAY,
    ),
)
