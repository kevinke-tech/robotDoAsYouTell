"""
BackgroundRunner — manages timers and vision watchers.

Each active item has:
  id           — short unique id ('timer_abcd1234' / 'watch_abcd1234')
  kind         — 'timer' | 'vision'
  label        — short human-readable label
  created_at   — ISO timestamp
  task         — asyncio.Task (timers only)
  ...kind-specific fields...

State changes (add/remove of any vision watcher) trigger a broadcast of
{type: 'frames_required', value: bool} so the frontend starts/stops streaming
camera frames to /ws/frames.

Fires push {type: 'speak', text, from, collide: 'tone_interrupt'} over the same
/ws/output channel; the frontend plays a short tone then speaks via TTS.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

import runtime
from frame_filter import is_duplicate, phash_from_b64

TriggerCheckFn = Callable[[str, str], Awaitable[tuple[bool, str]]]
OutputSendFn = Callable[[dict], Awaitable[None]]

# Where active timers/watchers + the spawning-skills set are persisted across
# restarts. logs/ is already in .gitignore, so this stays out of git.
STATE_FILE = Path(__file__).parent / "logs" / "runner_state.json"

# A past-due timer found on restart fires only if it was due within this window.
# Older deadlines are silently dropped (you don't want a "drink water" reminder
# from 3 days ago to fire when you boot the laptop).
STALE_TIMER_GRACE_SEC = 5 * 60


class BackgroundRunner:
    def __init__(self, output_send: OutputSendFn) -> None:
        self._output_send = output_send
        self._active: dict[str, dict] = {}
        self._prev_vision_count = 0
        # Skills known to spawn long-running active instances. Used by the
        # /skills endpoint to decide whether to render a "Run" button (one-shot)
        # or an activation checkbox (background-spawning) in the frontend.
        # Seeded for the hardcoded generic skills; populated lazily for any
        # other skill the first time it calls add_timer / add_vision_watcher.
        self._spawning_skills: set[str] = {"generic_timer", "generic_vision_watcher"}
        # Disabled during restore_from_disk so the file we're reading from isn't
        # rewritten halfway through. Server enables it after restore completes.
        self._persist_enabled = False

    def is_spawning_skill(self, name: str) -> bool:
        return name in self._spawning_skills

    def mark_spawning_skill(self, name: str) -> None:
        self._spawning_skills.add(name)
        self._save()

    # ───── persistence ─────

    def _serialize_instance(self, id_: str, info: dict) -> dict:
        kind = info["kind"]
        base = {
            "id": id_,
            "kind": kind,
            "label": info.get("label"),
            "source_skill": info.get("source_skill"),
            "created_at": info.get("created_at"),
            "is_active": bool(info.get("is_active", False)),
        }
        if kind == "timer":
            base["message"] = info.get("message", "")
            base["delay_seconds"] = info.get("delay_seconds")
            base["fire_at"] = info.get("fire_at")
        elif kind == "vision":
            base["trigger"] = info.get("trigger", "")
            base["say_on_match"] = info.get("say_on_match", "")
            base["cooldown_sec"] = info.get("cooldown_sec", 30.0)
            base["rate_hz"] = info.get("rate_hz", 1.0)
        return base

    def _save(self) -> None:
        if not self._persist_enabled:
            return
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "spawning_skills": sorted(self._spawning_skills),
                "instances": [self._serialize_instance(id_, info) for id_, info in self._active.items()],
            }
            tmp = STATE_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            tmp.replace(STATE_FILE)
        except Exception as e:
            print(f"[bg/persist] save failed: {e}", flush=True)

    async def restore_from_disk(self) -> None:
        """Re-create timers + vision watchers from logs/runner_state.json.

        Called once at server startup BEFORE persist is enabled, so add_*()
        calls below don't trigger writes back to the file we're reading.

        Instances retain their original id; is_active is preserved. Stale
        past-due timers are kept as inactive entries so the user can re-run
        them, instead of being silently dropped.
        """
        if not STATE_FILE.exists():
            self._persist_enabled = True
            return
        try:
            payload = json.loads(STATE_FILE.read_text())
        except Exception as e:
            print(f"[bg/persist] load failed: {e}", flush=True)
            self._persist_enabled = True
            return

        for name in payload.get("spawning_skills") or []:
            self._spawning_skills.add(name)

        # New format key "instances" — fall back to legacy "active" for migration.
        items = payload.get("instances")
        if items is None:
            items = payload.get("active") or []

        now = time.time()
        n_timer_active = n_timer_fired_late = n_timer_inactive = 0
        n_vision_active = n_vision_inactive = 0

        for inst in items:
            kind = inst.get("kind")
            id_ = inst.get("id")
            if not id_:
                continue
            was_active = bool(inst.get("is_active", True))

            if kind == "timer":
                delay_seconds = float(inst.get("delay_seconds") or 0)
                fire_at = float(inst.get("fire_at") or 0)
                remaining = fire_at - now
                # If marked active and still in the future → resume the countdown.
                # If marked active but past-due within grace → fire shortly.
                # If marked active but very stale → demote to inactive.
                # If marked inactive → restore as inactive (keep the config).
                if was_active and remaining > 0:
                    self._instantiate_timer(
                        id_=id_,
                        delay_seconds=delay_seconds or remaining,
                        message=inst.get("message", ""),
                        label=inst.get("label"),
                        source_skill=inst.get("source_skill"),
                        created_at=inst.get("created_at"),
                        fire_at=fire_at,
                        is_active=True,
                    )
                    n_timer_active += 1
                elif was_active and -remaining <= STALE_TIMER_GRACE_SEC:
                    self._instantiate_timer(
                        id_=id_,
                        delay_seconds=delay_seconds,
                        message=inst.get("message", ""),
                        label=inst.get("label"),
                        source_skill=inst.get("source_skill"),
                        created_at=inst.get("created_at"),
                        fire_at=now + 0.5,
                        is_active=True,
                    )
                    n_timer_fired_late += 1
                else:
                    self._instantiate_timer(
                        id_=id_,
                        delay_seconds=delay_seconds,
                        message=inst.get("message", ""),
                        label=inst.get("label"),
                        source_skill=inst.get("source_skill"),
                        created_at=inst.get("created_at"),
                        fire_at=None,
                        is_active=False,
                    )
                    n_timer_inactive += 1
            elif kind == "vision":
                self._instantiate_vision(
                    id_=id_,
                    trigger=inst.get("trigger", ""),
                    say_on_match=inst.get("say_on_match", ""),
                    cooldown_sec=float(inst.get("cooldown_sec") or 30.0),
                    rate_hz=float(inst.get("rate_hz") or 1.0),
                    label=inst.get("label"),
                    source_skill=inst.get("source_skill"),
                    created_at=inst.get("created_at"),
                    is_active=was_active,
                )
                if was_active:
                    n_vision_active += 1
                else:
                    n_vision_inactive += 1

        await self._maybe_announce_frames_change()

        print(
            f"[bg/persist] restored: timer_active={n_timer_active} "
            f"timer_fired_late={n_timer_fired_late} timer_inactive={n_timer_inactive} "
            f"vision_active={n_vision_active} vision_inactive={n_vision_inactive}",
            flush=True,
        )
        self._persist_enabled = True
        # Rewrite to canonicalize the file with the current is_active flags.
        self._save()

    # ───── inspection ─────

    def list(self) -> list[dict]:
        return [
            {"id": id_, **{k: v for k, v in info.items() if k not in {"task", "phash_last"}}}
            for id_, info in self._active.items()
        ]

    def has_vision_watchers(self) -> bool:
        return any(
            info["kind"] == "vision" and info.get("is_active")
            for info in self._active.values()
        )

    # ───── lifecycle ─────

    async def _broadcast_state_change(self) -> None:
        try:
            await self._output_send({"type": "skills_changed"})
        except Exception as e:
            print(f"[bg] skills_changed broadcast failed: {e}", flush=True)

    async def stop(self, id_: str) -> bool:
        """Soft-stop: cancel the running task, mark inactive, keep the entry.

        The user can re-activate the same id later via start(). To purge an
        entry permanently, use delete().
        """
        info = self._active.get(id_)
        if info is None:
            return False
        if not info.get("is_active"):
            return True  # already stopped
        task = info.get("task")
        if task and not task.done():
            task.cancel()
        info.pop("task", None)
        info["is_active"] = False
        await self._maybe_announce_frames_change()
        self._save()
        await self._broadcast_state_change()
        print(f"[bg] -stop {id_}", flush=True)
        return True

    async def start(self, id_: str) -> bool:
        """Re-activate a previously-stopped instance. New timer countdown
        starts from the original delay_seconds. Returns False if the id is
        unknown."""
        info = self._active.get(id_)
        if info is None:
            return False
        if info.get("is_active"):
            return True
        kind = info["kind"]
        if kind == "timer":
            info["fire_at"] = time.time() + float(info.get("delay_seconds") or 0)
            info["is_active"] = True
            info["task"] = asyncio.create_task(self._run_timer(id_))
        elif kind == "vision":
            info["is_active"] = True
            info["last_eval_t"] = 0.0
            info["last_fire_t"] = 0.0
            info["phash_last"] = None
        await self._maybe_announce_frames_change()
        self._save()
        await self._broadcast_state_change()
        print(f"[bg] +start {id_} ({kind})", flush=True)
        return True

    async def delete(self, id_: str) -> bool:
        """Permanently remove an instance entry."""
        info = self._active.pop(id_, None)
        if info is None:
            return False
        task = info.get("task")
        if task and not task.done():
            task.cancel()
        await self._maybe_announce_frames_change()
        self._save()
        await self._broadcast_state_change()
        print(f"[bg] -delete {id_}", flush=True)
        return True

    async def stop_all(self) -> int:
        """Soft-stop all currently-running instances."""
        ids = [id_ for id_, info in self._active.items() if info.get("is_active")]
        for id_ in ids:
            await self.stop(id_)
        return len(ids)

    async def stop_by_source_skill(self, skill_name: str) -> int:
        """Soft-stop all currently-running instances owned by a skill."""
        ids = [
            id_ for id_, info in self._active.items()
            if info.get("source_skill") == skill_name and info.get("is_active")
        ]
        for id_ in ids:
            await self.stop(id_)
        return len(ids)

    async def delete_by_source_skill(self, skill_name: str) -> int:
        """Permanently drop all instance entries owned by a skill — used by
        DELETE /skills/{name} so removing a skill also clears its history."""
        ids = [id_ for id_, info in self._active.items() if info.get("source_skill") == skill_name]
        for id_ in ids:
            await self.delete(id_)
        return len(ids)

    def instances_for_skill(self, skill_name: str) -> "list[str]":
        return [id_ for id_, info in self._active.items() if info.get("source_skill") == skill_name]

    # ───── timer ─────

    def _instantiate_timer(
        self,
        id_: str,
        delay_seconds: float,
        message: str,
        label: Optional[str],
        source_skill: Optional[str],
        created_at: Optional[str],
        fire_at: Optional[float],
        is_active: bool,
    ) -> None:
        """Internal: insert a timer entry. Used by both add_timer (new) and
        restore_from_disk (preserve original id)."""
        info = {
            "kind": "timer",
            "delay_seconds": float(delay_seconds),
            "fire_at": fire_at,
            "message": message,
            "label": label or (message[:48] if message else "(timer)"),
            "source_skill": source_skill,
            "created_at": created_at or datetime.now().isoformat(timespec="seconds"),
            "is_active": False,
        }
        if source_skill:
            self._spawning_skills.add(source_skill)
        self._active[id_] = info
        if is_active:
            info["is_active"] = True
            info["task"] = asyncio.create_task(self._run_timer(id_))

    async def add_timer(
        self,
        delay_seconds: float,
        message: str,
        label: Optional[str] = None,
        source_skill: Optional[str] = None,
    ) -> str:
        id_ = f"timer_{uuid.uuid4().hex[:8]}"
        self._instantiate_timer(
            id_=id_,
            delay_seconds=delay_seconds,
            message=message,
            label=label,
            source_skill=source_skill or runtime.get_current_skill(),
            created_at=None,
            fire_at=time.time() + float(delay_seconds),
            is_active=True,
        )
        await self._maybe_announce_frames_change()
        self._save()
        await self._broadcast_state_change()
        print(f"[bg] +timer {id_} delay={delay_seconds}s msg={message!r}", flush=True)
        return id_

    async def _run_timer(self, id_: str) -> None:
        info = self._active.get(id_)
        if info is None:
            return
        try:
            # Sleep until fire_at — using fire_at instead of delay_seconds lets
            # restored timers honour the original deadline (remaining time).
            now = time.time()
            sleep_for = max(0.0, float(info.get("fire_at") or now) - now)
            await asyncio.sleep(sleep_for)
            await self._fire(id_, info["message"])
        except asyncio.CancelledError:
            print(f"[bg] timer {id_} cancelled", flush=True)
            return
        finally:
            # Soft-stop: clear the task and mark inactive, keep the entry so the
            # user can re-arm via start(). The user's only way to purge is delete().
            cur = self._active.get(id_)
            if cur is not None:
                cur.pop("task", None)
                cur["is_active"] = False
            await self._maybe_announce_frames_change()
            self._save()
            await self._broadcast_state_change()

    # ───── vision watcher ─────

    def _instantiate_vision(
        self,
        id_: str,
        trigger: str,
        say_on_match: str,
        cooldown_sec: float,
        rate_hz: float,
        label: Optional[str],
        source_skill: Optional[str],
        created_at: Optional[str],
        is_active: bool,
    ) -> None:
        info = {
            "kind": "vision",
            "trigger": trigger,
            "say_on_match": say_on_match,
            "cooldown_sec": float(cooldown_sec),
            "rate_hz": float(rate_hz),
            "label": label or (trigger[:48] if trigger else "(watch)"),
            "source_skill": source_skill,
            "created_at": created_at or datetime.now().isoformat(timespec="seconds"),
            "last_eval_t": 0.0,
            "last_fire_t": 0.0,
            "phash_last": None,
            "eval_count": 0,
            "match_count": 0,
            "is_active": bool(is_active),
        }
        if source_skill:
            self._spawning_skills.add(source_skill)
        self._active[id_] = info

    async def add_vision_watcher(
        self,
        trigger: str,
        say_on_match: str,
        cooldown_sec: float = 30.0,
        rate_hz: float = 1.0,
        label: Optional[str] = None,
        source_skill: Optional[str] = None,
    ) -> str:
        id_ = f"watch_{uuid.uuid4().hex[:8]}"
        self._instantiate_vision(
            id_=id_,
            trigger=trigger,
            say_on_match=say_on_match,
            cooldown_sec=cooldown_sec,
            rate_hz=rate_hz,
            label=label,
            source_skill=source_skill or runtime.get_current_skill(),
            created_at=None,
            is_active=True,
        )
        await self._maybe_announce_frames_change()
        self._save()
        await self._broadcast_state_change()
        print(
            f"[bg] +watch {id_} trigger={trigger!r} cooldown={cooldown_sec}s rate={rate_hz}Hz",
            flush=True,
        )
        return id_

    async def evaluate_frame(self, frame_b64: str, trigger_check: TriggerCheckFn) -> None:
        """Called per frame from /ws/frames. Fans out to each active vision watcher."""
        if not self.has_vision_watchers():
            return
        now = time.time()
        try:
            current_phash = phash_from_b64(frame_b64)
        except Exception as e:
            print(f"[bg/frame] phash decode error: {e}", flush=True)
            return

        for id_, info in list(self._active.items()):
            if info["kind"] != "vision":
                continue
            if not info.get("is_active"):
                continue

            # Cooldown after a fire
            if info["last_fire_t"] and (now - info["last_fire_t"] < info["cooldown_sec"]):
                continue

            # Rate cap on evaluations
            min_gap = 1.0 / info["rate_hz"] if info["rate_hz"] > 0 else 1.0
            if now - info["last_eval_t"] < min_gap:
                continue

            # pHash dedup vs the last frame this watcher actually evaluated
            if is_duplicate(info["phash_last"], current_phash):
                continue

            info["phash_last"] = current_phash
            info["last_eval_t"] = now
            info["eval_count"] += 1

            try:
                is_match, reason = await trigger_check(frame_b64, info["trigger"])
            except Exception as e:
                print(f"[bg/{id_}] trigger check exception: {e}", flush=True)
                continue

            print(
                f"[bg/{id_}] eval#{info['eval_count']} match={is_match} reason={reason[:80]!r}",
                flush=True,
            )

            if is_match:
                info["match_count"] += 1
                info["last_fire_t"] = now
                await self._fire(id_, info["say_on_match"])

    # ───── fire / broadcast ─────

    async def _fire(self, id_: str, text: str) -> None:
        print(f"[bg] FIRE {id_}: {text!r}", flush=True)
        await self._output_send({
            "type": "speak",
            "text": text,
            "from": id_,
            "collide": "tone_interrupt",
        })

    async def _maybe_announce_frames_change(self) -> None:
        """Broadcast frames_required state if the vision-watcher count changed.

        Counts only ACTIVE vision watchers — inactive entries don't need frames.
        """
        cur = sum(
            1 for i in self._active.values()
            if i["kind"] == "vision" and i.get("is_active")
        )
        if (cur > 0) != (self._prev_vision_count > 0):
            self._prev_vision_count = cur
            await self._output_send({
                "type": "frames_required",
                "value": cur > 0,
            })
        else:
            self._prev_vision_count = cur
