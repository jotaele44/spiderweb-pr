# Spatial iPhone baselines

Run the frontend without `VITE_CESIUM_ION_TOKEN`, then run `npm run visual:iphone`.
The token-free grid shell is intentional: mutable third-party imagery is not a
deterministic regression source, and Google Photorealistic 3D Tiles must not be
cached or stored as regression artifacts. The capture produces:

- `iphone-portrait.png` at 390×844 CSS pixels, device scale factor 3;
- `iphone-landscape.png` at 844×390 CSS pixels, device scale factor 3.

The capture fails on a blank page, Vite error overlay, missing Spatial module,
or missing Puerto Rico recenter control. Generated images must be visually
reviewed before replacing prior baselines. The runner also verifies the
rendered runtime marker and fails before writing a PNG unless the active
basemap is exactly `grid`.

## Live Google calibration (not a stored baseline)

With a URL-restricted `VITE_CESIUM_ION_TOKEN`, inspect both viewport profiles
in a live browser without saving Google imagery. The runtime marker must move
from `google-loading` to `google-photorealistic` within 15 seconds. A rejected
or timed-out load switches to `grid-fallback`, reports a basemap error, and
fails Google-provider approval.

Approve only when all of these are visible in portrait and landscape:

- Puerto Rico has textured terrain at the recentered view, with recognizable
  urban 3D detail where Google provides it;
- the full island can be reached without crossing the 1,050 km ceiling;
- at maximum height, the intended regional context (eastern Hispaniola,
  Puerto Rico, the Virgin Islands, and St. Croix) is neither materially clipped
  nor replaced by excessive unrelated extent;
- Google Maps and dynamic data-provider attribution remain legible and are not
  obscured by application controls;
- the Puerto Rico recenter control returns to the same center, height, heading,
  and pitch in both orientations.

The 1,050 km ceiling is falsified only by a live failure of the regional-context
criterion above. If falsified, record viewport, device scale, measured height,
and the smallest replacement ceiling that satisfies the criterion. If Puerto
Rico lacks adequate photorealistic coverage, retain the existing provider as a
fallback and open a separate provider-adjudication vector; changing access keys
does not establish different source coverage.
