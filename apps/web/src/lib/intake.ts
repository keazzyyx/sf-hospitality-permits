import type {
  AlcoholServed,
  EntertainmentAnswer,
  ExistingBusinessChange,
  FoodServiceAnswer,
  IntakeAnswers,
  IntakeQuestionId,
  LastUse,
  LiquorLicence,
  OccupancyGroup,
  OutdoorAreaAnswer,
  StoryAnswer,
} from "@/lib/api-types";

/**
 * The optional intake questions on the page where a report is started. The words are the API's own
 * (apps/api/app/memo/intake.py, `QUESTIONS`); a test in the API checks that every question, answer label and value
 * below is written exactly as it is there. A skipped question is never read as "no": the report then names what it
 * could not tell, in the question's own words.
 *
 * Two groups, as in the API: the "main" questions are always shown; the "more" questions sit under "More details"
 * (only some reports ask for them, and the report names each one it needs).
 */
export const INTAKE_SKIP_NOTE = "Optional. If you skip it, the report will say it could not tell.";
export const INTAKE_SKIP_LABEL = "Skip";

export const OTHER_LOCATIONS_MAX = 100_000;
export const FLOOR_AREA_MAX_SQFT = 1_000_000;

const YES_NO = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
] as const;

export const INTAKE_QUESTIONS = {
  part_of_chain: {
    question: "Is the business part of a chain that shares its name, look or menu with other locations?",
    help: "Planning Code § 303.1 treats a business as formula retail when it has eleven or more other locations and shares two or more standard features with them, such as its name or trademark, signage, facade, decor or a standard range of merchandise.",
    answers: YES_NO,
  },
  other_locations: {
    question: "How many other locations does the chain have, open or approved, anywhere in the world?",
    help: "Count the locations already open and those with their permits approved. Eleven or more makes the business formula retail.",
  },
  floor_area_sqft: {
    question: "What is the floor area of the business, in square feet?",
    help: "Some districts need a Conditional Use for a business above a set size.",
  },
  liquor_licence: {
    question: "How will the liquor licence be obtained?",
    help: "Some districts limit new licences, and state law tests a new licence or a transfer from another location for over-concentration.",
    answers: [
      { value: "new", label: "New licence" },
      { value: "transfer_from_another_owner", label: "Transfer from another owner" },
      { value: "transfer_from_another_location", label: "Transfer from another location" },
      { value: "already_held", label: "Already hold a licence at this address" },
      { value: "none", label: "No alcohol" },
    ] as { value: LiquorLicence; label: string }[],
  },
  stories: {
    question: "Which stories does the business occupy?",
    help: "The zoning tables set the control for a business story by story, so the report cannot decide the zoning row without it. Pick every story the business will use.",
    answers: [
      { value: "basement", label: "Basement" },
      { value: "first", label: "First story (street level)" },
      { value: "second", label: "Second story" },
      { value: "third_or_above", label: "Third story or above" },
    ] as { value: StoryAnswer; label: string }[],
  },
  alcohol_served: {
    question: "What alcohol will be served: beer and wine, or spirits too?",
    help: "It decides the licence type: a restaurant that pours beer and wine takes a Type 41 licence and one that pours spirits a Type 47; a bar takes a Type 42 or a Type 48.",
    answers: [
      { value: "beer_wine", label: "Beer and wine only" },
      { value: "full_liquor", label: "Spirits too (a full bar)" },
    ] as { value: AlcoholServed; label: string }[],
  },
  closing_time: {
    question: "What is the closing time?",
    help: "Each district permits business hours up to a set time and asks for a Conditional Use after it. Give the latest closing time of the week.",
  },
  last_use: {
    question: "What was the space last used as?",
    help: "It decides whether opening here is a change of use. If the space is empty now, pick what it was last used as.",
    answers: [
      { value: "restaurant", label: "A restaurant" },
      { value: "bar", label: "A bar" },
      { value: "limited_restaurant", label: "A cafe or take-out counter (a limited restaurant)" },
      { value: "nighttime_entertainment", label: "A nightclub or entertainment venue" },
      { value: "retail", label: "A shop (retail)" },
      { value: "laundromat", label: "A laundromat" },
      { value: "other", label: "Something else" },
    ] as { value: LastUse; label: string }[],
  },
  fewer_than_50_people: {
    question: "Is the space for fewer than 50 people?",
    help: "The Building Code treats a restaurant or bar for fewer than 50 people as Group B and a larger one as Assembly Group A-2. It is the number of people the space is built to hold (its occupant load), not only the seats.",
    answers: YES_NO,
  },
  outdoor_area: {
    question: "Where is the outdoor area?",
    help: "An outdoor area in front is read differently from one at the rear, on the roof or on the sidewalk, so the report cannot decide the outdoor row without its place.",
    answers: [
      { value: "none", label: "No outdoor area" },
      { value: "front", label: "In front, on the lot" },
      { value: "rear_or_side", label: "At the rear or side" },
      { value: "rooftop", label: "On the roof" },
      { value: "parking_lot", label: "In a parking lot" },
      { value: "sidewalk", label: "On the sidewalk or in the parking lane" },
    ] as { value: OutdoorAreaAnswer; label: string }[],
  },
  outdoor_alcohol_service: {
    question: "Will alcohol be served in the outdoor area?",
    help: "Some outdoor areas are permitted only where alcohol is brought to seated patrons by wait staff.",
    answers: YES_NO,
  },
  food_service: {
    question: "What kind of food or drink service is it?",
    help: "Asked for a business that serves no alcohol: Planning Code § 102 defines a Bar by its on-site alcohol sales, so such a business is not a Bar. Under § 102 a Restaurant \"serves prepared, ready-to-eat cooked foods to customers for consumption on the premises\" and has seating; it may serve them to take away only as a minor and incidental use. A Limited Restaurant \"serves ready-to-eat foods and/or drinks to customers for consumption on or off the premises\", with or without seating, for example a sandwich shop, coffee house, pizzeria or ice cream shop.",
    answers: [
      { value: "restaurant", label: "A Restaurant (cooked food served on the premises, with seating)" },
      { value: "limited_restaurant", label: "A Limited Restaurant (ready-to-eat food or drinks, with or without seating)" },
      { value: "other", label: "Other, or not sure" },
    ] as { value: FoodServiceAnswer; label: string }[],
  },
  existing_business_change: {
    question: "Is an existing business to be enlarged or intensified?",
    help: "Answer only when a business of the same kind is already at the address and stays or is taken over: any answer tells the report that it is. Skip it when the space was something else.",
    answers: [
      { value: "none", label: "No: it stays as it is" },
      { value: "enlarge", label: "Enlarged (more floor area)" },
      { value: "intensify", label: "Intensified (new entertainment, longer hours or a stronger licence)" },
      { value: "enlarge_and_intensify", label: "Both" },
    ] as { value: ExistingBusinessChange; label: string }[],
  },
  floor_area_before_sqft: {
    question: "What was the floor area before the project, in square feet?",
    help: "The size rules compare the floor area before the project with the floor area after it.",
  },
  merges_storefronts: {
    question: "Are storefronts to be merged?",
    help: "The size rules ask whether two or more storefronts are combined into one business.",
    answers: YES_NO,
  },
  amends_prior_approval: {
    question: "Are the conditions of an earlier approval to be changed?",
    help: "Asked when an earlier approval at the address set conditions, such as hours: changing them goes back to the body that set them.",
    answers: YES_NO,
  },
  entertainment: {
    question: "Is there entertainment, and what kind?",
    help: "The kind of entertainment decides which Entertainment Commission permit applies.",
    answers: [
      { value: "none", label: "No entertainment" },
      { value: "limited_live_performance", label: "Limited live performance (a Limited Live Performance permit)" },
      { value: "place_of_entertainment", label: "A place of entertainment (a Place of Entertainment permit)" },
    ] as { value: EntertainmentAnswer; label: string }[],
  },
  existing_occupancy_group: {
    question: "What occupancy group do the plans or the certificate of occupancy of the existing space show?",
    help: "No public record shows it. With it the report can say whether the Building Code occupancy changes; without it that question stays open until plans or an inspection show the group.",
    answers: [
      { value: "B", label: "Group B" },
      { value: "A-2", label: "Assembly Group A-2" },
    ] as { value: OccupancyGroup; label: string }[],
  },
} as const;

/** The questions under "More details", in the API's order (`IntakeQuestion.group == "more"`). */
export const MORE_QUESTION_IDS: readonly IntakeQuestionId[] = [
  "existing_business_change",
  "floor_area_before_sqft",
  "merges_storefronts",
  "amends_prior_approval",
  "entertainment",
  "existing_occupancy_group",
];

export type YesNoChoice = "yes" | "no" | "skip";
export type ChainChoice = YesNoChoice;
type Skippable<T extends string> = T | "skip";

/** What the form holds: the choices, and the numbers and the time as typed. */
export interface IntakeForm {
  chain: ChainChoice;
  otherLocations: string;
  floorArea: string;
  licence: Skippable<LiquorLicence>;
  stories: StoryAnswer[];
  alcoholServed: Skippable<AlcoholServed>;
  closingTime: string;
  lastUse: Skippable<LastUse>;
  under50: YesNoChoice;
  outdoorArea: Skippable<OutdoorAreaAnswer>;
  outdoorAlcohol: YesNoChoice;
  foodService: Skippable<FoodServiceAnswer>;
  businessChange: Skippable<ExistingBusinessChange>;
  floorAreaBefore: string;
  mergesStorefronts: YesNoChoice;
  amendsApproval: YesNoChoice;
  entertainment: Skippable<EntertainmentAnswer>;
  occupancyGroup: Skippable<OccupancyGroup>;
}

export const EMPTY_INTAKE_FORM: IntakeForm = {
  chain: "skip",
  otherLocations: "",
  floorArea: "",
  licence: "skip",
  stories: [],
  alcoholServed: "skip",
  closingTime: "",
  lastUse: "skip",
  under50: "skip",
  outdoorArea: "skip",
  outdoorAlcohol: "skip",
  foodService: "skip",
  businessChange: "skip",
  floorAreaBefore: "",
  mergesStorefronts: "skip",
  amendsApproval: "skip",
  entertainment: "skip",
  occupancyGroup: "skip",
};

function values<T extends string>(answers: readonly { value: T }[]): readonly string[] {
  return answers.map((a) => a.value);
}

const LICENCES = values(INTAKE_QUESTIONS.liquor_licence.answers);
// The API's own order for the stories (`Story` in apps/api/app/models/profile.py): the answers are sent and
// read back in it, whatever order the form shows or ticks them in.
const STORIES: readonly string[] = ["first", "second", "third_or_above", "basement"];
const POURS = values(INTAKE_QUESTIONS.alcohol_served.answers);
const LAST_USES = values(INTAKE_QUESTIONS.last_use.answers);
const OUTDOOR_AREAS = values(INTAKE_QUESTIONS.outdoor_area.answers);
const FOOD_SERVICES = values(INTAKE_QUESTIONS.food_service.answers);
const BUSINESS_CHANGES = values(INTAKE_QUESTIONS.existing_business_change.answers);
const ENTERTAINMENTS = values(INTAKE_QUESTIONS.entertainment.answers);
const OCCUPANCY_GROUPS = values(INTAKE_QUESTIONS.existing_occupancy_group.answers);
const CLOSING_TIME = /^([01]\d|2[0-3]):[0-5]\d$/;

/** A whole number typed in a field, within bounds; null when blank or not one. */
function wholeNumber(text: string, min: number, max: number): number | null {
  const t = text.trim().replace(/,/g, "");
  if (!/^\d+$/.test(t)) return null;
  const n = Number(t);
  return Number.isSafeInteger(n) && n >= min && n <= max ? n : null;
}

/** A closing time as the API takes it ("HH:MM", 24-hour; a browser's "HH:MM:SS" is cut); null when blank or not one. */
function closingTime(text: string): string | null {
  const t = text.trim().slice(0, 5);
  return CLOSING_TIME.test(t) ? t : null;
}

function oneOf<T extends string>(raw: unknown, allowed: readonly string[]): Skippable<T> {
  return typeof raw === "string" && allowed.includes(raw) ? (raw as T) : "skip";
}

function yesNo(raw: unknown): YesNoChoice {
  return raw === true || raw === "yes" ? "yes" : raw === false || raw === "no" ? "no" : "skip";
}

function storyList(raw: unknown): StoryAnswer[] {
  const given = Array.isArray(raw) ? raw : typeof raw === "string" ? raw.split(",") : [];
  // each story once, in the API's order (first, second, third or above, basement)
  return STORIES.filter((s) => given.includes(s)) as StoryAnswer[];
}

/** There is no alcohol to ask about once the applicant answers "No alcohol". */
export function asksAboutAlcohol(form: IntakeForm): boolean {
  return form.licence !== "none";
}

/** The outdoor follow-up is asked unless the applicant answers "No outdoor area". */
export function asksAboutOutdoorAlcohol(form: IntakeForm): boolean {
  return form.outdoorArea !== "none" && asksAboutAlcohol(form);
}

/**
 * Whether the form shows the outdoor alcohol follow-up: once a place is chosen, when the report asked for it (the
 * description gave the place), or when the form already holds an answer to it (one carried by a link). The create
 * request sends the answer only when this holds, so an answer the form does not show is never sent.
 */
export function showsOutdoorAlcohol(form: IntakeForm, asked: readonly IntakeQuestionId[] = []): boolean {
  return asksAboutOutdoorAlcohol(form) && (form.outdoorArea !== "skip" || form.outdoorAlcohol !== "skip" || asked.includes("outdoor_alcohol_service"));
}

/**
 * The form with the outdoor area answered. Going back to Skip takes back the answer about alcohol outdoors too,
 * unless the report asked for it: that question stands without a place.
 */
export function withOutdoorArea(form: IntakeForm, outdoorArea: Skippable<OutdoorAreaAnswer>, asked: readonly IntakeQuestionId[] = []): IntakeForm {
  const next = { ...form, outdoorArea };
  return outdoorArea === "skip" && !asked.includes("outdoor_alcohol_service") ? { ...next, outdoorAlcohol: "skip" } : next;
}

/**
 * The kind of food or drink service is asked only for a business that serves no alcohol (a bar that serves none is
 * not a Bar, Planning Code § 102): not once the form holds an answer that says alcohol is served (a liquor licence,
 * what is poured, alcohol outdoors). The API refuses the two together.
 */
export function asksAboutFoodService(form: IntakeForm): boolean {
  const licensed = form.licence !== "skip" && form.licence !== "none";
  const pours = form.alcoholServed !== "skip" && asksAboutAlcohol(form);
  const outdoors = form.outdoorAlcohol === "yes" && showsOutdoorAlcohol(form);
  return !licensed && !pours && !outdoors;
}

/**
 * Whether the form shows the question on the kind of food or drink service, under the liquor licence question: once
 * "No alcohol" is answered, when the report asked for it (the description says the bar serves no alcohol), or when
 * the form already holds an answer to it; never once an answer says alcohol is served. The create request sends the
 * answer by the same test (without `asked`, which the form has answered by then), so an answer not shown is not sent.
 */
export function showsFoodService(form: IntakeForm, asked: readonly IntakeQuestionId[] = []): boolean {
  return asksAboutFoodService(form) && (form.licence === "none" || form.foodService !== "skip" || asked.includes("food_service"));
}

/** What is wrong with a number or a time typed in the form, one plain line per field; empty when nothing is. */
export function intakeFormErrors(form: IntakeForm): string[] {
  const errors: string[] = [];
  if (form.chain === "yes" && form.otherLocations.trim() && wholeNumber(form.otherLocations, 0, OTHER_LOCATIONS_MAX) === null) {
    errors.push("Enter the number of other locations as a whole number, or leave it blank.");
  }
  if (form.floorArea.trim() && wholeNumber(form.floorArea, 1, FLOOR_AREA_MAX_SQFT) === null) {
    errors.push("Enter the floor area as a whole number of square feet, or leave it blank.");
  }
  if (form.floorAreaBefore.trim() && wholeNumber(form.floorAreaBefore, 1, FLOOR_AREA_MAX_SQFT) === null) {
    errors.push("Enter the floor area before the project as a whole number of square feet, or leave it blank.");
  }
  if (form.closingTime.trim() && closingTime(form.closingTime) === null) {
    errors.push("Enter the closing time as a time of day, or leave it blank.");
  }
  return errors;
}

/**
 * The answers the create request sends: only the questions answered; null when none was. An answer to a follow-up
 * the form no longer shows (what is poured after "No alcohol", alcohol outdoors after "No outdoor area" or once
 * the outdoor area is back to Skip: `showsOutdoorAlcohol`, `withOutdoorArea`; the kind of food or drink service
 * once an answer says alcohol is served: `showsFoodService`) is left out: the API refuses two answers that
 * contradict each other.
 */
export function intakeAnswersFromForm(form: IntakeForm): IntakeAnswers | null {
  const out: IntakeAnswers = {};
  if (form.chain !== "skip") {
    out.part_of_chain = form.chain === "yes";
    const count = form.chain === "yes" ? wholeNumber(form.otherLocations, 0, OTHER_LOCATIONS_MAX) : null;
    if (count !== null) out.other_locations = count;
  }
  const area = wholeNumber(form.floorArea, 1, FLOOR_AREA_MAX_SQFT);
  if (area !== null) out.floor_area_sqft = area;
  if (form.licence !== "skip") out.liquor_licence = form.licence;
  if (form.stories.length > 0) out.stories = storyList(form.stories);
  if (form.alcoholServed !== "skip" && asksAboutAlcohol(form)) out.alcohol_served = form.alcoholServed;
  const closes = closingTime(form.closingTime);
  if (closes !== null) out.closing_time = closes;
  if (form.lastUse !== "skip") out.last_use = form.lastUse;
  if (form.under50 !== "skip") out.fewer_than_50_people = form.under50 === "yes";
  if (form.outdoorArea !== "skip") out.outdoor_area = form.outdoorArea;
  if (form.outdoorAlcohol !== "skip" && showsOutdoorAlcohol(form)) out.outdoor_alcohol_service = form.outdoorAlcohol === "yes";
  if (form.foodService !== "skip" && showsFoodService(form)) out.food_service = form.foodService;
  if (form.businessChange !== "skip") out.existing_business_change = form.businessChange;
  const before = wholeNumber(form.floorAreaBefore, 1, FLOOR_AREA_MAX_SQFT);
  if (before !== null) out.floor_area_before_sqft = before;
  if (form.mergesStorefronts !== "skip") out.merges_storefronts = form.mergesStorefronts === "yes";
  if (form.amendsApproval !== "skip") out.amends_prior_approval = form.amendsApproval === "yes";
  if (form.entertainment !== "skip") out.entertainment = form.entertainment;
  if (form.occupancyGroup !== "skip") out.existing_occupancy_group = form.occupancyGroup;
  return Object.keys(out).length > 0 ? out : null;
}

/** The form for raw answers (from the API, a URL or storage): anything not well formed is a skipped question. */
function formFromRaw(r: Record<string, unknown>): IntakeForm {
  return {
    chain: typeof r.part_of_chain === "boolean" ? yesNo(r.part_of_chain) : "skip",
    otherLocations: typeof r.other_locations === "number" ? String(r.other_locations) : "",
    floorArea: typeof r.floor_area_sqft === "number" ? String(r.floor_area_sqft) : "",
    licence: oneOf<LiquorLicence>(r.liquor_licence, LICENCES),
    stories: storyList(r.stories),
    alcoholServed: oneOf<AlcoholServed>(r.alcohol_served, POURS),
    closingTime: typeof r.closing_time === "string" ? (closingTime(r.closing_time) ?? "") : "",
    lastUse: oneOf<LastUse>(r.last_use, LAST_USES),
    under50: typeof r.fewer_than_50_people === "boolean" ? yesNo(r.fewer_than_50_people) : "skip",
    outdoorArea: oneOf<OutdoorAreaAnswer>(r.outdoor_area, OUTDOOR_AREAS),
    outdoorAlcohol: typeof r.outdoor_alcohol_service === "boolean" ? yesNo(r.outdoor_alcohol_service) : "skip",
    foodService: oneOf<FoodServiceAnswer>(r.food_service, FOOD_SERVICES),
    businessChange: oneOf<ExistingBusinessChange>(r.existing_business_change, BUSINESS_CHANGES),
    floorAreaBefore: typeof r.floor_area_before_sqft === "number" ? String(r.floor_area_before_sqft) : "",
    mergesStorefronts: typeof r.merges_storefronts === "boolean" ? yesNo(r.merges_storefronts) : "skip",
    amendsApproval: typeof r.amends_prior_approval === "boolean" ? yesNo(r.amends_prior_approval) : "skip",
    entertainment: oneOf<EntertainmentAnswer>(r.entertainment, ENTERTAINMENTS),
    occupancyGroup: oneOf<OccupancyGroup>(r.existing_occupancy_group, OCCUPANCY_GROUPS),
  };
}

/** The form showing answers given earlier (a re-run, or a memo resumed after sign-in). */
export function intakeFormFromAnswers(answers: IntakeAnswers | null | undefined): IntakeForm {
  if (!answers) return EMPTY_INTAKE_FORM;
  return formFromRaw(answers as Record<string, unknown>);
}

/** Keep only well-formed answers (from a URL or storage); null when none is. */
export function cleanIntakeAnswers(raw: unknown): IntakeAnswers | null {
  if (!raw || typeof raw !== "object") return null;
  return intakeAnswersFromForm(formFromRaw(raw as Record<string, unknown>));
}

const YES_NO_KEYS = ["part_of_chain", "fewer_than_50_people", "outdoor_alcohol_service", "merges_storefronts", "amends_prior_approval"] as const;
const NUMBER_KEYS = ["other_locations", "floor_area_sqft", "floor_area_before_sqft"] as const;
const TEXT_KEYS = ["liquor_licence", "alcohol_served", "closing_time", "last_use", "outdoor_area", "food_service", "existing_business_change", "entertainment", "existing_occupancy_group"] as const;

/** Add the answers to a `/app/memo?...` query (a skipped question adds nothing). */
export function setIntakeQuery(q: URLSearchParams, answers: IntakeAnswers | null | undefined): void {
  if (!answers) return;
  for (const key of YES_NO_KEYS) {
    const v = answers[key];
    if (typeof v === "boolean") q.set(key, v ? "yes" : "no");
  }
  for (const key of NUMBER_KEYS) {
    const v = answers[key];
    if (typeof v === "number") q.set(key, String(v));
  }
  for (const key of TEXT_KEYS) {
    const v = answers[key];
    if (v) q.set(key, v);
  }
  if (answers.stories && answers.stories.length > 0) q.set("stories", answers.stories.join(","));
}

/** The answers a `/app/memo?...` query carries; null when it carries none. */
export function intakeFromQuery(params: { get(name: string): string | null }): IntakeAnswers | null {
  const raw: Record<string, unknown> = {};
  for (const key of YES_NO_KEYS) {
    const v = params.get(key);
    if (v === "yes" || v === "no") raw[key] = v === "yes";
  }
  for (const key of NUMBER_KEYS) {
    const v = params.get(key);
    if (v && /^\d+$/.test(v.trim())) raw[key] = Number(v.trim());
  }
  for (const key of TEXT_KEYS) {
    const v = params.get(key);
    if (v) raw[key] = v;
  }
  const stories = params.get("stories");
  if (stories) raw.stories = stories;
  return cleanIntakeAnswers(raw);
}

/**
 * The questions a report asked for (`OpenQuestion.intake_question`), in a `/app/memo?...&answer=1&ask=a,b` link:
 * the form then opens with the earlier input filled in and those questions marked, and waits for the answers
 * instead of starting the report at once.
 */
export const ANSWER_PARAM = "answer";
export const ASK_PARAM = "ask";

export function isIntakeQuestionId(id: unknown): id is IntakeQuestionId {
  return typeof id === "string" && id in INTAKE_QUESTIONS;
}

/** The question ids a `?ask=` value names, each once, unknown ones dropped. */
export function askedQuestions(value: string | null | undefined): IntakeQuestionId[] {
  const ids = (value ?? "").split(",").map((s) => s.trim());
  return [...new Set(ids)].filter(isIntakeQuestionId);
}
