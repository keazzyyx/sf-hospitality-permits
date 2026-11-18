// A damped spring stepped by time (semi-implicit Euler in fixed substeps, so it is stable at any frame rate).

export class Spring {
  value: number;
  velocity = 0;
  target: number;

  constructor(
    value = 0,
    public stiffness = 170,
    public damping = 26,
    public mass = 1,
  ) {
    this.value = value;
    this.target = value;
  }

  /** Advance by `dt` seconds. Returns true while the spring is still moving. */
  step(dt: number): boolean {
    let left = Math.min(dt, 0.1);
    while (left > 0) {
      const h = Math.min(left, 1 / 240);
      const a = (-this.stiffness * (this.value - this.target) - this.damping * this.velocity) / this.mass;
      this.velocity += a * h;
      this.value += this.velocity * h;
      left -= h;
    }
    if (Math.abs(this.velocity) < 0.001 && Math.abs(this.value - this.target) < 0.001) {
      this.value = this.target;
      this.velocity = 0;
      return false;
    }
    return true;
  }

  /** Put the spring at `value`, at rest. */
  set(value: number): void {
    this.value = value;
    this.target = value;
    this.velocity = 0;
  }

  get resting(): boolean {
    return this.velocity === 0 && this.value === this.target;
  }
}

/** Move `current` toward `target` with time constant `tau` seconds (exponential ease, frame-rate independent). */
export function follow(current: number, target: number, dt: number, tau: number): number {
  if (tau <= 0) return target;
  return target + (current - target) * Math.exp(-dt / tau);
}

export const clamp = (x: number, lo: number, hi: number): number => (x < lo ? lo : x > hi ? hi : x);
export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;
export const smoothstep = (t: number): number => {
  const x = clamp(t, 0, 1);
  return x * x * (3 - 2 * x);
};
