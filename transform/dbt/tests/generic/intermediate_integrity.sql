{# ========================================================================= #}
{# GRAIN: no duplicate combinations, including partially missing keys.         #}
{# ========================================================================= #}
{% test unique_grain(model, columns) %}
select
    {% for column in columns %}{{ adapter.quote(column) }}{% if not loop.last %}, {% endif %}{% endfor %},
    count() as row_count
from {{ model }}
group by {% for column in columns %}{{ adapter.quote(column) }}{% if not loop.last %}, {% endif %}{% endfor %}
having row_count > 1
{% endtest %}

{# ========================================================================= #}
{# LINEAGE: bidirectional source-key coverage and exact column preservation.  #}
{# ========================================================================= #}
{% test preserves_source_rows(model, source_relation, primary_key) %}
{% set source_columns = adapter.get_columns_in_relation(source_relation) if execute else [] %}
{# A fresh DW has no materialized parents yet. Use their declared schema so that #}
{# compile still validates the full projection before the first dbt build.       #}
{% if execute and not source_columns %}
    {% for node in graph.nodes.values() if node.resource_type == 'model'
        and node.alias == source_relation.identifier and node.schema == source_relation.schema %}
        {% for column in node.columns.values() %}
            {% do source_columns.append(column) %}
        {% endfor %}
    {% endfor %}
{% endif %}
{% if execute and not source_columns %}
    {{ exceptions.raise_compiler_error('Source column metadata is required for preservation testing: ' ~ source_relation) }}
{% endif %}
select
    coalesce(expected.{{ adapter.quote(primary_key) }}, actual.{{ adapter.quote(primary_key) }}) as source_id
from {{ source_relation }} as expected
full outer join {{ model }} as actual
    on expected.{{ adapter.quote(primary_key) }} = actual.{{ adapter.quote(primary_key) }}
where expected.{{ adapter.quote(primary_key) }} is null
    or actual.{{ adapter.quote(primary_key) }} is null
    {% for column in source_columns %}
    or (isNull(expected.{{ adapter.quote(column.name) }}) != isNull(actual.{{ adapter.quote(column.name) }})
        or ifNull(expected.{{ adapter.quote(column.name) }} != actual.{{ adapter.quote(column.name) }}, false))
    {% endfor %}
settings join_use_nulls = 1
{% endtest %}
