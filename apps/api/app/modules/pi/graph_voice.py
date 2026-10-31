# ruff: noqa: E501  (one fixed line per row reads better than wrapped text)
"""PS-flow: what the owner reads about how their problems connect (brain mode, from PS-7's graph).

Fixed templates in English, Roman Urdu, Urdu and Arabic. Nothing here is a result or a promise, and
nothing asks a question (the one question stays last, in `option_voice`):

  * an edge the owner stated is said as theirs ("You told me ... are connected");
  * every other edge is a guess, worded "may be connected" and labelled as not checked;
  * what to find out first is the cause that would explain the most problems; a cause pi guessed is
    labelled as pi's guess, one the owner said is to be confirmed;
  * problems are ordered only from the owner's own figures; with no complete order the line says
    "cannot rank yet".
"""

from typing import Any

from app.modules.pi import problem_graph as pg

T: dict[str, dict[str, str]] = {
    "en": {
        "stated": 'You told me that "{a}" and "{b}" are connected.',
        "maybe": 'It may be that "{a}" and "{b}" are connected. That is only a guess; I have not checked it.',
        "first_guess": "Worth checking first: {text}. That is my own guess, not something you told me.",
        "first_said": "You said: {text}. I would like to confirm that first.",
        "unranked": "I cannot rank these problems yet, because I do not have a figure for each of them.",
        "ranked": "From the figures you gave, the order is: {order}.",
    },
    "roman_ur": {
        "stated": 'Aap ne bataya ke "{a}" aur "{b}" ek doosre se jude hain.',
        "maybe": 'Ho sakta hai "{a}" aur "{b}" ek doosre se jude hon. Yeh sirf andaza hai; maine isay check nahi kiya.',
        "first_guess": "Pehle yeh dekhna munasib hoga: {text}. Yeh mera apna andaza hai, aap ki batayi hui baat nahi.",
        "first_said": "Aap ne kaha: {text}. Main pehle isay pakka karna chahunga.",
        "unranked": "Main abhi in masalon ko tarteeb nahi de sakta, kyunke har ek ka ankra mere paas nahi.",
        "ranked": "Aap ke diye hue ankron se tarteeb yeh hai: {order}.",
    },
    "ur": {
        "stated": 'آپ نے بتایا کہ "{a}" اور "{b}" ایک دوسرے سے جڑے ہیں۔',
        "maybe": 'ہو سکتا ہے "{a}" اور "{b}" ایک دوسرے سے جڑے ہوں۔ یہ صرف اندازہ ہے، اسے جانچا نہیں گیا۔',
        "first_guess": "پہلے یہ دیکھنا مناسب ہوگا: {text}۔ یہ میرا اپنا اندازہ ہے، آپ کی بتائی ہوئی بات نہیں۔",
        "first_said": "آپ نے کہا: {text}۔ اسے پہلے پکا کر لینا بہتر ہوگا۔",
        "unranked": "ابھی ان مسائل کو ترتیب نہیں دی جا سکتی، کیونکہ ہر ایک کا عدد موجود نہیں۔",
        "ranked": "آپ کے دیے ہوئے اعداد سے ترتیب یہ ہے: {order}۔",
    },
    "ar": {
        "stated": 'أخبرتني أن "{a}" و"{b}" مرتبطان.',
        "maybe": 'قد يكون "{a}" و"{b}" مرتبطين. هذا مجرد تخمين ولم أتحقق منه.',
        "first_guess": "من المفيد التحقق أولا من: {text}. هذا تخميني أنا وليس ما قلته لي.",
        "first_said": "قلت: {text}. أود تأكيد ذلك أولا.",
        "unranked": "لا أستطيع ترتيب هذه المشكلات بعد، لأنه لا يوجد رقم لكل منها.",
        "ranked": "من الأرقام التي ذكرتها، الترتيب هو: {order}.",
    },
}


def table(language: str | None) -> dict[str, str]:
    return T.get(language or "en") or T["en"]


def graph_of(
    noted: list[dict[str, Any]], owner_messages: list[str], language: str, requirements: Any = None
) -> pg.ProblemGraph:
    """The PS-7 graph over the noted problems and the owner's own messages. Never raises."""
    problems = [
        {
            "id": str(p.get("ref") or p.get("id") or i),
            "title": str(p.get("title") or ""),
            "title_local": str(p.get("title_local") or ""),
            "user_words": list(p.get("user_words") or []),
        }
        for i, p in enumerate(noted)
        if isinstance(p, dict)
    ]
    return pg.build_problem_graph(problems, owner_messages, requirements, language)


def lines(
    graph: pg.ProblemGraph, language: str | None, *, want_first: bool = False, max_edges: int = 2
) -> list[str]:
    """The statements, in the owner's language. `want_first` adds the line about what to find out
    first (used when no idea could be cleared)."""
    tb = table(language)
    titles = {n.id: n.title for n in graph.problems}
    out: list[str] = []
    shown = 0
    for edge in graph.edges:
        a, b = titles.get(edge.from_id, ""), titles.get(edge.to_id, "")
        if not (a and b) or shown >= max_edges:
            continue
        key = "stated" if edge.kind is pg.EdgeKind.OWNER_STATED and not edge.hypothesis else "maybe"
        out.append(tb[key].format(a=a, b=b))
        shown += 1
    if want_first and graph.learn_first:
        item = graph.learn_first[0]
        key = "first_said" if item.status == pg.OWNER_SAID else "first_guess"
        out.append(tb[key].format(text=item.text))
    if len(graph.problems) >= 2 and graph.priority is not None:
        if graph.priority.complete and graph.priority.ranked:
            order = ", ".join(
                titles.get(r.problem_id, "")
                for r in graph.priority.ranked
                if titles.get(r.problem_id)
            )
            if order:
                out.append(tb["ranked"].format(order=order))
        else:
            out.append(tb["unranked"])
    return out
