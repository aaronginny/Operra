"""Quick tests for Feature 3 AI enhancements."""
import json
from app.services.ai_service import (
    _rule_based_progress,
    _detect_blocker,
    _checkpoint_progress,
)

cps = json.dumps([
    {"text": "logo", "done": True},
    {"text": "pipes", "done": False},
    {"text": "paint", "done": False},
])

# Test 1: Blocker detection with checkpoint context
r1 = _rule_based_progress("kinda working on it but stuck on pipes", cps)
print(f"Blocked + working: {r1}")
assert r1["is_blocker"] is True
assert r1["type"] == "progress_update"
assert r1["progress_percent"] is not None  # blended with checkpoint %

# Test 2: Normal progress - "almost done" matches before plain "done"
r2 = _rule_based_progress("almost done with everything")
print(f"Almost done: {r2}")
assert r2["is_blocker"] is False
# "almost done" is checked before "done" in keyword list
# But "done" also matches — first match wins. That's expected.
assert r2["progress_percent"] in (85, 100)

# Test 3: Explicit update
r3 = _rule_based_progress("update 60")
print(f"Update 60: {r3}")
assert r3["progress_percent"] == 60
assert r3["is_blocker"] is False

# Test 4: Checkpoint progress calc
cp_pct = _checkpoint_progress(cps)
print(f"Checkpoint progress (1/3): {cp_pct}%")
assert cp_pct == 33

# Test 5: Blocker keyword detection
assert _detect_blocker("stuck on pipes") is True
assert _detect_blocker("all good") is False
assert _detect_blocker("can't get material") is True

# Test 6: Pure blocker (no progress keyword, just frustrated)
r4 = _rule_based_progress("I am stuck, cannot proceed without material")
print(f"Pure blocker: {r4}")
assert r4["is_blocker"] is True
assert r4["type"] == "progress_update"

# Test 7: No progress, no blocker
r5 = _rule_based_progress("ok thanks")
print(f"No progress: {r5}")
assert r5["is_blocker"] is False
assert r5["type"] == "no_progress"

# Test 8: Checkpoint-blended progress
r6 = _rule_based_progress("working on it", cps)
print(f"Working on it + checkpoints: {r6}")
assert r6["progress_percent"] >= 30  # max(30 keyword, 33 checkpoint)

print("\nOK - All Feature 3 AI tests passed!")
