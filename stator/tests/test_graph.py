import pytest

from stator.graph import State, StateGraph


def test_declare():
    """
    Tests a basic graph declaration and various kinds of handler
    lookups.
    """

    fake_handler = lambda: True

    class TestGraph(StateGraph):
        initial = State()
        second = State()
        third = State()
        fourth = State()
        final = State()

        initial.add_transition(second, 60, handler=fake_handler)
        second.add_transition(third, 60, handler="check_third")

        def check_third(cls):
            return True

        @third.add_transition(fourth, 60)
        def check_fourth(cls):
            return True

        fourth.add_manual_transition(final)

    assert TestGraph.initial_state == TestGraph.initial
    assert TestGraph.terminal_states == {TestGraph.final}

    assert TestGraph.initial.children[TestGraph.second].get_handler() == fake_handler
    assert (
        TestGraph.second.children[TestGraph.third].get_handler()
        == TestGraph.check_third
    )
    assert (
        TestGraph.third.children[TestGraph.fourth].get_handler().__name__
        == "check_fourth"
    )


def test_bad_declarations():
    """
    Tests that you can't declare an invalid graph.
    """
    # More than one initial state
    with pytest.raises(ValueError):

        class TestGraph(StateGraph):
            initial = State()
            initial2 = State()

    # No initial states
    with pytest.raises(ValueError):

        class TestGraph(StateGraph):
            loop = State()
            loop2 = State()

            loop.add_transition(loop2, 1, handler="fake")
            loop2.add_transition(loop, 1, handler="fake")
