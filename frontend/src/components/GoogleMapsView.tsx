/**
 * Google Maps View Component
 * Renders issues on Google Maps when VITE_GOOGLE_MAPS_API_KEY is available.
 * Falls back to MapView (Leaflet/OSM) when not configured.
 * Shape-coded custom markers preserved from MapView for color-blind safety.
 */
import { useEffect, useRef, useCallback } from 'react';
import type { Issue } from '@/types';

const STATUS_COLORS: Record<string, string> = {
  reported:    '#718096',
  verified:    '#3182CE',
  assigned:    '#805AD5',
  in_progress: '#D69E2E',
  resolved:    '#38A169',
  disputed:    '#E53E3E',
  closed:      '#2D3748',
};

// SVG marker paths for color-blind safety (same as MapView)
const CATEGORY_SHAPES: Record<string, string> = {
  pothole:       'M 0,0 L 20,0 L 20,20 L 0,20 Z',     // square
  water_leakage: 'M 10,0 A 10,10 0 1,1 10,0.001 Z',   // circle
  streetlight:   'M 10,0 L 20,20 L 0,20 Z',           // triangle
  garbage:       'M 10,0 L 17,4 L 20,12 L 15,20 L 5,20 L 0,12 L 3,4 Z', // hexagon
  drainage:      'M 10,0 L 20,8 L 17,20 L 3,20 L 0,8 Z',  // pentagon
  other:         'M 10,0 L 13,7 L 20,7 L 14,12 L 17,20 L 10,15 L 3,20 L 6,12 L 0,7 L 7,7 Z', // star
};

const CATEGORY_EMOJI: Record<string, string> = {
  pothole:       '🕳️',
  water_leakage: '💧',
  streetlight:   '💡',
  garbage:       '🗑️',
  drainage:      '🌊',
  road_damage:   '🚧',
  tree_hazard:   '🌳',
  vandalism:     '✏️',
  noise:         '🔊',
  other:         '⚠️',
};

interface Props {
  issues: Issue[];
  onIssueSelect: (issue: Issue) => void;
  center: [number, number];
  zoom?: number;
}

export default function GoogleMapsView({ issues, onIssueSelect, center, zoom = 14 }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const googleMapRef = useRef<google.maps.Map | null>(null);
  const markersRef = useRef<Map<string, google.maps.Marker>>(new Map());

  const initMap = useCallback(async () => {
    const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
    if (!apiKey || !mapRef.current) return;

    try {
      const { Loader } = await import('@googlemaps/js-api-loader');
      const loader = new Loader({
        apiKey,
        version: 'weekly',
        libraries: ['places', 'marker'],
      });
      const google = await loader.load();

      googleMapRef.current = new google.maps.Map(mapRef.current, {
        center: { lat: center[0], lng: center[1] },
        zoom,
        mapTypeControl: false,
        streetViewControl: true,
        fullscreenControl: false,
        styles: [
          // Subtle style to de-emphasize POIs and highlight civic infrastructure
          { featureType: 'poi', elementType: 'labels', stylers: [{ visibility: 'off' }] },
          { featureType: 'transit', elementType: 'labels', stylers: [{ visibility: 'simplified' }] },
        ],
      });

      // Add markers
      issues.forEach((issue) => {
        if (!issue.latitude || !issue.longitude) return;

        const color = STATUS_COLORS[issue.status] || '#718096';
        const categoryName = issue.category?.name || issue.ai_category || 'other';
        const emoji = CATEGORY_EMOJI[categoryName] ?? '⚠️';

        // SVG marker for color-blind safety
        const svgMarker = {
          path: CATEGORY_SHAPES[categoryName] || CATEGORY_SHAPES['other'],
          fillColor: color,
          fillOpacity: 0.9,
          strokeWeight: 2,
          strokeColor: '#FFFFFF',
          rotation: 0,
          scale: 1.2,
          anchor: new google.maps.Point(10, 10),
          labelOrigin: new google.maps.Point(10, 10),
        };

        const marker = new google.maps.Marker({
          position: { lat: issue.latitude, lng: issue.longitude },
          map: googleMapRef.current!,
          icon: svgMarker,
          title: `${issue.status}: ${issue.title}`,
          label: {
            text: emoji,
            color: '#FFFFFF',
            fontSize: '12px',
          },
          animation: issue.is_emergency
            ? google.maps.Animation.BOUNCE
            : undefined,
        });

        marker.addListener('click', () => onIssueSelect(issue));
        markersRef.current.set(issue.id, marker);
      });

    } catch (err) {
      console.warn('Google Maps failed to load:', err);
    }
  }, [issues, center, zoom, onIssueSelect]);

  useEffect(() => {
    initMap();
    return () => {
      markersRef.current.forEach((m) => m.setMap(null));
      markersRef.current.clear();
    };
  }, [initMap]);

  return (
    <div className="w-full h-full relative" role="region" aria-label="Community issue map">
      <div
        ref={mapRef}
        className="w-full h-full"
      />

      {/* Legend */}
      <div
        className="absolute bottom-20 left-2 bg-white/90 backdrop-blur-sm rounded-xl px-3 py-2 shadow-md z-10 text-xs"
        aria-label="Map legend"
        role="complementary"
      >
        <p className="font-semibold text-gray-700 mb-1.5 text-[11px]">Status</p>
        {Object.entries(STATUS_COLORS)
          .filter(([k]) => k !== 'closed')
          .map(([status, color]) => (
            <div key={status} className="flex items-center gap-1.5 mb-1 last:mb-0">
              <span
                style={{
                  display: 'inline-block',
                  width: 10,
                  height: 10,
                  background: color,
                  borderRadius: status === 'verified' ? '50%' : '2px',
                  flexShrink: 0,
                }}
                aria-hidden="true"
              />
              <span className="text-gray-600 text-[11px] capitalize">{status.replace('_', ' ')}</span>
            </div>
          ))}
      </div>
    </div>
  );
}
