/**
 * Shared types + helpers for the Permit Memo permit catalog.
 * The JSON files under ./data are the source of truth; the API loads them with Python.
 */
export type Confidence = "verified" | "estimated";
export type JurisdictionLevel = "federal" | "state" | "county" | "city";
export type Category =
  | "business_registration" | "federal_tax" | "state_tax" | "local_tax" | "health" | "food_safety_cert"
  | "building" | "fire" | "alcohol" | "zoning" | "signage" | "grease" | "entertainment" | "outdoor_dining"
  | "labor" | "music_licensing" | "hotel" | "mobile_vending" | "other";

export interface Range { min: number; max: number }

export type Rule =
  | { always: true }
  | { all: Rule[] }
  | { any: Rule[] }
  | { not: Rule }
  | ({ field: string } & Partial<Record<"eq" | "neq" | "in" | "not_in" | "gt" | "gte" | "lt" | "lte", unknown>>);

export interface CatalogPermit {
  id: string;
  name: string;
  category: Category;
  issuing_agency: string;
  jurisdiction_level: JurisdictionLevel;
  typical_timeline_days: Range;
  fee_range_usd: Range;
  prerequisites: string[];
  applies_when: Rule;
  application_url: string;
  notes: string;
  last_verified: string;
  confidence: Confidence;
  sources?: string[];
  renewal?: string;
  stall_risk?: string;
}

export interface CatalogFile {
  jurisdiction: {
    level: "federal" | "state" | "city";
    name: string;
    state: string | null;
    city_slug: string | null;
    county?: string | null;
    supported?: boolean;
    aliases?: string[];
    notes?: string;
  };
  permits: CatalogPermit[];
}

export const SUPPORTED_CITIES: { slug: string; name: string; state: string }[] = [
  { slug: "san_francisco", name: "San Francisco", state: "CA" },
  { slug: "los_angeles", name: "Los Angeles", state: "CA" },
  { slug: "san_diego", name: "San Diego", state: "CA" },
  { slug: "new_york_city", name: "New York City", state: "NY" },
  { slug: "austin", name: "Austin", state: "TX" },
  { slug: "houston", name: "Houston", state: "TX" },
  { slug: "miami", name: "Miami", state: "FL" },
  { slug: "chicago", name: "Chicago", state: "IL" },
  { slug: "denver", name: "Denver", state: "CO" },
  { slug: "seattle", name: "Seattle", state: "WA" },
];

export const CATEGORY_LABELS: Record<Category, string> = {
  business_registration: "Business registration",
  federal_tax: "Federal tax",
  state_tax: "State tax",
  local_tax: "Local tax",
  health: "Health",
  food_safety_cert: "Food safety certification",
  building: "Building",
  fire: "Fire",
  alcohol: "Alcohol",
  zoning: "Zoning",
  signage: "Signage",
  grease: "Grease / wastewater",
  entertainment: "Entertainment",
  outdoor_dining: "Outdoor dining",
  labor: "Labor / payroll",
  music_licensing: "Music licensing",
  hotel: "Hotel",
  mobile_vending: "Mobile vending",
  other: "Other",
};
