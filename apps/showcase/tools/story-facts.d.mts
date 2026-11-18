/** The part of story.json that the front page's story shows. */
export function subset(story: unknown): Record<string, unknown>;
/** The same, read from src/data/story.json. */
export function readSubset(): Record<string, unknown>;
export const SOURCE: string;
