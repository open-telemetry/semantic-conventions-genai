def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Rewrite the `errors:` block of every case file under tests/cases from the current schemas.",
    )
