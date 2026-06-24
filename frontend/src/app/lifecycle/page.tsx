import { redirect } from "next/navigation";

// Lifecycle tab removed — redirect any stale links to the Dashboard.
export default function LifecycleRemoved() {
  redirect("/");
}
