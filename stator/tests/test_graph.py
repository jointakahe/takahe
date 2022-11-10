import pytest

from stator.graph import State, StateGraph


def test_declare():
    """
    Tests a basic graph declaration and various kinds of handler
    lookups.
    """

    class TestGraph(StateGraph):
        initial = State(try_interval=3600)
        second = State(try_interval=1)
        third = State()

        initial.transitions_to(second)
        second.transitions_to(third)

        @classmethod
        def handle_initial(cls):
            pass

        @classmethod
        def handle_second(cls):
            pass

    assert TestGraph.initial_state == TestGraph.initial
    assert TestGraph.terminal_states == {TestGraph.third}

    assert TestGraph.initial.handler == TestGraph.handle_initial
    assert TestGraph.initial.try_interval == 3600
    assert TestGraph.second.handler == TestGraph.handle_second
    assert TestGraph.second.try_interval == 1


def test_bad_declarations():
    """
    Tests that you can't declare an invalid graph.
    """
    # More than one initial state
    with pytest.raises(ValueError):

        class TestGraph2(StateGraph):
            initial = State()
            initial2 = State()

    # No initial states
    with pytest.raises(ValueError):

        class TestGraph3(StateGraph):
            loop = State()
            loop2 = State()

            loop.transitions_to(loop2)
            loop2.transitions_to(loop)


def test_state():
    """
    Tests basic values of the State class
    """

    class TestGraph(StateGraph):
        initial = State()

    assert "initial" == TestGraph.initial
    assert TestGraph.initial == "initial"
    assert TestGraph.initial == TestGraph.initial
