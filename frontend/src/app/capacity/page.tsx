import { redirect } from "next/navigation";

// Capacity tab removed — redirect any stale links to the Dashboard.
export default function CapacityRemoved() {
  redirect("/");
}
