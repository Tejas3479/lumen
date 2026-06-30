/**
 * MapView — Leaflet-based civic issue map.
 *
 * Design principles:
 *  - Color-blind-safe: every status uses BOTH a unique color AND a unique SVG shape
 *    so information is never conveyed by color alone.
 *  - Emergency issues have a red pulse ring animation.
 *  - Markers are keyboard accessible (Enter key triggers onIssueSelect).
 *  - A legend in the bottom-left corner labels all shapes.
 *  - The map recentres smoothly when the `center` prop changes.
 */
import { useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Issue } from '@/types';
import GoogleMapsView from '@/components/GoogleMapsView';
import { useAppStore } from '@/store/appStore';

const HAS_GOOGLE_MAPS = Boolean(import.meta.env.VITE_GOOGLE_MAPS_API_KEY);

// ── Status → color + shape mapping ──────────────────────────────────────────
// Shape options: square | circle | diamond | triangle | star | cross
const STATUS_CONFIG: Record<string, { color: string; shape: string; label: string }> = {
  reported:    { color: '#718096', shape: 'square',   label: 'Reported'    },
  verified:    { color: '#3182CE', shape: 'circle',   label: 'Verified'    },
  assigned:    { color: '#805AD5', shape: 'diamond',  label: 'Assigned'    },
  in_progress: { color: '#D69E2E', shape: 'triangle', label: 'In Progress' },
  resolved:    { color: '#38A169', shape: 'star',     label: 'Resolved'    },
  disputed:    { color: '#E53E3E', shape: 'cross',    label: 'Disputed'    },
  closed:      { color: '#2D3748', shape: 'square',   label: 'Closed'      },
};

// ── Category → emoji ────────────────────────────────────────────────────────
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

// ── SVG shape renderer ───────────────────────────────────────────────────────
/**
 * Returns an SVG path/shape string for a given shape name, color, and canvas size.
 * Each shape is visually distinct so color-blind users can differentiate markers.
 */
function getShapeSVG(shape: string, color: string, size: number = 28): string {
  const h = size / 2;
  const shapes: Record<string, string> = {
    // ■ Square — reported
    square: `<rect x="3" y="3" width="${size - 6}" height="${size - 6}" rx="3"
               fill="${color}" stroke="white" stroke-width="2"/>`,
    // ● Circle — verified
    circle: `<circle cx="${h}" cy="${h}" r="${h - 3}"
               fill="${color}" stroke="white" stroke-width="2"/>`,
    // ◆ Diamond — assigned
    diamond: `<polygon points="${h},3 ${size - 3},${h} ${h},${size - 3} 3,${h}"
                fill="${color}" stroke="white" stroke-width="2"/>`,
    // ▲ Triangle up — in_progress
    triangle: `<polygon points="${h},3 ${size - 3},${size - 3} 3,${size - 3}"
                 fill="${color}" stroke="white" stroke-width="2"/>`,
    // ★ Star — resolved
    star: `<polygon
             points="${h},3 ${h + 4},${h - 3} ${size - 3},${h - 3}
                    ${h + 7},${h + 4} ${h + 4},${size - 3}
                    ${h},${h + 6} ${h - 4},${size - 3}
                    ${h - 7},${h + 4} 3,${h - 3} ${h - 4},${h - 3}"
             fill="${color}" stroke="white" stroke-width="1.5"/>`,
    // ✕ Cross — disputed
    cross: `
      <line x1="5"        y1="5"        x2="${size - 5}" y2="${size - 5}"
            stroke="${color}" stroke-width="5" stroke-linecap="round"/>
      <line x1="${size - 5}" y1="5"     x2="5"           y2="${size - 5}"
            stroke="${color}" stroke-width="5" stroke-linecap="round"/>`,
  };
  return shapes[shape] ?? shapes['square'];
}

// ── Leaflet DivIcon factory ──────────────────────────────────────────────────
function createMarkerIcon(issue: Issue): L.DivIcon {
  const cfg = STATUS_CONFIG[issue.status] ?? STATUS_CONFIG['reported'];
  const categoryName = issue.category?.name ?? issue.ai_category ?? 'other';
  const emoji        = CATEGORY_EMOJI[categoryName] ?? '⚠️';
  const size         = 32;
  const isEmergency  = issue.is_emergency;

  const svgContent = `
    <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"
         xmlns="http://www.w3.org/2000/svg"
         role="img"
         aria-label="${cfg.label} issue">
      ${getShapeSVG(cfg.shape, cfg.color, size)}
      <text x="${size / 2}" y="${size / 2 + 5}"
            text-anchor="middle"
            font-size="12"
            dominant-baseline="middle"
            style="user-select:none;pointer-events:none;">
        ${emoji}
      </text>
    </svg>`;

  return L.divIcon({
    html: `
      <div
        class="${isEmergency ? 'emergency-pulse-marker' : ''}"
        title="${cfg.label}: ${issue.title}"
        role="button"
        aria-label="${cfg.label} ${categoryName} issue: ${issue.title}"
        style="
          width:${size}px;
          height:${size}px;
          filter:drop-shadow(0 2px 4px rgba(0,0,0,0.3));
          ${isEmergency ? 'outline:3px solid #E53E3E;border-radius:4px;' : ''}
        "
      >${svgContent}</div>`,
    className: '',
    iconSize:    [size, size],
    iconAnchor:  [size / 2, size / 2],
    popupAnchor: [0, -(size / 2)],
  });
}

// ── Map re-centrer ───────────────────────────────────────────────────────────
/**
 * Child component that watches the `center` prop and calls Leaflet's
 * `setView` whenever it changes, giving a smooth animated pan.
 */
function MapCentreController({ center }: { center: [number, number] }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, map.getZoom(), { animate: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [center[0], center[1]]);
  return null;
}

// ── Props ────────────────────────────────────────────────────────────────────
interface MapViewProps {
  issues: Issue[];
  onIssueSelect: (issue: Issue) => void;
  center: [number, number];
  zoom?: number;
}

// ── Component ────────────────────────────────────────────────────────────────
export default function MapView({
  issues,
  onIssueSelect,
  center,
  zoom = 14,
}: MapViewProps) {
  const mapProvider = useAppStore((state) => state.mapProvider);

  // Use Google Maps if API key is available and selected, otherwise use Leaflet/OSM
  if (HAS_GOOGLE_MAPS && mapProvider === 'google') {
    return (
      <GoogleMapsView
        issues={issues}
        onIssueSelect={onIssueSelect}
        center={center}
        zoom={zoom}
      />
    );
  }

  // Only render markers that have valid coordinates
  const markers = useMemo(
    () => issues.filter((i) => i.latitude != null && i.longitude != null),
    [issues],
  );

  return (
    <div className="w-full h-full relative" role="region" aria-label="Community issue map">
      <MapContainer
        center={center}
        zoom={zoom}
        className="w-full h-full z-0"
        zoomControl={true}
        attributionControl={true}
      >
        {/* Screen reader announcement of marker count */}
        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          {markers.length} issue{markers.length !== 1 ? 's' : ''} on map
        </div>

        {/* OpenStreetMap — free tiles, no API key */}
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          maxZoom={19}
        />

        {/* Smooth re-centre when center prop changes */}
        <MapCentreController center={center} />

        {/* Issue markers */}
        {markers.map((issue) => (
          <Marker
            key={issue.id}
            position={[issue.latitude, issue.longitude]}
            icon={createMarkerIcon(issue)}
            keyboard={true}
            eventHandlers={{
              click: () => onIssueSelect(issue),
              keypress: (e) => {
                if ((e.originalEvent as KeyboardEvent).key === 'Enter') {
                  onIssueSelect(issue);
                }
              },
            }}
          >
            {/* Minimal popup — full detail opens in IssueBottomSheet */}
            <Popup>
              <div className="text-xs max-w-[200px] space-y-1">
                <p className="font-semibold text-gray-800 line-clamp-2">{issue.title}</p>
                <p className="text-gray-500">
                  {STATUS_CONFIG[issue.status]?.label ?? issue.status}
                </p>
                <button
                  onClick={() => onIssueSelect(issue)}
                  className="text-blue-600 underline text-xs"
                >
                  View details →
                </button>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>

      {/* ── Legend ─────────────────────────────────────────────── */}
      <div
        className="absolute bottom-20 left-2 bg-white/90 backdrop-blur-sm rounded-xl px-3 py-2 shadow-md z-10 text-xs"
        aria-label="Map legend"
        role="complementary"
      >
        <p className="font-semibold text-gray-700 mb-1.5 text-[11px]">Status</p>
        {Object.entries(STATUS_CONFIG)
          .filter(([k]) => k !== 'closed')
          .map(([status, cfg]) => (
            <div key={status} className="flex items-center gap-1.5 mb-1 last:mb-0">
              <svg
                width="14"
                height="14"
                viewBox="0 0 28 28"
                aria-hidden="true"
                dangerouslySetInnerHTML={{ __html: getShapeSVG(cfg.shape, cfg.color, 28) }}
                style={{ flexShrink: 0 }}
              />
              <span className="text-gray-600 text-[11px]">{cfg.label}</span>
            </div>
          ))}
      </div>

      {/* ── Emergency pulse CSS ────────────────────────────────── */}
      <style>{`
        .emergency-pulse-marker {
          animation: emergencyPulse 1.4s ease-in-out infinite;
        }
        @keyframes emergencyPulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(229, 62, 62, 0.6); }
          50%       { box-shadow: 0 0 0 8px rgba(229, 62, 62, 0); }
        }
        .leaflet-container {
          font-family: inherit;
        }
      `}</style>
    </div>
  );
}
