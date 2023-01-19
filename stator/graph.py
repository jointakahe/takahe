from collections.abc import Callable
from typing import Any, ClassVar


class StateGraph:
    """
    Represents a graph of possible states and transitions to attempt on them.
    Does not support subclasses of existing graphs yet.
    """

    states: ClassVar[dict[str, "State"]]
    choices: ClassVar[list[tuple[object, str]]]
    initial_state: ClassVar["State"]
    terminal_states: ClassVar[set["State"]]
    automatic_states: ClassVar[set["State"]]

    def __init_subclass__(cls) -> None:
        # Collect state members
        cls.states = {}
        for name, value in cls.__dict__.items():
            if name in ["__module__", "__doc__", "states"]:
                pass
            elif name in ["initial_state", "terminal_states", "choices"]:
                raise ValueError(f"Cannot name a state {name} - this is reserved")
            elif isinstance(value, State):
                value._add_to_graph(cls, name)
            elif callable(value) or isinstance(value, classmethod):
                pass
            else:
                raise ValueError(
                    f"Graph has item {name} of unallowed type {type(value)}"
                )
        # Check the graph layout
        terminal_states = set()
        automatic_states = set()
        initial_state = None
        for state in cls.states.values():
            # Check for multiple initial states
            if state.initial:
                if initial_state:
                    raise ValueError(
                        f"The graph has more than one initial state: {initial_state} and {state}"
                    )
                initial_state = state
            # Collect terminal states
            if state.terminal:
                state.externally_progressed = True
                terminal_states.add(state)
                # Ensure they do NOT have a handler
                try:
                    state.handler
                except AttributeError:
                    pass
                else:
                    raise ValueError(
                        f"Terminal state '{state}' should not have a handler method ({state.handler_name})"
                    )
            else:
                # Ensure non-terminal/manual states have a try interval and a handler
                if not state.externally_progressed:
                    if not state.try_interval:
                        raise ValueError(
                            f"State '{state}' has no try_interval and is not terminal or manual"
                        )
                    try:
                        state.handler
                    except AttributeError:
                        raise ValueError(
                            f"State '{state}' does not have a handler method ({state.handler_name})"
                        )
                    automatic_states.add(state)
        if initial_state is None:
            raise ValueError("The graph has no initial state")
        cls.initial_state = initial_state
        cls.terminal_states = terminal_states
        cls.automatic_states = automatic_states
        # Generate choices
        cls.choices = [(name, name) for name in cls.states.keys()]


class State:
    """
    Represents an individual state
    """

    def __init__(
        self,
        try_interval: float | None = None,
        handler_name: str | None = None,
        externally_progressed: bool = False,
        attempt_immediately: bool = True,
        force_initial: bool = False,
        delete_after: int | None = None,
    ):
        self.try_interval = try_interval
        self.handler_name = handler_name
        self.externally_progressed = externally_progressed
        self.attempt_immediately = attempt_immediately
        self.force_initial = force_initial
        self.delete_after = delete_after
        self.parents: set["State"] = set()
        self.children: set["State"] = set()
        self.timeout_state: State | None = None
        self.timeout_value: int | None = None

    def _add_to_graph(self, graph: type[StateGraph], name: str):
        self.graph = graph
        self.name = name
        self.graph.states[name] = self
        if self.handler_name is None:
            self.handler_name = f"handle_{self.name}"

    def __repr__(self):
        return f"<State {self.name}>"

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if isinstance(other, State):
            return self is other
        return self.name == other

    def __hash__(self):
        return hash(id(self))

    def transitions_to(self, other: "State"):
        self.children.add(other)
        other.parents.add(other)

    def times_out_to(self, other: "State", seconds: int):
        if self.timeout_state is not None:
            raise ValueError("Timeout state already set!")
        self.timeout_state = other
        self.timeout_value = seconds
        self.children.add(other)
        other.parents.add(other)

    @property
    def initial(self):
        return self.force_initial or (not self.parents)

    @property
    def terminal(self):
        return not self.children

    @property
    def handler(self) -> Callable[[Any], str | None]:
        # Retrieve it by name off the graph
        if self.handler_name is None:
            raise AttributeError("No handler defined")
        return getattr(self.graph, self.handler_name)
