import secrets
import time


class Snowflake:
    """
    Snowflake ID generator and parser.
    """

    # Epoch is 2022/1/1 at midnight, as these are used for _created_ times in our
    # own database, not original publish times (which would need an earlier one)
    EPOCH = 1641020400

    TYPE_POST = 0b000
    TYPE_POST_INTERACTION = 0b001
    TYPE_IDENTITY = 0b010
    TYPE_REPORT = 0b011
    TYPE_FOLLOW = 0b100

    @classmethod
    def generate(cls, type_id: int) -> int:
        """
        Generates a snowflake-style ID for the given "type". They are designed
        to fit inside 63 bits (a signed bigint)

        ID layout is:
        * 41 bits of millisecond-level timestamp (enough for EPOCH + 69 years)
        * 19 bits of random data (1% chance of clash at 10000 per millisecond)
        * 3 bits of type information

        We use random data rather than a sequence ID to try and avoid pushing
        this job onto the DB - we may do that in future. If a clash does
        occur, the insert will fail and Stator will retry the work for anything
        that's coming in remotely, leaving us to just handle that scenario for
        our own posts, likes, etc.
        """
        # Get the current time in milliseconds
        now: int = int((time.time() - cls.EPOCH) * 1000)
        # Generate random data
        rand_seq: int = secrets.randbits(19)
        # Compose them together
        return (now << 22) | (rand_seq << 3) | type_id

    @classmethod
    def get_type(cls, snowflake: int) -> int:
        """
        Returns the type of a given snowflake ID
        """
        if snowflake < (1 << 22):
            raise ValueError("Not a valid Snowflake ID")
        return snowflake & 0b111

    @classmethod
    def get_time(cls, snowflake: int) -> float:
        """
        Returns the generation time (in UNIX timestamp seconds) of the ID
        """
        if snowflake < (1 << 22):
            raise ValueError("Not a valid Snowflake ID")
        return ((snowflake >> 22) / 1000) + cls.EPOCH

    # Handy pre-baked methods for django model defaults
    @classmethod
    def generate_post(cls) -> int:
        return cls.generate(cls.TYPE_POST)

    @classmethod
    def generate_post_interaction(cls) -> int:
        return cls.generate(cls.TYPE_POST_INTERACTION)

    @classmethod
    def generate_identity(cls) -> int:
        return cls.generate(cls.TYPE_IDENTITY)

    @classmethod
    def generate_report(cls) -> int:
        return cls.generate(cls.TYPE_REPORT)

    @classmethod
    def generate_follow(cls) -> int:
        return cls.generate(cls.TYPE_FOLLOW)
