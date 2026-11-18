# Concepts: three candidates for each prototype, and the one built

> **2026-11-17:** C was chosen and is the front end of the public site (see [production-c.md](production-c.md)). Prototypes A and B, their notes, the build briefs and the research are not part of this repository; this file stays as the short record of how C was chosen.

Written 2026-11-17. The research behind these (notes on outside sites) is not part of this repository. C is built in `apps/showcase/` (route `/c/`, and the public site's front page).

## The idea all three share

The subject is paper: a typed Planning Commission motion, an inked stamp, a city drawn as lines. So the whole design uses three materials and three colours per theme, and nothing else.

| | Light theme, "paper" | Dark theme, "blueprint" |
|---|---|---|
| Ground | paper `#F2EDE1` | blue-black `#0A0F1F` |
| Text | ink `#171A21` | `#E9ECF7` |
| Drawing lines, links, highlights | cobalt `#1E3FCF` | pale cobalt `#9DB2FF` |
| The stamp, and only the stamp | vermilion `#E23A2B` | `#FF4D3A` |

- **Type:** Instrument Serif for headlines, Public Sans (the US government's own typeface) for reading, IBM Plex Mono for case numbers and dates, Big Shoulders Display for the words on the stamp, Architects Daughter for pencil notes in the margin. All open-licence and self-hosted.
- **The stamp is the character.** In the reference gate (why.zero.university) the hand under the ice becomes the protagonist of the story below it. Here the stamp plays that part: it follows the cursor, it lands, and its red mark is the only red on the page afterwards.
- **The site talks back in pencil.** Reactions to the visitor (idle, hesitation, leaving) appear as short hand-lettered notes in the margin, like a planner's annotations.
- **The search is never hostage.** A visible "Skip to search" link, a keyboard path, and memory of returning visitors are part of every design below, not an afterthought.

---

## Prototypes A and B

A (the gate: a desk, a sheet, the stamp) and B (the scroll story: a pop-up map of the case) were built, reviewed and
set aside when C, which combines them, was chosen. Their candidates, sketches and notes are not part of this
repository.

---

## Prototype C: both combined

### C1. The living grid (built)

```
  dark: the whole street grid, tilting and bulging under the cursor,
  352 points on it          ◐ click the mark: flips to paper
        ╲  ╲  ╲   ╲    ╲      ╲
     ────·──·──╲─●─╲────·───────     ● = the motion on the grid
       ╲   ┌────────┐  ╲     ·        ╔═╗
     ───·──│ MOTION │───·──────       ╚═╝ stamp
        ╲  └────────┘ ╲    ╲
   hold → stamp → the sheet breaks into the grid → fly to the address
   → the story, flown across the real grid → "5,048 more" → search,
     where every result lights its motion on the map
```

- **Pitch:** The world is San Francisco's street grid as a living field of lines that tilts with the cursor and bulges under it, with the 352 motions as points. A motion lies on the grid. You stamp it; it breaks, and its pieces fall into the grid and become that case's point. The camera dives to the address and the scroll story is flown across the real streets, in the grid's own spare language (lines, points, labels). At the end the grid becomes the backdrop of the search, and every result lights its motion on the map. Clicking the mark flips the whole world between blueprint dark and paper light, spreading out from the click.
- **References:** cantoreality.com (a line-and-dot field as the whole world; a black and white flip from the logo). Studying it showed its grid only turns slowly in two layers and its flip is a hard cut, so the cursor tilt, the bulge and a flip that spreads from the click are our own. Also bruno-simon.com (revealing a world by one radius from a point), the HackerRank theme switch on designspells.com (the new theme spreading as a circle from the toggle), and Stripe Press (a thin rail of real buttons as a keyboard index beside a 3D scene).
- **Build:** A's stamp and gate and B's story engine, on one shared world: street lines drawn with a vertex shader (tilt, bulge, theme), points drawn in one call. The search panel floats over a dimmed grid.
- **Risks:** it is the biggest build; the grid must not hurt the search's legibility or frame rate; three ideas in one must still read as one.

### C2. Gate, then story, then search, as three rooms

- **Pitch:** A's desk, then a cut to B's pop-up map, then the search: the two finished prototypes joined end to end.
- **For:** cheapest; reuses everything.
- **Against:** three looks, two cuts. Nothing ties the stamp to the map, and there is no world.

### C3. The globe of cases

- **Pitch:** The 352 motions as a slowly turning cloud of papers; stamp one to open it.
- **Against:** throws away the real geography, which is the strongest thing this data has.

**Picked: C1.**
