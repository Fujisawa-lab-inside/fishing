# Stage 17 candidate-station boundary audit

## Purpose

This audit compares official public station metadata with the corrected approved domain `v4.8.0-candidate-r3` (680,633 water pixels) and Linux metric mesh v2 (50,129 cells). It records station coordinates, image-space location, geodesic distance to open-boundary midpoints, public water-level fields, and unresolved vertical-reference metadata.

The audit does not assign a station to M, N, O, or G. A station inside the domain is treated as a possible internal validation point, while an upstream station outside the domain still requires discharge or routing evidence before boundary use.

## Network boundary

The audit and related probes allow HTTPS GET requests only to an explicit set of official hosts. Redirects outside that set are rejected before the redirected request is made. Each station-audit JSON response is limited to 8 MiB and an oversized response fails closed. No email, form submission, telephone call, POST request, or solver write occurs.

## 2026-07-14 diagnostic audit snapshot

The committed machine-readable file is a diagnostic snapshot, not a sealed authorization record. It fixes the exact three source-report role/SHA-256 pairs, the three station IDs and names, and the official contact-page SHA-256. The validator recomputes its summary before accepting it. The snapshot remains non-authoritative for source selection and requires the cited workflow artifacts for independent evidence review.

The current official resources identified 祇園橋，唐熊，and 中間 and returned recent public water-level series for all three. None of the inspected resources exposed a discharge field, none resolved the vertical-datum meaning sufficiently for solver use, and none of the station points fell inside the approved water mask.

- 祇園橋 is approximately 455 m from the N-boundary midpoint by geodesic distance.
- 唐熊 and 中間 are many kilometres upstream of the compact model domain. Their geometrically nearest boundary midpoint is not interpreted as their hydraulic role.
- Every boundary assignment remains `null`; geographic proximity does not select a boundary.

The official contact page also confirmed the general office email `onga@qsr.mlit.go.jp`. It has been recorded as a candidate verified route, but no external contact has been performed and the submission gate remains blocked on requester metadata and exact-message approval.

## Bathymetry review requirement

The Stage 18 v3 median-depth map is not an actual bathymetry map. The refined user hypothesis is an idealized smooth, approximately symmetric, upside-down normal-distribution-like trough: shallow near land and deepest near the channel centre. It must be tested against authoritative surveyed cross sections and their vertical datum, including real asymmetry, thalweg offset, compound sections, and local scour. It must not be converted into a bed field through visual fitting.

## Fail-closed interpretation

- Public water-level availability does not establish discharge or a rating curve.
- Local zero-height metadata does not by itself resolve the vertical datum.
- Geographic proximity does not establish hydraulic compatibility.
- Every source remains unselected, the physical run remains disabled, and the public simulator remains disconnected.
