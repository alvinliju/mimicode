"""helpers with several references to `foo` that need a coordinated rename."""


def foo() -> str:
    return "foo result"


def caller_one() -> str:
    return foo()


def caller_two() -> str:
    return foo() + "_" + foo()


VALUE = foo()
