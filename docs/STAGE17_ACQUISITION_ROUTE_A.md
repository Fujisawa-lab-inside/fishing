# Stage 17 physical-data acquisition route A

> Retired on 2026-07-14. The requester explicitly disabled the Onga River Office request and selected public data plus declared inference. The current route is documented in `docs/STAGE19_PUBLIC_DATA_INFERENCE_ROUTE.md`; this file remains historical evidence only.

## Approved route

The approved acquisition route is to proceed in parallel with:

1. an official request to the Onga River Office for non-public or insufficiently documented hydraulic data; and
2. acquisition and audit of publicly available official hydrology and tide-reference resources.

The route approval was originally recorded in `config/stage17_physical_data_acquisition_decision_record_v1.json`. The current binding is `config/stage17_physical_data_acquisition_decision_record_v2.json`, which preserves that decision and rebinds it to the separately approved `v4.8.0-candidate-r3` water authority (680,633 pixels) and Linux metric mesh v2 (50,129 cells). It does not expand the approved route or authorize solver inputs.

The current source inventory is `config/stage17_physical_data_source_inventory_v2.json`. The unchanged `config/stage17_physical_data_source_inventory_v1.json` remains a read-only snapshot of the superseded r2 / 50,333-cell, route-pending state and is never used to ask for the acquisition-route decision again.

## Official-request package

The request package shall seek, when available:

- surveyed cross sections or bathymetry with survey epoch, units, uncertainty, and vertical datum;
- observed lower-river or downstream water level suitable for boundary M, with datum and quality information;
- discharge observations or approved rating curves relevant to boundaries N, O, and G;
- barrage gate geometry, discharge coefficients, gate-by-gate opening records, and operation timestamps;
- fishway geometry, hydraulic relation, operation records, or observed discharge;
- independent current-velocity measurements suitable for physical Validation.

The final recipient and contact route must be verified from an official source before transmission. The request must not state that any candidate source has already been selected for the solver.

## Public-database package

The public acquisition track may archive official page metadata, observation identifiers, water-level time series, quality flags, timestamps, coordinates, and vertical-datum metadata. Each payload must retain its original bytes or hash and a provenance record.

A station being reachable or geographically nearby does not make it a valid numerical boundary. Compatibility with M, N, O, or G requires a separate hydraulic audit.

## Prohibited shortcuts

- No station is automatically assigned to M, N, O, or G.
- Astronomical tide is not substituted for observed mouth water level.
- Missing discharge is not inferred from stage without an approved rating curve.
- Bed elevation is not inferred from the water mask or shoreline image.
- Manning roughness, fishway discharge, barrage coefficients, and gate openings are not invented.
- Physical execution and public-simulator integration remain disabled.

## Change control

Acquired data remain candidates until their provenance, datum, spatial applicability, temporal coverage, quality control, and uncertainty are reviewed and explicitly approved. The approved water geometry and metric mesh remain frozen.
