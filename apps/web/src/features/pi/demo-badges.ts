import { demoPi } from "./demo-data";

export function demoOpenHandoffCount() {
  return demoPi().handoffs.filter((h) => ["open", "assigned", "in_progress"].includes(h.status))
    .length;
}
