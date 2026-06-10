# Skill registry directory.
# Each capability is a separate .py file with either:
#   - async def run(page, vision, **kwargs)              # one-shot
#   - WATCH = {...} + async def on_match(frame, ...)      # watcher
# Generated skills are written here by the synthesizer (phase 6).
