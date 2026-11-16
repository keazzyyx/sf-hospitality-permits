import { CATEGORY_LABELS, SUPPORTED_CITIES } from "@sfhp/catalog";
import type { Category } from "@/lib/api-types";

export { CATEGORY_LABELS, SUPPORTED_CITIES };

export function categoryLabel(category: string): string {
  return (CATEGORY_LABELS as Record<string, string>)[category] ?? category.replace(/_/g, " ");
}

/** Stable display order for grouped permit lists: the order operators tackle them. */
export const CATEGORY_ORDER: Category[] = [
  "business_registration",
  "federal_tax",
  "state_tax",
  "local_tax",
  "zoning",
  "building",
  "fire",
  "health",
  "food_safety_cert",
  "grease",
  "alcohol",
  "entertainment",
  "music_licensing",
  "outdoor_dining",
  "signage",
  "hotel",
  "mobile_vending",
  "labor",
  "other",
];

export function groupBy<T, K extends string>(items: T[], key: (item: T) => K): { key: K; items: T[] }[] {
  const map = new Map<K, T[]>();
  for (const item of items) {
    const k = key(item);
    const bucket = map.get(k);
    if (bucket) bucket.push(item);
    else map.set(k, [item]);
  }
  return Array.from(map, ([k, v]) => ({ key: k, items: v }));
}

export function sortCategories<T extends { key: string }>(groups: T[]): T[] {
  const rank = (k: string) => {
    const i = CATEGORY_ORDER.indexOf(k as Category);
    return i === -1 ? CATEGORY_ORDER.length : i;
  };
  return groups.slice().sort((a, b) => rank(a.key) - rank(b.key));
}
