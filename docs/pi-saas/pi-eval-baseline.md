# pi understanding: scripted baseline

Scripted replay: hand-written reference notes (not model output) go through the real
extraction path, no model call. A high score here proves the code keeps what a good model
returns; it says nothing about the model. The real-model run needs owner approval.
Groups under 3 cases are reported as not yet measured.

## Split

| group | cases | problem recall | precision | figures kept | corrections kept | unsupported causes |
|---|---|---|---|---|---|---|
| development | 69 | 100% | 100% | 100% | 100% | 0 |
| held_out | 60 | 100% | 100% | 100% | 100% | 0 |
| regression | 3 | 100% | 100% | 100% | 100% | 0 |

## Language

| group | cases | problem recall | precision | figures kept | corrections kept | unsupported causes |
|---|---|---|---|---|---|---|
| ar | 12 | 100% | 100% | 100% | 100% | 0 |
| en | 52 | 100% | 100% | 100% | 100% | 0 |
| hi | 8 | 100% | 100% | 100% | 100% | 0 |
| roman_ur | 41 | 100% | 100% | 100% | 100% | 0 |
| ur | 19 | 100% | 100% | 100% | 100% | 0 |

## Case kind

| group | cases | problem recall | precision | figures kept | corrections kept | unsupported causes |
|---|---|---|---|---|---|---|
| constraints | 9 | 100% | 100% | 100% | n/a | 0 |
| correction | 18 | 100% | 100% | 100% | 100% | 0 |
| list | 37 | 100% | 100% | 100% | n/a | 0 |
| mixed | 7 | 100% | 100% | 100% | n/a | 0 |
| multi_turn | 9 | 100% | 100% | 100% | n/a | 0 |
| rant | 10 | 100% | 100% | 100% | n/a | 0 |
| single | 42 | 100% | 100% | 100% | n/a | 0 |

## Industry

| group | cases | problem recall | precision | figures kept | corrections kept | unsupported causes |
|---|---|---|---|---|---|---|
| accounting_audit_and_tax_practices | 3 | 100% | 100% | 100% | 100% | 0 |
| aesthetic_and_dermatology_clinics | 3 | 100% | 100% | 100% | n/a | 0 |
| air_cargo_and_air_freight_agents | 1 | not yet measured | | | | |
| auto_workshops_and_service_centres | 1 | not yet measured | | | | |
| bakeries_mithai_and_confectionery | 1 | not yet measured | | | | |
| banquet_halls_and_marquees | 1 | not yet measured | | | | |
| beef_cattle_fattening_and_feedlots | 3 | 100% | 100% | 100% | 100% | 0 |
| beekeeping_and_honey | 3 | 100% | 100% | 100% | n/a | 0 |
| books_stationery_and_school_supplies | 1 | not yet measured | | | | |
| cafes_and_coffee_shops | 1 | not yet measured | | | | |
| car_rental_and_chauffeur_services | 1 | not yet measured | | | | |
| car_wash_and_detailing | 1 | not yet measured | | | | |
| carpets_handicrafts_and_artisan_workshops | 1 | not yet measured | | | | |
| cattle_and_buffalo_dairy_farms | 1 | not yet measured | | | | |
| cinemas_and_theatres | 1 | not yet measured | | | | |
| cleaning_and_janitorial_companies | 1 | not yet measured | | | | |
| clinics_and_gp_practices | 3 | 100% | 100% | 100% | n/a | 0 |
| cold_storage_operators | 1 | not yet measured | | | | |
| colleges_and_universities | 1 | not yet measured | | | | |
| courier_and_last_mile_delivery_companies | 3 | 100% | 100% | 100% | n/a | 0 |
| dairy_processing | 3 | 100% | 100% | 100% | n/a | 0 |
| daycare_nurseries_and_preschools | 1 | not yet measured | | | | |
| dental_clinics | 1 | not yet measured | | | | |
| dhabas_food_trucks_chai_stalls_and_street_food | 1 | not yet measured | | | | |
| driving_schools | 1 | not yet measured | | | | |
| e_commerce_and_d2c_brands | 1 | not yet measured | | | | |
| electrical_goods | 1 | not yet measured | | | | |
| electronics_and_home_appliances_retail | 1 | not yet measured | | | | |
| florists_and_gifting | 1 | not yet measured | | | | |
| flour_rice_and_feed_mills | 1 | not yet measured | | | | |
| footwear_retail | 1 | not yet measured | | | | |
| freight_forwarders | 1 | not yet measured | | | | |
| fuel_stations_and_lpg_cng_distributors | 1 | not yet measured | | | | |
| furniture_manufacturing_and_woodwork | 1 | not yet measured | | | | |
| garment_and_knitwear_export_units | 3 | 100% | 100% | 100% | 100% | 0 |
| general_contractors | 1 | not yet measured | | | | |
| guest_houses_b_and_bs_and_holiday_home_hosts | 1 | not yet measured | | | | |
| gyms_and_fitness_studios | 3 | 100% | 100% | 100% | n/a | 0 |
| hajj_and_umrah_operators | 1 | not yet measured | | | | |
| hardware_paint_sanitary_and_building_materials_shops | 3 | 100% | 100% | 100% | n/a | 0 |
| hospitals | 1 | not yet measured | | | | |
| hotels | 1 | not yet measured | | | | |
| hr_and_recruitment_agencies | 1 | not yet measured | | | | |
| insurance_agencies_and_brokers | 1 | not yet measured | | | | |
| internet_service_providers_and_cable_tv_operators | 3 | 100% | 100% | 100% | 100% | 0 |
| jewellery | 1 | not yet measured | | | | |
| kiryana_corner_shops_and_convenience_stores | 3 | 100% | 100% | 100% | n/a | 0 |
| laundry_and_dry_cleaning | 1 | not yet measured | | | | |
| law_firms | 1 | not yet measured | | | | |
| meat_shops_and_butchers | 1 | not yet measured | | | | |
| milk_collection_centres_and_chillers | 1 | not yet measured | | | | |
| mobile_phones_and_accessories | 1 | not yet measured | | | | |
| mosques_religious_trusts_and_community_institutions | 3 | 100% | 100% | 100% | n/a | 0 |
| new_car_dealerships_and_showrooms | 3 | 100% | 100% | 100% | n/a | 0 |
| orchards | 1 | not yet measured | | | | |
| packaging_and_corrugation | 1 | not yet measured | | | | |
| perfumes_attar_and_oud | 1 | not yet measured | | | | |
| pest_control | 1 | not yet measured | | | | |
| pet_shops_and_pet_supplies | 1 | not yet measured | | | | |
| pharmaceutical_manufacturing | 3 | 100% | 100% | 100% | n/a | 0 |
| pharmacies_and_medical_stores | 3 | 100% | 100% | 100% | 100% | 0 |
| photography_and_videography_studios | 1 | not yet measured | | | | |
| poultry_farms | 1 | not yet measured | | | | |
| printing_presses_and_print_on_demand | 1 | not yet measured | | | | |
| private_schools_and_school_chains | 1 | not yet measured | | | | |
| quran_academies_and_madrassas | 1 | not yet measured | | | | |
| real_estate_agencies_and_brokers | 3 | 100% | 100% | 100% | 100% | 0 |
| restaurants | 3 | 100% | 100% | 100% | 100% | 0 |
| salons_and_barbers | 3 | 100% | 100% | 100% | n/a | 0 |
| security_guard_companies | 1 | not yet measured | | | | |
| seed_fertiliser_and_pesticide_dealers | 1 | not yet measured | | | | |
| solar_epc_and_installers | 1 | not yet measured | | | | |
| spices_dry_fruit_and_nuts_traders | 1 | not yet measured | | | | |
| startups_and_early_stage_businesses | 1 | not yet measured | | | | |
| tailoring_and_alteration_shops | 1 | not yet measured | | | | |
| textile_spinning_and_weaving_mills | 1 | not yet measured | | | | |
| tiles_marble_and_bathroom_kitchen_showrooms | 3 | 100% | 100% | 100% | n/a | 0 |
| tractor_and_farm_machinery_dealers_and_rental | 1 | not yet measured | | | | |
| travel_agencies_and_ticketing | 1 | not yet measured | | | | |
| trucking_and_goods_transport_companies | 1 | not yet measured | | | | |
| tuition_centres_and_academies | 1 | not yet measured | | | | |
| tyre_battery_and_auto_parts_shops | 1 | not yet measured | | | | |
| unknown_business_owner | 4 | 100% | 100% | 100% | 100% | 0 |
| veterinary_clinics_and_animal_health_suppliers | 1 | not yet measured | | | | |
| warehousing_and_3pl | 1 | not yet measured | | | | |
| watches_eyewear_and_opticians | 1 | not yet measured | | | | |
| water_tanker_and_ro_filtration_plant_operators | 1 | not yet measured | | | | |
| wedding_planners_and_event_management | 1 | not yet measured | | | | |
| wholesale_market_traders | 1 | not yet measured | | | | |

## Cases that missed something

