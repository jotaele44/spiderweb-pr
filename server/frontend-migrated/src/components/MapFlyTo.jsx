import { useEffect } from 'react';
import { useMap } from 'react-leaflet';

export default function MapFlyTo({ target }) {
  const map = useMap();

  useEffect(() => {
    if (!target) return;
    map.flyTo([target.lat, target.lng], target.zoom, { duration: 1.2 });
  }, [target]);

  return null;
}