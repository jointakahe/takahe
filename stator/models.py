import datetime
import traceback
from typing import ClassVar

from asgiref.sync import async_to_sync, iscoroutinefunction
from django.db import models, transaction
from django.db.models.signals import class_prepared
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


def add_stator_indexes(sender, **kwargs):
    """
    Inject Indexes used by StatorModel in to any subclasses. This sidesteps the
    current Django inability to inherit indexes when the Model subclass defines
    its own indexes.
    """
    if issubclass(sender, StatorModel):
        indexes = [
            models.Index(
                fields=["state", "state_next_attempt", "state_locked_until"],
                name=f"ix_{sender.__name__.lower()[:11]}_state_next",
            ),
        ]

        if not sender._meta.indexes:
            # Meta.indexes needs to not be None to trigger Django behaviors
            sender.Meta.indexes = []
            sender._meta.indexes = []

        for idx in indexes:
            sender._meta.indexes.append(idx)


# class_prepared might become deprecated [1]. If it's removed, the named Index
# injection would need to happen in a metaclass subclass of ModelBase's _prepare()
#
# [1] https://code.djangoproject.com/ticket/24313
class_prepared.connect(add_stator_indexes)


class StatorModel(models.Model):
    """
    A model base class that has a state machine backing it, with tasks to work
    out when to move the state to the next one.

    You need to provide a "state" field as an instance of StateField on the
    concrete model yourself.
    """

    CLEAN_BATCH_SIZE = 1000
    DELETE_BATCH_SIZE = 500

    state: StateField

    # When the state last actually changed, or the date of instance creation
    state_changed = models.DateTimeField(auto_now_add=True)

    # When the next state change should be attempted (null means immediately)
    state_next_attempt = models.DateTimeField(blank=True, null=True)

    # If a lock is out on this row, when it is locked until
    # (we don't identify the lock owner, as there's no heartbeats)
    state_locked_until = models.DateTimeField(null=True, blank=True, db_index=True)

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
    def state_age(self) -> float:
        return (timezone.now() - self.state_changed).total_seconds()

    @classmethod
    def transition_get_with_lock(
        cls, number: int, lock_expiry: datetime.datetime
    ) -> list["StatorModel"]:
        """
        Returns up to `number` tasks for execution, having locked them.
        """
        with transaction.atomic():
            # Query for `number` rows that:
            #  - Have a next_attempt that's either null or in the past
            #  - Have one of the states we care about
            # Then, sort them by next_attempt NULLS FIRST, so that we handle the
            # rows in a roughly FIFO order.
            selected = list(
                cls.objects.filter(
                    models.Q(state_next_attempt__isnull=True)
                    | models.Q(state_next_attempt__lte=timezone.now()),
                    state__in=cls.state_graph.automatic_states,
                    state_locked_until__isnull=True,
                )[:number].select_for_update()
            )
            cls.objects.filter(pk__in=[i.pk for i in selected]).update(
                state_locked_until=lock_expiry
            )
        return selected

    @classmethod
    def transition_delete_due(cls) -> int | None:
        """
        Finds instances of this model that need to be deleted and deletes them
        in small batches. Returns how many were deleted.
        """
        if cls.state_graph.deletion_states:
            constraints = models.Q()
            for state in cls.state_graph.deletion_states:
                constraints |= models.Q(
                    state=state,
                    state_changed__lte=(
                        timezone.now() - datetime.timedelta(seconds=state.delete_after)
                    ),
                )
            select_query = cls.objects.filter(
                models.Q(state_next_attempt__isnull=True)
                | models.Q(state_next_attempt__lte=timezone.now()),
                constraints,
            )[: cls.DELETE_BATCH_SIZE]
            return cls.objects.filter(pk__in=select_query).delete()[0]
        return None

    @classmethod
    def transition_ready_count(cls) -> int:
        """
        Returns how many instances are "queued"
        """
        return cls.objects.filter(
            models.Q(state_next_attempt__isnull=True)
            | models.Q(state_next_attempt__lte=timezone.now()),
            state_locked_until__isnull=True,
            state__in=cls.state_graph.automatic_states,
        ).count()

    @classmethod
    def transition_clean_locks(cls):
        """
        Deletes stale locks (in batches, to avoid a giant query)
        """
        select_query = cls.objects.filter(state_locked_until__lte=timezone.now())[
            : cls.CLEAN_BATCH_SIZE
        ]
        cls.objects.filter(pk__in=select_query).update(state_locked_until=None)

    def transition_attempt(self) -> State | None:
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

        # Try running its handler function
        try:
            if iscoroutinefunction(current_state.handler):
                next_state = async_to_sync(current_state.handler)(self)
            else:
                next_state = current_state.handler(self)
        except TryAgainLater:
            pass
        except BaseException as e:
            exceptions.capture_exception(e)
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
                self.transition_perform(next_state)
                return next_state

        # See if it timed out since its last state change
        if (
            current_state.timeout_value
            and current_state.timeout_value
            <= (timezone.now() - self.state_changed).total_seconds()
        ):
            self.transition_perform(current_state.timeout_state)  # type: ignore
            return current_state.timeout_state

        # Nothing happened, set next execution and unlock it
        self.__class__.objects.filter(pk=self.pk).update(
            state_next_attempt=(
                timezone.now() + datetime.timedelta(seconds=current_state.try_interval)  # type: ignore
            ),
            state_locked_until=None,
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

    @classmethod
    def transition_perform_queryset(
        cls,
        queryset: models.QuerySet,
        state: State | str,
    ):
        """
        Transitions every instance in the queryset to the given state name, forcibly.
        """
        # Really ensure we have the right state object
        if isinstance(state, State):
            state_obj = cls.state_graph.states[state.name]
        else:
            state_obj = cls.state_graph.states[state]
        # See if it's ready immediately (if not, delay until first try_interval)
        if state_obj.attempt_immediately or state_obj.try_interval is None:
            queryset.update(
                state=state_obj,
                state_changed=timezone.now(),
                state_next_attempt=None,
                state_locked_until=None,
            )
        else:
            queryset.update(
                state=state_obj,
                state_changed=timezone.now(),
                state_next_attempt=(
                    timezone.now() + datetime.timedelta(seconds=state_obj.try_interval)
                ),
                state_locked_until=None,
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
