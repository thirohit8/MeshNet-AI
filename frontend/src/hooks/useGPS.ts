import { useState, useEffect } from "react";

export interface GPSPosition {
  lat: number;
  lng: number;
  accuracy: number;
  timestamp: number;
}

export function useGPS() {
  const [position, setPosition] = useState<GPSPosition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [watching, setWatching] = useState(false);

  useEffect(() => {
    if (!navigator.geolocation) {
      setError("Geolocation not supported");
      return;
    }

    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        setPosition({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          timestamp: pos.timestamp,
        });
        setWatching(true);
        setError(null);
      },
      (err) => setError(err.message),
      { enableHighAccuracy: true, maximumAge: 10_000, timeout: 15_000 }
    );

    return () => navigator.geolocation.clearWatch(watchId);
  }, []);

  const formatCoords = () =>
    position
      ? `${Math.abs(position.lat).toFixed(4)}° ${position.lat >= 0 ? "N" : "S"}, ${Math.abs(position.lng).toFixed(4)}° ${position.lng >= 0 ? "E" : "W"}`
      : "Acquiring…";

  return { position, error, watching, formatCoords };
}
