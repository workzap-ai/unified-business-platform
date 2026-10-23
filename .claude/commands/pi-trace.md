Explain one pi message. $ARGUMENTS (a message id)

Read only. For the pi reply with that id, show: the conversation's flow state at that moment
(`pi_conversations.flow_state`, `flow_state_since`), the agent run that wrote it (`pi_agent_runs`,
`response_message_id`), the reply linter result for the text (`constitution.lint` with the
context rules in `service_conversation.py`), the learning stamps in `service_brief["learning_used"]`
(example ids, question arm), any `lint_slips` entry, the style profile inputs, and the experience
row (`pi_experiences`: signals and reward) if scored. Use the disposable database or the read-only
`.cache` helpers; never write.
