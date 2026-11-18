// A small seeded random source (mulberry32): the same seed always gives the same mark, crack and flecks.

export type Rng = () => number;

/** A function that returns the next number in [0, 1) of the sequence that `seed` starts. */
export function rng(seed: number): Rng {
  let a = seed >>> 0 || 0x9e3779b9;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A number in [lo, hi). */
export const between = (r: Rng, lo: number, hi: number): number => lo + (hi - lo) * r();

/** A seed that differs on every call (the time and a counter), for replays that should not repeat. */
let calls = 0;
export function freshSeed(): number {
  calls += 1;
  return (Date.now() ^ Math.imul(calls, 0x9e3779b1)) >>> 0;
}
