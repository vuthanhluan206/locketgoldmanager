from pathlib import Path
from tempfile import TemporaryDirectory


def pytest_configure(config):
    if config.option.basetemp is None:
        # Avoid shared pytest-of-<user> folders with stale Windows permissions.
        temporary = TemporaryDirectory(prefix='locket-pytest-')
        config.add_cleanup(temporary.cleanup)
        config.option.basetemp = Path(temporary.name) / 'run'
