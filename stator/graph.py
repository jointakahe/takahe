from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
    cast,
)


class StateGraph:
    """
    Represents a graph of possible states and transitions to attempt on them.
    Does not support subclasses of existing graphs yet.
    """

    states: ClassVar[Dict[str, "State"]]
    choices: ClassVar[List[Tuple[object, str]]]
    initial_state: ClassVar["State"]
    terminal_states: ClassVar[Set["State"]]

    def __init_subclass__(cls) -> None:
        # Collect state memebers
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
        initial_state = None
        for state in cls.states.values():
            if state.initial:
                if initial_state:
                    raise ValueError(
                        f"The graph has more than one initial state: {initial_state} and {state}"
                    )
                initial_state = state
            if state.terminal:
                terminal_states.add(state)
        if initial_state is None:
            raise ValueError("The graph has no initial state")
        cls.initial_state = initial_state
        cls.terminal_states = terminal_states
        # Generate choices
        cls.choices = [(state, name) for name, state in cls.states.items()]


class State:
    """
    Represents an individual state
    """

    def __init__(self, try_interval: float = 300):
        self.try_interval = try_interval
        self.parents: Set["State"] = set()
        self.children: Dict["State", "Transition"] = {}

    def _add_to_graph(self, graph: Type[StateGraph], name: str):
        self.graph = graph
        self.name = name
        self.graph.states[name] = self

    def __repr__(self):
        return f"<State {self.name}>"

    def __str__(self):
        return self.name

    def __len__(self):
        return len(self.name)

    def add_transition(
        self,
        other: "State",
        handler: Optional[Callable] = None,
        priority: int = 0,
    ) -> Callable:
        def decorator(handler: Callable[[Any], bool]):
            self.children[other] = Transition(
                self,
                other,
                handler,
                priority=priority,
            )
            other.parents.add(self)
            return handler

        # If we're not being called as a decorator, invoke it immediately
        if handler is not None:
            decorator(handler)
        return decorator

    def add_manual_transition(self, other: "State"):
        self.children[other] = ManualTransition(self, other)
        other.parents.add(self)

    @property
    def initial(self):
        return not self.parents

    @property
    def terminal(self):
        return not self.children

    def transitions(self, automatic_only=False) -> List["Transition"]:
        """
        Returns all transitions from this State in priority order
        """
        if automatic_only:
            transitions = [t for t in self.children.values() if t.automatic]
        else:
            transitions = list(self.children.values())
        return sorted(transitions, key=lambda t: t.priority, reverse=True)


class Transition:
    """
    A possible transition from one state to another
    """

    def __init__(
        self,
        from_state: State,
        to_state: State,
        handler: Union[str, Callable],
        priority: int = 0,
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.handler = handler
        self.priority = priority
        self.automatic = True

    def get_handler(self) -> Callable:
        """
        Returns the handler (it might need resolving from a string)
        """
        if isinstance(self.handler, str):
            self.handler = getattr(self.from_state.graph, self.handler)
        return cast(Callable, self.handler)

    def __repr__(self):
        return f"<Transition {self.from_state} -> {self.to_state}>"


class ManualTransition(Transition):
    """
    A possible transition from one state to another that cannot be done by
    the stator task runner, and must come from an external source.
    """

    def __init__(
        self,
        from_state: State,
        to_state: State,
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.priority = 0
        self.automatic = False
