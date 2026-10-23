"""Trade words in Arabic and Urdu script, so a person who writes in those scripts gets an industry.

The packs hold English and Roman Urdu signal words. In the specification PDF the Arabic and Urdu
glosses are stored as reversed glyphs that cannot be read back, so none of them reached the packs,
and a message such as "عندنا مطعم في دبي" (golden G8) matched no industry at all. This file adds the
plain, everyday word for each of the most common trades, as a hint for `industry_packs.detect`
only (the same rules apply: an explicit statement, or two different terms).

Written by hand, not taken from the specification: the Workzap team's native Arabic and Urdu
speakers should review it, the same as the Roman Urdu lines. A wrong word here can only fail to
help or point at the wrong pack; it can never change a rule.
"""

TRADE_WORDS: dict[str, tuple[str, ...]] = {
    "restaurants": (
        "مطعم",
        "مطاعم",
        "ریسٹورنٹ",
        "ریستوران",
    ),
    "cafes_and_coffee_shops": (
        "مقهى",
        "كافيه",
        "كوفي شوب",
        "کیفے",
    ),
    "bakeries_mithai_and_confectionery": (
        "مخبز",
        "مخابز",
        "حلويات",
        "بیکری",
        "مٹھائی",
    ),
    "pharmacies_and_medical_stores": (
        "صيدلية",
        "صيدليات",
        "فارمیسی",
        "میڈیکل اسٹور",
    ),
    "clinics_and_gp_practices": (
        "عيادة",
        "عيادات",
        "کلینک",
    ),
    "dental_clinics": (
        "عيادة اسنان",
        "طبيب اسنان",
        "ڈینٹل",
        "دانتوں کا کلینک",
    ),
    "hospitals": (
        "مستشفى",
        "ہسپتال",
        "اسپتال",
    ),
    "hotels": (
        "فندق",
        "فنادق",
        "ہوٹل",
    ),
    "supermarkets_and_hypermarkets": (
        "سوبر ماركت",
        "سوبرماركت",
        "هايبرماركت",
        "سپر مارکیٹ",
    ),
    "kiryana_corner_shops_and_convenience_stores": (
        "بقالة",
        "كريانه",
        "کریانہ",
    ),
    "salons_and_barbers": (
        "صالون",
        "حلاق",
        "صالون تجميل",
        "سیلون",
        "بیوٹی پارلر",
        "حجام",
    ),
    "gyms_and_fitness_studios": (
        "نادي رياضي",
        "صالة رياضية",
        "جيم",
    ),
    "private_schools_and_school_chains": (
        "مدرسه",
        "مدارس",
        "سکول",
        "اسکول",
    ),
    "daycare_nurseries_and_preschools": (
        "حضانة",
        "دار حضانة",
    ),
    "colleges_and_universities": (
        "جامعة",
        "کالج",
        "یونیورسٹی",
    ),
    "tuition_centres_and_academies": (
        "دروس خصوصية",
        "سنتر تعليمي",
        "ٹیوشن",
        "اکیڈمی",
    ),
    "law_firms": (
        "مكتب محاماة",
        "محاماة",
        "محامي",
        "وکیل",
        "وکالت",
    ),
    "accounting_audit_and_tax_practices": (
        "مكتب محاسبة",
        "محاسبة",
        "اکاؤنٹنٹ",
        "ٹیکس کنسلٹنٹ",
    ),
    "real_estate_agencies_and_brokers": (
        "عقارات",
        "مكتب عقارات",
        "وسيط عقاري",
        "پراپرٹی ڈیلر",
        "رئیل اسٹیٹ",
    ),
    "property_developers": (
        "مطور عقاري",
        "تطوير عقاري",
        "پراپرٹی ڈیولپر",
    ),
    "car_rental_and_chauffeur_services": (
        "تاجير سيارات",
        "ايجار سيارات",
        "رینٹ اے کار",
    ),
    "used_car_dealers": (
        "سيارات مستعمله",
        "معرض سيارات مستعمله",
        "استعمال شدہ گاڑیاں",
    ),
    "new_car_dealerships_and_showrooms": (
        "وكاله سيارات",
        "معرض سيارات",
        "گاڑیوں کا شو روم",
        "شو روم",
    ),
    "auto_workshops_and_service_centres": (
        "ورشه سيارات",
        "كراج",
        "گاڑیوں کی ورکشاپ",
        "ورکشاپ",
    ),
    "car_wash_and_detailing": (
        "مغسله سيارات",
        "غسيل سيارات",
        "کار واش",
    ),
    "tyre_battery_and_auto_parts_shops": (
        "اطارات",
        "بطاريات",
        "قطع غيار سيارات",
        "ٹائر",
    ),
    "jewellery": (
        "مجوهرات",
        "صائغ",
        "جیولری",
        "زیورات",
        "سنار",
    ),
    "perfumes_attar_and_oud": (
        "عطور",
        "عطر",
    ),
    "florists_and_gifting": (
        "زهور",
        "محل ورد",
        "پھولوں کی دکان",
    ),
    "fashion_and_apparel_brands": (
        "ازياء",
        "ماركه ملابس",
        "گارمنٹس برانڈ",
    ),
    "tailoring_and_alteration_shops": (
        "خياط",
        "خياطه",
        "مشغل خياطه",
        "درزی",
        "ٹیلرنگ",
    ),
    "laundry_and_dry_cleaning": (
        "مغسله ملابس",
        "دراي كلين",
        "لانڈری",
        "ڈرائی کلین",
    ),
    "cleaning_and_janitorial_companies": (
        "شركه تنظيف",
        "نظافه",
        "صفائی کی کمپنی",
    ),
    "security_guard_companies": (
        "شركه حراسه",
        "حراسه امنيه",
        "سیکیورٹی گارڈ",
    ),
    "travel_agencies_and_ticketing": (
        "وكاله سفر",
        "مكتب سفريات",
        "ٹریول ایجنسی",
    ),
    "tour_operators_and_dmcs": (
        "شركه سياحه",
        "مكتب سياحه",
        "ٹور آپریٹر",
    ),
    "courier_and_last_mile_delivery_companies": (
        "شركه توصيل",
        "توصيل طلبات",
        "كورير",
        "کوریئر",
    ),
    "customs_clearing_agents": (
        "تخليص جمركي",
        "مخلص جمركي",
        "کسٹم کلیئرنگ",
    ),
    "trucking_and_goods_transport_companies": (
        "نقل بضائع",
        "شاحنات",
        "ٹرانسپورٹ کمپنی",
        "ٹرکوں کا کاروبار",
    ),
    "movers_and_relocation_companies": (
        "نقل اثاث",
        "شركه نقل عفش",
        "شفٹنگ",
    ),
    "warehousing_and_3pl": (
        "مستودع",
        "مستودعات",
        "گودام",
    ),
    "general_contractors": (
        "مقاولات",
        "مقاول",
        "ٹھیکیدار",
    ),
    "interior_design_and_fit_out": (
        "ديكور",
        "تصميم داخلي",
        "انٹیریئر ڈیزائن",
    ),
    "electrical_goods": (
        "كهربائيات",
        "ادوات كهربائيه",
        "الیکٹرک کا سامان",
    ),
    "electronics_and_home_appliances_retail": (
        "اجهزه منزليه",
        "الكترونيات",
        "گھریلو آلات",
    ),
    "mobile_phones_and_accessories": (
        "جوالات",
        "هواتف",
        "موبائل کی دکان",
        "موبائل شاپ",
    ),
    "computers_laptops_and_it_hardware_shops": (
        "کمپیوٹر کی دکان",
        "محل كمبيوتر",
    ),
    "it_services_and_software_houses": (
        "شركه برمجيات",
        "برمجه",
        "سافٹ ویئر ہاؤس",
    ),
    "marketing_creative_and_digital_agencies": (
        "وكاله تسويق",
        "تسويق رقمي",
        "مارکیٹنگ ایجنسی",
    ),
    "photography_and_videography_studios": (
        "استوديو تصوير",
        "فوٹوگرافی",
        "فوٹو سٹوڈیو",
    ),
    "printing_presses_and_print_on_demand": (
        "مطبعه",
        "طباعه",
        "پرنٹنگ پریس",
        "پرنٹنگ",
    ),
    "books_stationery_and_school_supplies": (
        "مكتبه",
        "قرطاسيه",
        "سٹیشنری",
        "کتابوں کی دکان",
    ),
    "pet_shops_and_pet_supplies": (
        "حيوانات اليفه",
        "محل حيوانات",
        "پالتو جانور",
    ),
    "veterinary_clinics_and_animal_health_suppliers": (
        "بيطري",
        "عياده بيطريه",
        "جانوروں کا ڈاکٹر",
        "ویٹرنری",
        "بيطريه",
    ),
    "crop_farming": (
        "مزرعه",
        "مزارع",
        "زراعه",
        "کھیتی",
        "زراعت",
    ),
    "poultry_farms": (
        "دواجن",
        "مزرعه دجاج",
        "پولٹری",
        "مرغی فارم",
    ),
    "cattle_and_buffalo_dairy_farms": (
        "مزرعه البان",
        "ڈیری فارم",
        "بھینسوں کا فارم",
    ),
    "camel_farms": (
        "مزرعه ابل",
        "اونٹوں کا فارم",
    ),
    "seafood_and_fish_markets": (
        "اسماك",
        "سوق السمك",
        "مچھلی کی دکان",
    ),
    "meat_shops_and_butchers": (
        "ملحمه",
        "جزار",
        "لحام",
        "قصائی",
        "گوشت کی دکان",
    ),
    "flour_rice_and_feed_mills": (
        "مطحنه",
        "آٹا چکی",
        "فلور مل",
        "رائس مل",
    ),
    "juice_shakes_dessert_and_ice_cream_parlours": (
        "عصير",
        "ايس كريم",
        "جوس کارنر",
        "آئس کریم",
    ),
    "catering_and_event_food": (
        "تموين",
        "ضيافه",
        "كاترينغ",
        "کیٹرنگ",
    ),
    "banquet_halls_and_marquees": (
        "قاعه افراح",
        "قاعات",
        "شادی ہال",
        "میرج ہال",
    ),
    "wedding_planners_and_event_management": (
        "تنظيم حفلات",
        "منسق زفاف",
        "ایونٹ مینجمنٹ",
    ),
    "hajj_and_umrah_operators": (
        "حج",
        "حملات حج وعمره",
        "حج وعمره",
        "حج اور عمره",
    ),
    "money_exchange_and_remittance_agents": (
        "صرافه",
        "تحويل اموال",
        "منی چینجر",
        "کرنسی ایکسچینج",
    ),
    "insurance_agencies_and_brokers": (
        "وكيل تامين",
        "انشورنس",
        "شركه تامين",
    ),
    "solar_epc_and_installers": (
        "طاقه شمسيه",
        "الواح شمسيه",
        "سولر",
    ),
    "hvac_ac_sales_installation_and_service": (
        "تكييف",
        "مكيفات",
        "ایئر کنڈیشنر",
        "اے سی",
    ),
    "pest_control": (
        "مكافحه حشرات",
        "پیسٹ کنٹرول",
    ),
    "spas_and_wellness_centres": (
        "مركز استجمام",
        "اسپا",
    ),
    "cinemas_and_theatres": (
        "سينما",
        "سنیما",
    ),
    "yacht_and_boat_charters": (
        "يخوت",
        "قوارب",
    ),
    "fuel_stations_and_lpg_cng_distributors": (
        "محطه وقود",
        "محطه بنزين",
        "پٹرول پمپ",
    ),
    "medical_equipment_and_device_distributors": (
        "معدات طبيه",
        "طبی آلات",
    ),
    "diagnostic_labs_and_sample_collection_centres": (
        "مختبر",
        "مختبرات",
        "ڈائیگناسٹک لیب",
        "لیبارٹری",
    ),
    "radiology_and_imaging_centres": (
        "اشعه",
        "مركز اشعه",
        "ایکس رے",
    ),
    "physiotherapy_and_rehabilitation": (
        "علاج طبيعي",
        "فزیو تھراپی",
    ),
    "elderly_care_homes": (
        "دار مسنين",
        "رعايه المسنين",
        "بزرگوں کا گھر",
    ),
    "ambulance_and_patient_transport_services": (
        "ايمبولانس",
        "ایمبولینس",
    ),
    "driving_schools": (
        "تعليم قياده",
        "مدرسه قياده",
        "ڈرائیونگ سکول",
    ),
    "language_centres": (
        "مركز لغات",
        "معهد لغات",
        "لینگویج سینٹر",
    ),
    "study_abroad_and_education_consultants": (
        "دراسه بالخارج",
        "استشارات تعليميه",
        "سٹڈی ابروڈ",
    ),
    "steel_re_rolling_mills_and_metal_fabrication": (
        "مصنع حديد",
        "تشكيل معادن",
        "سریا",
        "اسٹیل ملز",
    ),
    "tiles_marble_and_bathroom_kitchen_showrooms": (
        "سيراميك",
        "رخام",
        "ٹائلز",
        "ماربل",
        "محل بلاط",
    ),
    "furniture_and_home_decor_retail": (
        "معرض اثاث",
        "فرنیچر",
    ),
    "carpets_handicrafts_and_artisan_workshops": (
        "سجاد",
        "حرف يدويه",
        "قالین",
    ),
    "footwear_retail": (
        "احذيه",
        "محل احذيه",
        "جوتوں کی دکان",
    ),
    "garment_and_knitwear_export_units": (
        "مصنع ملابس",
        "مصنع ملابس جاهزه",
        "گارمنٹس فیکٹری",
        "گارمنٹس",
    ),
    "textile_spinning_and_weaving_mills": (
        "مصنع نسيج",
        "مغزل",
        "ٹیکسٹائل مل",
        "اسپننگ مل",
    ),
    "unstitched_fabric_lawn_and_textile_retail": (
        "اقمشه",
        "محل اقمشه",
        "کپڑے کی دکان",
        "لان",
    ),
    "plastics_and_injection_moulding": (
        "مصنع بلاستيك",
        "بلاستيك",
        "پلاسٹک فیکٹری",
    ),
    "packaging_and_corrugation": (
        "تغليف",
        "مصنع تغليف",
        "پیکجنگ",
    ),
    "chemicals_paints_and_coatings": (
        "دهانات",
        "مصنع دهانات",
        "رنگ کی فیکٹری",
    ),
    "hardware_paint_sanitary_and_building_materials_shops": (
        "مواد بناء",
        "ادوات صحيه",
        "ہارڈویئر",
    ),
    "cement_blocks_pavers_and_precast": (
        "اسمنت",
        "بلوك",
        "سیمنٹ",
        "بلاکس",
    ),
    "beverage_juice_and_water_bottling_plants": (
        "تعبئه مياه",
        "مصنع مياه",
        "منرل واٹر",
    ),
    "cold_storage_operators": (
        "تخزين مبرد",
        "مخزن مبرد",
        "کولڈ سٹوریج",
    ),
    "generator_sales_rental_and_service": (
        "مولدات",
        "مولد كهرباء",
        "جنریٹر",
    ),
    "electricity_and_power_contractors": (
        "مقاول كهرباء",
        "كهربائي",
        "الیکٹریشن",
    ),
    "funeral_services_and_graveyard_administration": (
        "خدمات جنائز",
        "كفن ودفن",
        "کفن دفن",
    ),
    "quran_academies_and_madrassas": (
        "مدرسه تحفيظ",
        "تحفيظ القران",
        "مدرسہ",
        "قرآن اکیڈمی",
    ),
    "ngos_charities_and_trusts": (
        "جمعيه خيريه",
        "منظمه غير ربحيه",
        "این جی او",
        "فلاحی ادارہ",
    ),
    "internet_service_providers_and_cable_tv_operators": (
        "مزود انترنت",
        "انٹرنیٹ سروس",
        "کیبل نیٹ ورک",
    ),
    "call_centres_and_bpos": (
        "مركز اتصال",
        "كول سنتر",
        "کال سینٹر",
    ),
    "freelancers_solopreneurs_and_home_based_businesses": (
        "عمل حر",
        "فريلانسر",
        "فری لانسر",
    ),
    "dropshipping_and_social_commerce_sellers": (
        "دروب شيبنج",
        "ڈراپ شپنگ",
    ),
    "tractor_and_farm_machinery_dealers_and_rental": (
        "جرارات",
        "معدات زراعيه",
        "ٹریکٹر",
    ),
    "seed_fertiliser_and_pesticide_dealers": (
        "بذور",
        "اسمده",
        "مبيدات",
        "کھاد",
        "بیج اور کھاد",
    ),
    "sugar_mills_and_cotton_ginning": (
        "مصنع سكر",
        "شوگر مل",
        "جننگ فیکٹری",
    ),
    "motorcycle_and_rickshaw_dealers_and_workshops": (
        "دراجات ناريه",
        "موٹر سائیکل",
        "رکشہ",
    ),
    "mobile_wallet_and_payment_agents": (
        "ایزی پیسہ ایجنٹ",
        "جاز کیش ایجنٹ",
    ),
    "microfinance_field_operations": (
        "تمويل اصغر",
        "مائیکرو فنانس",
    ),
    "mental_health_and_therapy_practices": (
        "عياده نفسيه",
        "طبيب نفسي",
        "معالج نفسي",
        "ماہر نفسیات",
        "نفسیاتی کلینک",
    ),
    "fertility_and_ivf_clinics": (
        "عياده خصوبه",
        "علاج العقم",
        "آئی وی ایف",
        "بانجھ پن کا علاج",
    ),
    "aesthetic_and_dermatology_clinics": (
        "عياده جلديه",
        "عياده تجميل",
        "جلد کا کلینک",
        "ڈرمیٹولوجی",
    ),
    "home_healthcare_and_nursing_agencies": (
        "رعايه صحيه منزليه",
        "ممرضه منزليه",
        "نرسنگ ایجنسی",
    ),
    "pharmaceutical_manufacturing": (
        "مصنع ادويه",
        "شركه ادويه",
        "دوا ساز کمپنی",
    ),
}
