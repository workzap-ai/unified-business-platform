# ruff: noqa: E501
"""Practical solution regression: real composition guards, scripted model, no database."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.pi import (
    ask_classifier,
    constitution,
    decisions,
    practical_solution,
    self_review,
    self_review_types,
    solution_ask,
    solution_context,
)
from app.modules.pi import service_conversation as service
from app.modules.pi.guard import ReplyRejected

OLD = "This is only a suggestion so far, and I have not started anything. Which part would you like to go through first?"
GOOD = (
    "A shared furniture order tracker could connect your registers and Excel records to production. "
    "Each order would have its design, material, delivery date and responsible worker in a job card, "
    "so staff can find the same details. A production board would show cutting, assembly, finishing "
    "and delivery, with the supervisor setting the next job for each worker. Blocked jobs would show "
    "the reason alongside the promised date, helping you spot likely delays. Customer updates could "
    "use the same recorded progress, so customers need fewer calls to find out where their order stands. "
    "Who currently decides which order the workshop works on next?"
)


def context(state="S4_SORTED_SUMMARY"):
    return {
        "pi_mode": "brain",
        "brain_settings": {},
        "flow": {"state": state},
        "reply_language": "en",
        "latest_customer_message": "How would you solve this practically?",
        "history": [
            {
                "role": "customer",
                "text": "We manufacture custom furniture. Orders are in registers and Excel. Workers do not know the next job. Customers call for progress. Delays are hard to predict.",
            },
            {"role": "ai", "text": "Hi, I am pi, an AI from Workzap."},
            {"role": "ai", "text": OLD},
        ],
        "noted_problems": [
            {
                "ref": "p-order",
                "title": "Furniture orders scattered across registers and Excel",
                "group": "operations",
            },
            {"ref": "p-work", "title": "Workers lack production priorities", "group": "operations"},
        ],
        "problem_relationships": [
            {"from": "p-order", "to": "p-work", "type": "causes", "status": "confirmed"}
        ],
        "brief": {
            "map_reviewed": True,
            "industry_confirmed": True,
            "business_profile": {"facts": ["Custom furniture manufacturing"]},
        },
    }


class Manager:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    async def complete_structured(self, scope, model, **kwargs):
        if kwargs["purpose"] in {"pi_problem_extract", "pi_wants_extract"}:
            return SimpleNamespace(value=model(), response=SimpleNamespace(attempts=[]))
        self.calls.append(kwargs)
        assert self.answers, kwargs["messages"][-1].content
        return SimpleNamespace(
            value=service.ServiceTurn(
                reply=self.answers.pop(0), action="task", ready_for_team=True
            ),
            response=SimpleNamespace(attempts=[]),
        )


def objects():
    return (
        SimpleNamespace(
            id=uuid4(), flow_state="S4_SORTED_SUMMARY", service_brief={"map_reviewed": True}
        ),
        SimpleNamespace(response_rules={"pi_mode": "brain"}, ai_config={}),
    )


@pytest.mark.parametrize(
    "state", ["S4_SORTED_SUMMARY", "S_LISTEN_THINK", "S_MAP_SHARE", "S_BOX_OFFER"]
)
def test_request_enters_exploration_from_old_and_current_states(state):
    assert solution_ask.asked_for_ideas(context()["latest_customer_message"])
    assert practical_solution.eligible(context(state))


@pytest.mark.parametrize("state", ["S_HOLD", "X_BLOCKED", "S10_AWAITING_PAYMENT"])
def test_restricted_states_do_not_enter_exploration(state):
    assert not practical_solution.eligible(context(state))


@pytest.mark.asyncio
async def test_full_composition_rewrites_repeat_and_preserves_context():
    corrected = GOOD.rsplit("Who currently", 1)[0] + "Do workers update job progress themselves?"
    manager = Manager(OLD, corrected)
    conversation, policy = objects()
    ctx = context()
    ctx["latest_customer_message"] = (
        "Correction: the supervisor sets priorities, not workers. How would you solve this practically?"
    )
    turn = await service.compose_service_turn(manager, None, conversation, policy, ctx)
    assert turn.reply == corrected
    assert len(manager.calls) == 2
    payload = json.loads(manager.calls[0]["messages"][1].content)
    assert payload["latest_customer_message"] == ctx["latest_customer_message"]
    assert payload["noted_problems"] == ctx["noted_problems"]
    assert payload["problem_relationships"] == ctx["problem_relationships"]
    assert turn.action == "none" and not turn.ready_for_team
    assert turn.reply.count("?") == 1
    service.advance_flow(conversation, turn)
    assert conversation.service_brief["conversation_stage"] == "solution_exploration"
    assert conversation.service_brief["map_reviewed"]
    assert conversation.service_brief["solution_question_pending"]
    assert conversation.flow_state == "S4_SORTED_SUMMARY"


@pytest.mark.asyncio
async def test_twice_repeated_reply_is_never_returned():
    conversation, policy = objects()
    with pytest.raises(ReplyRejected):
        await service.compose_service_turn(Manager(OLD, OLD), None, conversation, policy, context())


@pytest.mark.asyncio
async def test_workflow_does_not_consume_idea_budget_or_reuse_pending_ideas():
    conversation, _ = objects()
    conversation.service_brief["ideas_given"] = 8
    before = dict(conversation.service_brief)
    result = await solution_context.build(
        None,
        None,
        conversation,
        context()["latest_customer_message"],
        context()["noted_problems"],
        {},
    )
    assert result == {}
    assert conversation.service_brief == before


@pytest.mark.parametrize("reply", ["I guarantee zero delays.", "Send your password and OTP."])
def test_practical_mode_keeps_safety_checks(reply):
    ctx = {**context(), "solution_exploration": True, "solution_asked": True}
    assert constitution.hard(constitution.lint(reply, ctx))


@pytest.mark.parametrize(
    "said",
    [
        "We provide digital solutions",
        "I do not want a digital solution",
        "The map looks correct",
        "How much will it cost?",
    ],
)
def test_discovery_or_refusal_is_not_practical_exploration(said):
    ctx = context()
    ctx["latest_customer_message"] = said
    assert not practical_solution.eligible(ctx)


def test_no_notes_keeps_discovery():
    ctx = context()
    ctx["noted_problems"] = []
    assert not practical_solution.eligible(ctx)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["S_LISTEN_THINK", "S_MAP_SHARE", "S_BOX_OFFER"])
async def test_current_flow_states_can_send_the_workflow(state):
    conversation, policy = objects()
    turn = await service.compose_service_turn(
        Manager(GOOD), None, conversation, policy, context(state)
    )
    assert turn.reply == GOOD


@pytest.mark.asyncio
async def test_no_questions_preference_is_preserved():
    conversation, policy = objects()
    ctx = context()
    ctx["no_questions"] = True
    answer = GOOD.rsplit("Who currently", 1)[0].strip()
    turn = await service.compose_service_turn(Manager(answer), None, conversation, policy, ctx)
    assert "?" not in turn.reply
    assert not turn.awaiting_customer


@pytest.mark.parametrize(
    "said",
    [
        "How would you solve this practically?",
        "Show me a modern digital solution.",
        "What actual system would you build?",
        "I want software for this.",
        "How will my staff use it daily?",
        "Can you automate these processes?",
        "What can you develop for my business?",
        "aur aap kia karay gaye meray liye>?",
        "Mujhe inventory software chahiye, how will my staff use it daily?",
    ],
)
def test_natural_solution_requests(said):
    assert solution_ask.asked_for_ideas(said)
    assert practical_solution.eligible({**context(), "latest_customer_message": said})


@pytest.mark.parametrize(
    "said",
    [
        "mujhay yeh bataye kharcha kitna hoga?",
        "What will the software cost?",
        "Please prepare a quote for this system.",
    ],
)
def test_price_and_quote_are_not_solution_approval(said):
    assert not practical_solution.eligible({**context(), "latest_customer_message": said})


def test_pharmacy_expenses_and_data_entry_are_not_pricing():
    said = (
        "Dukaan ka kharch pani, light ka bill, staff ki salary aur ghar ka hisaab "
        "automate karna hai. Data entry aap karke denge ya hamein khud karni hogi?"
    )
    assert not decisions.cost_asked(said)
    assert practical_solution.implementation_asked(said)
    assert practical_solution.eligible({**context(), "latest_customer_message": said})
    assert "responsibility, availability, scope and cost" in practical_solution.PROMPT
    assert "only when approved technical context supports it" in practical_solution.PROMPT


@pytest.mark.parametrize(
    "said",
    [
        "أريد نظاماً رقمياً لمتجري، كيف سيستخدمه الموظفون؟",
        "Quiero un sistema para mi negocio, ¿cómo lo usará mi equipo?",
        "Мне нужна система для бизнеса, как сотрудники будут ей пользоваться?",
        "Маған бизнесіме жүйе керек, қызметкерлер оны қалай қолданады?",
        "برای کسب و کارم یک سیستم می‌خواهم، کارکنان چگونه از آن استفاده می‌کنند؟",
    ],
)
@pytest.mark.asyncio
async def test_shared_semantic_fallback_routes_supported_languages(said):
    class Classifier:
        async def complete(self, scope, **kwargs):
            assert kwargs["messages"][-1].content == said
            return SimpleNamespace(text='{"asks": true}')

    await ask_classifier.prefetch(
        Classifier(), None, said=said, flow_state="S_MAP_SHARE", conversation_id=None
    )
    assert practical_solution.eligible({**context("S_MAP_SHARE"), "latest_customer_message": said})
    solution_ask._LEARNED_ASKS.pop(said, None)


def test_repeated_response_filter_never_restores_original():
    assert service.without_repeats(OLD, context()) == ""


def test_incomplete_map_is_not_replayed_or_confirmed():
    turn = service.ServiceTurn(reply="What else is missing from the map?")
    ctx = {**context(), "map_incomplete": True, "quiet_replies": 10}
    service.brain_summary(turn, ctx)
    assert not turn._summary
    assert turn.reply == "What else is missing from the map?"
    assert practical_solution.map_incomplete("Kuch reh gaya")


@pytest.mark.asyncio
async def test_self_review_repairs_false_implementation_claim_instead_of_fixed_disclaimer():
    conversation, policy = objects()
    ctx = {**context(), "solution_exploration": True, "solution_asked": True}
    turn = service.ServiceTurn(reply="I have built the order tracking system.")
    manager = Manager(GOOD)
    await service.pre_send_guard(turn, ctx, manager, None, policy, conversation)
    assert turn.reply == GOOD
    assert len(manager.calls) == 1
    assert "SR-16" in manager.calls[0]["messages"][-1].content


def test_conditional_workflow_is_not_implementation():
    report = self_review.review(
        self_review_types.DraftResult(
            reply_text="Staff would mark each job completed after checking it.",
            implementation_status="proposed",
        )
    )
    assert next(check for check in report.checks if check.id == "SR-16").status == "PASS"


def test_answer_to_workflow_question_does_not_restart_discovery():
    ctx = {
        **context(),
        "latest_customer_message": "Supervisor decides",
        "brief": {
            "conversation_stage": "solution_exploration",
            "solution_question_pending": True,
        },
    }
    assert practical_solution.eligible(ctx)
    assert not practical_solution.eligible({**ctx, "topic_event": "new_topic"})
    assert not practical_solution.eligible({**ctx, "latest_customer_message": "No software please"})


@pytest.mark.asyncio
async def test_cached_diagnosis_does_not_replace_digital_workflow():
    conversation, policy = objects()
    ctx = {
        **context(),
        "expert_on": True,
        "main_problem_causes": ["Missing material"],
        "suggested_next_question": "Why is material missing?",
    }
    answer = GOOD.rsplit("Who currently", 1)[0] + "Who handles production scheduling?"
    turn = await service.compose_service_turn(Manager(answer), None, conversation, policy, ctx)
    assert turn.reply == answer


@pytest.mark.asyncio
async def test_data_entry_ownership_answer_is_not_replaced_by_quote():
    conversation, policy = objects()
    ctx = {
        **context(),
        "latest_customer_message": "Will you do the initial data entry or will our staff?",
    }
    answer = (
        "Workzap's team needs to confirm who handles the initial data entry and whether this is "
        "included in the scope. Initial data entry and daily entries are separate tasks. "
        "For ongoing use, your designated staff could record new sales, stock receipts and expenses "
        "as they happen. The responsibility for entering existing records remains unconfirmed. "
        "Which staff role would enter new stock?"
    )
    turn = await service.compose_service_turn(Manager(answer), None, conversation, policy, ctx)
    assert turn.reply == answer
    assert turn.action == "none" and turn.proposal_answer == "none"


def test_roman_urdu_negation_keeps_real_guarantees_blocked():
    assert not constitution._promise_hits("Visa ki guarantee nahi hogi.")
    assert constitution._promise_hits("Visa ki guarantee hogi.")
    assert constitution._promise_hits("Visa ki guarantee. Nahi, payment baad mein.")


def test_explanation_is_not_mistaken_for_an_answered_choice_question():
    from app.modules.pi import listening_tidy

    owner = ["We record sales, stock and expenses on paper."]
    assert not listening_tidy.answered_questions(
        "You could track sales, stock and expenses together. Who receives incoming stock?", owner
    )
    assert listening_tidy.answered_questions("Do you record sales, stock or expenses?", owner)


SCENARIOS = [
    (
        "We run a pharmacy in Karachi. Medicine stock and sales are on paper slips. Daily totals "
        "do not match. Bills, salaries and household expenses are mixed. Inspectors visit and "
        "we have tax record difficulties. What can you build for us?",
        "A pharmacy inventory and sales system could connect each sale to its stock movement. "
        "Staff would receive medicines against a supplier record, with batches and expiry dates, "
        "then record sales at the counter. The owner could view daily sales, stock and cash differences. "
        "Expense records would separate shop bills and salaries from household spending, so daily "
        "cash reconciliation has a clear basis. Expiry alerts and low-stock warnings could highlight "
        "items needing attention. Recorded purchases and supporting documents would be easier to "
        "retrieve for an accountant or inspector; the relevant professional must verify requirements. "
        "Who records incoming medicines today?",
        "Medicine stock and daily sales unclear",
        "en",
    ),
    (
        "Hum Hajj aur Umrah travel agency hain. Website nahi, referrals se clients aatay hain. "
        "International customers tak pohanchna hai. Aap kya bana sakte hain?",
        "Aap ki travel agency ke liye website aur enquiry tracking ka aik jura hua system "
        "tajweez kiya ja sakta hai. Website par Hajj aur Umrah packages ki tasdeeq shuda "
        "tafseel aur rabtay ka rasta ho. Customer ki enquiry office ki list mein aaye, "
        "jahan staff us ka jawab aur agla follow-up record kare. Owner dekh sake ke kis "
        "package par enquiries aa rahi hain aur kahan baat rukti hai. International "
        "customers ke liye zaroorat ke mutabiq mukhtalif zabanon mein pages rakhe ja "
        "sakte hain. Visa ya booking ki guarantee nahi hogi. Abhi enquiry ka jawab kaun deta hai?",
        "Travel agency lacks online presence and enquiry tracking",
        "roman_ur",
    ),
    (
        "We repair underwater inspection robots. Sensor modules travel between our bench, "
        "a pressure chamber and client vessels. Firmware versions and test reports get mixed. "
        "Show me a modern digital solution.",
        "A repair tracking system could connect each robot and sensor module to its test history. "
        "The receiving technician would open a repair record with the reported fault and current "
        "firmware version. Bench staff could record parts changed, while the pressure chamber team "
        "would attach the relevant test report to that same repair. A release checklist would "
        "show which checks remain before dispatch to the client vessel. The owner could see "
        "waiting repairs and missing reports without searching separate files. Any automated "
        "test-equipment connection would need a technical compatibility check first. Who approves "
        "a repaired robot for release?",
        "Robot firmware versions and pressure test reports get mixed",
        "en",
    ),
    (
        "لدينا متجر قطع غيار، المخزون والمبيعات مسجلة على الورق. أعطني حلاً رقمياً مناسباً.",
        "يمكن اقتراح نظام رقمي يربط مبيعات قطع الغيار بالمخزون. يسجل الموظف القطع عند "
        "استلامها من المورد، ثم يسجل كل عملية بيع على سجل الصنف نفسه، بحيث يستطيع "
        "صاحب المتجر مراجعة حركة المخزون والمبيعات اليومية من شاشة واحدة. يمكن إضافة "
        "تنبيه للأصناف التي تحتاج إلى إعادة طلب بعد تحديد الحد المناسب لكل صنف. "
        "تُسجل الفروقات عند مراجعة المخزون مع سببها بدلاً من البحث بين الأوراق. "
        "هذه طريقة عمل مقترحة، وتبقى تفاصيل الربط مع أي أجهزة موجودة بحاجة إلى "
        "تحقق فني. من يتولى تسجيل البضاعة عند وصولها إلى المتجر؟",
        "Spare parts stock and sales recorded on paper",
        "ar",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("said,answer,title,language", SCENARIOS)
async def test_representative_industries_use_same_composition(said, answer, title, language):
    conversation, policy = objects()
    ctx = context("S_LISTEN_THINK")
    ctx.update(
        latest_customer_message=said,
        reply_language=language,
        noted_problems=[{"ref": "p1", "title": title, "group": "operations"}],
        problem_relationships=[],
    )
    ctx["history"][0]["text"] = said
    ctx["brief"]["business_profile"] = {"facts": [title]}
    solution_ask.remember_ask(said, True)  # same semantic verdict used by runtime prefetch
    manager = Manager(answer)
    try:
        turn = await service.compose_service_turn(manager, None, conversation, policy, ctx)
    finally:
        solution_ask._LEARNED_ASKS.pop(said, None)
    assert turn.reply == answer
    assert turn.language == language
    assert turn.action == "none" and turn.proposal_answer == "none"
    payload = json.loads(manager.calls[0]["messages"][1].content)
    assert payload["latest_customer_message"] == said
    assert payload["noted_problems"][0]["title"] == title
    prompt = manager.calls[0]["messages"][0].content
    assert "DIGITAL system" in prompt and "unfamiliar industries" in prompt
