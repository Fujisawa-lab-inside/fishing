# Stage 20 hybrid browser path on mesh v2

The approved 36-hour hybrid browser architecture is now connected to the Linux-verified 50,199-cell browser mesh v2 on the work branch. The synthetic response pack retains the established six-mode format and produces 37 hourly snapshots from hour -12 through hour +24.

The response pack is 3,614,328 bytes and the 37-snapshot float32 output is 22,288,356 bytes. Deterministic repeat synthesis produced SHA-256 `146429c21fecc13359710bb5335885258b63cd1f5750b6816f01098659135417`, rejected an out-of-envelope barrage input, and produced no non-finite values.

The direct module run synthesised all snapshots in 73.3 ms. The HTTP Worker path completed loading, hashing, synthesis, output hashing, and transfer validation in 125.6 ms. A real WebKit page load and button click completed synthesis in 375 ms and the total in 395 ms. These are measurements on this development machine and the synthetic pack, not guarantees for every device.

The four maps use the approved estuary, barrage, confluence, and fishway extents. Their colours and arrows are computed from the synthetic response pack at hour 0 and use the same mesh-cell values. They demonstrate display transport and coverage only; they are not physical flow, fishing, or safety predictions.

No physical response precomputation, new numerical pilot, public simulator connection, publication, or `main` merge is authorized by this validation.
