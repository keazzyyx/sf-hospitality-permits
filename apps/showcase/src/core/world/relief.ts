// The rise of the ground, as arithmetic (no three.js): the same formula the line shader uses, so a label or a
// drawing made without WebGL can ask how high the ground is.

/** A rise in the ground: a smooth bump the street lines and anything planted on it follow. */
export interface Relief {
  x: number;
  z: number;
  /** Metres from the top to where the bump has all but gone. */
  radius: number;
  /** Metres at the top. */
  height: number;
}

/** Height of the ground at a point, in metres, with every rise fully up. */
export function reliefHeight(reliefs: readonly Relief[], x: number, z: number): number {
  let h = 0;
  for (const r of reliefs) {
    const dx = x - r.x, dz = z - r.z;
    h += r.height * Math.exp(-(dx * dx + dz * dz) / (0.36 * r.radius * r.radius));
  }
  return h;
}
