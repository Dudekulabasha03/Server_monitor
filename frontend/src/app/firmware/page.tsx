import { redirect } from "next/navigation";

// Firmware tab merged into "Firmware & BIOS" (/bios → Compliance sub-tab).
export default function FirmwareMerged() {
  redirect("/bios");
}
