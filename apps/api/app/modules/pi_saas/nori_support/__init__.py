"""Nori support mode: pi answers a Nori Platform registry person about nori and their workspace.

Only for numbers on the registry (pi_saas/nori_board) of a workspace that turned on
`response_rules.nori_bridge.support`. The sales brain never runs for these numbers. Facts come from
nori (read-only `workspace_info`), are never stored, and pi never states a figure that is not
in them.
Docs: docs/pi-saas/nori-support.md.
"""
