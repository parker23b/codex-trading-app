from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models.runtime_leadership import RuntimeLease


@dataclass(frozen=True, slots=True)
class RuntimeLeaseAcquisition:
    acquired: bool
    owner_id: str
    current_owner_id: str | None
    expires_at: datetime | None


class RuntimeLeadershipService:
    RUNTIME_LEASE_NAME = "runtime-autonomy"
    DEFAULT_TTL = timedelta(seconds=15)

    def __init__(self, session: Session, *, owner_id: str):
        self.session = session
        self.owner_id = owner_id

    def acquire(
        self,
        *,
        now: datetime | None = None,
        ttl: timedelta | None = None,
    ) -> RuntimeLeaseAcquisition:
        timestamp = _as_utc(now)
        lease_ttl = ttl or self.DEFAULT_TTL
        expires_at = timestamp + lease_ttl
        lease = RuntimeLease(
            lease_name=self.RUNTIME_LEASE_NAME,
            owner_id=self.owner_id,
            acquired_at=timestamp,
            heartbeat_at=timestamp,
            expires_at=expires_at,
            released_at=None,
        )
        self.session.add(lease)
        try:
            self.session.commit()
            return RuntimeLeaseAcquisition(
                acquired=True,
                owner_id=self.owner_id,
                current_owner_id=self.owner_id,
                expires_at=expires_at,
            )
        except IntegrityError:
            self.session.rollback()

        return self._take_existing_lease(now=timestamp, ttl=lease_ttl)

    def renew(
        self,
        *,
        now: datetime | None = None,
        ttl: timedelta | None = None,
    ) -> bool:
        timestamp = _as_utc(now)
        lease_ttl = ttl or self.DEFAULT_TTL
        result = self.session.execute(
            update(RuntimeLease)
            .where(RuntimeLease.lease_name == self.RUNTIME_LEASE_NAME)
            .where(RuntimeLease.owner_id == self.owner_id)
            .where(RuntimeLease.released_at.is_(None))
            .values(heartbeat_at=timestamp, expires_at=timestamp + lease_ttl)
        )
        self.session.commit()
        return result.rowcount == 1

    def release(self, *, now: datetime | None = None) -> bool:
        timestamp = _as_utc(now)
        result = self.session.execute(
            update(RuntimeLease)
            .where(RuntimeLease.lease_name == self.RUNTIME_LEASE_NAME)
            .where(RuntimeLease.owner_id == self.owner_id)
            .where(RuntimeLease.released_at.is_(None))
            .values(released_at=timestamp, expires_at=timestamp)
        )
        self.session.commit()
        return result.rowcount == 1

    def _take_existing_lease(
        self, *, now: datetime, ttl: timedelta
    ) -> RuntimeLeaseAcquisition:
        expires_at = now + ttl
        result = self.session.execute(
            update(RuntimeLease)
            .where(RuntimeLease.lease_name == self.RUNTIME_LEASE_NAME)
            .where(
                or_(
                    RuntimeLease.owner_id == self.owner_id,
                    RuntimeLease.released_at.is_not(None),
                    RuntimeLease.expires_at <= now,
                )
            )
            .values(
                owner_id=self.owner_id,
                acquired_at=now,
                heartbeat_at=now,
                expires_at=expires_at,
                released_at=None,
            )
        )
        if result.rowcount == 1:
            self.session.commit()
            return RuntimeLeaseAcquisition(
                acquired=True,
                owner_id=self.owner_id,
                current_owner_id=self.owner_id,
                expires_at=expires_at,
            )
        self.session.rollback()
        lease = self.session.get(RuntimeLease, self.RUNTIME_LEASE_NAME)
        return RuntimeLeaseAcquisition(
            acquired=False,
            owner_id=self.owner_id,
            current_owner_id=lease.owner_id if lease is not None else None,
            expires_at=lease.expires_at if lease is not None else None,
        )


def _as_utc(value: datetime | None = None) -> datetime:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)
