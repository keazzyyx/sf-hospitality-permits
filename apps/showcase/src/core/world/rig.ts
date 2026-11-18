// Puts the world's camera where a pose says. A pose is plain numbers (see ../story/camera.ts for the table that
// produces them), so it can be interpolated, stored and tested without three.js.

import type { World } from "./world";

/** Where the camera is, as the things a person would say about a shot. */
export interface Pose {
  /** The point looked at, in world metres. */
  tx: number;
  ty: number;
  tz: number;
  /** Metres from the camera to that point. */
  distance: number;
  /** Compass direction the camera looks in, degrees clockwise from north (0: from the south, looking north). */
  heading: number;
  /** Degrees the camera looks down from the horizon (90: straight down). */
  pitch: number;
  /** Vertical field of view in degrees. */
  fov: number;
  /** Where the looked-at point sits on the canvas, as a fraction of its size from the centre (+x right, +y
   *  down). 0, 0 is the centre. Used to compose a shot beside a text panel or inside a band. */
  shiftX: number;
  shiftY: number;
}

const RAD = Math.PI / 180;

/** Move the world's camera to a pose. Does not render: call world.invalidate(). */
export function setPose(world: World, pose: Pose): void {
  const { camera } = world;
  const h = pose.heading * RAD;
  const p = Math.min(89.9, Math.max(1, pose.pitch)) * RAD;
  // the direction of sight: north is -z, east is +x, down is -y
  const dx = Math.sin(h) * Math.cos(p);
  const dy = -Math.sin(p);
  const dz = -Math.cos(h) * Math.cos(p);
  camera.position.set(pose.tx - dx * pose.distance, pose.ty - dy * pose.distance, pose.tz - dz * pose.distance);
  camera.up.set(0, 1, 0);
  camera.lookAt(pose.tx, pose.ty, pose.tz);
  camera.fov = pose.fov;
  camera.aspect = world.width / world.height;
  camera.near = Math.max(1, pose.distance / 60);
  camera.far = Math.max(4000, pose.distance * 14 + 30000);
  if (pose.shiftX || pose.shiftY) {
    camera.setViewOffset(world.width, world.height, -pose.shiftX * world.width, -pose.shiftY * world.height, world.width, world.height);
  } else {
    camera.clearViewOffset();
  }
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld();
}
