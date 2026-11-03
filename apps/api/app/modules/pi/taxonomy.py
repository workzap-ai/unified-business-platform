# ruff: noqa: E501  (the taxonomy tables read better on one line each)
"""The master problem taxonomy and severity scoring (pi Brain spec, Part 4.4 to 4.7).

Categories are stable (changing one is a code change). Sub-types here are the master list;
industry packs may add their own (snake_case), which are kept as written. Labels in Urdu and
Arabic come from the spec and still need a native-speaker review before launch (spec 2.5.1).
"""

import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Category:
    key: str
    en: str
    roman_ur: str
    ur: str
    ar: str
    subtypes: tuple[str, ...]


def _c(key: str, en: str, roman_ur: str, ur: str, ar: str, subtypes: str) -> Category:
    return Category(key, en, roman_ur, ur, ar, tuple(subtypes.split()))


CATEGORIES: tuple[Category, ...] = (
    _c("stock_inventory", "Stock", "Maal", "اسٹاک", "المخزون",
       "stockout overstock_dead_stock overstock_ageing shrinkage_theft count_mismatch transfers_lost expiry_wastage "
       "wrong_location slow_replenishment no_visibility returns_handling serial_batch_tracking "
       "raw_material_shortage"),
    _c("sales_revenue", "Sales", "Bikri", "سیل", "المبيعات",
       "sales_drop clearance branch_underperforming target_missed seasonal_dip conversion_low basket_small "
       "pricing_errors discount_abuse salesforce_performance no_sales_visibility channel_conflict"),
    _c("cash_collections", "Cash & payments", "Paisa aur wusooli", "نقد", "النقد والتحصيل",
       "cash_mismatch receivables_late credit_customers cash_handling_risk deposit_delays "
       "payment_methods cash_flow_tight supplier_payments_late petty_cash refunds cod_remittance"),
    _c("margin_cost", "Margin & costs", "Munafa aur kharcha", "منافع", "الهامش والتكاليف",
       "margin_unknown margin_shrinking cost_overruns wastage_cost utility_costs rent freight_costs "
       "price_increases_supplier currency_exposure hidden_costs"),
    _c("customers_retention", "Customers", "Gahak", "گاہک", "العملاء",
       "repeat_low complaints reviews_bad no_customer_data slow_response service_quality loyalty "
       "churn_subscription customer_communication after_sales"),
    _c("marketing_leads", "Marketing & leads", "Ishtehaar aur naye gahak", "مارکیٹنگ", "التسويق",
       "few_leads lead_quality ad_spend_waste no_tracking social_media_inconsistent brand_awareness "
       "lead_followup_slow campaign_roi_unknown website_issues marketplace_visibility"),
    _c("orders_fulfilment", "Orders & delivery", "Order aur delivery", "آرڈر", "الطلبات والتوصيل",
       "orders_lost order_errors delivery_late delivery_cost rider_management returns_rto "
       "order_tracking packing_errors multi_channel_orders pre_orders_custom"),
    _c("suppliers_purchasing", "Suppliers & buying", "Supplier aur khareed", "سپلائر",
       "الموردون والمشتريات",
       "supplier_late supplier_quality po_tracking buying_wrong_items price_comparison "
       "import_delays minimum_orders supplier_communication credit_terms"),
    _c("people_staff", "Staff", "Staff", "عملہ", "الموظفون",
       "attendance_lateness turnover hiring_difficulty training performance_unknown accountability "
       "payroll_errors shift_scheduling commission_disputes communication_internal trust_honesty "
       "overtime"),
    _c("operations_process", "Operations", "Kaam ka tareeqa", "آپریشنز", "العمليات",
       "manual_work duplicate_entry bottleneck approvals_slow no_sop quality_inconsistent capacity "
       "maintenance_downtime checklists_not_done handoffs"),
    _c("reporting_visibility", "Reports & visibility", "Report aur hisaab", "رپورٹس", "التقارير",
       "reports_late reports_wrong data_scattered no_dashboard owner_blind branch_comparison "
       "kpi_undefined manual_reports"),
    _c("tech_systems", "Systems & tools", "System aur software", "سسٹم", "الأنظمة",
       "pos_issues software_not_connected outdated_system no_system system_downtime vendor_lock "
       "whatsapp_overload excel_dependency data_loss user_adoption integration_marketplace"),
    _c("quality_complaints", "Quality", "Quality", "معیار", "الجودة",
       "product_defects service_errors rework inspection_missing hygiene consistency_across_branches"),
    _c("compliance_admin", "Paperwork & compliance", "Kaghazi kaam", "دستاویزات", "الامتثال",
       "tax_filing_effort licences_renewals audits documentation contracts_tracking "
       "regulatory_reporting record_keeping"),
    _c("communication_coordination", "Coordination", "Rabta", "رابطہ", "التنسيق",
       "info_lost_in_whatsapp branches_not_aligned owner_bottleneck meetings_wasteful tasks_dropped "
       "field_team_visibility"),
    _c("loss_security", "Loss & security", "Chori aur nuksan", "نقصان", "الفقد والأمن",
       "theft_internal theft_external fraud cash_leakage cctv_gaps void_refund_abuse"),
    _c("planning_growth", "Planning & growth", "Planning", "منصوبہ بندی", "التخطيط والنمو",
       "expansion_pains forecasting budgeting_process new_branch_setup franchise_control "
       "seasonal_planning succession_family"),
    _c("customer_experience_digital", "Online presence", "Online", "آن لائن", "الحضور الرقمي",
       "website_slow_broken no_online_ordering booking_appointments chat_overload "
       "marketplace_listing app_issues"),
    _c("other", "Other", "Other", "دیگر", "أخرى", ""),
)  # fmt: skip

BY_KEY = {c.key: c for c in CATEGORIES}
KEYS = frozenset(BY_KEY)
OTHER = "other"

STATUSES = (
    "draft", "confirmed", "corrected", "merged", "split",
    "in_document", "quoted", "in_build", "resolved", "withdrawn", "parked",
)  # fmt: skip
# Problems still in play: shown in summaries and counted in groups. A parked problem (the owner
# said to leave it, Book 5 4.5) is not: it stays on the map, greyed, and can be reopened.
ACTIVE = ("draft", "confirmed", "corrected", "in_document", "quoted", "in_build")
SEVERITIES = ("low", "medium", "high", "critical", "unknown")
FREQUENCIES = ("daily", "weekly", "monthly", "seasonal", "once", "unknown")
IMPACT_TYPES = (
    "lost_sales", "lost_money", "lost_time", "customer_dissatisfaction", "stress", "other",
)  # fmt: skip
LINK_TYPES = (
    "same_root_suspected", "causes", "same_area", "duplicate_across_contacts", "blocks",
    "worsens", "competes", "same_root", "symptom_of",
)  # fmt: skip
# Who stands behind a link (spec 4.3): the owner's own words, pi's inference, or confirmed.
LINK_EVIDENCE = ("owner_said", "pi_inferred", "confirmed")
LINK_STATUSES = ("suggested", "confirmed", "rejected")

# Confidence under this means pi checks with the person before the note is confirmed.
CONFIRM_BELOW = Decimal("0.6")
# Links are only mentioned to the person at or above this confidence (spec 4.4). The same number
# as brain_config.LINK_DEFAULT (75 percent); a test pins them together.
LINK_SHOWN_AT = Decimal("0.75")


def normalise_category(key: str | None) -> str:
    """A known category key, else 'other' (which queues the problem for taxonomy review)."""
    return key if key in BY_KEY else OTHER


def label(key: str, language: str = "en") -> str:
    """The category's name in the person's language (roman_ur, ur, ar), English otherwise."""
    category = BY_KEY.get(key) or BY_KEY[OTHER]
    return {"roman_ur": category.roman_ur, "ur": category.ur, "ar": category.ar}.get(
        language, category.en
    )


def is_master_subtype(category: str, subtype: str) -> bool:
    return subtype in BY_KEY.get(category, BY_KEY[OTHER]).subtypes


# Severity (spec 4.7): impact x frequency x scope x what the person said. Internal only.
IMPACT_WEIGHT = {
    "lost_sales": Decimal(3), "customer_dissatisfaction": Decimal(3), "lost_money": Decimal(3),
    "lost_time": Decimal(2), "stress": Decimal(1), "other": Decimal(1),
}  # fmt: skip
UNKNOWN_IMPACT = Decimal("1.5")
FREQUENCY_WEIGHT = {
    "daily": Decimal(3), "weekly": Decimal("2.5"), "monthly": Decimal(2),
    "seasonal": Decimal("1.5"), "once": Decimal(1),
}  # fmt: skip
UNKNOWN_FREQUENCY = Decimal("1.5")
SCOPE_WEIGHT = {
    "all": Decimal(3),
    "most": Decimal("2.5"),
    "some": Decimal(2),
    "one": Decimal("1.5"),
}
UNKNOWN_SCOPE = Decimal("1.5")
STATED = {
    "critical": Decimal("1.5"), "high": Decimal("1.3"), "medium": Decimal(1),
    "low": Decimal("0.8"), "unknown": Decimal(1),
}  # fmt: skip


def severity_score(
    impact_types: list[str], frequency: str, scope: str, stated: str = "unknown"
) -> Decimal:
    """impact_weight x frequency_weight x scope_weight x stated_multiplier. The impact weight
    is the worst of the impact types named; nothing named means unknown."""
    impact = max((IMPACT_WEIGHT.get(t, Decimal(1)) for t in impact_types), default=UNKNOWN_IMPACT)
    return (
        impact
        * FREQUENCY_WEIGHT.get(frequency, UNKNOWN_FREQUENCY)
        * SCOPE_WEIGHT.get(scope, UNKNOWN_SCOPE)
        * STATED.get(stated, Decimal(1))
    ).quantize(Decimal("0.1"))


def severity_band(score: Decimal) -> str:
    """low / medium / high / critical from a score (the maximum possible is 40.5)."""
    if score < 6:
        return "low"
    if score < 15:
        return "medium"
    if score < 27:
        return "high"
    return "critical"


# Goal verbs (spec 7.2): what the owner wants done decides the sort, not the nouns they use.
GOAL_VERBS = (
    "sell_clear",  # sell / clear
    "know_track",  # know / track
    "avoid_running_out",
    "bring_back",
    "collect_cash",
    "get_customers",
    "cut_cost",
    "stop_loss",
    "save_time",
)


@dataclass(frozen=True)
class GoalSort:
    goal_verb: str
    category: str
    subtype: str
    secondary: tuple[str, str] | None = None  # (category, subtype)


# (pattern, sort). Checked in order, first match wins; the specific shapes come first.
_GOAL_RULES: tuple[tuple[str, GoalSort], ...] = (
    (
        r"(stock|maal|inventory|goods)\W+(\w+\W+){0,3}?(bech(na|ni|ne)|bik(ta|ti|te)?\s+nahi|clear|sell|selling|"
        r"not\s+sell|sitting|ageing|aging|purana|dead)|"
        r"(bech(na|ni|ne)|sell|clear|clearance|offload|dispose)\W+(\w+\W+){0,4}?(stock|maal|inventory|goods)",
        GoalSort(
            "sell_clear", "stock_inventory", "overstock_ageing", ("sales_revenue", "clearance")
        ),
    ),
    (
        r"maal\s+(kam|khatam|ruk)|stock\s+(kam|khatam)\s+ho|run(ning)?\s+out\s+of\s+(stock|goods|items)|"
        r"(stock|maal)\s+(runs?|ran)\s+(out|short)|out\s+of\s+stock|stock\s*out|short\s+of\s+(stock|maal)",
        GoalSort("avoid_running_out", "stock_inventory", "stockout"),
    ),
    (
        r"(stock|maal|inventory)\s+(ka\s+)?(hisaab|hisab|record|count|tracking|track|trace)|"
        r"(track|know|see|count)\s+(my\s+|our\s+|the\s+)?(stock|inventory)|"
        r"(stock|inventory)\s+(tracking|count|numbers?)\s+(is|are)?\s*(wrong|off|missing)|"
        r"(stock|maal)\s+(ka\s+)?pata\s+nahi",
        GoalSort("know_track", "stock_inventory", "no_visibility"),
    ),
    (
        r"(customers?|gahak|gaahak|clients?)\s+(\w+\s+){0,2}?(wapas|wapis|dobara|repeat|return|come\s+back)|"
        r"(bring|win|get)\s+(back\s+)?(old\s+|lost\s+)?(customers?|clients?)\s+back|"
        r"(customers?|clients?)\s+(don'?t|do\s+not|never)\s+(come\s+back|return)",
        GoalSort("bring_back", "customers_retention", "repeat_low"),
    ),
    (
        r"recovery|wusooli|wasooli|waisooli|collect\s+(my\s+|our\s+|the\s+)?(payments?|money|cash|dues)|"
        r"(payments?|paisa|paise|udhaar|udhar)\s+(\w+\s+){0,2}?(nahi\s+aa|late|stuck|pending|owed)|"
        r"unpaid\s+invoices?|customers?\s+(don'?t|do\s+not)\s+pay",
        GoalSort("collect_cash", "cash_collections", "receivables_late"),
    ),
)


def goal_sort(text: str) -> GoalSort | None:
    """The goal verb and the right sort for what the owner said, or None when no rule fits
    (the model's own category then stands). English and Roman Urdu; spec 7.2."""
    lowered = " ".join((text or "").lower().replace("’", "'").split())
    if not lowered:
        return None
    for pattern, sort in _GOAL_RULES:
        if re.search(pattern, lowered):
            return sort
    return None
