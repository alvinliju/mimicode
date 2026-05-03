"""small helpers."""
foo = 42


def use_foo() -> int:
    return foo * 2


def twice_foo() -> int:
    return foo + foo
