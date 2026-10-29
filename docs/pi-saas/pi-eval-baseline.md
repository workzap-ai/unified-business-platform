# pi understanding: scripted baseline

Scripted replay: hand-written reference notes (not model output) go through the real
extraction path, no model call. A high score here proves the code keeps what a good model
returns; it says nothing about the model. The real-model run needs owner approval.
Groups under 3 cases are reported as not yet measured.

## Split

| group | cases | problem recall | precision | figures kept | corrections kept | unsupported causes |
|---|---|---|---|---|---|---|
| development | 39 | 100% | 100% | 100% | 100% | 0 |
| held_out | 21 | 100% | 100% | 100% | 100% | 0 |
| regression | 3 | 100% | 100% | 100% | 100% | 0 |

## Language

| group | cases | problem recall | precision | figures kept | corrections kept | unsupported causes |
|---|---|---|---|---|---|---|
| en | 34 | 100% | 100% | 100% | 100% | 0 |
| roman_ur | 24 | 100% | 100% | 100% | 100% | 0 |
| ur | 5 | 100% | 100% | n/a | n/a | 0 |

## Case kind

| group | cases | problem recall | precision | figures kept | corrections kept | unsupported causes |
|---|---|---|---|---|---|---|
| correction | 8 | 100% | 100% | 100% | 100% | 0 |
| list | 22 | 100% | 100% | 100% | n/a | 0 |
| mixed | 2 | not yet measured | | | | |
| multi_turn | 3 | 100% | 100% | 100% | n/a | 0 |
| rant | 3 | 100% | 100% | 100% | n/a | 0 |
| single | 25 | 100% | 100% | 100% | n/a | 0 |

## Industry

| group | cases | problem recall | precision | figures kept | corrections kept | unsupported causes |
|---|---|---|---|---|---|---|
| accounting_audit_and_tax_practices | 3 | 100% | 100% | 100% | 100% | 0 |
| aesthetic_and_dermatology_clinics | 3 | 100% | 100% | 100% | n/a | 0 |
| beef_cattle_fattening_and_feedlots | 3 | 100% | 100% | 100% | 100% | 0 |
| beekeeping_and_honey | 3 | 100% | 100% | 100% | n/a | 0 |
| clinics_and_gp_practices | 3 | 100% | 100% | 100% | n/a | 0 |
| courier_and_last_mile_delivery_companies | 3 | 100% | 100% | 100% | n/a | 0 |
| dairy_processing | 3 | 100% | 100% | 100% | n/a | 0 |
| garment_and_knitwear_export_units | 3 | 100% | 100% | 100% | 100% | 0 |
| gyms_and_fitness_studios | 3 | 100% | 100% | 100% | n/a | 0 |
| hardware_paint_sanitary_and_building_materials_shops | 3 | 100% | 100% | 100% | n/a | 0 |
| internet_service_providers_and_cable_tv_operators | 3 | 100% | 100% | 100% | 100% | 0 |
| kiryana_corner_shops_and_convenience_stores | 3 | 100% | 100% | 100% | n/a | 0 |
| mosques_religious_trusts_and_community_institutions | 3 | 100% | 100% | 100% | n/a | 0 |
| new_car_dealerships_and_showrooms | 3 | 100% | 100% | 100% | n/a | 0 |
| pharmaceutical_manufacturing | 3 | 100% | 100% | 100% | n/a | 0 |
| pharmacies_and_medical_stores | 3 | 100% | 100% | 100% | 100% | 0 |
| real_estate_agencies_and_brokers | 3 | 100% | 100% | 100% | 100% | 0 |
| restaurants | 3 | 100% | 100% | 100% | 100% | 0 |
| salons_and_barbers | 3 | 100% | 100% | 100% | n/a | 0 |
| tiles_marble_and_bathroom_kitchen_showrooms | 3 | 100% | 100% | 100% | n/a | 0 |
| unknown_business_owner | 3 | 100% | 100% | 100% | 100% | 0 |

## Cases that missed something

