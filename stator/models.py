import datetime
import pprint
import traceback
from typing import ClassVar, List, Optional, Type, Union, cast

from asgiref.sync import sync_to_async
from django.db import models, transaction
from django.utils import timezone
from django.utils.functional import classproperty

from stator.graph import State, StateGraph


class StateField(models.CharField):
    """
    A special field that automatically gets choices from a state graph
    """

    def __init__(self, graph: Type[StateGraph], **kwargs):
        # Sensible default for state length
        kwargs.setdefault("max_length", 100)
        # Add choices and initial
        self.graph = graph
        kwargs["choices"] = self.graph.choices
        kwargs["default"] = self.graph.initial_state.name
        super().__init__(**kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["graph"] = self.graph
        return name, path, args, kwargs

    def get_prep_value(self, value):
        if isinstance(value, State):
            return value.name
        return value


class StatorModel(models.Model):
    """
    A model base class that has a state machine backing it, with tasks to work
    out when to move the state to the next one.

    You need to provide a "state" field as an instance of StateField on the
    concrete model yourself.
    """

    # If this row is up for transition attempts
    state_ready = models.BooleanField(default=False)

    # When the state last actually changed, or the date of instance creation
    state_changed = models.DateTimeField(auto_now_add=True)

    # When the last state change for the current state was attempted
    # (and not successful, as this is cleared on transition)
    state_attempted = models.DateTimeField(blank=True, null=True)

    # If a lock is out on this row, when it is locked until
    # (we don't identify the lock owner, as there's no heartbeats)
    state_locked_until = models.DateTimeField(null=True, blank=True)

    # Collection of subclasses of us
    subclasses: ClassVar[List[Type["StatorModel"]]] = []

    class Meta:
        abstract = True

    def __init_subclass__(cls) -> None:
        if cls is not StatorModel:
            cls.subclasses.append(cls)

    @classproperty
    def state_graph(cls) -> Type[StateGraph]:
        return cls._meta.get_field("state").graph

    @classmethod
    async def atransition_schedule_due(cls, now=None) -> models.QuerySet:
        """
        Finds instances of this model that need to run and schedule them.
        """
        q = models.Q()
        for state in cls.state_graph.states.values():
            state = cast(State, state)
            if not state.externally_progressed:
                q = q | models.Q(
                    (
                        models.Q(
                            state_attempted__lte=timezone.now()
                            - datetime.timedelta(
                                seconds=cast(float, state.try_interval)
                            )
                        )
                        | models.Q(state_attempted__isnull=True)
                    ),
                    state=state.name,
                )
        await cls.objects.filter(q).aupdate(state_ready=True)

    @classmethod
    def transition_get_with_lock(
        cls, number: int, lock_expiry: datetime.datetime
    ) -> List["StatorModel"]:
        """
        Returns up to `number` tasks for execution, having locked them.
        """
        with transaction.atomic():
            selected = list(
                cls.objects.filter(state_locked_until__isnull=True, state_ready=True)[
                    :number
                ].select_for_update()
            )
            cls.objects.filter(pk__in=[i.pk for i in selected]).update(
                state_locked_until=lock_expiry
            )
        return selected

    @classmethod
    async def atransition_get_with_lock(
        cls, number: int, lock_expiry: datetime.datetime
    ) -> List["StatorModel"]:
        return await sync_to_async(cls.transition_get_with_lock)(number, lock_expiry)

    @classmethod
    async def atransition_clean_locks(cls):
        await cls.objects.filter(state_locked_until__lte=timezone.now()).aupdate(
            state_locked_until=None
        )

    def transition_schedule(self):
        """
        Adds this instance to the queue to get its state transition attempted.

        The scheduler will call this, but you can also call it directly if you
        know it'll be ready and want to lower latency.
        """
        self.state_ready = True
        self.save()

    async def atransition_attempt(self) -> Optional[State]:
        """
        Attempts to transition the current state by running its handler(s).
        """
        current_state = self.state_graph.states[self.state]
        # If it's a manual progression state don't even try
        # We shouldn't really be here in this case, but it could be a race condition
        if current_state.externally_progressed:
            print("Externally progressed state!")
            return None
        try:
            next_state = await current_state.handler(self)
        except BaseException as e:
            await StatorError.acreate_from_instance(self, e)
            traceback.print_exc()
        else:
            if next_state:
                # Ensure it's a State object
                if isinstance(next_state, str):
                    next_state = self.state_graph.states[next_state]
                # Ensure it's a child
                if next_state not in current_state.children:
                    raise ValueError(
                        f"Cannot transition from {current_state} to {next_state} - not a declared transition"
                    )
                await self.atransition_perform(next_state)
                return next_state
        await self.__class__.objects.filter(pk=self.pk).aupdate(
            state_attempted=timezone.now(),
            state_locked_until=None,
            state_ready=False,
        )
        return None

    def transition_perform(self, state: Union[State, str]):
        """
        Transitions the instance to the given state name, forcibly.
        """
        if isinstance(state, State):
            state = state.name
        if state not in self.state_graph.states:
            raise ValueError(f"Invalid state {state}")
        self.__class__.objects.filter(pk=self.pk).update(
            state=state,
            state_changed=timezone.now(),
            state_attempted=None,
            state_locked_until=None,
            state_ready=False,
        )

    atransition_perform = sync_to_async(transition_perform)


class StatorError(models.Model):
    """
    Tracks any errors running the transitions.
    Meant to be cleaned out regularly. Should probably be a log.
    """

    # appname.modelname (lowercased) label for the model this represents
    model_label = models.CharField(max_length=200)

    # The primary key of that model (probably int or str)
    instance_pk = models.CharField(max_length=200)

    # The state we were on
    state = models.CharField(max_length=200)

    # When it happened
    date = models.DateTimeField(auto_now_add=True)

    # Error name
    error = models.TextField()

    # Error details
    error_details = models.TextField(blank=True, null=True)

    @classmethod
    async def acreate_from_instance(
        cls,
        instance: StatorModel,
        exception: Optional[BaseException] = None,
    ):
        detail = traceback.format_exc()
        if exception and len(exception.args) > 1:
            detail += "\n\n" + "\n\n".join(
                pprint.pformat(arg) for arg in exception.args
            )

        return await cls.objects.acreate(
            model_label=instance._meta.label_lower,
            instance_pk=str(instance.pk),
            state=instance.state,
            error=str(exception),
            error_details=detail,
        )
