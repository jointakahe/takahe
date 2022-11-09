import datetime
from functools import reduce
from typing import Type, cast

from asgiref.sync import sync_to_async
from django.apps import apps
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

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return self.graph.states[value]

    def to_python(self, value):
        if isinstance(value, State) or value is None:
            return value
        return self.graph.states[value]

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

    # When the state last actually changed, or the date of instance creation
    state_changed = models.DateTimeField(auto_now_add=True)

    # When the last state change for the current state was attempted
    # (and not successful, as this is cleared on transition)
    state_attempted = models.DateTimeField(blank=True, null=True)

    class Meta:
        abstract = True

    @classmethod
    def schedule_overdue(cls, now=None) -> models.QuerySet:
        """
        Finds instances of this model that need to run and schedule them.
        """
        q = models.Q()
        for transition in cls.state_graph.transitions(automatic_only=True):
            q = q | transition.get_query(now=now)
        return cls.objects.filter(q)

    @classproperty
    def state_graph(cls) -> Type[StateGraph]:
        return cls._meta.get_field("state").graph

    def schedule_transition(self, priority: int = 0):
        """
        Adds this instance to the queue to get its state transition attempted.

        The scheduler will call this, but you can also call it directly if you
        know it'll be ready and want to lower latency.
        """
        StatorTask.schedule_for_execution(self, priority=priority)

    async def attempt_transition(self):
        """
        Attempts to transition the current state by running its handler(s).
        """
        # Try each transition in priority order
        for transition in self.state_graph.states[self.state].transitions(
            automatic_only=True
        ):
            success = await transition.get_handler()(self)
            if success:
                await self.perform_transition(transition.to_state.name)
                return
        await self.__class__.objects.filter(pk=self.pk).aupdate(
            state_attempted=timezone.now()
        )

    async def perform_transition(self, state_name):
        """
        Transitions the instance to the given state name
        """
        if state_name not in self.state_graph.states:
            raise ValueError(f"Invalid state {state_name}")
        await self.__class__.objects.filter(pk=self.pk).aupdate(
            state=state_name,
            state_changed=timezone.now(),
            state_attempted=None,
        )


class StatorTask(models.Model):
    """
    The model that we use for an internal scheduling queue.

    Entries in this queue are up for checking and execution - it also performs
    locking to ensure we get closer to exactly-once execution (but we err on
    the side of at-least-once)
    """

    # appname.modelname (lowercased) label for the model this represents
    model_label = models.CharField(max_length=200)

    # The primary key of that model (probably int or str)
    instance_pk = models.CharField(max_length=200)

    # Locking columns (no runner ID, as we have no heartbeats - all runners
    # only live for a short amount of time anyway)
    locked_until = models.DateTimeField(null=True, blank=True)

    # Basic total ordering priority - higher is more important
    priority = models.IntegerField(default=0)

    def __str__(self):
        return f"#{self.pk}: {self.model_label}.{self.instance_pk}"

    @classmethod
    def schedule_for_execution(cls, model_instance: StatorModel, priority: int = 0):
        # We don't do a transaction here as it's fine to occasionally double up
        model_label = model_instance._meta.label_lower
        pk = model_instance.pk
        # TODO: Increase priority of existing if present
        if not cls.objects.filter(
            model_label=model_label, instance_pk=pk, locked__isnull=True
        ).exists():
            StatorTask.objects.create(
                model_label=model_label,
                instance_pk=pk,
                priority=priority,
            )

    @classmethod
    def get_for_execution(cls, number: int, lock_expiry: datetime.datetime):
        """
        Returns up to `number` tasks for execution, having locked them.
        """
        with transaction.atomic():
            selected = list(
                cls.objects.filter(locked_until__isnull=True)[
                    :number
                ].select_for_update()
            )
            cls.objects.filter(pk__in=[i.pk for i in selected]).update(
                locked_until=timezone.now()
            )
        return selected

    @classmethod
    async def aget_for_execution(cls, number: int, lock_expiry: datetime.datetime):
        return await sync_to_async(cls.get_for_execution)(number, lock_expiry)

    @classmethod
    async def aclean_old_locks(cls):
        await cls.objects.filter(locked_until__lte=timezone.now()).aupdate(
            locked_until=None
        )

    async def aget_model_instance(self) -> StatorModel:
        model = apps.get_model(self.model_label)
        return cast(StatorModel, await model.objects.aget(pk=self.pk))

    async def adelete(self):
        self.__class__.objects.adelete(pk=self.pk)
