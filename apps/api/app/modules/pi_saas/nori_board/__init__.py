"""The Nori Platform board: nori users' requirements, problems and feedback on pi's team board.

models.py   the number registry and the per-card facts
service.py  numbers, filing an item as a board card, the WhatsApp path (pure rules, no HTTP)
door.py     POST /api/pi/nori-board: nori pushes an item (signed like the send door)
routes.py   the team's own API (/pi/nori-board: numbers, a requirement by hand) and the door

Off unless response_rules.nori_bridge.enabled and .board are exactly true and the server has the
bridge variables (docs/pi-saas/nori-bridge.md). pi's brain is not touched: a message from a number
on the board's registry is filed and answered by the bridge hook, before the brain would run.
"""
