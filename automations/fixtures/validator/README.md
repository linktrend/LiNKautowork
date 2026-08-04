# Catalogue validator fixtures

These files exercise n8n graph and source-content checks that are not expressible in the GAP JSON Schemas. The test suite copies the Golden Automation Package into a temporary directory, substitutes one fixture, and expects a safe, named validation error without echoing a sensitive value.
