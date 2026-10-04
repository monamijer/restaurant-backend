import threading

from django.db import connection

from apps.core.api import ConflictError

BARRIER_TIMEOUT_SECONDS = 20


def run_concurrently(attempts):
    """Run each callable in its own thread, all released at the same instant.

    Returns one label per attempt: "ok", "conflict", or "unexpected: <error>"."""
    barrier = threading.Barrier(len(attempts))
    outcomes = []

    def worker(attempt):
        try:
            barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
            attempt()
            outcomes.append("ok")
        except ConflictError:
            outcomes.append("conflict")
        except Exception as error:  # Anything else (deadlock, timeout) must fail the test.
            outcomes.append(f"unexpected: {error!r}")
        finally:
            connection.close()  # Each thread owns its own database connection.

    threads = [threading.Thread(target=worker, args=(attempt,)) for attempt in attempts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return outcomes