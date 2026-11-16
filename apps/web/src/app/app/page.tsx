import { redirect } from "next/navigation";

/** The paid product is the memo; `/app` lands on the memo list. Permit checklists live at `/app/plans`. */
export default function AppIndexPage() {
  redirect("/app/memos");
}
