# pi problem-solving: scripted baseline (PS-0)

Pinned to `origin/main` **c73cf4f** (worktree `ps0`, branch `pi/ps0-baseline`, 2026-10-31). Numbers only: no
acceptance wording, no percentage target. Nothing here is a measure of the model.

## 1. Protocol (written before the numbers)

**Minimum for a measured cell** (set in code before this report was produced: `ps_scorers.MIN_CASES = 3`,
the existing evalkit constant, and `ps_scorers.MIN_ITEMS = 10`): a cell is printed as a percentage only when
it has at least **3 cases that contribute items** and at least **10 scored items** (the denominator). Below
either, the cell prints `not yet measured (num/den, N cases)`. Every cell shows its `num/den`.

**Cases.** `cases/problem_solving.json`: 60 conversation cases (`case_type` conversation, `format_version` 2,
`kind` problem_solving), 15 scenarios x 4 languages (en, roman_ur, ur, ar). 15 industries: property
management and rentals (rental management), e-commerce and D2C, sports clubs and turf rentals (bookings),
wedding planners (wedding management), banquet halls, salons, clinics (reception), auto workshops (repair),
poultry farms, private schools, restaurants, trucking, gyms, pharmacies, dropshipping. Each case has four owner
turns: T0 incomplete first message with one wrong figure, T1 a connected second problem + a hard limit + a thing
tried + the owner's own cause, T2 the corrected figure ("not 10, it was 100", "10 nahi 100", Urdu, Arabic) and a
request for a fix, T3 a rejection of pi's idea and a changed requirement. Each case also holds three
reference pi replies, reference extractor notes per turn, labelled candidate ideas, the allowed question slot per
pi turn, and a reference blueprint (steps, dependencies, resources, success criteria). All text is synthetic and
was drafted by agents; **no human has reviewed it** (`provenance.reviewer` is null).

**Splits.** Not stored in a case. `splits.split_of`: `regression` true gives Regression, else
`sha256(id)[0] % 100 < 25` gives Held-out, else Development. The case-id to split table is section 5. The 60 new
cases have no Regression case (none is a past failure); the Regression row below uses the 3 existing extraction
cases tagged `regression`. **Held-out is sealed**: the report skips it (`ps_report.score_all`), `replay_case`
refuses it without an `access_log.Pass`, a unit test proves both, and no Held-out case was replayed, scored or
used to choose a cue, threshold or wording. Authors of the case text did not compute splits.

**What is scripted and what is the live code.** Run per owner turn, no model call: the live gate
`problem_extract.wants_extraction`; the live `problem_extract.extract` (caps, per-note checks, known-title filter)
fed by the case's hand-written reference notes through the existing `ScriptedManager`; the live
`figure_correction.numeric_correction`; the live `problem_fields.merge_cause`; the live `idea_filter.failures`
with `context_from` the noted problems; `language.detect_language`; `expert_advisor.question_ok` and
`same_question`; the Solution Box schema `brain_docs.BoxDraft`. Scripted (not model output): the extractor's
notes, pi's three replies per case, the labelled candidate ideas, the blueprint. Not run: the reply model, the
flow state machine, the database, the idea engines, document drafting.

**Two record sets.** `live` = what the current extractor shape (`SimpleNote`, `problem_extract.py:51-68`) can
carry: it has no field for constraints, things tried, a cause or an expected outcome, so the real path drops them
(metrics without a suffix). `_reference` = the same notes with those fields added back; it checks the scorers
and shows what the notes hold (reference notes exist for owner turns 0 and 1 only, so limits said in turn 3 are
not in them); it is not a ceiling for the model.

**Metrics** (all as `num/den`): problem recall and precision; figure fidelity; correction detected (the live
finder) and applied; stated facts, constraints and things tried kept in the saved records; owner-said cause
captured; unsupported cause confirmed; a guessed cause stays a hypothesis (`merge_cause`, with and without a
wrong "owner said" flag); relevance scorer agreement with the labels, false relevant, limit-violating ideas the
scorer missed; limit-violating ideas rejected by the live idea filter (any rule, and by a rule other than G8);
relevant ideas kept by the live filter; language of pi's reference replies; repeated question; unclassified
question; one-question form; blueprint elements present, dependencies valid, tied to owner words, steps breaking
a stated limit, price or promise in the blueprint.

**Known limits of the numbers.** Question, language and blueprint metrics score hand-written reference text, so
they check the scorers and the case design, not pi. The repeated-question scorer uses a small fixed cue list per
slot (en, roman_ur, ur, ar); the cues were adjusted on Development cases after a first run showed which
questions it could not classify; unclassified questions are counted separately and never as "fine". The
relevance scorer agreed 55% with an independent grader on the borderline set (see `relevance.py`). The live
idea filter is given only the noted problems and the owner's words (no pack entries, industries or map nodes
the live path may add). Correction application is simulated by `figure_correction.replace_figure` over the
record's text fields; where the live path applies it was not traced into the run.

## 2. Run

Command (from `apps/api`, disposable test environment, no model call, no database use):
`python -m app.modules.pi.evalkit.ps_report --out <file>`. Cases: 60 = Development 43 +
Held-out 17 (not scored) + Regression 0. Scored: the 43 Development cases and the 3
existing extraction Regression cases. Each column header shows its case count n.

## 3. Results

### Development, by language

| metric | all (43 cases) | ar (12 cases) | en (9 cases) | roman_ur (9 cases) | ur (13 cases) |
|---|---|---|---|---|---|
| recall | 85/86 (99%) | 23/24 (96%) | 18/18 (100%) | 18/18 (100%) | 26/26 (100%) |
| precision | 85/86 (99%) | 23/24 (96%) | 18/18 (100%) | 18/18 (100%) | 26/26 (100%) |
| figure_fidelity | 31/42 (74%) | 0/11 (0%) | not yet measured (9/9, 9 cases) | not yet measured (9/9, 9 cases) | 13/13 (100%) |
| correction_detected | 31/43 (72%) | 0/12 (0%) | not yet measured (9/9, 9 cases) | not yet measured (9/9, 9 cases) | 13/13 (100%) |
| correction_applied | 31/43 (72%) | 0/12 (0%) | not yet measured (9/9, 9 cases) | not yet measured (9/9, 9 cases) | 13/13 (100%) |
| stated_facts_kept | 40/143 (28%) | 9/41 (22%) | 8/29 (28%) | 10/30 (33%) | 13/43 (30%) |
| constraints_kept | 0/157 (0%) | 0/44 (0%) | 0/34 (0%) | 0/32 (0%) | 0/47 (0%) |
| tried_kept | 0/43 (0%) | 0/12 (0%) | not yet measured (0/9, 9 cases) | not yet measured (0/9, 9 cases) | 0/13 (0%) |
| owner_cause_captured | 0/43 (0%) | 0/12 (0%) | not yet measured (0/9, 9 cases) | not yet measured (0/9, 9 cases) | 0/13 (0%) |
| unsupported_cause | 0/86 (0%) | 0/24 (0%) | 0/18 (0%) | 0/18 (0%) | 0/26 (0%) |
| hypothesis_stays_hypothesis | 171/172 (99%) | 48/48 (100%) | 35/36 (97%) | 36/36 (100%) | 52/52 (100%) |
| relevance_agreement | 177/215 (82%) | 39/60 (65%) | 39/45 (87%) | 42/45 (93%) | 57/65 (88%) |
| false_relevant | 1/215 (0%) | 0/60 (0%) | 1/45 (2%) | 0/45 (0%) | 0/65 (0%) |
| violations_missed_by_scorer | 2/43 (5%) | 2/12 (17%) | not yet measured (0/9, 9 cases) | not yet measured (0/9, 9 cases) | 0/13 (0%) |
| violations_rejected_by_live_filter | 29/43 (67%) | 12/12 (100%) | not yet measured (1/9, 9 cases) | not yet measured (3/9, 9 cases) | 13/13 (100%) |
| violations_rejected_by_other_than_g8 | 0/43 (0%) | 0/12 (0%) | not yet measured (0/9, 9 cases) | not yet measured (0/9, 9 cases) | 0/13 (0%) |
| relevant_kept_by_live_filter | 35/86 (41%) | 0/24 (0%) | 18/18 (100%) | 17/18 (94%) | 0/26 (0%) |
| language_match | 129/129 (100%) | 36/36 (100%) | 27/27 (100%) | 27/27 (100%) | 39/39 (100%) |
| language_undetected | 0/129 (0%) | 0/36 (0%) | 0/27 (0%) | 0/27 (0%) | 0/39 (0%) |
| repeated_question | 0/129 (0%) | 0/36 (0%) | 0/27 (0%) | 0/27 (0%) | 0/39 (0%) |
| unclassified_question | 3/129 (2%) | 0/36 (0%) | 1/27 (4%) | 0/27 (0%) | 2/39 (5%) |
| question_form_ok | 127/129 (98%) | 36/36 (100%) | 25/27 (93%) | 27/27 (100%) | 39/39 (100%) |
| blueprint_elements_present | 172/172 (100%) | 48/48 (100%) | 36/36 (100%) | 36/36 (100%) | 52/52 (100%) |
| blueprint_dependencies_valid | 157/157 (100%) | 44/44 (100%) | 32/32 (100%) | 33/33 (100%) | 48/48 (100%) |
| blueprint_tied_to_owner_words | 206/215 (96%) | 51/60 (85%) | 45/45 (100%) | 45/45 (100%) | 65/65 (100%) |
| blueprint_steps_breaking_a_limit | 13/258 (5%) | 1/72 (1%) | 5/54 (9%) | 2/54 (4%) | 5/78 (6%) |
| blueprint_price_or_promise | 0/258 (0%) | 0/72 (0%) | 0/54 (0%) | 0/54 (0%) | 0/78 (0%) |
| constraints_kept_reference | 69/157 (44%) | 19/44 (43%) | 15/34 (44%) | 14/32 (44%) | 21/47 (45%) |
| tried_kept_reference | 43/43 (100%) | 12/12 (100%) | not yet measured (9/9, 9 cases) | not yet measured (9/9, 9 cases) | 13/13 (100%) |
| owner_cause_captured_reference | 41/43 (95%) | 10/12 (83%) | not yet measured (9/9, 9 cases) | not yet measured (9/9, 9 cases) | 13/13 (100%) |
| stated_facts_kept_reference | 100/143 (70%) | 24/41 (59%) | 22/29 (76%) | 22/30 (73%) | 32/43 (74%) |

### Development, by industry (key metrics)

| metric | auto_workshops_and_service_centres (2 cases) | banquet_halls_and_marquees (2 cases) | clinics_and_gp_practices (3 cases) | dropshipping_and_social_commerce_sellers (3 cases) | e_commerce_and_d2c_brands (3 cases) | gyms_and_fitness_studios (3 cases) | pharmacies_and_medical_stores (2 cases) | poultry_farms (4 cases) | private_schools_and_school_chains (3 cases) | property_management_and_rentals (2 cases) | restaurants (4 cases) | salons_and_barbers (2 cases) | sports_clubs_academies_and_turf_court_rentals (4 cases) | trucking_and_goods_transport_companies (3 cases) | wedding_planners_and_event_management (3 cases) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| recall | not yet measured (4/4, 2 cases) | not yet measured (4/4, 2 cases) | not yet measured (6/6, 3 cases) | not yet measured (6/6, 3 cases) | not yet measured (5/6, 3 cases) | not yet measured (6/6, 3 cases) | not yet measured (4/4, 2 cases) | not yet measured (8/8, 4 cases) | not yet measured (6/6, 3 cases) | not yet measured (4/4, 2 cases) | not yet measured (8/8, 4 cases) | not yet measured (4/4, 2 cases) | not yet measured (8/8, 4 cases) | not yet measured (6/6, 3 cases) | not yet measured (6/6, 3 cases) |
| figure_fidelity | not yet measured (2/2, 2 cases) | not yet measured (1/2, 2 cases) | not yet measured (3/3, 3 cases) | not yet measured (2/3, 3 cases) | not yet measured (2/2, 2 cases) | not yet measured (2/3, 3 cases) | not yet measured (2/2, 2 cases) | not yet measured (3/4, 4 cases) | not yet measured (2/3, 3 cases) | not yet measured (1/2, 2 cases) | not yet measured (3/4, 4 cases) | not yet measured (1/2, 2 cases) | not yet measured (3/4, 4 cases) | not yet measured (2/3, 3 cases) | not yet measured (2/3, 3 cases) |
| correction_detected | not yet measured (2/2, 2 cases) | not yet measured (1/2, 2 cases) | not yet measured (3/3, 3 cases) | not yet measured (2/3, 3 cases) | not yet measured (2/3, 3 cases) | not yet measured (2/3, 3 cases) | not yet measured (2/2, 2 cases) | not yet measured (3/4, 4 cases) | not yet measured (2/3, 3 cases) | not yet measured (1/2, 2 cases) | not yet measured (3/4, 4 cases) | not yet measured (1/2, 2 cases) | not yet measured (3/4, 4 cases) | not yet measured (2/3, 3 cases) | not yet measured (2/3, 3 cases) |
| stated_facts_kept | not yet measured (0/6, 2 cases) | not yet measured (1/8, 2 cases) | not yet measured (3/9, 3 cases) | not yet measured (3/9, 3 cases) | 1/12 (8%) | not yet measured (3/9, 3 cases) | not yet measured (2/6, 2 cases) | 4/12 (33%) | not yet measured (1/9, 3 cases) | not yet measured (3/8, 2 cases) | 4/12 (33%) | not yet measured (4/6, 2 cases) | 3/16 (19%) | not yet measured (3/9, 3 cases) | 5/12 (42%) |
| constraints_kept | not yet measured (0/6, 2 cases) | not yet measured (0/8, 2 cases) | not yet measured (0/9, 3 cases) | 0/12 (0%) | 0/12 (0%) | 0/12 (0%) | not yet measured (0/8, 2 cases) | 0/16 (0%) | not yet measured (0/9, 3 cases) | not yet measured (0/6, 2 cases) | 0/16 (0%) | not yet measured (0/6, 2 cases) | 0/16 (0%) | 0/12 (0%) | not yet measured (0/9, 3 cases) |
| relevance_agreement | not yet measured (10/10, 2 cases) | not yet measured (8/10, 2 cases) | 8/15 (53%) | 12/15 (80%) | 13/15 (87%) | 13/15 (87%) | not yet measured (8/10, 2 cases) | 20/20 (100%) | 14/15 (93%) | not yet measured (7/10, 2 cases) | 17/20 (85%) | not yet measured (8/10, 2 cases) | 15/20 (75%) | 10/15 (67%) | 14/15 (93%) |
| repeated_question | not yet measured (0/6, 2 cases) | not yet measured (0/6, 2 cases) | not yet measured (0/9, 3 cases) | not yet measured (0/9, 3 cases) | not yet measured (0/9, 3 cases) | not yet measured (0/9, 3 cases) | not yet measured (0/6, 2 cases) | 0/12 (0%) | not yet measured (0/9, 3 cases) | not yet measured (0/6, 2 cases) | 0/12 (0%) | not yet measured (0/6, 2 cases) | 0/12 (0%) | not yet measured (0/9, 3 cases) | not yet measured (0/9, 3 cases) |
| language_match | not yet measured (6/6, 2 cases) | not yet measured (6/6, 2 cases) | not yet measured (9/9, 3 cases) | not yet measured (9/9, 3 cases) | not yet measured (9/9, 3 cases) | not yet measured (9/9, 3 cases) | not yet measured (6/6, 2 cases) | 12/12 (100%) | not yet measured (9/9, 3 cases) | not yet measured (6/6, 2 cases) | 12/12 (100%) | not yet measured (6/6, 2 cases) | 12/12 (100%) | not yet measured (9/9, 3 cases) | not yet measured (9/9, 3 cases) |
| blueprint_elements_present | not yet measured (8/8, 2 cases) | not yet measured (8/8, 2 cases) | 12/12 (100%) | 12/12 (100%) | 12/12 (100%) | 12/12 (100%) | not yet measured (8/8, 2 cases) | 16/16 (100%) | 12/12 (100%) | not yet measured (8/8, 2 cases) | 16/16 (100%) | not yet measured (8/8, 2 cases) | 16/16 (100%) | 12/12 (100%) | 12/12 (100%) |

### Regression

New problem-solving cases tagged regression: 0. Existing extraction cases tagged regression, through the existing scripted replay:

| metric | regression (extraction) (3 cases) |
|---|---|
| recall | 11/11 (100%) |
| precision | 11/11 (100%) |
| figure_fidelity | not yet measured (3/3, 3 cases) |
| correction_applied | not yet measured (1/1, 1 cases) |

### Live idea filter: rule ids fired per candidate label (Development)

| label | rule | count |
|---|---|---|
| generic | G8 | 43 |
| irrelevant | G8 | 39 |
| irrelevant | pass | 4 |
| relevant | G8 | 51 |
| relevant | pass | 35 |
| violates_constraint | G8 | 29 |
| violates_constraint | pass | 14 |


### Live Solution Box schema, blueprint elements (schema read of `brain_docs.BoxDraft`)

| element | field in the live draft schema |
|---|---|
| steps | phases |
| dependencies | none |
| resources | needs |
| success_criteria | none |

`phases` holds short phase names and `needs` a short list of what the owner must provide; the schema has no
field for dependencies between steps or for success criteria.

## 4. Facts read from the tables

- Problems found through the live extraction path: 85/86 (one Arabic case missed one).
- Limits, things tried and owner-said causes: 0 kept in every group (constraints 0/157, tried 0/43, owner
  cause 0/43) because `SimpleNote` has no field for them. With the fields added back from the reference notes
  (`_reference`): tried 43/43, owner cause 41/43, limits 69/157 (limits said in turn 3 are outside the reference
  notes).
- Stated owner phrases found in the saved records: 40/143 live, 100/143 reference.
- Figure corrections detected by the live finder: 31/43. English 9/9 and Roman Urdu 9/9 (cells below n=10 print
  as not yet measured), Urdu 13/13, Arabic 0/12. Where detected, the corrected figure replaced the old one in the
  saved record in every case (correction applied 31/43 = detected).
- A guessed cause stays a hypothesis in `merge_cause`: 171/172.
- Limit-violating candidate ideas: the relevance scorer missed 2/43 (both Arabic). The live idea filter rejected
  29/43, every one by rule G8 (the idea shares no word with the noted problems); 0/43 were rejected by a rule
  that reads a stated limit (the filter has no input for one). G8 also rejected 51/86 relevant ideas: Urdu 26/26 and
  Arabic 24/24 relevant ideas rejected, English 0/18, Roman Urdu 1/18.
- Reference pi replies (hand-written): language detected as the case language 129/129; repeated question
  0/129; unclassified question 3/129; one-question form 127/129. Reference blueprint element kinds present 172/172
  checks; steps flagged as breaking a stated limit by the relevance scorer 13/258. These score hand-written text.

## 5. Case id to split table (Held-out ids are listed and never scored)

| case id | split |
|---|---|
| ps_banquet_ar | development |
| ps_banquet_en | held_out |
| ps_banquet_roman_ur | held_out |
| ps_banquet_ur | development |
| ps_bookings_ar | development |
| ps_bookings_en | development |
| ps_bookings_roman_ur | development |
| ps_bookings_ur | development |
| ps_clinic_reception_ar | held_out |
| ps_clinic_reception_en | development |
| ps_clinic_reception_roman_ur | development |
| ps_clinic_reception_ur | development |
| ps_dropship_ar | development |
| ps_dropship_en | development |
| ps_dropship_roman_ur | development |
| ps_dropship_ur | held_out |
| ps_ecommerce_ar | development |
| ps_ecommerce_en | development |
| ps_ecommerce_roman_ur | held_out |
| ps_ecommerce_ur | development |
| ps_gym_ar | development |
| ps_gym_en | development |
| ps_gym_roman_ur | held_out |
| ps_gym_ur | development |
| ps_pharmacy_ar | held_out |
| ps_pharmacy_en | held_out |
| ps_pharmacy_roman_ur | development |
| ps_pharmacy_ur | development |
| ps_poultry_ar | development |
| ps_poultry_en | development |
| ps_poultry_roman_ur | development |
| ps_poultry_ur | development |
| ps_rental_mgmt_ar | development |
| ps_rental_mgmt_en | held_out |
| ps_rental_mgmt_roman_ur | development |
| ps_rental_mgmt_ur | held_out |
| ps_repair_shop_ar | held_out |
| ps_repair_shop_en | held_out |
| ps_repair_shop_roman_ur | development |
| ps_repair_shop_ur | development |
| ps_restaurant_ar | development |
| ps_restaurant_en | development |
| ps_restaurant_roman_ur | development |
| ps_restaurant_ur | development |
| ps_salon_ar | development |
| ps_salon_en | held_out |
| ps_salon_roman_ur | held_out |
| ps_salon_ur | development |
| ps_school_ar | development |
| ps_school_en | development |
| ps_school_roman_ur | held_out |
| ps_school_ur | development |
| ps_trucking_ar | development |
| ps_trucking_en | development |
| ps_trucking_roman_ur | held_out |
| ps_trucking_ur | development |
| ps_wedding_ar | development |
| ps_wedding_en | held_out |
| ps_wedding_roman_ur | development |
| ps_wedding_ur | development |
