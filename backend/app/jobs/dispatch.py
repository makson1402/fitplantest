"""Push delivery of stored notifications (B-26; FR-R7).

Every notification row that has no `sent_at` is pushed to the devices of its user, then marked sent. Because the rows
are the queue, a crash between creating a notification and pushing it loses nothing: the next run delivers it. A row
is claimed with `FOR UPDATE SKIP LOCKED`, so two dispatchers never push the same notification twice.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from app.core.clock import Clock
from app.repositories import UnitOfWorkFactory
from app.services.push import PushDeliveryError, PushMessage, PushSender

log = logging.getLogger(__name__)

BATCH = 200
GIVE_UP_AFTER = timedelta(hours=24)  # a push that could not be delivered for a day is no longer news


@dataclass
class DispatchStats:
    sent: int = 0          # notifications handled (pushed, or nothing to push to)
    pushes: int = 0        # pushes accepted by the push service
    removed_tokens: int = 0
    retry_later: int = 0


async def dispatch_pending(uow_factory: UnitOfWorkFactory, clock: Clock, sender: PushSender) -> DispatchStats:
    stats = DispatchStats()
    async with uow_factory() as uow:
        ids = await uow.schedule.unsent_notification_ids(BATCH)
    for notification_id in ids:
        try:
            await _dispatch_one(uow_factory, clock, sender, notification_id, stats)
        except Exception:  # noqa: BLE001
            stats.retry_later += 1
            log.exception("push dispatch failed for notification %s", notification_id)
    return stats


async def _dispatch_one(uow_factory: UnitOfWorkFactory, clock: Clock, sender: PushSender, notification_id: int,
                        stats: DispatchStats) -> None:
    async with uow_factory() as uow:
        claimed = await uow.schedule.claim_unsent_notification(notification_id)
        if claimed is None:
            return  # sent meanwhile, or another dispatcher holds it
        notification, user_id = claimed
        tokens = await uow.schedule.push_tokens(user_id)
        invalid: list[str] = []
        if tokens:
            messages = [PushMessage(t.token, notification.title, notification.message,
                                    {**notification.data, "notification_id": notification.id}) for t in tokens]
            try:
                result = await sender.send(messages)
            except PushDeliveryError as exc:
                if clock.now() - notification.created_at < GIVE_UP_AFTER:
                    stats.retry_later += 1
                    log.warning("push service unavailable (%s); notification %s stays queued", exc, notification.id)
                    return
                log.warning("giving up on the push of notification %s", notification.id)
            else:
                stats.pushes += result.delivered
                invalid = result.invalid_tokens
        await uow.schedule.delete_push_tokens_by_value(invalid)
        await uow.schedule.mark_notification_sent(notification.id, clock.now())
        await uow.commit()
        stats.sent += 1
        stats.removed_tokens += len(invalid)
