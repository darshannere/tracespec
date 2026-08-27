import tracespec


def test_version():
    assert isinstance(tracespec.__version__, str)
    assert len(tracespec.__version__.split(".")) == 3
