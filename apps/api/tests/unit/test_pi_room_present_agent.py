"""The agent keeps pi's video in step with what the room says is on show; it never breaks a call."""

from app.modules.pi_meetings import room_present as rp
from app.modules.pi_meetings.room_present_agent import MAX_TRIES, Presenter

SLIDES = rp.build([{"when": "2026-11-12", "points": ["decision: Start with the shop page"]}], [])


class Track:
    def __init__(self, image):
        self.image, self.shown, self.stopped = image, [], False

    def show(self, image):
        self.shown.append(image)

    def stop(self):
        self.stopped = True


class Connection:
    def __init__(self):
        self.published, self.fail = [], 0

    async def add_tracks(self, video=None):
        if self.fail:
            self.fail -= 1
            raise RuntimeError("publish failed")
        self.published.append(video)


def build(connection=None):
    connection = connection or Connection()
    made = []

    def make(image):
        made.append(Track(image))
        return made[-1]

    def picture(slide, number, total):
        return (slide["heading"], number, total)

    return Presenter(connection, make_track=make, picture=picture), connection, made


def state(**kw):
    value = rp.start(SLIDES, {})
    value.update(kw)
    return value


async def test_a_slide_is_published_once_and_the_next_one_only_swaps_the_picture():
    presenter, connection, made = build()
    await presenter.apply(state())
    assert len(connection.published) == 1 and made[0].image[1:] == (1, len(SLIDES))
    await presenter.apply(state())  # nothing changed: nothing sent
    assert len(connection.published) == 1 and made[0].shown == []
    await presenter.apply(state(index=1))
    assert len(connection.published) == 1  # no second track
    assert made[0].shown == [("Our call on 12 November 2026", 2, len(SLIDES))]
    assert presenter.showing


async def test_stopping_ends_the_track_and_a_new_start_makes_a_new_one():
    presenter, connection, made = build()
    await presenter.apply(state())
    await presenter.apply(rp.stop(state()))
    assert made[0].stopped and not presenter.showing
    await presenter.apply(rp.stop(state()))  # already stopped: nothing happens
    await presenter.apply(state(v=2))
    assert len(connection.published) == 2 and made[1] is not made[0]
    await presenter.apply({})  # the room says nothing is on show
    assert made[1].stopped


async def test_nothing_to_show_publishes_nothing():
    presenter, connection, made = build()
    await presenter.apply(None)
    await presenter.apply({})
    await presenter.apply({"on": True, "slides": [], "index": 0, "v": 1})
    assert connection.published == [] and made == [] and not presenter.showing


async def test_a_failed_publish_is_retried_a_few_times_and_never_raises():
    connection = Connection()
    connection.fail = 2
    presenter, connection, made = build(connection)
    for _ in range(3):  # three beats with the same slide
        await presenter.apply(state())
    assert len(connection.published) == 1  # the third try worked
    always = Connection()
    always.fail = 99
    stuck, always, _ = build(always)
    for _ in range(MAX_TRIES + 3):
        await stuck.apply(state())
    assert always.fail == 99 - MAX_TRIES  # it stopped trying: pi is not hammering the service
    await stuck.apply(state(v=2))  # a new presentation starts with a clean count
    assert always.fail == 99 - MAX_TRIES - 1


async def test_an_index_past_the_end_is_clamped_to_the_last_slide():
    presenter, connection, made = build()
    await presenter.apply(state(index=99))
    assert made[0].image[1] == len(SLIDES)


async def test_a_track_that_cannot_be_stopped_does_not_break_the_call():
    presenter, connection, made = build()
    await presenter.apply(state())

    def broken():
        raise RuntimeError("already ended")

    made[0].stop = broken
    await presenter.stop()  # no exception
    assert not presenter.showing
