// The gate on the grid: the stamp hangs under the cursor over the motion, which lies on the ground at its own
// address. Press and hold lowers it and the grid sinks under the weight; at full pressure it slams, a ring runs
// through the whole city, and the mark is left. Then the sheet cracks, its pieces fall into the grid at the
// address, and where it lay the case's point is lit in the stamp's colour. The stamp, the hold, the mark and the
// crack line come from src/core/stamp; the fall into the grid is this page's own (crack.split() gives the halves).

import {
  MARK_RATIO,
  MARK_TILT,
  between,
  clamp,
  crackThrough,
  createHold,
  createShaker,
  createStamp,
  flecks,
  freshSeed,
  renderMark,
  rng,
  type Hold,
  type Point,
  type Stamp,
} from "../core/stamp";
import { isTouch } from "../core/env";
import { inWords, MONTHS_TO_DECIDE } from "./content";
import { CASTLE } from "./places";
import { SHEET_ANCHOR, SHEET_H, SHEET_W } from "./poses";
import { applyH, invertH, type Homography } from "./project";
import type { Scene } from "./scene";
import type { GateDom } from "./sheet";

const NS = "http://www.w3.org/2000/svg";

export interface GateHost {
  dom: GateDom;
  /** Height of the header: the gate's own pixels start under it. */
  top(): number;
  /** The sheet's homography now (its own pixels to the window). */
  homography(): Homography;
  /** Half the sheet's diagonal on the ground, in metres: the dent under a press has to be wider than the sheet. */
  sheetRadius(): number;
  /** The scene, once it has loaded (null before, and without WebGL). */
  scene(): Scene | null;
  reduced: boolean;
  webgl: boolean;
  /** The visitor has paused the page's motion: the stamp does not drum for attention. */
  still(): boolean;
  /** Left alone long enough, the gate rests (the map stops drifting and ringing, the stamp lies down on the page
   *  and nothing is drawn); the next move, key or touch wakes it. */
  rest(resting: boolean): void;
  /** The gate has finished: take it away. */
  done(): void;
}

export interface Gate {
  /** "idle", "charging", "stamped", "cracking" or "open". */
  readonly state: string;
  /** Stamp now, as a single key press does. */
  stampNow(): void;
  /** The window or the camera changed: the sheet is somewhere else. */
  relay(): void;
  /** The visitor paused the page's motion, or let it move again (host.still() says which): held still, the gate
   *  draws once on a change and its loop sleeps. */
  setStill(): void;
  destroy(): void;
}

type State = "idle" | "charging" | "stamped" | "cracking" | "open";

const HOLD_MS = 1200;
/** How long the gate is left alone before it rests (after its two notes at 6 and 15 seconds). */
const REST_MS = 25000;
/** The mark's width on the sheet, in the sheet's own pixels. */
const MARK_W = 300;
const wait = (ms: number): Promise<void> => new Promise(done => setTimeout(done, ms));

export function startGate(host: GateHost): Gate {
  const { dom } = host;
  const abort = new AbortController();
  const { signal } = abort;
  const touch = isTouch();
  let state: State = "idle";
  let dead = false;
  const setState = (next: State): void => {
    state = next;
    dom.root.dataset.gate = next;
  };
  const say = (text: string): void => {
    dom.live.textContent = text;
  };

  // ---- the pencil: one short note at a time, written on a word at a time -------------------------------------------
  let noteText = "";
  const pencil = {
    say(text: string): void {
      noteText = text;
      const words = text.split(" ");
      const each = 400 / words.length;
      dom.note.replaceChildren(
        ...words.map((word, i) => {
          const span = document.createElement("span");
          span.textContent = i < words.length - 1 ? `${word} ` : word;
          span.style.setProperty("--at", `${Math.round(i * each)}ms`);
          span.style.setProperty("--write", `${Math.round(each * 1.25)}ms`);
          return span;
        }),
      );
      dom.note.classList.remove("is-erased");
    },
    erase(): void {
      if (!noteText) return;
      noteText = "";
      dom.note.classList.add("is-erased");
    },
  };
  try {
    // (a face that cannot be had is not an error: the note is written in the fallback)
    document.fonts.load('22px "Architects Daughter"', "Go on.").catch(() => {});
  } catch {
    // no Font Loading API: the face arrives with the first note
  }

  // ---- measures: the sheet's own pixels, the window, the stage (the gate under the header) -------------------------
  const defaultLocal = (): Point => ({ x: SHEET_W * SHEET_ANCHOR.x, y: SHEET_H * SHEET_ANCHOR.y });
  const toStage = (local: Point): Point => {
    const p = applyH(host.homography(), local.x, local.y);
    return { x: p.x, y: p.y - host.top() };
  };
  /** How many screen pixels one of the sheet's pixels is, across the page, at a point. */
  const scaleAt = (local: Point): number => {
    const H = host.homography();
    const a = applyH(H, local.x - 50, local.y);
    const b = applyH(H, local.x + 50, local.y);
    return Math.hypot(b.x - a.x, b.y - a.y) / 100;
  };
  /** Keep a mark's centre far enough inside the sheet for the whole mark to land on it. */
  const fit = (p: Point): Point => {
    const a = (Math.abs(MARK_TILT) * Math.PI) / 180;
    const mh = MARK_W * MARK_RATIO;
    const hx = (MARK_W * Math.cos(a) + mh * Math.sin(a)) / 2 + 10;
    const hy = (MARK_W * Math.sin(a) + mh * Math.cos(a)) / 2 + 10;
    return { x: clamp(p.x, hx, SHEET_W - hx), y: clamp(p.y, hy, SHEET_H - hy) };
  };
  let die = MARK_W * scaleAt(defaultLocal());

  // ---- the still version: no following stamp, one press, a short fade ---------------------------------------------
  if (host.reduced) {
    const stamp = createStamp(dom.stage, { dieWidth: die, webgl: false });
    const place = (): void => {
      const at = toStage({ x: SHEET_W * 0.86, y: SHEET_H * 0.86 });
      stamp.place(at.x, at.y);
    };
    place();
    stamp.setStill(true);
    stamp.stand(true);
    stamp.show();
    const press = async (): Promise<void> => {
      if (state !== "idle") return;
      setState("stamped");
      const local = fit(defaultLocal());
      const mark = renderMark(dom.stack, { seed: freshSeed(), width: MARK_W });
      mark.el.style.left = `${local.x}px`;
      mark.el.style.top = `${local.y}px`;
      mark.el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 150, fill: "backwards" });
      say("Stamped: approved with conditions.");
      host.scene()?.setHero(true, { instant: true });
      await wait(900);
      if (dead) return;
      dom.root.classList.add("is-fading");
      await wait(160);
      if (dead) return;
      setState("open");
      host.done();
    };
    dom.button.addEventListener("click", () => void press(), { signal });
    return {
      get state() {
        return state;
      },
      stampNow: () => void press(),
      relay() {
        die = MARK_W * scaleAt(defaultLocal());
        stamp.resize(die);
        place();
      },
      setStill() {},
      destroy() {
        dead = true;
        abort.abort();
        stamp.destroy();
      },
    };
  }

  // ---- the stamp and the shake ---------------------------------------------------------------------------------------
  const stamp: Stamp = createStamp(dom.stage, { dieWidth: die, webgl: host.webgl });
  stamp.setStill(host.still());
  const shaker = createShaker(dom.stage);
  let stageBox = dom.root.getBoundingClientRect();
  /** The cursor in stage pixels, once it has been seen. */
  let cursor: Point | null = null;
  let lying = false;
  let errand = 0;
  let busy = false;
  let lastActive = performance.now();
  let idleStage = 0;
  let healing: { from: number; at: number } | null = null;
  let hitStopUntil = 0;

  /** Over the page's target, where it waits before the cursor has been seen. */
  const perch = (): Point => toStage(defaultLocal());
  {
    const at = perch();
    stamp.place(at.x, at.y);
    stamp.show();
  }
  void stamp.ready.then(kind => {
    dom.root.dataset.stamp = kind;
  });

  // ---- what the press does to the sheet: a pencil ring that closes round the die, and the die's shade -------------
  const press = document.createElement("div");
  press.className = "c-press";
  press.setAttribute("aria-hidden", "true");
  press.style.setProperty("--mark-tilt", `${MARK_TILT}deg`);
  const dent = document.createElement("div");
  dent.className = "c-press__dent";
  const gauge = document.createElementNS(NS, "svg");
  gauge.setAttribute("class", "c-press__gauge");
  const gaugePath = document.createElementNS(NS, "path");
  gaugePath.setAttribute("pathLength", "1");
  gauge.append(gaugePath);
  press.append(dent, gauge);
  {
    const mw = MARK_W;
    const mh = MARK_W * MARK_RATIO;
    dent.style.width = `${mw}px`;
    dent.style.height = `${mh}px`;
    // a ring drawn by hand: a little uneven, and it overshoots where it closes
    const rx = mw / 2 + mw * 0.085;
    const ry = mh / 2 + mw * 0.12;
    const r = rng(11);
    const steps = 44;
    let d = "";
    for (let i = 0; i <= steps + 1; i++) {
      const a = -Math.PI / 2 + (i / steps) * Math.PI * 2;
      const wobble = 1 + Math.sin(a * 2 + 0.7) * 0.012 + between(r, -0.006, 0.006) + (i / steps) * 0.018;
      d += `${i ? "L" : "M"}${(Math.cos(a) * rx * wobble).toFixed(1)} ${(Math.sin(a) * ry * wobble).toFixed(1)}`;
    }
    gaugePath.setAttribute("d", d);
    const size = Math.max(rx, ry) * 2 + 16;
    gauge.setAttribute("width", String(size));
    gauge.setAttribute("height", String(size));
    gauge.setAttribute("viewBox", `${-size / 2} ${-size / 2} ${size} ${size}`);
  }
  let target: { local: Point; stage: Point; ground: { x: number; z: number } } | null = null;

  /** Everything that follows the progress of a hold, from one number: on the sheet, and in the grid under it. */
  function pressure(p: number): void {
    gaugePath.style.strokeDasharray = "1 1";
    gaugePath.style.strokeDashoffset = String(1 - p);
    gauge.style.opacity = String(Math.min(1, p * 9));
    dent.style.opacity = String(p * p);
    shaker.rumble(p * p * 1.5);
    if (target) host.scene()?.dent(p, target.ground.x, target.ground.z, host.sheetRadius());
  }

  function aim(point: Point | null): void {
    const H = host.homography();
    let from: Point | null = point ? applyH(invertH(H), point.x, point.y) : null;
    if (!from && cursor) {
      // a key press stamps where the cursor is, if it is over the page; else at the default place
      const l = applyH(invertH(H), cursor.x, cursor.y + host.top());
      if (l.x > 0 && l.y > 0 && l.x < SHEET_W && l.y < SHEET_H) from = l;
    }
    const local = fit(from ?? defaultLocal());
    const client = applyH(H, local.x, local.y);
    const ground = host.scene()?.groundAt(client.x, client.y) ?? CASTLE;
    target = { local, stage: { x: client.x, y: client.y - host.top() }, ground: { x: ground.x, z: ground.z } };
    press.style.left = `${local.x}px`;
    press.style.top = `${local.y}px`;
    if (!press.isConnected) dom.stack.append(press);
    const next = MARK_W * scaleAt(local);
    if (Math.abs(next - die) > 1) {
      die = next;
      stamp.resize(die);
    }
  }

  // ---- notes for a hold that was let go -----------------------------------------------------------------------------
  const LET_GO = ["Hold it down.", "Commit.", `It took them ${inWords(MONTHS_TO_DECIDE)} months. You need one second.`];
  let ghosts = 0;
  function ghost(progress: number): void {
    if (!target || ghosts >= 3) return;
    ghosts += 1;
    const mark = renderMark(dom.stack, { seed: freshSeed(), width: MARK_W, label: "" });
    mark.el.classList.add("is-ghost");
    mark.el.style.left = `${target.local.x}px`;
    mark.el.style.top = `${target.local.y}px`;
    mark.el.style.setProperty("--ghost", (0.08 + progress * 0.2).toFixed(2));
    mark.el.addEventListener("animationend", () => {
      mark.el.remove();
      ghosts -= 1;
    });
  }

  // ---- the hold -------------------------------------------------------------------------------------------------------
  const hold: Hold = createHold(dom.root, {
    duration: HOLD_MS,
    button: dom.button,
    globalSpace: true,
    ignore: "a, button, input, select",
    enabled: () => state === "idle" && !dead,
    onStart({ point, progress }) {
      errand += 1;
      busy = false;
      active();
      pencil.erase();
      healing = null;
      aim(point);
      if (lying) {
        lying = false;
        stamp.lie(false);
      }
      if (target) stamp.moveTo(target.stage.x, target.stage.y, 0.06);
      setState("charging");
      pressure(progress);
      stamp.press(progress);
    },
    onProgress(p) {
      stamp.press(p);
      pressure(p);
    },
    onCancel({ progress, count }) {
      setState("idle");
      stamp.release();
      healing = { from: progress, at: performance.now() };
      if (progress > 0.3) ghost(progress);
      const note = LET_GO[count - 1];
      if (note) {
        pencil.say(note);
        say(note);
        noteAt = cursor ? { ...cursor } : null;
      }
      active();
    },
    onComplete() {
      void slam();
    },
    onTap() {
      setState("idle");
      healing = null;
      void auto();
    },
  });

  /** A single press: the stamp does the whole thing itself, quickly. */
  async function auto(): Promise<void> {
    if (state !== "idle" || dead) return;
    errand += 1;
    pencil.erase();
    aim(null);
    if (lying) {
      lying = false;
      stamp.lie(false);
    }
    if (target) stamp.moveTo(target.stage.x, target.stage.y, 0.07);
    setState("charging");
    const started = performance.now();
    const length = 460;
    await new Promise<void>(resolve => {
      const stop = stamp.onFrame((_dt, _pose, now) => {
        const t = clamp((now - started) / length, 0, 1);
        const p = t * t;
        stamp.press(p);
        pressure(p);
        if (t >= 1) {
          stop();
          resolve();
        }
      });
    });
    if (!dead) void slam();
  }

  // ---- the slam, the crack, the fall into the grid ------------------------------------------------------------------
  async function slam(): Promise<void> {
    if (!target || dead) return;
    const at = target;
    const seed = freshSeed();
    const scene = host.scene();
    setState("stamped");
    hold.abort();
    await stamp.slam(() => {
      // the frame the die meets the page: the mark is under it, the flecks are out, everything stops, and then
      // the ring leaves through the whole city
      const mark = renderMark(dom.stack, { seed, width: MARK_W });
      mark.el.style.left = `${at.local.x}px`;
      mark.el.style.top = `${at.local.y}px`;
      flecks(dom.stack, at.local.x, at.local.y, { seed: seed ^ 0x2f, width: MARK_W, height: MARK_W * MARK_RATIO, tilt: MARK_TILT, count: 17 });
      gauge.style.opacity = "0";
      dent.style.opacity = "0";
      press.remove();
      const r = rng(seed);
      shaker.rumble(0);
      shaker.kick(between(r, -50, 50), 230, between(r, -6, 6));
      hitStopUntil = performance.now() + 70;
      stamp.freeze(70);
      scene?.dent(0);
      // the dome under the pointer does not come back over the sheet: the grid under it rests at its own tone
      scene?.setAlive({ bulge: 0 });
      scene?.ring(at.ground.x, at.ground.z, 1);
      scene?.kick(190);
      scene?.freeze(70);
    });
    if (dead) return;
    say("Stamped: approved with conditions.");
    // the weight rests on the page, then comes off it, straight up and clear of the mark
    await wait(70 + 150);
    if (dead) return;
    stamp.lift(die * 0.9);
    // a beat of stillness: let the mark be read while the ring runs out
    await wait(560);
    if (dead) return;
    // the stamp's work is done: it is taken up and away, whole, over the top of the window (a hand lifting it)
    stamp.moveTo(at.stage.x + die * 0.9, -die * 1.6, 0.09);
    window.setTimeout(() => {
      if (!dead) stamp.show(false);
    }, 420);
    await wait(160);
    if (dead) return;

    setState("cracking");
    const crack = crackThrough(dom.stack, at.local, { seed, angle: MARK_TILT - 9, bleed: 28, shards: 8, strip: ".c-under" });
    await crack.draw(300);
    if (dead) return;
    const [a, b] = crack.split();
    // the half that carries most of the mark stays above the other as they part
    a.style.zIndex = "2";
    b.style.zIndex = "1";
    const box = a.parentElement;
    const shards = box ? [...box.querySelectorAll<HTMLElement>(".stamp-shard")] : [];
    // the halves jump apart, square to the line …
    const n = crack.normal;
    const gap = 26;
    const r = rng(seed ^ 0x77c1);
    const apartA = `translate(${(n.x * gap).toFixed(1)}px, ${(n.y * gap).toFixed(1)}px) rotate(${(-between(r, 0.9, 1.9)).toFixed(2)}deg)`;
    const apartB = `translate(${(-n.x * gap * 0.8).toFixed(1)}px, ${(-n.y * gap * 0.8).toFixed(1)}px) rotate(${between(r, 0.7, 1.6).toFixed(2)}deg)`;
    const jump: KeyframeAnimationOptions = { duration: 190, easing: "cubic-bezier(0.2, 1.4, 0.4, 1)", fill: "forwards" };
    a.animate([{ transform: "none" }, { transform: apartA }], jump);
    b.animate([{ transform: "none" }, { transform: apartB }], jump);
    for (const shard of shards) {
      const side = Number(shard.dataset.side) || 1;
      const out = between(r, 40, 130);
      shard.animate(
        [
          { transform: "none", opacity: 1 },
          { transform: `translate(${(n.x * side * out + between(r, -60, 60)).toFixed(1)}px, ${(n.y * side * out).toFixed(1)}px) rotate(${between(r, -200, 200).toFixed(0)}deg) scale(0.4)`, opacity: 0 },
        ],
        { duration: between(r, 420, 640), easing: "cubic-bezier(0.2, 0.7, 0.3, 1)", fill: "forwards" },
      );
    }
    await wait(230);
    if (dead) return;
    // … and fall into the grid, each where it lies: a half tips on the edge it broke along, keeps drifting away from
    // the other, and goes down into the ground under it (it shrinks toward its own middle), one after the other
    const sink = (piece: HTMLElement, from: string, away: number, turn: number, delay: number): Animation => {
      const ax = n.x * away, ay = n.y * away;
      return piece.animate(
        [
          { transform: from, opacity: 1 },
          { transform: `translate(${(ax * 0.7).toFixed(1)}px, ${(ay * 0.7 + 10).toFixed(1)}px) rotate(${(turn * 0.4).toFixed(1)}deg) scale(0.74)`, opacity: 1, offset: 0.45 },
          { transform: `translate(${ax.toFixed(1)}px, ${(ay + 22).toFixed(1)}px) rotate(${turn.toFixed(1)}deg) scale(0.04)`, opacity: 0.7 },
        ],
        { duration: 600, delay, easing: "cubic-bezier(0.55, 0, 0.8, 0.45)", fill: "forwards" },
      );
    };
    const falls = [sink(a, apartA, gap * 1.9, -between(r, 7, 12), 0), sink(b, apartB, -gap * 1.7, between(r, 6, 11), 120)];
    // as the last of it goes under, the point it leaves is lit, and a smaller ring leaves from the address
    window.setTimeout(() => {
      if (dead) return;
      scene?.setHero(true);
      scene?.ring(CASTLE.x, CASTLE.z, 0.42);
    }, 560);
    await Promise.all(falls.map(f => f.finished.catch(() => {})));
    if (dead) return;
    crack.destroy();
    dom.stack.style.visibility = "hidden";
    await wait(260);
    if (dead) return;
    setState("open");
    // (the stamp was announced once, at the slam: the heading of the first chapter takes the focus from here, and
    // says the rest itself)
    host.done();
  }

  // ---- being noticed: idle, leaving ---------------------------------------------------------------------------------
  let noteAt: Point | null = null;
  let resting = false;
  function active(): void {
    lastActive = performance.now();
    idleStage = 0;
    if (resting) {
      resting = false;
      host.rest(false);
      if (lying && !touch && cursor) {
        lying = false;
        stamp.lie(false);
      }
      stamp.wake();
    }
  }
  async function drum(): Promise<void> {
    const mine = ++errand;
    busy = true;
    for (let i = 0; i < 2; i++) {
      if (mine !== errand) return;
      await stamp.tap(() => shaker.kick(0, 34));
      await wait(190);
    }
    if (mine !== errand) return;
    pencil.say("Go on. It’s only a formality.");
    noteAt = cursor ? { ...cursor } : null;
    busy = false;
  }

  window.addEventListener(
    "pointermove",
    event => {
      if (event.pointerType === "touch") return;
      // over the header the pointer is not over the sheet: the stamp goes back to its place over the page
      if (event.clientY < stageBox.top) {
        cursor = null;
        return;
      }
      const p = { x: event.clientX - stageBox.left, y: event.clientY - stageBox.top };
      cursor = { x: clamp(p.x, 12, stageBox.width - 12), y: clamp(p.y, 20, stageBox.height - 6) };
      active();
      if (noteText && state === "idle" && (!noteAt || Math.hypot(cursor.x - noteAt.x, cursor.y - noteAt.y) > 28)) pencil.erase();
      if (lying) {
        lying = false;
        stamp.lie(false);
      }
      if (state !== "idle" || busy) return;
      stamp.moveTo(cursor.x, cursor.y, 0.075);
    },
    { signal },
  );
  document.documentElement.addEventListener(
    "mouseleave",
    () => {
      if (state !== "idle" || touch) return;
      errand += 1;
      busy = false;
      lying = true;
      stamp.lie(true);
    },
    { signal },
  );
  window.addEventListener("keydown", active, { signal });
  // (a finger on the page, or a pointer pressed anywhere, wakes a gate at rest)
  window.addEventListener("pointerdown", active, { signal });
  // Enter with nothing in particular focused (the page itself) stamps, as one press of the button does
  window.addEventListener(
    "keydown",
    event => {
      if (event.key !== "Enter" || event.repeat || state !== "idle") return;
      const t = event.target as Element | null;
      if (t && t !== document.body && t !== document.documentElement) return;
      event.preventDefault();
      void auto();
    },
    { signal },
  );

  // ---- held still (motion paused): nothing moves of itself, so once nothing is in hand the loop sleeps. A move, a key
  // or a touch wakes it (they ask the stamp for something); so does a timer for the gate's next note, or its rest ---
  let stillKey = "";
  let stillTimer = 0;
  const sleepUntilNext = (): void => {
    window.clearTimeout(stillTimer);
    if (resting) return;
    const idle = performance.now() - lastActive;
    const next = idleStage === 0 ? 6000 : idleStage === 1 ? 15000 : REST_MS;
    stillTimer = window.setTimeout(() => stamp.wake(), Math.max(0, next - idle) + 30);
  };

  // ---- one loop: the stamp's ---------------------------------------------------------------------------------------------
  stamp.onFrame((dt, _pose, now) => {
    if (now < hitStopUntil) return;
    const shaking = shaker.step(dt, now);
    // the camera can still be on its way (a replay eases it in): the die keeps the size of the mark it would leave
    if (state === "idle" && !busy) {
      const next = MARK_W * scaleAt(defaultLocal());
      if (Math.abs(next - die) > 0.5) {
        die = next;
        stamp.resize(die);
      }
    }
    if (healing) {
      // let go: everything the press did undoes itself in about a third of a second
      const t = (now - healing.at) / 320;
      if (t >= 1) {
        pressure(0);
        press.remove();
        healing = null;
      } else pressure(healing.from * (1 - t) * (1 - t));
    }
    // before the cursor has been seen (and on a touch screen) the stamp keeps its place over the page as the view drifts
    if (!cursor && state === "idle" && !busy) {
      const at = perch();
      stamp.moveTo(at.x, at.y, 0.2);
    }
    if (state === "idle" && !busy && !lying && !document.hidden) {
      const idle = now - lastActive;
      if (idleStage === 0 && idle > 6000) {
        idleStage = 1;
        // (motion paused: the note alone, without the stamp drumming on the page)
        if (host.still()) pencil.say("Go on. It’s only a formality.");
        else void drum();
      } else if (idleStage === 1 && idle > 15000) {
        idleStage = 2;
        pencil.say("Or skip it. The search is one link away.");
        noteAt = cursor ? { ...cursor } : null;
      }
    }
    // left alone: the map rests and the stamp lies down on the page, and the loop asks for no more frames
    if (!resting && state === "idle" && !busy && !healing && performance.now() - lastActive > REST_MS) {
      resting = true;
      host.rest(true);
      if (!lying) {
        lying = true;
        stamp.lie(true);
      }
    }
    if (resting && state === "idle" && !busy && !healing) return false;
    if (host.still() && state === "idle" && !busy && !healing && !shaking) {
      // what the stamp follows here (its place over the page, the size of its die) has stopped changing: draw no more
      const at = cursor ?? perch();
      const key = `${at.x.toFixed(1)},${at.y.toFixed(1)},${die.toFixed(1)},${idleStage}`;
      if (key === stillKey) {
        sleepUntilNext();
        return false;
      }
      stillKey = key;
    }
    return undefined;
  });

  return {
    get state() {
      return state;
    },
    stampNow() {
      void auto();
    },
    setStill() {
      if (dead) return;
      stillKey = "";
      stamp.setStill(host.still());
      stamp.wake();
    },
    relay() {
      if (dead || state === "cracking" || state === "open") return;
      stageBox = dom.root.getBoundingClientRect();
      const next = MARK_W * scaleAt(defaultLocal());
      if (Math.abs(next - die) > 0.5) {
        die = next;
        stamp.resize(die);
      } else stamp.resize();
    },
    destroy() {
      dead = true;
      errand += 1;
      window.clearTimeout(stillTimer);
      abort.abort();
      hold.destroy();
      stamp.destroy();
      shaker.reset();
      host.scene()?.dent(0);
    },
  };
}
