import { demoNotifications } from "./service";

export function demoUnreadCount() {
  return demoNotifications().filter((n) => !n.read).length;
}
