import { z } from "zod";
import { apiRequest } from "@/services/api-client";

/**
 * Team board: everything the team must do across all customers, as a Kanban.
 * Backend: apps/api/app/modules/pi_saas/team_board.py, team_board_routes.py
 * (/api/v1/pi/team-board). Most cards are made (and closed) by pi itself.
 */

export const BOARD_KINDS = [
  "price",
  "approve",
  "invoice",
  "payment",
  "request",
  "reply",
  "start",
  "deliver",
  "feedback",
  "task",
] as const;
export type BoardKind = (typeof BOARD_KINDS)[number];

export const BOARD_COLUMNS = ["todo", "doing", "waiting", "done"] as const;
export type BoardColumn = (typeof BOARD_COLUMNS)[number];

/** The task status each column stands for. */
export const COLUMN_STATUS: Record<BoardColumn, string> = {
  todo: "open",
  doing: "in_progress",
  waiting: "blocked",
  done: "done",
};

export const PRIORITIES = ["low", "normal", "high", "urgent"] as const;
export type Priority = (typeof PRIORITIES)[number];

export const boardCardSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().catch(""),
  kind: z.enum(BOARD_KINDS).catch("task"),
  auto: z.boolean().catch(false),
  status: z.string(),
  column: z.enum(BOARD_COLUMNS).catch("todo"),
  customer: z
    .object({ id: z.string(), name: z.string().catch("") })
    .nullable()
    .catch(null),
  project: z.string().nullable().catch(null),
  assignee: z
    .object({ id: z.string(), name: z.string().catch("") })
    .nullable()
    .catch(null),
  priority: z.enum(PRIORITIES).catch("normal"),
  due_at: z.string().nullable().catch(null),
  overdue: z.boolean().catch(false),
  created_at: z.string(),
  updated_at: z.string().catch(""),
  created_by: z.string().catch(""),
  link: z.string().nullable().catch(null),
});
export type BoardCard = z.infer<typeof boardCardSchema>;

export const teamBoardSchema = z.object({
  columns: z.object({
    todo: z.array(boardCardSchema),
    doing: z.array(boardCardSchema),
    waiting: z.array(boardCardSchema),
    done: z.array(boardCardSchema),
  }),
  members: z.array(z.object({ id: z.string(), name: z.string() })),
  counts: z.record(z.string(), z.number()).catch({}),
  kinds: z.record(z.string(), z.number()).catch({}),
  by_member: z.record(z.string(), z.number()).catch({}),
  me: z.string().nullable().catch(null),
  updated_at: z.string(),
});
export type TeamBoard = z.infer<typeof teamBoardSchema>;

export type BoardFilter = {
  /** "all", "me", "unassigned" or one member's user id. */
  who: string;
  kind: BoardKind | null;
};

export type NewBoardTask = {
  title: string;
  description?: string;
  customer_id?: string | null;
  assignee_user_id?: string | null;
  priority: Priority;
  due_at?: string | null;
};

export type BoardTaskChange = {
  status?: string;
  assignee_user_id?: string | null;
  priority?: Priority;
  due_at?: string | null;
};

/** Team members' WhatsApp numbers for task alerts (team_alerts.py). */
export const teamMembersSchema = z.object({
  enabled: z.boolean().catch(true),
  template_name: z.string().catch(""),
  template_language: z.string().catch(""),
  business_number: z.string().nullable().catch(null),
  members: z.array(
    z.object({
      id: z.string(),
      name: z.string().catch(""),
      whatsapp: z.string().catch(""),
      window_open: z.boolean().catch(false),
    }),
  ),
});
export type TeamMembers = z.infer<typeof teamMembersSchema>;

export type TeamMembersChange = {
  enabled?: boolean;
  numbers?: Record<string, string>;
  template_name?: string;
  template_language?: string;
};

const testSchema = z.object({
  delivery: z.enum(["sent", "template", "no_window"]).catch("no_window"),
  business_number: z.string().nullable().catch(null),
});

export const teamBoardService = {
  get: ({ who, kind }: BoardFilter) =>
    apiRequest("GET", "/pi/team-board", teamBoardSchema, {
      query: { who, kind: kind ?? undefined },
    }),
  create: (input: NewBoardTask) =>
    apiRequest("POST", "/pi/team-board/tasks", boardCardSchema, {
      body: input,
    }),
  update: ({ id, ...change }: BoardTaskChange & { id: string }) =>
    apiRequest(
      "PATCH",
      `/pi/team-board/tasks/${encodeURIComponent(id)}`,
      boardCardSchema,
      { body: change },
    ),
  members: () => apiRequest("GET", "/pi/team-board/members", teamMembersSchema),
  saveMembers: (change: TeamMembersChange) =>
    apiRequest("PUT", "/pi/team-board/members", teamMembersSchema, {
      body: change,
    }),
  testMember: (userId: string) =>
    apiRequest(
      "POST",
      `/pi/team-board/members/${encodeURIComponent(userId)}/test`,
      testSchema,
    ),
};
