# Sentinel AI v7 changes

## Persons Database / face review
- Confirmed identities no longer expose Confirm Face / Deny Face controls.
- Pending flagged captures remain in Flagged for Review only until reviewed.
- Confirming a flagged face promotes the exact global Guest ID into the enrolled database, copies the accepted face image into `Faces/`, resolves older active incidents for that person, and writes a resolved green audit event with the message:
  `face has been accepted, person has been added to the database`
- Denying a flagged face marks that same global ID High Risk and creates the active High Risk incident.
- Accepted profiles expose Edit Details and Remove Enrolled actions.
- Editing updates name, badge ID, role, clearance, notes, and gallery filename.
- Person last-seen timestamps are returned in milliseconds so the browser no longer shows `Invalid Date`.
- A face review decision is restored from SQLite on application restart.

## Live boxes
- Confirmed face boxes are green and labeled `FACE VERIFIED`.
- Denied face boxes are red and labeled `FACE DENIED`.
- Pending faces are amber and labeled `FACE REVIEW`.

## Tracking & Intelligence dashboard
- Analytics cards and graphs use persisted SQLite `sighting_logs` instead of generated fallback numbers.
- High Risk detections are counted separately.
- Authorized/unregistered/high-risk table status is derived from the persisted face-review state.
- Match similarity is calculated before the current embedding is added to the identity history, preventing a false 100% score caused by comparing an embedding with itself.
- Camera filters are populated from the actual camera IDs in the telemetry returned by the API.

## Frontend build/run
`sentinel_app.py` serves the compiled React application from `dashboard/dist`. This release includes a Windows helper, `RUN_SENTINEL_AI.bat`, which installs the dashboard dependencies when necessary, runs `npm run build`, and then starts `sentinel_app.py`.
