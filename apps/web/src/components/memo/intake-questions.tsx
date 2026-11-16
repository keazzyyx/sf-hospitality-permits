"use client";

import { useEffect, useState } from "react";
import { cn } from "cn";
import { Input } from "@/components/ui/input";
import {
  INTAKE_QUESTIONS,
  INTAKE_SKIP_LABEL,
  INTAKE_SKIP_NOTE,
  MORE_QUESTION_IDS,
  asksAboutAlcohol,
  showsFoodService,
  showsOutdoorAlcohol,
  withOutdoorArea,
  type IntakeForm,
  type YesNoChoice,
} from "@/lib/intake";
import type { IntakeQuestionId, StoryAnswer } from "@/lib/api-types";

interface Choice<T extends string> {
  value: T;
  label: string;
}

const CHIP = "min-h-8 rounded-full border px-3.5 py-1 text-left text-sm transition-colors";
const CHIP_ON = "border-ink bg-ink text-paper";
const CHIP_OFF = "border-input bg-background text-foreground hover:border-ink/50";
const OPTIONAL = "ml-1 rounded-full border border-border bg-background px-2 py-0.5 align-middle text-[11px] font-medium text-muted-foreground";
const ASKED = "ml-1 rounded-full border border-estimated/50 bg-estimated-soft px-2 py-0.5 align-middle text-[11px] font-semibold text-foreground";
const INTAKE_HEADING = "Step 3 · A few details (optional)";
const INTAKE_HINT = "They settle what a description often leaves open. Each one you answer is one thing the report can decide instead of listing as not known.";

/** The words under a question the report named as not given (`OpenQuestion.intake_question`). */
export const INTAKE_ASKED_LABEL = "The report asked for this";

/** One answer of several, with "Skip" as the last choice. */
function Chips<T extends string>({ name, label, choices, value, onChange }: { name: string; label: string; choices: readonly Choice<T>[]; value: T | "skip"; onChange: (v: T | "skip") => void }) {
  const all: Choice<T | "skip">[] = [...choices, { value: "skip", label: INTAKE_SKIP_LABEL }];
  return (
    <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={label}>
      {all.map((c) => (
        <button
          key={c.value}
          type="button"
          role="radio"
          aria-checked={value === c.value}
          data-testid={`intake-${name}-${c.value}`}
          onClick={() => onChange(c.value)}
          className={cn(CHIP, value === c.value ? CHIP_ON : CHIP_OFF)}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}

/** Any number of the answers; none ticked is the skipped question. */
function Ticks<T extends string>({ name, label, choices, value, onChange }: { name: string; label: string; choices: readonly Choice<T>[]; value: readonly T[]; onChange: (v: T[]) => void }) {
  const toggle = (v: T) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={label}>
      {choices.map((c) => (
        <button
          key={c.value}
          type="button"
          role="checkbox"
          aria-checked={value.includes(c.value)}
          data-testid={`intake-${name}-${c.value}`}
          onClick={() => toggle(c.value)}
          className={cn(CHIP, value.includes(c.value) ? CHIP_ON : CHIP_OFF)}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}

function Question({ id, asked, children }: { id: IntakeQuestionId; asked: boolean; children: React.ReactNode }) {
  const q = INTAKE_QUESTIONS[id];
  return (
    <fieldset className={cn("space-y-2", asked && "rounded-xl border border-estimated/40 bg-estimated-soft/40 p-4")} data-testid={`intake-question-${id}`} data-asked={asked ? "true" : "false"}>
      <legend className="text-sm font-medium">
        {q.question} <span className={OPTIONAL}>Optional</span>
        {asked && (
          <span className={ASKED} data-testid="intake-asked">
            {INTAKE_ASKED_LABEL}
          </span>
        )}
      </legend>
      <p className="text-xs text-muted-foreground">{q.help}</p>
      <p className="text-xs text-muted-foreground" data-testid="intake-skip-note">
        {INTAKE_SKIP_NOTE}
      </p>
      {children}
    </fieldset>
  );
}

/** A follow-up shown under the question whose answer opens it. */
function FollowUp({ id, children }: { id: IntakeQuestionId; children: React.ReactNode }) {
  const q = INTAKE_QUESTIONS[id];
  return (
    <div className="mt-3 grid gap-1.5 border-l-2 border-border pl-4" data-testid={`intake-question-${id}`}>
      <p className="text-sm font-medium">
        {q.question} <span className={OPTIONAL}>Optional</span>
      </p>
      <p className="text-xs text-muted-foreground">{q.help}</p>
      <p className="text-xs text-muted-foreground">{INTAKE_SKIP_NOTE}</p>
      {children}
    </div>
  );
}

function SquareFeet({ id, testId, placeholder, value, onChange }: { id: IntakeQuestionId; testId: string; placeholder: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <Input
        id={testId}
        data-testid={testId}
        aria-label={INTAKE_QUESTIONS[id].question}
        type="number"
        inputMode="numeric"
        placeholder={placeholder}
        className="max-w-40 bg-background"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <span className="text-sm text-muted-foreground">sq ft</span>
    </div>
  );
}

/**
 * The optional intake questions under the concept description, in the new-memo form's style: the main questions,
 * then the ones only some reports ask for under "More details". `asked` are the questions a report named as not
 * given (a `?ask=` link from that report): each is marked, and "More details" opens when one of them is in it.
 */
export function IntakeQuestions({
  value,
  onChange,
  asked = [],
  heading = INTAKE_HEADING,
  hint = INTAKE_HINT,
}: {
  value: IntakeForm;
  onChange: (next: IntakeForm) => void;
  asked?: readonly IntakeQuestionId[];
  /** The new-memo form's step heading by default; the memo page's answer form gives its own. */
  heading?: string;
  hint?: string;
}) {
  const set = (patch: Partial<IntakeForm>) => onChange({ ...value, ...patch });
  const isAsked = (id: IntakeQuestionId) => asked.includes(id);
  const yesNo = (id: IntakeQuestionId, name: string, current: YesNoChoice, change: (v: YesNoChoice) => void) => (
    <Chips name={name} label={INTAKE_QUESTIONS[id].question} choices={INTAKE_QUESTIONS.part_of_chain.answers} value={current} onChange={change} />
  );
  // "More details" opens by itself when a report asked for one of its questions; after that it is the reader's.
  const askedMore = MORE_QUESTION_IDS.some(isAsked);
  const [moreOpen, setMoreOpen] = useState(askedMore);
  useEffect(() => {
    if (askedMore) setMoreOpen(true);
  }, [askedMore]);

  return (
    <div className="mt-6 grid gap-1.5" data-testid="intake-questions">
      <p className="text-base font-semibold">{heading}</p>
      <p className="text-sm text-muted-foreground">{hint}</p>
      <div className="mt-3 space-y-6">
        <Question id="part_of_chain" asked={isAsked("part_of_chain") || isAsked("other_locations")}>
          {yesNo("part_of_chain", "chain", value.chain, (chain) => set({ chain }))}
          {value.chain === "yes" && (
            <div className="mt-3 grid gap-1.5 border-l-2 border-border pl-4">
              <label htmlFor="intake-other-locations" className="text-sm font-medium">
                {INTAKE_QUESTIONS.other_locations.question} <span className={OPTIONAL}>Optional</span>
              </label>
              <p className="text-xs text-muted-foreground">{INTAKE_QUESTIONS.other_locations.help}</p>
              <p className="text-xs text-muted-foreground">{INTAKE_SKIP_NOTE}</p>
              <Input
                id="intake-other-locations"
                data-testid="intake-other-locations"
                type="number"
                inputMode="numeric"
                className="max-w-40 bg-background"
                value={value.otherLocations}
                onChange={(e) => set({ otherLocations: e.target.value })}
              />
            </div>
          )}
        </Question>

        <Question id="floor_area_sqft" asked={isAsked("floor_area_sqft")}>
          <SquareFeet id="floor_area_sqft" testId="intake-floor-area" placeholder="e.g. 1800" value={value.floorArea} onChange={(floorArea) => set({ floorArea })} />
        </Question>

        <Question id="liquor_licence" asked={isAsked("liquor_licence") || isAsked("food_service")}>
          <Chips name="licence" label={INTAKE_QUESTIONS.liquor_licence.question} choices={INTAKE_QUESTIONS.liquor_licence.answers} value={value.licence} onChange={(licence) => set({ licence })} />
          {/* a business that serves no alcohol is not a Bar (Planning Code § 102): asked once "No alcohol" is chosen
              here, or when a report asked for it (the description says the bar serves none); never once an answer
              says alcohol is served. The create request sends the answer by the same test. */}
          {showsFoodService(value, asked) && (
            <FollowUp id="food_service">
              <Chips name="food-service" label={INTAKE_QUESTIONS.food_service.question} choices={INTAKE_QUESTIONS.food_service.answers} value={value.foodService} onChange={(foodService) => set({ foodService })} />
            </FollowUp>
          )}
        </Question>

        {asksAboutAlcohol(value) && (
          <Question id="alcohol_served" asked={isAsked("alcohol_served")}>
            <Chips name="pours" label={INTAKE_QUESTIONS.alcohol_served.question} choices={INTAKE_QUESTIONS.alcohol_served.answers} value={value.alcoholServed} onChange={(alcoholServed) => set({ alcoholServed })} />
          </Question>
        )}

        <Question id="stories" asked={isAsked("stories")}>
          <Ticks<StoryAnswer> name="story" label={INTAKE_QUESTIONS.stories.question} choices={INTAKE_QUESTIONS.stories.answers} value={value.stories} onChange={(stories) => set({ stories })} />
        </Question>

        <Question id="closing_time" asked={isAsked("closing_time")}>
          <Input
            id="intake-closing-time"
            data-testid="intake-closing-time"
            aria-label={INTAKE_QUESTIONS.closing_time.question}
            type="time"
            className="max-w-40 bg-background"
            value={value.closingTime}
            onChange={(e) => set({ closingTime: e.target.value })}
          />
        </Question>

        <Question id="last_use" asked={isAsked("last_use")}>
          <Chips name="last-use" label={INTAKE_QUESTIONS.last_use.question} choices={INTAKE_QUESTIONS.last_use.answers} value={value.lastUse} onChange={(lastUse) => set({ lastUse })} />
        </Question>

        <Question id="fewer_than_50_people" asked={isAsked("fewer_than_50_people")}>
          {yesNo("fewer_than_50_people", "under-50", value.under50, (under50) => set({ under50 }))}
        </Question>

        <Question id="outdoor_area" asked={isAsked("outdoor_area") || isAsked("outdoor_alcohol_service")}>
          <Chips name="outdoor" label={INTAKE_QUESTIONS.outdoor_area.question} choices={INTAKE_QUESTIONS.outdoor_area.answers} value={value.outdoorArea} onChange={(outdoorArea) => onChange(withOutdoorArea(value, outdoorArea, asked))} />
          {/* asked once a place is chosen here, or when a report asked for it (the description gave the place); the
              create request sends the answer by the same test, so an answer not shown is not sent */}
          {showsOutdoorAlcohol(value, asked) && (
            <FollowUp id="outdoor_alcohol_service">{yesNo("outdoor_alcohol_service", "outdoor-alcohol", value.outdoorAlcohol, (outdoorAlcohol) => set({ outdoorAlcohol }))}</FollowUp>
          )}
        </Question>

        <details className="rounded-xl border border-border bg-background/60 p-4" open={moreOpen} onToggle={(e) => setMoreOpen(e.currentTarget.open)} data-testid="intake-more">
          <summary className="cursor-pointer text-sm font-semibold">More details (only some reports ask for these)</summary>
          <p className="mt-2 text-xs text-muted-foreground">A report names each of these when it needs it. Answer one now if you already know it applies.</p>
          <div className="mt-4 space-y-6">
            <Question id="existing_business_change" asked={isAsked("existing_business_change")}>
              <Chips
                name="business-change"
                label={INTAKE_QUESTIONS.existing_business_change.question}
                choices={INTAKE_QUESTIONS.existing_business_change.answers}
                value={value.businessChange}
                onChange={(businessChange) => set({ businessChange })}
              />
            </Question>

            <Question id="floor_area_before_sqft" asked={isAsked("floor_area_before_sqft")}>
              <SquareFeet id="floor_area_before_sqft" testId="intake-floor-area-before" placeholder="e.g. 1200" value={value.floorAreaBefore} onChange={(floorAreaBefore) => set({ floorAreaBefore })} />
            </Question>

            <Question id="merges_storefronts" asked={isAsked("merges_storefronts")}>
              {yesNo("merges_storefronts", "merges", value.mergesStorefronts, (mergesStorefronts) => set({ mergesStorefronts }))}
            </Question>

            <Question id="amends_prior_approval" asked={isAsked("amends_prior_approval")}>
              {yesNo("amends_prior_approval", "amends", value.amendsApproval, (amendsApproval) => set({ amendsApproval }))}
            </Question>

            <Question id="entertainment" asked={isAsked("entertainment")}>
              <Chips name="entertainment" label={INTAKE_QUESTIONS.entertainment.question} choices={INTAKE_QUESTIONS.entertainment.answers} value={value.entertainment} onChange={(entertainment) => set({ entertainment })} />
            </Question>

            <Question id="existing_occupancy_group" asked={isAsked("existing_occupancy_group")}>
              <Chips
                name="occupancy-group"
                label={INTAKE_QUESTIONS.existing_occupancy_group.question}
                choices={INTAKE_QUESTIONS.existing_occupancy_group.answers}
                value={value.occupancyGroup}
                onChange={(occupancyGroup) => set({ occupancyGroup })}
              />
            </Question>
          </div>
        </details>
      </div>
    </div>
  );
}
