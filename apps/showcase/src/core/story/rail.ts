// The chapter rail: one real button per chapter (a thin tick, the current one longer, named on hover and focus),
// a line that fills with progress, and, for small touch screens, a previous / next pair with the chapter's number
// between them. It only draws and asks: the story does the moving.

import "./story.css";
import type { Story, StoryState } from "./engine";

export interface Rail {
  element: HTMLElement;
  update(state: StoryState): void;
}

const NS = "http://www.w3.org/2000/svg";

function chevron(direction: "up" | "down"): SVGSVGElement {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 12 12");
  svg.setAttribute("width", "12");
  svg.setAttribute("height", "12");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const path = document.createElementNS(NS, "path");
  path.setAttribute("d", direction === "up" ? "M2 8l4-4 4 4" : "M2 4l4 4 4-4");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.5");
  svg.append(path);
  return svg;
}

export interface RailOptions {
  label?: string;
  /** A tick was pressed: the story is on its way to this chapter (the page can give its heading the focus there). */
  onPick?(chapter: number): void;
}

export function createRail(story: Story, { label = "Chapters", onPick }: RailOptions = {}): Rail {
  const nav = document.createElement("nav");
  nav.className = "story-rail";
  nav.setAttribute("aria-label", label);

  const track = document.createElement("span");
  track.className = "story-rail__track";
  track.setAttribute("aria-hidden", "true");
  const fill = document.createElement("span");
  fill.className = "story-rail__fill";
  track.append(fill);

  const list = document.createElement("ol");
  list.className = "story-rail__list";
  const buttons = story.timeline.chapters.map(chapter => {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "story-rail__tick";
    const name = document.createElement("span");
    name.className = "story-rail__name";
    name.textContent = `${chapter.index + 1} · ${chapter.title}`;
    button.append(name);
    button.addEventListener("click", () => {
      onPick?.(chapter.index);
      story.goTo(chapter.index);
    });
    li.append(button);
    list.append(li);
    return button;
  });

  const stepper = document.createElement("div");
  stepper.className = "story-rail__stepper";
  // (they move one stop at a time, a chapter or one of its steps: "Previous" and "Next", and where the story now is
  // is said once it gets there, only after a press of one of them, never while the visitor scrolls)
  let said = 0;
  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "story-rail__step";
  prev.setAttribute("aria-label", "Previous");
  prev.append(chevron("up"));
  prev.addEventListener("click", () => {
    said = performance.now();
    story.prev();
  });
  const where = document.createElement("span");
  where.className = "story-rail__where";
  where.setAttribute("aria-hidden", "true");
  const next = document.createElement("button");
  next.type = "button";
  next.className = "story-rail__step";
  next.setAttribute("aria-label", "Next");
  next.append(chevron("down"));
  next.addEventListener("click", () => {
    said = performance.now();
    story.next();
  });
  const live = document.createElement("span");
  live.className = "vh";
  live.setAttribute("role", "status");
  live.setAttribute("aria-live", "polite");
  stepper.append(prev, where, next, live);

  nav.append(track, list, stepper);

  let current = -1;
  /** The stop last said aloud. */
  let reached = "";
  let lastScale = "";
  return {
    element: nav,
    update(state) {
      const scale = `scaleY(${state.progress.toFixed(4)})`;
      if (scale !== lastScale) {
        lastScale = scale;
        fill.style.transform = scale;
      }
      if (state.chapter !== current) {
        current = state.chapter;
        buttons.forEach((b, i) => {
          if (i === current) b.setAttribute("aria-current", "step");
          else b.removeAttribute("aria-current");
          b.classList.toggle("is-done", i < current);
        });
        where.textContent = `${current + 1} / ${buttons.length}`;
        prev.disabled = current === 0;
      }
      // what a press of Previous or Next reached, said once it is there
      const at = `${current}:${state.step}`;
      if (said && state.phase === "hold" && at !== reached && performance.now() - said < 3000) {
        reached = at;
        const chapter = story.timeline.chapters[current];
        const steps = chapter?.steps ?? 0;
        live.textContent = `Chapter ${current + 1} of ${buttons.length}: ${chapter?.title ?? ""}${steps > 0 && state.step >= 0 ? `, ${state.step + 1} of ${steps}` : ""}`;
      }
    },
  };
}
