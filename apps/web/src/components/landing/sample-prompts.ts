export interface SamplePrompt {
  label: string;
  city: string;
  text: string;
}

export const SAMPLE_PROMPTS: SamplePrompt[] = [
  {
    label: "Wine bar",
    city: "San Francisco",
    text: "Opening a 40-seat wine bar in SF Mission, small kitchen, serve until 1am, maybe live music",
  },
  {
    label: "Food truck",
    city: "Houston",
    text: "Launching a birria taco food truck in Houston, cooking on board with propane, parking at breweries and office parks, 3 employees",
  },
  {
    label: "Cafe",
    city: "Brooklyn",
    text: "A 25-seat specialty coffee cafe in Williamsburg, Brooklyn with pastries from a commissary, sidewalk seating for 8, new awning sign",
  },
  {
    label: "Boutique hotel",
    city: "Denver",
    text: "Converting a 3-story building in Denver RiNo into a 30-room boutique hotel with a lobby bar serving beer and wine and a small breakfast kitchen",
  },
];
