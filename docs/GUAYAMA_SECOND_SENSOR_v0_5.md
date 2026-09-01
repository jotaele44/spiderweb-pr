# Guayama–Punta Tuna second-sensor certification v0.5

This bounded pass identifies a real second acquisition root overlapping the byte-frozen W00247 BAG without treating catalog envelopes as sensor coverage.

## Result

The exact NCEI multibeam footprint service returned 11 footprint features intersecting the selected W00247 BAG envelope. Ten features belong to the previously frozen 13-survey denominator, representing nine unique survey IDs: AT20, EX1502L3, KN151L4, KN173L02, NF-14-01T, NF1501, NF2202, RB0604, and TN390.

EX1502L3 was the first exact-footprint candidate with a directly published processed XYZ grid suitable for byte-level spatial testing. The workflow froze `EX1502L3_MB_FNL_50m_WGS84.xyz.gz` at SHA-256 `0bb09757fd5433075b788f15546597c444cf63d9f617de9f3ba385ce31fc736c` and 23,635,239 bytes. It contains 3,700,961 numeric XYZ rows with zero parse rejects. Of those, 22,338 fall inside the selected W00247 BAG raster envelope and 282 fall on 212 valid W00247 BAG cells. This establishes nonzero spatial overlap between two distinct acquisition roots.

The authoritative NCEI EX1502L3 ISO record is internally contradictory for vertical reference: its reference-system declaration says `Vertical Datum: Unknown`, while its vertical extent links EPSG:5715 and labels it `msl depth in meters`. No datum transform is inferred. W00247 remains bound to EPSG:5866 / MLLW. Direct depth subtraction is therefore blocked.

A datum-independent ordering comparison was computed across the 212 paired valid BAG cells. Spearman rank rho is `0.9826226318260621`. This is a computed morphology-order association only; it is not a vertical-datum equivalence test and cannot by itself certify a geomorphic feature or screenshot match.

## Certification

- Second independent sensor root overlapping W00247: **PASS**
- EX1502L3 byte identity: **PASS**
- Nonzero overlap on valid W00247 cells: **PASS**
- EX1502L3 vertical datum: **UNRESOLVED_CONTRADICTION**
- Direct cross-dataset depth subtraction: **BLOCKED**
- Datum-independent rank/order comparison: **PASS_COMPUTED_ONLY**
- Multisensor feature confirmation: **BLOCKED_PENDING_FEATURE_BOUNDARY_AND_VERTICAL_ADJUDICATION**
- Screenshot registration: **BLOCKED_PENDING_REAL_CONTROL_POINTS**

The machine-readable receipt is `evidence/marine/GUAYAMA_SECOND_SENSOR_v0_5_RECEIPT.json`.
