import datetime
import traceback
from typing import ClassVar, cast

from asgiref.sync import sync_to_async
from django.db import models, transaction
from django.utils import timezone
from django.utils.functional import classproperty

from core import exceptions
from stator.exceptions import TryAgainLater
from stator.graph import State, StateGraph


class StateField(models.CharField):
    """
    A special field that automatically gets choices from a state graph
    """

    def __init__(self, graph: type[StateGraph], **kwargs):
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

    # If this row is up for transition attempts (which it always is on creation!)
    state_ready = models.BooleanField(default=True)

    # When the state last actually changed, or the date of instance creation
    state_changed = models.DateTimeField(auto_now_add=True)

    # When the last state change for the current state was attempted
    # (and not successful, as this is cleared on transition)
    state_attempted = models.DateTimeField(blank=True, null=True)

    # If a lock is out on this row, when it is locked until
    # (we don't identify the lock owner, as there's no heartbeats)
    state_locked_until = models.DateTimeField(null=True, blank=True)

    # Collection of subclasses of us
    subclasses: ClassVar[list[type["StatorModel"]]] = []

    class Meta:
        abstract = True

    def __init_subclass__(cls) -> None:
        if cls is not StatorModel:
            cls.subclasses.append(cls)

    @classproperty
    def state_graph(cls) -> type[StateGraph]:
        return cls._meta.get_field("state").graph

    @property
    def state_age(self) -> int:
        return (timezone.now() - self.state_changed).total_seconds()

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
    ) -> list["StatorModel"]:
        """
        Returns up to `number` tasks for execution, having locked them.
        """
        with transaction.atomic():
            selected = list(
                cls.objects.filter(
                    state_locked_until__isnull=True,
                    state_ready=True,
                    state__in=cls.state_graph.automatic_states,
                )[:number].select_for_update()
            )
            cls.objects.filter(pk__in=[i.pk for i in selected]).update(
                state_locked_until=lock_expiry
            )
        return selected

    @classmethod
    async def atransition_get_with_lock(
        cls, number: int, lock_expiry: datetime.datetime
    ) -> list["StatorModel"]:
        return await sync_to_async(cls.transition_get_with_lock)(number, lock_expiry)

    @classmethod
    async def atransition_ready_count(cls) -> int:
        """
        Returns how many instances are "queued"
        """
        return await (
            cls.objects.filter(
                state_locked_until__isnull=True,
                state_ready=True,
                state__in=cls.state_graph.automatic_states,
            ).acount()
        )

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

    async def atransition_attempt(self) -> State | None:
        """
        Attempts to transition the current state by running its handler(s).
        """
        current_state: State = self.state_graph.states[self.state]
        # If it's a manual progression state don't even try
        # We shouldn't really be here in this case, but it could be a race condition
        if current_state.externally_progressed:
            print(
                f"Warning: trying to progress externally progressed state {self.state}!"
            )
            return None
        try:
            next_state = await current_state.handler(self)  # type: ignore
        except TryAgainLater:
            pass
        except BaseException as e:
            await exceptions.acapture_exception(e)
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
        # See if it timed out
        if (
            current_state.timeout_value
            and current_state.timeout_value
            <= (timezone.now() - self.state_changed).total_seconds()
        ):
            await self.atransition_perform(current_state.timeout_state)
            return current_state.timeout_state
        await self.__class__.objects.filter(pk=self.pk).aupdate(
            state_attempted=timezone.now(),
            state_locked_until=None,
            state_ready=False,
        )
        return None

    def transition_perform(self, state: State | str):
        """
        Transitions the instance to the given state name, forcibly.
        """
        self.transition_perform_queryset(
            self.__class__.objects.filter(pk=self.pk),
            state,
        )

    atransition_perform = sync_to_async(transition_perform)

    @classmethod
    def transition_perform_queryset(
        cls,
        queryset: models.QuerySet,
        state: State | str,
    ):
        """
        Transitions every instance in the queryset to the given state name, forcibly.
        """
        if isinstance(state, State):
            state = state.name
        if state not in cls.state_graph.states:
            raise ValueError(f"Invalid state {state}")
        # See if it's ready immediately (if not, delay until first try_interval)
        if cls.state_graph.states[state].attempt_immediately:
            queryset.update(
                state=state,
                state_changed=timezone.now(),
                state_attempted=None,
                state_locked_until=None,
                state_ready=True,
            )
        else:
            queryset.update(
                state=state,
                state_changed=timezone.now(),
                state_attempted=timezone.now(),
                state_locked_until=None,
                state_ready=False,
            )


class Stats(models.Model):
    """
    Tracks summary statistics of each model over time.
    """

    # appname.modelname (lowercased) label for the model this represents
    model_label = models.CharField(max_length=200, primary_key=True)

    statistics = models.JSONField()

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Stats"

    @classmethod
    def get_for_model(cls, model: type[StatorModel]) -> "Stats":
        instance = cls.objects.filter(model_label=model._meta.label_lower).first()
        if instance is None:
            instance = cls(model_label=model._meta.label_lower)
        if not instance.statistics:
            instance.statistics = {}
        # Ensure there are the right keys
        for key in ["queued", "hourly", "daily", "monthly"]:
            if key not in instance.statistics:
                instance.statistics[key] = {}
        return instance

    @classmethod
    async def aget_for_model(cls, model: type[StatorModel]) -> "Stats":
        return await sync_to_async(cls.get_for_model)(model)

    def set_queued(self, number: int):
        """
        Sets the current queued amount.

        The queue is an instantaneous value (a "gauge") rather than a
        sum ("counter"). It's mostly used for reporting what things are right
        now, but basic trend analysis is also used to see if we think the
        queue is backing up.
        """
        self.statistics["queued"][
            int(timezone.now().replace(second=0, microsecond=0).timestamp())
        ] = number

    def add_handled(self, number: int):
        """
        Adds the "handled" number to the current stats.
        """
        hour = timezone.now().replace(minute=0, second=0, microsecond=0)
        day = hour.replace(hour=0)
        hour_timestamp = str(int(hour.timestamp()))
        day_timestamp = str(int(day.timestamp()))
        month_timestamp = str(int(day.replace(day=1).timestamp()))
        self.statistics["hourly"][hour_timestamp] = (
            self.statistics["hourly"].get(hour_timestamp, 0) + number
        )
        self.statistics["daily"][day_timestamp] = (
            self.statistics["daily"].get(day_timestamp, 0) + number
        )
        self.statistics["monthly"][month_timestamp] = (
            self.statistics["monthly"].get(month_timestamp, 0) + number
        )

    def trim_data(self):
        """
        Removes excessively old data from the field
        """
        queued_horizon = int((timezone.now() - datetime.timedelta(hours=2)).timestamp())
        hourly_horizon = int(
            (timezone.now() - datetime.timedelta(hours=50)).timestamp()
        )
        daily_horizon = int((timezone.now() - datetime.timedelta(days=62)).timestamp())
        monthly_horizon = int(
            (timezone.now() - datetime.timedelta(days=3653)).timestamp()
        )
        self.statistics["queued"] = {
            ts: v
            for ts, v in self.statistics["queued"].items()
            if int(ts) >= queued_horizon
        }
        self.statistics["hourly"] = {
            ts: v
            for ts, v in self.statistics["hourly"].items()
            if int(ts) >= hourly_horizon
        }
        self.statistics["daily"] = {
            ts: v
            for ts, v in self.statistics["daily"].items()
            if int(ts) >= daily_horizon
        }
        self.statistics["monthly"] = {
            ts: v
            for ts, v in self.statistics["monthly"].items()
            if int(ts) >= monthly_horizon
        }

    def most_recent_queued(self) -> int:
        """
        Returns the most recent number of how many were queued
        """
        queued = [(int(ts), v) for ts, v in self.statistics["queued"].items()]
        queued.sort(reverse=True)
        if queued:
            return queued[0][1]
        else:
            return 0

    def most_recent_handled(self) -> tuple[int, int, int]:
        """
        Returns the current handling numbers for hour, day, month
        """
        hour = timezone.now().replace(minute=0, second=0, microsecond=0)
        day = hour.replace(hour=0)
        hour_timestamp = str(int(hour.timestamp()))
        day_timestamp = str(int(day.timestamp()))
        month_timestamp = str(int(day.replace(day=1).timestamp()))
        return (
            self.statistics["hourly"].get(hour_timestamp, 0),
            self.statistics["daily"].get(day_timestamp, 0),
            self.statistics["monthly"].get(month_timestamp, 0),
        )
