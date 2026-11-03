"""Several people from one business, the pure parts (pi Brain spec 4.9): name matching, the
sharing disclosure text, the objection regex, and can_approve following the business role."""

from uuid import uuid4

from app.modules.customers.models import Customer
from app.modules.pi import business


def _customer(**kw) -> Customer:
    defaults = {
        "name": "Ata",
        "can_approve": True,
        "business_id": None,
        "business_role": None,
        "shares_with_business": True,
        "business_disclosed_at": None,
    }
    return Customer(**{**defaults, **kw})


def test_normalize_folds_case_and_whitespace():
    assert business.normalize("  Ata   Traders ") == "ata traders"
    assert business.normalize("ATA TRADERS") == business.normalize("ata traders")


def test_can_approve_for_a_solo_customer_keeps_their_own_flag():
    assert business.can_approve_for(_customer(business_id=None, can_approve=True)) is True
    assert business.can_approve_for(_customer(business_id=None, can_approve=False)) is False


def test_can_approve_for_a_business_member_follows_the_role():
    biz_id = uuid4()
    owner = _customer(business_id=biz_id, business_role="owner")
    admin = _customer(business_id=biz_id, business_role="admin")
    member = _customer(business_id=biz_id, business_role="member")
    assert business.can_approve_for(owner) is True
    assert business.can_approve_for(admin) is True
    assert business.can_approve_for(member) is False
    # The standalone flag still gates it even for an owner.
    owner_declined = _customer(business_id=biz_id, business_role="owner", can_approve=False)
    assert business.can_approve_for(owner_declined) is False


def test_disclosure_due_only_for_a_joined_non_owner_who_has_not_opted_out():
    biz_id = uuid4()
    assert business.disclosure_due(_customer(business_id=None)) is False
    assert business.disclosure_due(_customer(business_id=biz_id, business_role="owner")) is False
    due = _customer(business_id=biz_id, business_role="member")
    assert business.disclosure_due(due) is True
    opted_out = _customer(business_id=biz_id, business_role="member", shares_with_business=False)
    assert business.disclosure_due(opted_out) is False
    already_told = _customer(business_id=biz_id, business_role="member")
    business.mark_disclosed(already_told)
    assert business.disclosure_due(already_told) is False


def test_disclosure_text_names_the_business_in_english_and_roman_urdu():
    en = business.disclosure_text("Ata Traders", "en")
    ur = business.disclosure_text("Ata Traders", "roman_ur")
    assert "Ata Traders" in en and "owner" in en
    assert "Ata Traders" in ur and ur != en


def test_objects_to_sharing_catches_the_spec_phrasings_not_ordinary_talk():
    assert business.objects_to_sharing("Please don't tell the owner about this") is True
    assert business.objects_to_sharing("owner ko mat batana") is True
    assert business.objects_to_sharing("keep this private between us") is True
    assert business.objects_to_sharing("Stock runs out every weekend") is False
    assert business.objects_to_sharing("Our owner already knows about this") is False


def test_opt_out_turns_off_sharing():
    customer = _customer(shares_with_business=True)
    business.opt_out(customer)
    assert customer.shares_with_business is False
