# Stage 20 hybrid browser architecture

The user selected option A, `hybrid_precomputed_response_browser_interpolation`, on 2026-07-15 with the statement `推奨のA案で進めてください`. This authorizes the response-pack format, browser synthesis path, one-hour output contract, synthetic benchmark, and checkpoint/restart control plane. It does not authorize a physical precomputation run, paid compute, connection to the public simulator, or a merge to `main`.

The browser response pack contains a float32 basis arranged as mode × component × cell. The three components are depth, east velocity, and north velocity. Runtime inputs provide 37 hourly values covering hour −12 through hour +24 for relative tide, Onga River discharge, Nishi River discharge, Magarigawa discharge, and barrage opening. The Worker validates every value against the response-pack envelope before synthesising all 37 fields.

The checked-in response pack is synthetic and exists only to validate transport and computation on the approved 50,339-cell mesh identity. Its 3,624,408-byte payload produces a 22,350,516-byte 37-snapshot output. The output is deterministic with SHA-256 `64255047d3bd272d07862d065aaaed6d03f0d2a2117fb8a73d8d915dc82e45a7`.

The direct module benchmark completed the first synthesis in 77.8 ms. The Worker-style HTTP benchmark loaded and hashed the pack, synthesised the fields, hashed the output, and transferred the 22.4 MB typed array successfully. Synthesis took 75.0 ms and the measured total before transfer delivery was 115.0 ms. This is an implementation benchmark on synthetic fields, not a promise for every browser or a physical-accuracy result.

`tools/stage20_offline_precompute_runner.py` provides an atomic checkpoint ledger, output SHA-256 validation, completed-job skipping on restart, and corruption rejection. Its only connected executor is a deterministic fixture. The eleven-job low/reference/high precompute plan remains `execution.authorized=false`; no physical solver or paid resource is connected.

The isolated page `stage20-hybrid-reference.html` is not linked from the public simulator. The next gated step is a small physical precompute pilot, which requires both an identified Linux x86 compute resource and a separate explicit execution authorization.
