# Stage 20 browser reference integration

The approved 50,339-cell Linux mesh is exported without changing any array value to a 2,302,668-byte little-endian browser binary. The browser manifest pins the binary SHA-256 `717a076b901c29763b3b565250e68e15ad72fe2b87306ebd41f35b9dd37f4347` and retains the approved Linux package SHA-256 as provenance.

`onga_stage20_reference_worker.mjs` loads and hashes the mesh outside the main UI thread. `onga_stage20_reference_solver.mjs` reconstructs cell areas, face lengths, and consistently oriented face normals. The 456-byte WebAssembly update kernel performs the conservative state update and semi-implicit Manning damping on typed arrays owned by the Worker.

The current validation is deliberately limited to one synthetic uniform-still-water step. On the actual approved mesh it produced zero clipped cells, zero non-finite values, zero depth drift, and maximum numerical velocity `2.5947374698634663e-17 m/s`. This proves browser transport, geometry reconstruction, residual assembly, and the WASM update connection; it is not a physical-flow result.

The isolated development page is `stage20-browser-reference.html`. It is not linked from the public simulator. The existing public runtime, 64-condition runner, and `main` branch remain unchanged.

The next user decision is limited to the map display encoding shown in `docs/visuals/stage20-browser-display-decision-v1.png`: speed colour, direction arrows, satellite-image legibility, and the visibility of the approved barrage and fishway markers. The displayed velocity field is a synthetic rendering sample, so its physical value and direction are explicitly outside the decision scope.
