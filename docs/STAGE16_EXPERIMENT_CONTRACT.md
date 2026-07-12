# Stage 16 experiment and provenance contract

## Purpose

This contract prevents synthetic Verification，physical Validation，and public production runs from being confused with one another．Every solver run must declare its purpose，frozen geometry identity，solver modules，input provenance，approval state，calibration state，and public-runtime state．

## Frozen geometry

Every scenario must reference water-authority version `v4.8.0-candidate-r2` and exactly 679，791 water pixels．A physical run additionally requires an audited production mesh and a traceable bathymetry source．A flow result may not be used to alter the approved water geometry．

## Run classes

- `synthetic_verification` permits synthetic inputs but forbids public runtime activation and forbids the label `physical_prediction`．
- `physical_validation` forbids synthetic inputs and requires explicit approval of geometry，governing equation，and physical inputs．It remains outside the public runtime．
- `public_production` requires all approvals，including calibration and release approval，and explicitly enables the public runtime．

## Provenance

Non-synthetic data sources require an identifier and checksum or version．The run manifest contains a stable scenario hash，code commit，and creation timestamp．Boundary inputs M，N，O，and G，fishway input，barrage input，roughness，bathymetry，and solver-module versions are all recorded．

## Prohibited behaviour

Visual fitting is rejected by the contract．Synthetic output may not be labelled as a physical prediction．A public run cannot be created merely because a numerical test passes．Missing approvals，missing boundary sources，water-authority mismatch，and untraceable physical data are hard errors．

## Safeguards

The module is not connected to the public simulator．It changes no geometry，physical parameter，or existing flow calculation．Its role is to ensure that subsequent development cannot silently cross from numerical Verification into physical or public use．
