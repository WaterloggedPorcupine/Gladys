"""Port contract suites, shared by the in-memory fakes (unit) and the real adapters (integration).

Each suite is a plain base class (not named ``Test*``, so pytest does not collect it directly).
A concrete ``Test*`` subclass supplies the adapter through a fixture.
"""
