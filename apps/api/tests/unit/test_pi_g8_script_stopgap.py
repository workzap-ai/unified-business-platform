from app.modules.pi import idea_filter


def test_g8_never_rejects_urdu_idea():
    assert (
        idea_filter.off_the_map("پرانا مال پہلے بیچیں", ["stock is stuck"], ["stock_inventory"])
        is None
    )


def test_g8_never_rejects_when_map_is_arabic():
    assert idea_filter.off_the_map("Bundle the oldest items.", ["المخزون راكد"]) is None


def test_g8_entry_idea_concepts_pass():
    entry = ["Put a weekly rota on the wall"]
    assert (
        idea_filter.off_the_map("Share the rota on the wall", ["stock stuck"], (), "", entry)
        is None
    )


def test_g8_still_rejects_unrelated_latin():
    assert idea_filter.off_the_map("Repaint the signboard blue.", ["stock stuck"]) == "G8"
