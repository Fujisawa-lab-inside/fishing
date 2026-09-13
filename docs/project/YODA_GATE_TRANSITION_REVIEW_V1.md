# YODA gate transition review v1

## Purpose

Use an official total-release transition to choose a low-cost pair of fixed-camera frames and present candidate A8 through A1 spans for human review. The output is a visual inspection aid, not a per-gate opening label.

One candidate state cue is the field observation supplied by the user: an operating gate illuminates rotating lamps at both its west and east ends. The official camera publishes one static frame every 10 minutes, so it can miss the visible phase of a rotating lamp. A visible pair is positive evidence for an operating gate; absence is `UNKNOWN`, never a closed-gate label. Gate-leaf position, downstream plume/texture, total release, water levels, rain, and tide context remain separate inputs. The gate-5 example is recorded as a hypothesis to verify against archived images; lamp pixel coordinates and A-number correspondence are not yet confirmed.

## Current candidate event

- high: official point observation 2026-09-13 16:10 JST, barrage release 59.1 m3/s
- low: official point observation 2026-09-13 17:10 JST, barrage release 0.1 m3/s
- camera frames: collection runs `20260913T1620+0900` and `20260913T1720+0900`

## Run

```sh
python3 tools/stage20_yoda_gate_transition_review_v1.py \
  --collection-root /home/swarm/work/seabass_observations/gate-multimodal-v1 \
  --roi-config config/stage20_gate_camera_candidate_rois_v1.json \
  --high-run-id '20260913T1620+0900' \
  --low-run-id '20260913T1720+0900' \
  --output /home/swarm/work/seabass_observations/gate-multimodal-v1/derived/gate-transition-review-v1/20260913-release-drop-v1
```

Omitting both run IDs selects the largest adjacent total-release transition and then the clearest high/low plateau frames within one hour of it.

The output contains a direct high/low comparison, a whole-barrage time-sequence sheet, and an enlarged per-gate time strip. The sequence views keep up to 12 high-release and 12 low-release frames so an intermittent rotating lamp is not missed merely because it faced away from the camera in one frame.

## Hard boundary

- Raw camera frames and observation files are never changed.
- Total barrage release is not apportioned to A1 through A8.
- Candidate ROIs require human confirmation of gate numbering and physical span.
- Paired rotating-lamp locations must be confirmed before they are used as a feature or label.
- Lamp absence in a 10-minute frame must never be interpreted as a closed gate.
- No gate state, actuator motion, training label, model fit, or hydraulic result is produced.
