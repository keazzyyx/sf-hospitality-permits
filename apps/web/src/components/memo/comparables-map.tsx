"use client";

import { useMemo } from "react";
import L from "leaflet";
import { Circle, CircleMarker, GeoJSON, MapContainer, Marker, Popup, TileLayer, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { formatDistance, outcomeBucket, OUTCOME_HEX, OUTCOME_LABELS, outcomeLabel, overlayKindHex } from "@/lib/memo";
import type { ComparableCase, GeoJsonFeatureCollection } from "@/lib/api-types";

export const RING_500_FT_M = 152.4;
export const RING_1000_FT_M = 304.8;

export interface ComparablesMapProps {
  subject: { lat: number; lng: number; address: string };
  cases: ComparableCase[];
  geojson?: GeoJsonFeatureCollection | null;
  className?: string;
}

const SUBJECT_ICON = L.divIcon({
  className: "pp-subject-marker",
  html: '<span style="display:block;width:18px;height:18px;border-radius:9999px;background:#e4572e;border:3px solid #fffdf9;box-shadow:0 0 0 2px #e4572e, 0 4px 12px rgba(20,27,45,.35)"></span>',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
  popupAnchor: [0, -12],
});

function isAreaFeature(f: GeoJsonFeatureCollection["features"][number]): boolean {
  const t = f.geometry?.type ?? "";
  return t === "Polygon" || t === "MultiPolygon" || t === "LineString" || t === "MultiLineString";
}

/** `map.geojson` marks every overlay feature `kind: "overlay"` and puts the overlay's own kind in `overlay_kind`. */
function overlayKind(properties: unknown): string | null {
  const p = (properties ?? {}) as Record<string, unknown>;
  if (typeof p.overlay_kind === "string") return p.overlay_kind;
  return typeof p.kind === "string" ? p.kind : null;
}

/**
 * Leaflet + OpenStreetMap tiles (no API key). Subject marker, comparable cases as circle markers
 * coloured by outcome, 500 ft / 1,000 ft rings and overlay polygons from `map.geojson` styled by kind.
 * Rendered only in the browser via `ComparablesMapLazy`.
 */
export default function ComparablesMap({ subject, cases, geojson, className }: ComparablesMapProps) {
  const center: [number, number] = [subject.lat, subject.lng];
  const overlays = useMemo(() => {
    if (!geojson) return null;
    const features = geojson.features.filter(isAreaFeature);
    if (features.length === 0) return null;
    return { type: "FeatureCollection", features } as unknown as GeoJSON.FeatureCollection;
  }, [geojson]);

  const legend = useMemo(() => {
    const seen = new Map<string, string>();
    for (const c of cases) {
      const b = outcomeBucket(c.outcome);
      if (!seen.has(b)) seen.set(b, OUTCOME_LABELS[b]);
    }
    return Array.from(seen.entries());
  }, [cases]);

  return (
    <div className={className}>
      <MapContainer center={center} zoom={16} scrollWheelZoom={false} className="h-[380px] w-full rounded-xl sm:h-[440px]" attributionControl>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
        />
        {overlays && (
          <GeoJSON
            key={geojson?.features.length ?? 0}
            data={overlays}
            style={(feature) => {
              const color = overlayKindHex(overlayKind(feature?.properties));
              return { color, weight: 1.5, fillColor: color, fillOpacity: 0.05, dashArray: "4 3" };
            }}
            onEachFeature={(feature, layer) => {
              const props = (feature.properties ?? {}) as Record<string, unknown>;
              const name = typeof props.name === "string" ? props.name : "Overlay";
              const kind = (overlayKind(props) ?? "").replace(/_/g, " ");
              layer.bindTooltip(`${name}${kind ? ` · ${kind}` : ""}`, { sticky: true });
            }}
          />
        )}
        <Circle center={center} radius={RING_1000_FT_M} pathOptions={{ color: "#141b2d", weight: 1, fillOpacity: 0.02, dashArray: "6 4" }}>
          <Tooltip direction="top" offset={[0, -RING_1000_FT_M / 2]} permanent={false}>
            1,000 ft
          </Tooltip>
        </Circle>
        <Circle center={center} radius={RING_500_FT_M} pathOptions={{ color: "#141b2d", weight: 1.25, fillOpacity: 0.04 }}>
          <Tooltip>500 ft</Tooltip>
        </Circle>
        {cases
          .filter((c): c is ComparableCase & { lat: number; lng: number } => typeof c.lat === "number" && typeof c.lng === "number")
          .map((c) => {
            const bucket = outcomeBucket(c.outcome);
            return (
              <CircleMarker
                key={c.application_id}
                center={[c.lat, c.lng]}
                radius={7 + Math.round(c.similarity_score * 5)}
                pathOptions={{ color: "#fffdf9", weight: 2, fillColor: OUTCOME_HEX[bucket], fillOpacity: 0.9 }}
              >
                <Popup>
                  <div style={{ minWidth: 200, fontSize: 13, lineHeight: 1.4 }}>
                    <strong>{c.address ?? c.application_id}</strong>
                    <div style={{ color: "#5c6270", fontSize: 12 }}>
                      {c.permit_type} · {formatDistance(c.distance_m)}
                    </div>
                    <div style={{ marginTop: 6 }}>
                      <span style={{ color: OUTCOME_HEX[bucket], fontWeight: 600 }}>{outcomeLabel(c.outcome)}</span>
                      {c.hours_close ? ` · closes ${c.hours_close}` : ""}
                    </div>
                    <a href={c.source_url} target="_blank" rel="noreferrer noopener" style={{ display: "inline-block", marginTop: 8, fontSize: 12 }}>
                      Open source record
                    </a>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
        <Marker position={center} icon={SUBJECT_ICON} zIndexOffset={1000}>
          <Popup>
            <strong>Subject address</strong>
            <div style={{ fontSize: 12 }}>{subject.address}</div>
          </Popup>
        </Marker>
      </MapContainer>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Map legend">
        <span className="inline-flex items-center gap-1.5">
          <span className="size-3 rounded-full border-2 border-card bg-signal ring-1 ring-signal" aria-hidden /> Subject address
        </span>
        {legend.map(([bucket, label]) => (
          <span key={bucket} className="inline-flex items-center gap-1.5">
            <span className="size-3 rounded-full" style={{ background: OUTCOME_HEX[bucket as keyof typeof OUTCOME_HEX] }} aria-hidden /> {label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="size-3 rounded-full border border-ink/60" aria-hidden /> 500 ft / 1,000 ft rings
        </span>
        {overlays && (
          <span className="inline-flex items-center gap-1.5">
            <span className="size-3 rounded-sm border border-dashed border-muted-foreground bg-muted" aria-hidden /> Overlay districts
          </span>
        )}
      </div>
    </div>
  );
}
