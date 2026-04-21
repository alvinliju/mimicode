"""mimicode: a minimal coding agent. entry point."""
from logger import log


def main() -> None:
    log("session_start", {})
    print(f"mimicode ready. not much to do yet.")


if __name__ == "__main__":
    main()
