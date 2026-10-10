from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .database import Database, StoredEvent

DEFAULT_TIME_GOAL = 3600
DEFAULT_OUTPUT_GOAL = 20
DEFAULT_WEEKLY_GOAL = 5
MIN_MEANINGFUL_SECONDS = 900
DISTRIBUTION_DAYS = 28
LEVEL_XP = 500


def _is_active_event(event: StoredEvent) -> bool:
    """Return whether an event is verified evidence of active development time."""
    return (
        event.kind == "heartbeat" and event.source in {"editor", "terminal"}
    ) or (event.kind == "ai_activity" and event.source == "ai")


@dataclass(slots=True)
class DayStats:
    active_seconds: int = 0
    output_points: int = 0
    event_count: int = 0
    editor_seconds: int = 0

    @property
    def meaningful(self) -> bool:
        return self.active_seconds >= MIN_MEANINGFUL_SECONDS or self.output_points >= 5


def output_points(events: list[StoredEvent]) -> int:
    points = 0
    editor_seconds = 0
    for event in events:
        magnitude = event.magnitude if event.magnitude is not None else 1
        if event.kind == "commit":
            points += 10 * max(1, magnitude)
        elif event.kind == "git_snapshot":
            points += min(5, magnitude)
        elif event.kind == "test_run":
            points += 4 if event.success else 1
        elif event.kind == "build":
            points += 6 if event.success else 1
        elif event.kind == "milestone":
            points += 15 * magnitude
        elif event.kind == "heartbeat" and event.source == "editor":
            editor_seconds += event.duration_seconds
    return points + editor_seconds // 900


def dashboard(database: Database, selected: date, timezone_name: str) -> dict[str, Any]:
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("unknown timezone") from exc

    end_local = datetime.combine(selected + timedelta(days=1), time.min, zone)
    # Full history keeps cumulative XP, long streaks, achievements, and the last
    # 28 active days exact. The API never returns raw records from this query.
    events = database.events_between(
        datetime(1970, 1, 1, tzinfo=timezone.utc), end_local.astimezone(timezone.utc)
    )
    grouped: dict[date, list[StoredEvent]] = defaultdict(list)
    for event in events:
        grouped[event.occurred_at.astimezone(zone).date()].append(event)

    days: dict[date, DayStats] = {}
    for local_day, day_events in grouped.items():
        days[local_day] = DayStats(
            active_seconds=sum(
                event.duration_seconds for event in day_events if _is_active_event(event)
            ),
            output_points=output_points(day_events),
            event_count=len(day_events),
            editor_seconds=sum(
                event.duration_seconds
                for event in day_events
                if event.source == "editor" and event.kind == "heartbeat"
            ),
        )

    today = days.get(selected, DayStats())
    prior_active = [
        days[day]
        for day in sorted(days, reverse=True)
        if day < selected and days[day].meaningful
    ][:28]
    time_goal = _adaptive_time_goal(prior_active)
    output_goal = _adaptive_output_goal(prior_active)

    trailing_dates = [selected - timedelta(days=offset) for offset in range(6, -1, -1)]
    active_days = sum(days.get(day, DayStats()).meaningful for day in trailing_dates)
    weekly_goal = _adaptive_weekly_goal(days, selected)
    streak = _streak(days, selected)
    cumulative_xp = sum(_daily_xp(stats) for day, stats in days.items() if day <= selected)
    level = cumulative_xp // LEVEL_XP + 1

    selected_events = sorted(grouped.get(selected, []), key=lambda event: event.occurred_at, reverse=True)
    recent = [
        {
            "occurred_at": _timestamp(event.occurred_at),
            "source": event.source,
            "kind": event.kind,
            "label": _event_label(event),
        }
        for event in selected_events[:20]
    ]
    active_minutes = today.active_seconds // 60
    commits = sum(
        max(1, event.magnitude or 1) for event in selected_events if event.kind == "commit"
    )
    successful_checks = sum(
        event.kind in {"test_run", "build"} and event.success is True
        for event in selected_events
    )
    focus_sessions = _focus_sessions(selected_events)
    trend = [
        {
            "date": day.isoformat(),
            "active_minutes": round(days.get(day, DayStats()).active_seconds / 60, 2),
            "output_points": days.get(day, DayStats()).output_points,
        }
        for day in (selected - timedelta(days=offset) for offset in range(13, -1, -1))
    ]
    distribution_start = selected - timedelta(days=DISTRIBUTION_DAYS - 1)
    distribution_events = [
        event
        for event in events
        if distribution_start <= event.occurred_at.astimezone(zone).date() <= selected
    ]
    insight = (
        f"Goals blend your last {len(prior_active)} meaningful active "
        f"{'day' if len(prior_active) == 1 else 'days'} with healthy defaults."
        if prior_active
        else "Goals start at healthy defaults and adapt gradually after meaningful active days."
    )

    # The original aggregate fields remain for older clients. The top-level
    # metrics and collections exactly match DashboardSnapshot's coding keys.
    return {
        "date": selected.isoformat(),
        "timezone": timezone_name,
        "rings": {
            "time": _ring(today.active_seconds, time_goal),
            "output": _ring(today.output_points, output_goal),
            "consistency": _ring(active_days, weekly_goal),
        },
        "active_seconds": today.active_seconds,
        "output_points": today.output_points,
        "active_days_last_7": active_days,
        "event_count": today.event_count,
        "streak_days": streak,
        "recent_events": recent,
        "generated_at": _timestamp(datetime.now(timezone.utc)),
        "time": {"kind": "time", "value": round(today.active_seconds / 60, 2), "goal": time_goal / 60, "unit": "min"},
        "output": {"kind": "output", "value": today.output_points, "goal": output_goal, "unit": "pts"},
        "consistency": {"kind": "consistency", "value": active_days, "goal": weekly_goal, "unit": "days"},
        "xp": cumulative_xp,
        "level": level,
        "xp_in_level": cumulative_xp % LEVEL_XP,
        "xp_for_next_level": LEVEL_XP,
        "streak": streak,
        "goals": {
            "active_minutes": time_goal // 60,
            "output_points": output_goal,
            "active_days": weekly_goal,
            "insight": insight,
        },
        "trend": trend,
        "languages": _distribution(distribution_events, "language"),
        "projects": _distribution(distribution_events, "project"),
        "achievements": _achievements(events, grouped, days),
        "quests": [
            {"id": "daily-focus", "title": "Daily focus", "current": active_minutes, "target": time_goal // 60, "unit": "min"},
            {"id": "daily-output", "title": "Make progress", "current": today.output_points, "target": output_goal, "unit": "pts"},
            {"id": "weekly-consistency", "title": "Stay consistent", "current": active_days, "target": weekly_goal, "unit": "days"},
        ],
        "summary": {
            "active_minutes": active_minutes,
            "commits": commits,
            "successful_checks": successful_checks,
            "focus_sessions": focus_sessions,
        },
    }


def _ring(value: int, goal: int) -> dict[str, int | float]:
    return {"value": value, "goal": goal, "progress": round(min(value / goal, 1.0), 4)}


def _daily_xp(stats: DayStats) -> int:
    return min(
        200,
        round(min(stats.active_seconds / 60, 120) * 0.5 + min(stats.output_points, 100) * 1.5),
    )


def _adaptive_time_goal(active_days: list[DayStats]) -> int:
    if not active_days:
        return DEFAULT_TIME_GOAL
    average = sum(day.active_seconds for day in active_days) / len(active_days)
    blended = DEFAULT_TIME_GOAL * 0.75 + average * 0.25
    bounded = min(7200, max(1800, blended))
    return int(round(bounded / 300) * 300)


def _adaptive_output_goal(active_days: list[DayStats]) -> int:
    if not active_days:
        return DEFAULT_OUTPUT_GOAL
    average = sum(day.output_points for day in active_days) / len(active_days)
    return round(min(100, max(10, DEFAULT_OUTPUT_GOAL * 0.75 + average * 0.25)))


def _adaptive_weekly_goal(days: dict[date, DayStats], selected: date) -> int:
    weekly_counts = []
    for week in range(4):
        week_end = selected - timedelta(days=7 * week + 1)
        weekly_counts.append(
            sum(
                days.get(week_end - timedelta(days=offset), DayStats()).meaningful
                for offset in range(7)
            )
        )
    if not any(weekly_counts):
        return DEFAULT_WEEKLY_GOAL
    average = sum(weekly_counts) / len(weekly_counts)
    return round(min(6, max(3, DEFAULT_WEEKLY_GOAL * 0.75 + average * 0.25)))


def _streak(days: dict[date, DayStats], selected: date) -> int:
    count = 0
    cursor = selected
    while days.get(cursor, DayStats()).meaningful:
        count += 1
        cursor -= timedelta(days=1)
    return count


def _distribution(events: list[StoredEvent], attribute: str) -> list[dict[str, str | float]]:
    weights: dict[str, int] = defaultdict(int)
    for event in events:
        name = getattr(event, attribute)
        if name:
            # Duration is the best measure of attention. Zero-duration output
            # records still contribute one minute so real projects are visible.
            weights[name] += event.duration_seconds or 60 * max(1, event.magnitude or 1)
    if not weights:
        return []
    ranked = sorted(weights.items(), key=lambda item: (-item[1], item[0].casefold()))
    if len(ranked) > 5:
        ranked = ranked[:4] + [("Other", sum(value for _, value in ranked[4:]))]
    total = sum(value for _, value in ranked)
    percentages = [round(value * 100 / total, 1) for _, value in ranked]
    percentages[0] = round(percentages[0] + 100 - sum(percentages), 1)
    return [{"name": item[0], "value": percentages[index]} for index, item in enumerate(ranked)]


def _focus_sessions(events: list[StoredEvent]) -> int:
    active = sorted(
        (
            event
            for event in events
            if _is_active_event(event) and event.duration_seconds > 0
        ),
        key=lambda item: item.occurred_at,
    )
    if not active:
        return 0
    sessions: list[int] = []
    duration = 0
    previous: datetime | None = None
    for event in active:
        if previous is not None and event.occurred_at - previous > timedelta(minutes=30):
            sessions.append(duration)
            duration = 0
        duration += event.duration_seconds
        previous = event.occurred_at
    sessions.append(duration)
    return sum(duration >= 25 * 60 for duration in sessions)


def _achievements(
    events: list[StoredEvent],
    grouped: dict[date, list[StoredEvent]],
    days: dict[date, DayStats],
) -> list[dict[str, str]]:
    if not events:
        return []
    achievements: list[dict[str, str]] = []
    first = min(events, key=lambda event: (event.occurred_at, event.id))
    achievements.append(
        {
            "id": "first-activity",
            "title": "First Loop",
            "detail": "Recorded your first activity",
            "unlocked_at": _timestamp(first.occurred_at),
            "symbol": "play.fill",
        }
    )
    milestones = sorted(
        (item for item in events if item.kind == "milestone"),
        key=lambda item: (item.occurred_at, item.id),
    )[-14:]
    for event in milestones:
        achievements.append(
            {
                "id": f"milestone-{event.id}",
                "title": event.label or "Milestone",
                "detail": "Completed a milestone",
                "unlocked_at": _timestamp(event.occurred_at),
                "symbol": "sparkles",
            }
        )

    consecutive = 0
    thresholds = {3, 7, 14, 30}
    for day in sorted(days):
        if days[day].meaningful:
            previous = day - timedelta(days=1)
            consecutive = consecutive + 1 if days.get(previous, DayStats()).meaningful else 1
            if consecutive in thresholds:
                threshold_event = _meaningful_threshold_event(grouped[day])
                achievements.append(
                    {
                        "id": f"streak-{consecutive}",
                        "title": f"{consecutive}-Day Streak",
                        "detail": f"Reached {consecutive} consecutive meaningful days",
                        "unlocked_at": _timestamp(threshold_event.occurred_at),
                        "symbol": "flame.fill",
                    }
                )
        else:
            consecutive = 0
    return sorted(achievements, key=lambda item: (item["unlocked_at"], item["id"]), reverse=True)[:20]


def _meaningful_threshold_event(events: list[StoredEvent]) -> StoredEvent:
    chronological = sorted(events, key=lambda item: (item.occurred_at, item.id))
    active_seconds = 0
    seen: list[StoredEvent] = []
    for event in chronological:
        seen.append(event)
        if _is_active_event(event):
            active_seconds += event.duration_seconds
        if active_seconds >= MIN_MEANINGFUL_SECONDS or output_points(seen) >= 5:
            return event
    # Callers only use this for a meaningful day, but retaining a concrete
    # event makes this helper safe if scoring rules evolve independently.
    return chronological[-1]


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _event_label(event: StoredEvent) -> str:
    if event.label:
        return event.label
    if event.entity:
        return event.entity
    if event.project:
        return event.project
    return event.kind.replace("_", " ")
