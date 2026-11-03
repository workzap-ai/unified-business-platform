"""Several people from one business (pi Brain spec 4.9, R-MEM-06): the first to name a business
owns it, a second contact awaits approval (or staff link them directly), a joining member is told
once that their problems are shared, approval moves with the business role, and problems different
team members raise about the same thing are linked so the owner is told "mentioned by N people"."""

import pytest
from sqlalchemy import select
from test_pi_pipeline import pi_workspace

from app.modules.customers.models import Customer
from app.modules.pi import business
from app.modules.pi.problem_models import PiProblem, PiProblemLink

pytestmark = pytest.mark.integration


def _customer(scope, **kw):
    return Customer(tenant_id=scope.tenant_id, environment_id=scope.environment_id, **kw)


def _problem(scope, customer_id, number, title, category="stock_inventory"):
    return PiProblem(
        tenant_id=scope.tenant_id,
        environment_id=scope.environment_id,
        customer_id=customer_id,
        number=number,
        title=title,
        category=category,
        status="confirmed",
    )


async def _owner_and_member(api, db, phone_owner="+923001110001", phone_member="+923001110002"):
    pi = await pi_workspace(api, db)
    scope = pi.scope()
    owner = _customer(scope, name="Ata", phone=phone_owner)
    db.add(owner)
    await db.flush()
    biz, became_owner = await business.join_or_request(db, scope, owner, "Ata Traders")
    assert became_owner is True
    member = _customer(scope, name="Bilal", phone=phone_member)
    db.add(member)
    await db.flush()
    return pi, scope, biz, owner, member


async def test_the_first_to_name_a_business_owns_it(api, business_db):
    pi = await pi_workspace(api, business_db)
    scope = pi.scope()
    owner = _customer(scope, name="Ata", phone="+923001110001")
    business_db.add(owner)
    await business_db.flush()
    biz, became_owner = await business.join_or_request(business_db, scope, owner, "Ata Traders")
    assert became_owner is True
    assert owner.business_id == biz.id
    assert owner.business_role == "owner"
    assert owner.business_joined_at is not None
    await pi.close()


async def test_a_second_contact_naming_the_same_business_awaits_approval(api, business_db):
    pi, scope, biz, owner, member = await _owner_and_member(api, business_db)
    again, became_owner = await business.join_or_request(business_db, scope, member, "ata traders")
    assert became_owner is False
    assert again.id == biz.id
    assert member.business_id is None
    assert member.pending_business_name == "ata traders"
    approved = await business.approve_join(business_db, scope, owner, member)
    assert approved is True
    assert member.business_id == biz.id
    assert member.business_role == "member"
    assert member.pending_business_name is None
    await pi.close()


async def test_a_plain_member_cannot_approve_a_join(api, business_db):
    pi, scope, biz, owner, member = await _owner_and_member(api, business_db)
    business.staff_link(member, biz)
    assert member.business_role == "member"
    third = _customer(scope, name="Sana", phone="+923001110003")
    business_db.add(third)
    await business_db.flush()
    await business.join_or_request(business_db, scope, third, "Ata Traders")
    assert await business.approve_join(business_db, scope, member, third) is False
    assert third.business_id is None
    await pi.close()


async def test_disclosure_is_due_once_for_a_joined_member_never_the_owner(api, business_db):
    pi, scope, biz, owner, member = await _owner_and_member(api, business_db)
    assert business.disclosure_due(owner) is False
    assert business.disclosure_due(member) is False  # not joined yet
    business.staff_link(member, biz)
    assert business.disclosure_due(member) is True
    business.mark_disclosed(member)
    assert business.disclosure_due(member) is False
    await pi.close()


async def test_an_objection_keeps_problems_private_and_stops_the_disclosure(api, business_db):
    pi, scope, biz, owner, member = await _owner_and_member(api, business_db)
    business.staff_link(member, biz)
    assert business.disclosure_due(member) is True
    assert business.objects_to_sharing("Please don't share this with my owner") is True
    assert business.objects_to_sharing("Stock runs out every weekend") is False
    business.opt_out(member)
    assert business.disclosure_due(member) is False
    assert await business.find_business_mates(business_db, scope, member) == []
    await pi.close()


async def test_can_approve_follows_business_role_not_just_the_flag(api, business_db):
    pi, scope, biz, owner, member = await _owner_and_member(api, business_db)
    business.staff_link(member, biz)
    assert business.can_approve_for(owner) is True
    assert business.can_approve_for(member) is False
    member.business_role = "admin"
    assert business.can_approve_for(member) is True
    member.can_approve = False
    assert business.can_approve_for(member) is False  # the flag still gates it either way
    await pi.close()


async def test_duplicate_problems_across_team_members_are_linked_and_counted(api, business_db):
    pi, scope, biz, owner, member = await _owner_and_member(api, business_db)
    business.staff_link(member, biz)
    p1 = _problem(scope, owner.id, 1, "Stock runs out every weekend")
    business_db.add(p1)
    await business_db.flush()
    p2 = _problem(scope, member.id, 1, "Stock runs out on weekends too")
    business_db.add(p2)
    await business_db.flush()
    links = await business.link_duplicates_for_problem(business_db, scope, p2)
    assert len(links) == 1
    assert links[0].type == "duplicate_across_contacts"
    assert links[0].status == "confirmed"
    again = await business.link_duplicates_for_problem(business_db, scope, p2)
    assert again == []  # not linked twice
    assert await business.mentioned_by(business_db, scope, p1) == 2
    assert await business.mentioned_by(business_db, scope, p2) == 2
    [stored] = await business_db.scalars(
        select(PiProblemLink).where(
            PiProblemLink.tenant_id == scope.tenant_id,
            PiProblemLink.environment_id == scope.environment_id,
        )
    )
    assert stored.created_by == "pi"
    await pi.close()


async def test_a_solo_customer_problem_is_never_linked(api, business_db):
    pi = await pi_workspace(api, business_db)
    scope = pi.scope()
    solo = _customer(scope, name="Solo Trader", phone="+923001110009")
    business_db.add(solo)
    await business_db.flush()
    p = _problem(scope, solo.id, 1, "Stock runs out every weekend")
    business_db.add(p)
    await business_db.flush()
    assert await business.link_duplicates_for_problem(business_db, scope, p) == []
    assert await business.mentioned_by(business_db, scope, p) == 1
    await pi.close()


async def test_an_opted_out_member_is_never_matched_either_direction(api, business_db):
    pi, scope, biz, owner, member = await _owner_and_member(api, business_db)
    business.staff_link(member, biz)
    business.opt_out(member)
    p1 = _problem(scope, owner.id, 1, "Stock runs out every weekend")
    business_db.add(p1)
    await business_db.flush()
    p2 = _problem(scope, member.id, 1, "Stock runs out on weekends too")
    business_db.add(p2)
    await business_db.flush()
    assert await business.link_duplicates_for_problem(business_db, scope, p2) == []
    assert await business.mentioned_by(business_db, scope, p1) == 1
    await pi.close()
