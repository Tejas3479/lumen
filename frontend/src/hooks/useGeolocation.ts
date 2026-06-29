import { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '@/store/appStore';

interface GeolocationState {
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  error: string | null;
  isLoading: boolean;
  timestamp: number | null;
}

interface UseGeolocationOptions {
  enableHighAccuracy?: boolean;
  timeout?: number;
  maximumAge?: number;
  watch?: boolean;
}

export function useGeolocation(options: UseGeolocationOptions = {}) {
  const {
    enableHighAccuracy = true,
    timeout = 10_000,
    maximumAge = 30_000,
    watch = false,
  } = options;

  const setMapCenter = useAppStore((s) => s.setMapCenter);

  const [state, setState] = useState<GeolocationState>({
    latitude: null,
    longitude: null,
    accuracy: null,
    error: null,
    isLoading: false,
    timestamp: null,
  });

  const handleSuccess = useCallback(
    (position: GeolocationPosition) => {
      const { latitude, longitude, accuracy } = position.coords;
      setState({
        latitude,
        longitude,
        accuracy,
        error: null,
        isLoading: false,
        timestamp: position.timestamp,
      });
      setMapCenter([latitude, longitude]);
    },
    [setMapCenter]
  );

  const handleError = useCallback((error: GeolocationPositionError) => {
    const messages: Record<number, string> = {
      1: 'Location permission denied. Please enable location access.',
      2: 'Location unavailable. Please try again.',
      3: 'Location request timed out.',
    };
    setState((prev) => ({
      ...prev,
      error: messages[error.code] ?? 'Failed to get location.',
      isLoading: false,
    }));
  }, []);

  const getLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setState((prev) => ({
        ...prev,
        error: 'Geolocation is not supported by your browser.',
        isLoading: false,
      }));
      return;
    }
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    navigator.geolocation.getCurrentPosition(handleSuccess, handleError, {
      enableHighAccuracy,
      timeout,
      maximumAge,
    });
  }, [enableHighAccuracy, timeout, maximumAge, handleSuccess, handleError]);

  useEffect(() => {
    if (!watch) return;
    if (!navigator.geolocation) return;

    setState((prev) => ({ ...prev, isLoading: true }));
    const watchId = navigator.geolocation.watchPosition(handleSuccess, handleError, {
      enableHighAccuracy,
      timeout,
      maximumAge,
    });
    return () => navigator.geolocation.clearWatch(watchId);
  }, [watch, enableHighAccuracy, timeout, maximumAge, handleSuccess, handleError]);

  const location = state.latitude !== null && state.longitude !== null
    ? { latitude: state.latitude, longitude: state.longitude }
    : null;

  return { ...state, location, getLocation };
}
