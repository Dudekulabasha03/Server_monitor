import { redirect } from "next/navigation";

// Predictions tab removed — redirect any stale links to the Dashboard.
export default function PredictionsRemoved() {
  redirect("/");
}
