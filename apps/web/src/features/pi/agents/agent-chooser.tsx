"use client";

import { useState } from "react";
import { AgentFormDialog } from "./agent-form-dialog";
import { AgentPicker } from "./agent-picker";
import type { Agent } from "./meeting-agents-service";

/**
 * The picker plus "Create your own agent" in one piece: choosing closes it, creating opens the
 * form and then chooses the new agent. Used wherever a person picks an agent for something.
 */
export function AgentChooser({
  open,
  onOpenChange,
  value,
  onSelect,
  title,
  description,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  value: string | null | undefined;
  onSelect: (agent: Agent) => void;
  title?: string;
  description?: string;
}) {
  const [creating, setCreating] = useState(false);
  return (
    <>
      <AgentPicker
        open={open}
        onOpenChange={onOpenChange}
        value={value}
        onSelect={onSelect}
        title={title}
        description={description}
        onCreate={() => {
          onOpenChange(false);
          setCreating(true);
        }}
      />
      <AgentFormDialog
        open={creating}
        onOpenChange={setCreating}
        onSaved={onSelect}
      />
    </>
  );
}
