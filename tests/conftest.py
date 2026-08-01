from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def pytest_addoption(parser):
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help="Rewrite committed golden snapshot files from current parser output.",
    )


@pytest.fixture
def update_goldens(request) -> bool:
    return request.config.getoption("--update-goldens")


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
