// A fluted tower on a round step: a tapering shaft, an arcaded gallery near the top, a narrower crown. It
// telescopes up out of the map (the gallery slides out of the shaft, the crown out of the gallery).

import { CylinderGeometry, Group, type BufferGeometry } from "three";
import { printObject, type World } from "../world";
import { TOWER_PLAN } from "./plans";
import { box, castShadow, drum, grow, inked, merge, RAD, riser, smooth, span, type Fold } from "./build";


export interface Tower {
  group: Group;
  /** 0 flat, 1 standing. */
  fold(amount: number): void;
  setBase(y: number): void;
  /** 0 to 1: how long its shadow is (1: the whole shadow). For a close shot that leaves the tower out. */
  setShadow(amount: number): void;
}

export function createTower(world: World): Tower {
  const group = new Group();
  const folds: { fold: Fold; from: number; to: number }[] = [];
  const add = (parent: Group, fold: Fold, from: number, to: number): Fold => {
    parent.add(fold.group);
    folds.push({ fold, from, to });
    return fold;
  };
  // a low square podium and a round step
  const podium = printObject(world, merge(box(30, 1.6, 30), drum(12.5, 1.4, 0, 1.6, 0, 28)), { crease: 40 });
  add(group, grow(world, [podium.group]), 0, 0.18);
  // the shaft: eighteen flat flutes, each edge inked
  const shaftGeometry = new CylinderGeometry(7.5, TOWER_PLAN.radius, 40, 18);
  shaftGeometry.translate(0, 20, 0);
  const shaft = printObject(world, shaftGeometry, { crease: 12, outline: 0.7 });
  add(group, grow(world, [shaft.group], [0, 3, 0]), 0.1, 0.56);
  // the gallery: a drum with a ring of arched openings, under a cornice
  const openings: BufferGeometry[] = [];
  for (let i = 0; i < 14; i++) {
    const a = (i / 14) * 360 + 6;
    openings.push(box(1.5, 4.6, 0.3, Math.sin(a * RAD) * 7.05, 1.6, Math.cos(a * RAD) * 7.05, a));
  }
  const gallery = printObject(world, merge(drum(7.05, 8, 0, 0, 0, 28), drum(7.9, 1, 0, 8, 0, 28)), { crease: 40 });
  const galleryInk = inked(world, merge(...openings));
  const galleryFold = add(group, riser(world, [gallery.group, galleryInk.group], [0, 34, 0], [0, 43, 0], true), 0.5, 0.78);
  const crown = printObject(world, merge(drum(5.2, 4.6, 0, 0, 0, 24), drum(5.7, 0.7, 0, 4.6, 0, 24)), { crease: 40 });
  add(galleryFold.group, riser(world, [crown.group], [0, 3.4, 0], [0, 9, 0], true), 0.74, 0.96);

  const shadow = castShadow(world, merge(drum(TOWER_PLAN.radius, 52, 0, 0, 0, 14, 7.2), drum(5.4, 6, 0, 52, 0, 12)));
  const shadowGroup = new Group();
  shadowGroup.add(shadow.mesh);
  group.add(shadowGroup);

  let last = Number.NaN;
  let cast = 1;
  let up = 0;
  const applyShadow = (): void => {
    shadowGroup.visible = up * cast > 0.01;
    shadowGroup.scale.y = Math.max(0.001, up * cast);
  };
  const api: Tower = {
    group,
    fold(amount) {
      if (amount === last) return;
      last = amount;
      for (const f of folds) f.fold.set(smooth(span(amount, f.from, f.to)));
      up = smooth(span(amount, 0.05, 0.95));
      applyShadow();
      world.invalidate();
    },
    setShadow(amount) {
      if (amount === cast) return;
      cast = amount;
      applyShadow();
      world.invalidate();
    },
    setBase(y) {
      shadow.setBase(y);
    },
  };
  api.fold(0);
  return api;
}
