# Spatial iPhone baselines

Run the frontend without `VITE_CESIUM_ION_TOKEN`, then run `npm run visual:iphone`.
The token-free grid shell is intentional: mutable third-party imagery is not a
deterministic regression source. The capture produces:

- `iphone-portrait.png` at 390×844 CSS pixels, device scale factor 3;
- `iphone-landscape.png` at 844×390 CSS pixels, device scale factor 3.

The capture fails on a blank page, Vite error overlay, missing Spatial module,
or missing Puerto Rico recenter control. Generated images must be visually
reviewed before replacing prior baselines.
