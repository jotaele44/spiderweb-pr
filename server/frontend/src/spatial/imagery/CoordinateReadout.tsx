import { useEffect, useState } from "react";
import type * as maplibregl from "maplibre-gl";

export function formatCoordinate(lat: number, lng: number): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lng >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(5)}°${ns} ${Math.abs(lng).toFixed(5)}°${ew}`;
}

/** Cursor position and zoom level, bottom-left of the map. */
export function CoordinateReadout({
  mapRef,
  ready,
}: {
  mapRef: React.MutableRefObject<maplibregl.Map | null>;
  ready: boolean;
}) {
  const [cursor, setCursor] = useState<{ lat: number; lng: number } | null>(null);
  const [zoom, setZoom] = useState<number | null>(null);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const onMove = (event: maplibregl.MapMouseEvent) =>
      setCursor({ lat: event.lngLat.lat, lng: event.lngLat.lng });
    const onLeave = () => setCursor(null);
    const onZoom = () => setZoom(map.getZoom());
    map.on("mousemove", onMove);
    map.on("mouseout", onLeave);
    map.on("zoom", onZoom);
    onZoom();
    return () => {
      map.off("mousemove", onMove);
      map.off("mouseout", onLeave);
      map.off("zoom", onZoom);
      setCursor(null);
      setZoom(null);
    };
  }, [mapRef, ready]);

  if (zoom === null) return null;
  return (
    <div className="map-readout" data-testid="map-readout">
      <span>{cursor ? formatCoordinate(cursor.lat, cursor.lng) : "—"}</span>
      <span>z {zoom.toFixed(1)}</span>
    </div>
  );
}
