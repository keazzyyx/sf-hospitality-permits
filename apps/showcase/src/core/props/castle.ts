// A little castle that folds up out of the map like a pop-up book: a crenellated hall, a round corner turret in
// three telescoping sections, a square keep, and a lower wing with a roof terrace. Closed, it is a plan lying on
// its base card; opening, the walls hinge up from flat, the roofs rise between them, the turret telescopes, and
// the battlements flip up last. It is a drawing of "a small castle on a steep street", not a survey of one.
//
// The castle's own frame: x along the street (east), y up, z towards the street. Its origin is the middle of
// the hall's floor, on top of the base card; the base goes down from there, to be planted in a slope.

import { CylinderGeometry, Group, type BufferGeometry, type Object3D } from "three";
import { createSegments, printObject, type World } from "../world";
import { CASTLE_PLAN } from "./plans";
import { arch, battlement, box, card, castShadow, drum, grow, hinge, inked, merge, plate, RAD, rect, riser, settle, slab, smooth, span, type Fold, type Pt } from "./build";

export interface Castle {
  group: Group;
  /** 0: the closed book (a plan on its base card). 1: standing. */
  fold(amount: number): void;
  /** The height (world y) of the ground it stands on, for its shadow. */
  setBase(y: number): void;
}

const P = CASTLE_PLAN;

/** A plate turned to face a way and put somewhere: for cards that stand without a hinge. */
function stand(g: BufferGeometry, yaw: number, x: number, y: number, z: number): BufferGeometry {
  g.rotateY(yaw * RAD);
  g.translate(x, y, z);
  return g;
}

export function createCastle(world: World): Castle {
  const group = new Group();
  const folds: { fold: Fold; from: number; to: number; ease: (t: number) => number }[] = [];
  const add = (parent: Object3D, fold: Fold, from: number, to: number, ease: (t: number) => number = settle): Fold => {
    parent.add(fold.group);
    folds.push({ fold, from, to, ease });
    return fold;
  };

  // ---- the base card: a level pad, with walls that go down into the slope ---------------------------------------
  const b = P.base;
  // a retaining wall of stone, drawn as a print draws one: every face paper, the courses ruled along the front,
  // and the end that faces away from the light shaded with pencil strokes instead of a block of colour
  const base = printObject(world, box(b.x1 - b.x0, b.depth, b.z1 - b.z0, (b.x0 + b.x1) / 2, -b.depth, (b.z0 + b.z1) / 2), { flat: true });
  group.add(base.group);
  const starts: number[] = [];
  const ends: number[] = [];
  const line = (x0: number, y0: number, z0: number, x1: number, y1: number, z1: number): void => {
    starts.push(x0, y0, z0);
    ends.push(x1, y1, z1);
  };
  const course = 1.5;
  const faceZ = b.z1 + 0.03, east = b.x1 + 0.03;
  for (let k = 1; k <= 6; k++) {
    const y = -k * course;
    line(b.x0, y, faceZ, b.x1, y, faceZ);
    // the joints between the stones of a course, staggered from the course above
    for (let x = b.x0 + (k % 2 ? 3.2 : 6.4); x < b.x1 - 1; x += 6.4) line(x, y, faceZ, x, y + course, faceZ);
  }
  // the shaded end: strokes down the face at a slant, closer together than the courses
  const lean = 0.55;
  for (let z = b.z0 - 9 * lean; z < b.z1; z += 1.15) {
    const z0 = Math.max(b.z0, z), z1 = Math.min(b.z1, z + 9.6 * lean);
    if (z1 <= z0) continue;
    line(east, -(z0 - z) / lean, z0, east, -(z1 - z) / lean, z1);
  }
  const stone = createSegments(world, { starts: new Float32Array(starts), ends: new Float32Array(ends), width: 0.8, color: "ink2", opacity: 0.8, depthTest: true, relief: false, renderOrder: 3 });
  group.add(stone.mesh);
  // a short stair down to the street from the door: three treads, each wider than the one above
  const steps = printObject(world, merge(box(5.6, 0.5, 1.2, P.door.x, -0.5, b.z1 + 0.6), box(6.8, 0.5, 1.2, P.door.x, -1, b.z1 + 1.8), box(8, 0.5, 1.2, P.door.x, -1.5, b.z1 + 3)));
  group.add(steps.group);

  // ---- the hall: four walls that hinge up from lying inwards, a roof that rises between them ----------------------
  const { w, d, h } = P.hall;
  const front = card(world, plate(rect(w, h)));
  const frontInk = inked(
    world,
    merge(
      plate(arch(P.door.w, P.door.h, P.door.x), [], 0.12),
      // the tall windows of the dining room
      plate(arch(2, 4.4, -3.6, 7.4), [], 0.12),
      plate(arch(2, 4.4, 1.2, 7.4), [], 0.12),
      plate(arch(2, 4.4, 6, 7.4), [], 0.12),
      plate(arch(2, 4.4, 10.4, 7.4), [], 0.12),
      plate(rect(1.6, 2.2, -3.6, 2), [], 0.12),
      plate(rect(1.6, 2.2, 9.6, 2), [], 0.12),
    ),
  );
  add(group, hinge(world, [front.group, frontInk.group], { at: [0, 0.04, d / 2], yaw: 0 }), 0.2, 0.5);

  const right = card(world, plate(rect(d, h)));
  const rightInk = inked(world, merge(plate(arch(1.8, 3.6, -3, 9.8), [], 0.12), plate(arch(1.8, 3.6, 1.6, 9.8), [], 0.12)));
  add(group, hinge(world, [right.group, rightInk.group], { at: [w / 2, 0.08, 0], yaw: 90 }), 0.1, 0.38);

  const left = card(world, plate(rect(d, h)));
  add(group, hinge(world, [left.group], { at: [-w / 2, 0.12, 0], yaw: -90 }), 0.06, 0.34);

  const back = card(world, plate(rect(w, h)));
  add(group, hinge(world, [back.group], { at: [0, 0.16, -d / 2], yaw: 180 }), 0, 0.28);

  const roof = card(world, slab(rect(w, d, 0, -d / 2)));
  const roofFold = add(group, riser(world, [roof.group], [0, 0.2, 0], [0, h, 0]), 0.3, 0.56, smooth);
  // the battlements lie on the roof and flip up along its edges
  const teeth = (length: number): BufferGeometry => plate(battlement(length, 0.9, 1.9, 1.5).map(p => [p[0] - length / 2, p[1]] as Pt));
  const k = P.keep;
  const tr = P.turret.r;
  const frontLength = w - tr + 0.2;
  add(roofFold.group, hinge(world, [card(world, teeth(frontLength)).group], { at: [w / 2 - frontLength / 2, 0.02, d / 2], yaw: 0 }), 0.6, 0.72);
  add(roofFold.group, hinge(world, [card(world, teeth(d / 2)).group], { at: [w / 2, 0.03, d / 4], yaw: 90 }), 0.64, 0.76);
  const backLength = w - (k.x1 - k.x0);
  add(roofFold.group, hinge(world, [card(world, teeth(backLength)).group], { at: [-w / 2 + backLength / 2, 0.04, -d / 2], yaw: 180 }), 0.68, 0.8);
  const leftLength = d - tr + 0.6;
  add(roofFold.group, hinge(world, [card(world, teeth(leftLength)).group], { at: [-w / 2, 0.05, -d / 2 + leftLength / 2], yaw: -90 }), 0.66, 0.78);

  // ---- the keep: a square tower that comes up through the roof ---------------------------------------------------
  const kw = k.x1 - k.x0, kd = k.z1 - k.z0, kh = k.h - h;
  const keepBody = printObject(world, box(kw, kh, kd));
  const keepInk = inked(world, merge(plate(arch(1.4, 3, 0, 2.4), [], kd / 2 + 0.12), stand(plate(arch(1.4, 3, 0, 2.4), [], 0.12), 90, kw / 2, 0, 0)));
  const keepTeeth = (length: number): BufferGeometry => plate(battlement(length, 0.6, 1.5, 1.3).map(p => [p[0] - length / 2, p[1]] as Pt));
  const keepCrown = card(
    world,
    merge(stand(keepTeeth(kw), 0, 0, kh, kd / 2), stand(keepTeeth(kw), 180, 0, kh, -kd / 2), stand(keepTeeth(kd), 90, kw / 2, kh, 0), stand(keepTeeth(kd), -90, -kw / 2, kh, 0)),
  );
  add(group, grow(world, [keepBody.group, keepInk.group, keepCrown.group], [(k.x0 + k.x1) / 2, h, (k.z0 + k.z1) / 2]), 0.52, 0.74);

  // ---- the wing: three walls, and the roof terrace -----------------------------------------------------------------
  const g = P.wing;
  const ww = g.x1 - g.x0, wd = g.z1 - g.z0, wx = (g.x0 + g.x1) / 2, wz = (g.z0 + g.z1) / 2;
  const wingFront = card(world, plate(rect(ww, g.h)));
  const wingFrontInk = inked(world, merge(plate(arch(2.6, 4.6, -4.6, 1.6), [], 0.12), plate(arch(2.6, 4.6, 0, 1.6), [], 0.12), plate(arch(2.6, 4.6, 4.6, 1.6), [], 0.12)));
  add(group, hinge(world, [wingFront.group, wingFrontInk.group], { at: [wx, 0.05, g.z1], yaw: 0 }), 0.4, 0.64);
  const wingRight = card(world, plate(rect(wd, g.h)));
  const wingRightInk = inked(world, merge(plate(arch(2.2, 4.2, -2.6, 1.6), [], 0.12), plate(arch(2.2, 4.2, 2.6, 1.6), [], 0.12)));
  add(group, hinge(world, [wingRight.group, wingRightInk.group], { at: [g.x1, 0.09, wz], yaw: 90 }), 0.34, 0.56);
  const wingBack = card(world, plate(rect(ww, g.h)));
  add(group, hinge(world, [wingBack.group], { at: [wx, 0.13, g.z0], yaw: 180 }), 0.28, 0.5);

  const terrace = card(world, slab(rect(ww, wd, wx, -g.z1)));
  const terraceFold = add(group, riser(world, [terrace.group], [0, 0.24, 0], [0, g.h, 0]), 0.5, 0.68, smooth);
  // the parapet round the terrace: a low rail with posts
  const rail = (length: number): BufferGeometry => plate(battlement(length, 0.75, 0.5, 0.5, 2.3).map(p => [p[0] - length / 2, p[1]] as Pt));
  add(terraceFold.group, hinge(world, [card(world, rail(ww)).group], { at: [wx, 0.02, g.z1], yaw: 0 }), 0.68, 0.8);
  add(terraceFold.group, hinge(world, [card(world, rail(wd)).group], { at: [g.x1, 0.03, wz], yaw: 90 }), 0.71, 0.83);
  add(terraceFold.group, hinge(world, [card(world, rail(ww)).group], { at: [wx, 0.04, g.z0], yaw: 180 }), 0.74, 0.86);
  // what makes it a terrace: tables, and a parasol
  const table = (x: number, z: number): BufferGeometry[] => [box(0.24, 0.9, 0.24, x, 0, z), drum(1.05, 0.14, x, 0.9, z, 12)];
  const shade = new CylinderGeometry(0.1, 2.5, 1.1, 10);
  shade.translate(wx + 3.6, 3.15, wz + 1.6);
  const furniture = printObject(world, merge(...table(wx - 4.4, wz + 2.6), ...table(wx - 0.4, wz - 2.4), ...table(wx + 3.6, wz + 1.6), box(0.2, 2.7, 0.2, wx + 3.6, 0, wz + 1.6), shade), { crease: 35, profile: 0.9 });
  add(terraceFold.group, grow(world, [furniture.group]), 0.84, 1);

  // ---- the turret: three sections, each sliding up out of the one below, and a crenellated crown -----------------
  const t = P.turret;
  const slit = (r: number, y: number, deg: number): BufferGeometry => box(0.7, 2.6, 0.3, Math.sin(deg * RAD) * r, y, Math.cos(deg * RAD) * r, deg);
  const s1 = printObject(world, drum(t.r, 11, 0, 0, 0, 24), { crease: 40 });
  const s1Ink = inked(world, slit(t.r, 4.6, 24));
  const turret = new Group();
  turret.position.set(t.x, 0, t.z);
  group.add(turret);
  add(turret, grow(world, [s1.group, s1Ink.group]), 0.36, 0.52, smooth);
  const s2 = printObject(world, drum(t.r - 0.45, 9.5, 0, 0, 0, 24), { crease: 40 });
  const s2Ink = inked(world, slit(t.r - 0.45, 3.4, -28));
  const s2Fold = add(turret, riser(world, [s2.group, s2Ink.group], [0, 1.2, 0], [0, 11, 0], true), 0.5, 0.64, smooth);
  const s3 = printObject(world, drum(t.r - 0.9, 8.5, 0, 0, 0, 24), { crease: 40 });
  const s3Ink = inked(world, slit(t.r - 0.9, 3, 30));
  const s3Fold = add(s2Fold.group, riser(world, [s3.group, s3Ink.group], [0, 0.8, 0], [0, 9.5, 0], true), 0.62, 0.76, smooth);
  const crownParts: BufferGeometry[] = [drum(t.r - 0.9, 1.5, 0, 0, 0, 24, t.r + 0.2), drum(t.r + 0.2, 0.9, 0, 1.5, 0, 24)];
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * 360 + 22.5;
    crownParts.push(box(2, 1.5, 0.7, Math.sin(a * RAD) * (t.r - 0.15), 2.4, Math.cos(a * RAD) * (t.r - 0.15), a));
  }
  const crown = printObject(world, merge(...crownParts), { crease: 40 });
  add(s3Fold.group, grow(world, [crown.group], [0, 8.5, 0]), 0.76, 0.88);

  // ---- the shadow: of plain solids the size of the standing castle, growing as it stands up --------------------
  const shadow = castShadow(world, merge(box(w, h, d), box(ww, g.h, wd, wx, 0, wz), drum(t.r, t.h, t.x, 0, t.z, 12), box(kw, k.h, kd, (k.x0 + k.x1) / 2, 0, (k.z0 + k.z1) / 2)));
  const shadowGroup = new Group();
  shadowGroup.add(shadow.mesh);
  group.add(shadowGroup);

  let last = Number.NaN;
  const api: Castle = {
    group,
    fold(amount) {
      if (amount === last) return;
      last = amount;
      for (const f of folds) f.fold.set(f.ease(span(amount, f.from, f.to)));
      const up = smooth(span(amount, 0.04, 0.8));
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
