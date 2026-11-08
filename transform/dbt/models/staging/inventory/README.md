# Inventory staging SQL

Inventory documents/movements and product batches. Every model in this folder is a one-to-one typed view over a raw source table. The [Staging model guide](../README.md) documents each model's inputs, grain, important fields, normalization rules, downstream dependencies and tests. Column contracts stay in [the shared YAML](../_staging.yml); do not duplicate parsers or create business aggregates in this directory.
