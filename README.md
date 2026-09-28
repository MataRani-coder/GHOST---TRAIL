# Ghost Trail

**Anonymous until it matters.** Explainable, cross-camera perimeter defense.

Ghost Trail is a multi-camera surveillance pipeline for the Cybersecurity &
Defense track at ASYNC 2.0. Instead of alerting on every stranger a camera
sees, it tracks people **anonymously by default**, scores their *behavior*
across the whole perimeter (dwell time, loitering, repeat passes,
cross-camera zone-hopping, off-hours presence), and only escalates to face
recognition against a watchlist once that behavior earns suspicion.

## How it works

```
Detect (YOLOv8) -> Track (ByteTrack) -> Stitch (OSNet Re-ID, cross-camera)
      -> Score (behavior graph)  -> Escalate? -> Face match vs. watchlist
      -> Explainable alert
```

| Stage | What it does | Module |
|---|---|---|
| Detect | Spots people per camera feed | `detector.py` |
| Track | Per-camera multi-object tracking | `tracker.py` / `sentinel_tracker.py` |
| Stitch | Cross-camera Re-ID via OSNet body embeddings — anonymized, no identity stored | `identity_manager.py` |
| Score | Behavior-anomaly scoring: dwell time, loitering, repeat passes, zone-hopping, off-hours | `behavior_analyzer.py` |
| Escalate | Face recognition is **only attempted** once a track's own behavior crosses the Suspicious tier — everyone else stays a body-embedding-only Guest | `behavior_analyzer.py` + `sentinel_tracker.py` |
| Alert | Plain-language, explainable alerts (not just a red box) | `alert_manager.py` |
| Dashboard | Live camera grid, tactical map, alert feed, persons/watchlist view | `dashboard/` (React) |

### Why this is different from always-on facial recognition

Most surveillance systems either run facial recognition on everyone (privacy
and legal exposure) or fire on any motion (alert fatigue, no context).
Ghost Trail stays anonymous by default and only pulls in the most invasive
tool — face matching against a watchlist — once a track's behavior has
already earned it. Every alert also carries a plain-language reason
(`behavior_analyzer.py` builds this), so an analyst sees *why* something was
flagged instead of a bare notification.

## Risk tiers

| Tier | Meaning | Effect |
|---|---|---|
| Watch | Short dwell, nothing alarming yet | No alert, no escalation |
| Suspicious | Sustained dwell, a repeat pass, or crossing multiple camera zones | **Escalates to face recognition**; alert raised |
| High Risk | Long dwell, several repeat passes, or any of the above during off-hours | Alert raised, prioritized on-screen |

Tune thresholds in `config.yaml` under the `behavior:` section — they're set
short (seconds) for a live demo; raise them for real deployment.

## Manual Face Verification

The Persons Database now supports analyst review of every enrolled face. Each profile can be marked **Confirm Face** or **Deny Face**. A denial is persisted as a `high_risk` security incident, appears in the Security Incidents dashboard, and can be filtered with the **HIGH RISK** view. Confirming a previously denied face marks the face as verified and resolves its related incident.

Review decisions are stored in the SQLite database, so they survive application restarts. Re-enrolling/updating a profile resets its face-review state to pending.

## Run

### First run on Windows

1. Open this project folder in VS Code.
2. Activate/create the Python environment and install Python packages:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```
3. Build the React dashboard once (this is important because `sentinel_app.py` serves `dashboard/dist`):
   ```powershell
   cd dashboard
   npm install
   npm run build
   cd ..
   ```
4. Start the full application:
   ```powershell
   python sentinel_app.py
   ```

For convenience, use `RUN_SENTINEL_AI.bat` from the project root. It verifies the frontend dependencies, rebuilds the dashboard, and then starts `sentinel_app.py`.

The live application uses the persisted SQLite `sighting_logs` table for the Tracking & Intelligence dashboard. It does not invent sample telemetry when the API is unavailable. A newly-created identity has no match score until a previous identity can actually be compared.

### Face review workflow

- **Flagged for Review** is only a pending human-review queue.
- **Confirm Face** promotes that exact global Guest ID into the enrolled database, copies the accepted face to `Faces/`, resolves earlier active incidents for that person, and creates a resolved green audit event: `face has been accepted, person has been added to the database`.
- **Deny Face** marks the same global ID High Risk and creates the active High Risk incident.
- An enrolled/confirmed profile shows **FACE VERIFIED — AUTHORIZED** rather than Confirm/Deny buttons. It has **Edit Details** and **Remove Enrolled** instead.
- Editing a profile updates its name, badge ID, role, clearance, notes, and enrolled gallery filename.

### Identity stitching

The global stitcher keeps a global ID separate from each camera's local tracker ID. For a new local track it checks persisted confirmed/denied identities first, then recent anonymous Guests. Cross-camera links use recent face and OSNet body-ReID similarities, while the same camera cannot assign the same global ID to two simultaneous local tracks.

For a reliable demo, keep the two camera feeds available at the same time and move through the overlapping/handoff area without waiting longer than the configured `camera_handoff_max_gap_sec`. If you change camera sources or IDs, rebuild the dashboard only when the UI source has changed; the camera configuration itself is read directly from `config.yaml` at tracker start.

## Notes

- Cross-camera Re-ID uses OSNet (`osnet_x1_0`) body embeddings by default;
  swap in a different Re-ID model via `reid.model_name` in `config.yaml`.
- Face recognition (ArcFace, `buffalo_l`) is intentionally gated behind
  `behavior_analyzer.should_escalate_to_face()` — see that function and the
  `escalate` flag in `sentinel_tracker.py` for the exact trigger logic.
- For GPU, set the relevant `device` fields in `config.yaml` to `cuda:0`.

## Team

PowerPuff Girls — Garv Bhat (lead), 1MS25CS058 / 1MS25ME069 / 1MS25IS093 —
ASYNC 2.0, Cybersecurity & Defense track.

### Identity stitching v5

The global identity stitcher now permits the same global identity to be observed by multiple cameras at the same time, while preventing two active tracks in the same camera from sharing one identity. It uses recent face and body Re-ID embeddings, cross-camera handoff timing, and repeated face probing for new local tracks. This avoids the old camera-handoff lock that could create a second Guest when two camera frames were processed only milliseconds apart.
