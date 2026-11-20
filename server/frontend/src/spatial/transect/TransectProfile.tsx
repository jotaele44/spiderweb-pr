import { downloadJson } from "../../export/download";
import { words } from "../accessPoints/accessPointsApi";
import type { CrossSection, CrossSectionProfile } from "./transectApi";

export const SYNTHETIC_BANNER = "Synthetic control data — not a survey, not evidence about any real place.";

const WIDTH = 640;
const HEIGHT = 180;
const PAD = { left: 52, right: 12, top: 12, bottom: 26 };

/** Runs of consecutive covered samples. A line is never drawn across a gap. */
export function coveredRuns(profile: CrossSectionProfile): { distance: number; elevation: number; sigma: number | null }[][] {
  const runs: { distance: number; elevation: number; sigma: number | null }[][] = [];
  let current: { distance: number; elevation: number; sigma: number | null }[] = [];
  for (const sample of profile.samples) {
    if (sample.elevation_m === null) {
      if (current.length > 0) runs.push(current);
      current = [];
    } else {
      current.push({ distance: sample.distance_m, elevation: sample.elevation_m, sigma: sample.uncertainty_m });
    }
  }
  if (current.length > 0) runs.push(current);
  return runs;
}

function ProfilePlot({
  profiles,
  section,
  title,
}: {
  profiles: CrossSectionProfile[];
  section: CrossSection;
  title: string;
}) {
  const runs = profiles.map(coveredRuns);
  const values = runs.flat(2).flatMap((point) => [point.elevation - (point.sigma ?? 0), point.elevation + (point.sigma ?? 0)]);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const x = (distance: number) => PAD.left + (distance / section.length_m) * (WIDTH - PAD.left - PAD.right);
  const y = (elevation: number) => PAD.top + ((high - elevation) / span) * (HEIGHT - PAD.top - PAD.bottom);
  return (
    <figure className="transect-plot" data-datum={profiles.map((profile) => profile.datum).join(",")}>
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={title}>
        {section.gaps.map((gap) => (
          <g key={`${gap.start_m}-${gap.end_m}`} data-gap="true">
            <rect
              x={x(gap.start_m)}
              y={PAD.top}
              width={Math.max(x(gap.end_m) - x(gap.start_m), 2)}
              height={HEIGHT - PAD.top - PAD.bottom}
              className="transect-gap"
            />
            <text x={(x(gap.start_m) + x(gap.end_m)) / 2} y={PAD.top + 12} textAnchor="middle" className="transect-gap-label">
              no survey coverage ({gap.length_m.toLocaleString()} m)
            </text>
          </g>
        ))}
        {runs.map((profileRuns, index) =>
          profileRuns.map((run, runIndex) => {
            const banded = run.every((point) => point.sigma !== null);
            const upper = run.map((point) => `${x(point.distance)},${y(point.elevation + (point.sigma ?? 0))}`);
            const lower = [...run].reverse().map((point) => `${x(point.distance)},${y(point.elevation - (point.sigma ?? 0))}`);
            return (
              <g key={`${index}-${runIndex}`} data-profile-index={index} data-run-index={runIndex}>
                {banded && <polygon points={[...upper, ...lower].join(" ")} className="transect-band" data-uncertainty-band="true" />}
                <polyline
                  points={run.map((point) => `${x(point.distance)},${y(point.elevation)}`).join(" ")}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  strokeDasharray={index === 0 ? "none" : "6 3"}
                  data-profile-line="true"
                />
              </g>
            );
          }),
        )}
        <text x={4} y={PAD.top + 10} className="transect-axis">{high.toFixed(1)} m</text>
        <text x={4} y={HEIGHT - PAD.bottom} className="transect-axis">{low.toFixed(1)} m</text>
        <text x={PAD.left} y={HEIGHT - 6} className="transect-axis">0 m</text>
        <text x={WIDTH - PAD.right} y={HEIGHT - 6} textAnchor="end" className="transect-axis">
          {section.length_m.toLocaleString()} m along section
        </text>
      </svg>
    </figure>
  );
}

/** Cross-section view. Each surface keeps its own vertical reference unless a join is allowed. */
export function TransectProfile({ section }: { section: CrossSection }) {
  const shared = section.join?.may_difference === true && section.common_profiles.length > 0 && section.common_datum;
  return (
    <section className="card transect" aria-label="Cross-section">
      <h3>Cross-section</h3>
      {section.truth_kind === "SYNTHETIC_CONTROL" && (
        <p className="ap-alert transect-banner" role="alert">
          {SYNTHETIC_BANNER}
        </p>
      )}
      {section.join && !section.join.may_difference && (
        <p className="ap-note" role="note">
          The surfaces are shown separately, each on its own vertical reference, and no difference between them is
          computed: {section.join.reason}.
        </p>
      )}
      {!section.is_continuous && (
        <p className="ap-note" role="note">
          This section is not continuous. {section.gaps.length} stretch{section.gaps.length === 1 ? "" : "es"} of the
          line {section.gaps.length === 1 ? "has" : "have"} no survey coverage; nothing is interpolated across{" "}
          {section.gaps.length === 1 ? "it" : "them"}.
        </p>
      )}
      {shared ? (
        <ProfilePlot
          profiles={section.common_profiles}
          section={section}
          title={`All surfaces, elevation in metres (positive up) on ${section.common_datum}`}
        />
      ) : (
        section.profiles.map((profile, index) => (
          <ProfilePlot
            key={`${profile.kind}-${index}`}
            profiles={[profile]}
            section={section}
            title={`${words(profile.kind)}, elevation in metres (positive up) on ${profile.datum}`}
          />
        ))
      )}
      <button type="button" className="act" onClick={() => downloadJson("access-point-cross-section.json", section)}>
        Download cross-section (JSON)
      </button>
    </section>
  );
}
