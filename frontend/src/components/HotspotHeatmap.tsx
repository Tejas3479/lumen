import { useEffect, useRef, useState } from 'react';
import { apiGet } from '@/lib/api';
import type { PredictiveHotspot } from '@/types';

interface HeatPoint {
  lat: number;
  lng: number;
  weight: number;
}

interface Props {
  category?: string;
  ward?: string;
  height?: string;
}

export default function HotspotHeatmap({ category, ward, height = '400px' }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<unknown>(null);
  const [points, setPoints] = useState<HeatPoint[]>([]);
  const [hotspots, setHotspots] = useState<PredictiveHotspot[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch data
  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      try {
        const params: Record<string, string> = {};
        if (category) params.category = category;
        if (ward) params.ward = ward;

        const [heatData, hotspotData] = await Promise.all([
          apiGet<HeatPoint[]>('/analytics/heatmap', { params }),
          apiGet<PredictiveHotspot[]>('/analytics/hotspots', category ? { params: { category } } : undefined),
        ]);
        setPoints(heatData);
        setHotspots(hotspotData);
      } catch {
        // Silent fail — map shows empty
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [category, ward]);

  // Initialise Leaflet map
  useEffect(() => {
    if (!mapRef.current || isLoading) return;
    if (mapInstanceRef.current) {
      // Cleanup old instance
      (mapInstanceRef.current as { remove: () => void }).remove();
      mapInstanceRef.current = null;
    }

    (async () => {
      try {
        const L = (await import('leaflet')).default ?? (window as unknown as { L: typeof import('leaflet') }).L;
        if (!L || !mapRef.current) return;

        // Default to Nairobi if no data
        const defaultCenter = points.length > 0
          ? ([
              points.reduce((s, p) => s + p.lat, 0) / points.length,
              points.reduce((s, p) => s + p.lng, 0) / points.length,
            ] as [number, number])
          : ([-1.2921, 36.8219] as [number, number]);

        const map = L.map(mapRef.current, {
          center: defaultCenter,
          zoom: 12,
          zoomControl: true,
          scrollWheelZoom: true,
        });

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '© OpenStreetMap contributors',
          maxZoom: 19,
        }).addTo(map);

        // Add hotspot circles
        hotspots.forEach((h) => {
          L.circle([h.center_latitude, h.center_longitude], {
            radius: h.radius_meters,
            color: h.confidence > 0.7 ? '#ef4444' : h.confidence > 0.4 ? '#f97316' : '#eab308',
            fillColor: h.confidence > 0.7 ? '#fca5a5' : h.confidence > 0.4 ? '#fed7aa' : '#fef08a',
            fillOpacity: 0.25,
            weight: 2,
          })
            .addTo(map)
            .bindPopup(
              `<div style="min-width:160px">
                <strong>${h.category.replace('_', ' ')}</strong><br/>
                ${h.issue_count} issues · ${Math.round(h.confidence * 100)}% confidence<br/>
                ${h.ward ? `Ward: ${h.ward}<br/>` : ''}
                ${h.predicted_next_issue_date ? `Next predicted: ${h.predicted_next_issue_date}` : ''}
              </div>`
            );
        });

        mapInstanceRef.current = map;
      } catch (err) {
        console.warn('Map failed to initialise:', err);
      }
    })();

    return () => {
      if (mapInstanceRef.current) {
        (mapInstanceRef.current as { remove: () => void }).remove();
        mapInstanceRef.current = null;
      }
    };
  }, [points, hotspots, isLoading]);

  if (isLoading) {
    return (
      <div
        className="bg-slate-100 dark:bg-slate-800 rounded-2xl animate-pulse flex items-center justify-center"
        style={{ height }}
        aria-busy="true"
        aria-label="Loading heatmap"
      >
        <span className="text-sm text-slate-400 dark:text-slate-500">Loading map…</span>
      </div>
    );
  }

  return (
    <div className="rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-700 shadow-sm">
      <div
        ref={mapRef}
        style={{ height }}
        className="w-full"
        aria-label="Issue hotspot heatmap"
        role="img"
      />
    </div>
  );
}
