// A civic hall that stands up out of the map: a long block behind a facade that hinges up, a portico of columns
// under a pediment, and a dome on a colonnaded drum with a lantern. A drawing of "a domed city hall", not a
// survey. Its own frame: x along the facade, y up, z out of the front door. The origin is the middle of its floor.

import { BufferGeometry, CylinderGeometry, Float32BufferAttribute, Group, SphereGeometry } from "three";
import { printObject, type World } from "../world";
import { CITY_HALL_PLAN } from "./plans";
import { arch, box, card, castShadow, drum, grow, hinge, inked, merge, plate, RAD, rect, riser, settle, smooth, span, type Fold } from "./build";


export interface CityHall {
  group: Group;
  /** 0 flat, 1 standing. */
  fold(amount: number): void;
  setBase(y: number): void;
}

/** A roof with a gable at the front: a triangular prism lying along z. */
function prism(w: number, h: number, d: number): BufferGeometry {
  const a = [-w / 2, 0, d / 2], b = [w / 2, 0, d / 2], c = [0, h, d / 2];
  const e = [-w / 2, 0, -d / 2], f = [w / 2, 0, -d / 2], g = [0, h, -d / 2];
  const tris = [a, b, c, f, e, g, a, c, g, a, g, e, b, f, g, b, g, c];
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(tris.flat(), 3));
  geometry.computeVertexNormals();
  return geometry;
}

export function createCityHall(world: World): CityHall {
  const P = CITY_HALL_PLAN;
  const group = new Group();
  const folds: { fold: Fold; from: number; to: number; ease: (t: number) => number }[] = [];
  const add = (fold: Fold, from: number, to: number, ease: (t: number) => number = smooth): Fold => {
    group.add(fold.group);
    folds.push({ fold, from, to, ease });
    return fold;
  };
  const front = P.depth / 2;

  // ---- the facade: one long card with its windows, hinged at the foot ---------------------------------------------
  const windows: BufferGeometry[] = [];
  for (const side of [-1, 1]) {
    for (let i = 0; i < 6; i++) {
      const x = side * (22.5 + i * 5.4);
      windows.push(plate(arch(2.5, 9, x, 4.6), [], 0.14), plate(rect(2.2, 2, x, 16.4), [], 0.14));
    }
  }
  for (const x of [-9, 0, 9]) windows.push(plate(arch(3.4, 10, x, 2.4), [], 0.14));
  const facade = card(world, plate(rect(P.width, P.height)));
  const facadeInk = inked(world, merge(...windows));
  add(hinge(world, [facade.group, facadeInk.group], { at: [0, 0.05, front + 0.1], yaw: 0 }), 0, 0.36, settle);

  // ---- the block behind it, and its attic ---------------------------------------------------------------------------
  const body = printObject(world, box(P.width, P.height, P.depth));
  add(grow(world, [body.group]), 0.12, 0.46);
  const attic = printObject(world, box(P.width - 10, 3.4, P.depth - 10));
  add(grow(world, [attic.group], [0, P.height, 0]), 0.42, 0.56);

  // ---- the portico: steps, eight columns, an entablature, a pediment ---------------------------------------------
  const steps = printObject(world, merge(box(44, 1.2, P.portico + 1.5, 0, 0, front + (P.portico + 1.5) / 2), box(39, 1.2, P.portico - 1.5, 0, 1.2, front + (P.portico - 1.5) / 2)));
  add(grow(world, [steps.group]), 0.26, 0.4);
  const columns: BufferGeometry[] = [];
  for (let i = 0; i < 8; i++) columns.push(drum(1.15, 13, -15.75 + i * 4.5, 0, front + 5.6, 8));
  const colonnade = printObject(world, merge(...columns), { crease: 50, outline: 0.8 });
  add(grow(world, [colonnade.group], [0, 2.4, 0]), 0.38, 0.6);
  const entablature = printObject(world, box(36, 2.4, 7, 0, 0, front + 3.4));
  add(riser(world, [entablature.group], [0, 2.4, 0], [0, 15.4, 0], true), 0.38, 0.6);
  const pediment = printObject(world, prism(36, 6, 7).translate(0, 0, front + 3.4));
  add(grow(world, [pediment.group], [0, 17.8, 0]), 0.58, 0.7, settle);

  // ---- the dome: an eight-sided base, a drum ringed with columns, the dome, a lantern --------------------------
  const baseY = P.height + 3.4;
  const octagon = drum(22, 5, 0, 0, 0, 8);
  octagon.rotateY(22.5 * RAD);
  const base = printObject(world, octagon);
  add(grow(world, [base.group], [0, baseY, 0]), 0.5, 0.62);
  const ring: BufferGeometry[] = [drum(15.2, 15, 0, 0, 0, 28), drum(17.4, 1.3, 0, 15, 0, 28)];
  for (let i = 0; i < 18; i++) {
    const a = (i / 18) * 360;
    ring.push(drum(0.85, 13.4, Math.sin(a * RAD) * 16.3, 0.4, Math.cos(a * RAD) * 16.3, 6));
  }
  const drumPart = printObject(world, merge(...ring), { crease: 50, outline: 0.8 });
  add(grow(world, [drumPart.group], [0, baseY + 5, 0]), 0.58, 0.76);
  const shell = new SphereGeometry(15.4, 28, 9, 0, Math.PI * 2, 0, Math.PI / 2);
  shell.scale(1, 1.28, 1);
  const dome = printObject(world, shell, { crease: 60 });
  add(grow(world, [dome.group], [0, baseY + 21.3, 0]), 0.72, 0.9, settle);
  const spire = new CylinderGeometry(0.15, 2.7, 9.5, 10);
  spire.translate(0, 7.4 + 4.75, 0);
  const lantern = printObject(world, merge(drum(3.5, 6.6, 0, 0, 0, 10), drum(4.1, 0.8, 0, 6.6, 0, 10), spire), { crease: 40 });
  add(grow(world, [lantern.group], [0, baseY + 21.3 + 19.4, 0]), 0.86, 1, settle);

  // ---- the shadow -------------------------------------------------------------------------------------------------------
  const shadow = castShadow(world, merge(box(P.width, P.height + 3.4, P.depth), drum(16, 21, 0, baseY, 0, 14), drum(13, 26, 0, baseY + 21, 0, 12, 3)), false);
  const shadowGroup = new Group();
  shadowGroup.add(shadow.mesh);
  group.add(shadowGroup);

  let last = Number.NaN;
  const api: CityHall = {
    group,
    fold(amount) {
      if (amount === last) return;
      last = amount;
      for (const f of folds) f.fold.set(f.ease(span(amount, f.from, f.to)));
      const up = smooth(span(amount, 0.1, 0.9));
      shadowGroup.visible = up > 0.01;
      shadowGroup.scale.y = Math.max(0.001, up);
      world.invalidate();
    },
    setBase(y) {
      shadow.setBase(y);
    },
  };
  api.fold(0);
  return api;
}
