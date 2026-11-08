{% test matches_declared_schema(model) %}
{% set columns = [] %}
{% if execute %}
    {% for node in graph.nodes.values() if node.resource_type == 'model'
        and node.alias == model.identifier and node.schema == model.schema %}
        {% for column in node.columns.values() %}
            {% do columns.append(column) %}
        {% endfor %}
    {% endfor %}
    {% if not columns %}
        {{ exceptions.raise_compiler_error('Declared columns are required for ' ~ model) }}
    {% endif %}
{% endif %}
with expected as (
    {% for column in columns %}
    select '{{ column.name }}' as column_name,
        '{{ column.data_type }}' as column_type, toUInt64({{ loop.index }}) as position
    {% if not loop.last %}union all{% endif %}
    {% else %}
    select '' as column_name, '' as column_type, toUInt64(0) as position where false
    {% endfor %}
), actual as (
    select name as column_name, type as column_type, position
    from system.columns
    where database = '{{ model.schema }}' and table = '{{ model.identifier }}'
)
select coalesce(expected.column_name, actual.column_name) as column_name
from expected
full outer join actual on expected.column_name = actual.column_name
where expected.column_name is null or actual.column_name is null
    or replaceAll(expected.column_type, ' ', '') != replaceAll(actual.column_type, ' ', '')
    or expected.position != actual.position
settings join_use_nulls = 1
{% endtest %}

{% test dimensional_join_cardinality(model, grain, dimensions) %}
-- LEFT joins retain unmatched facts; relationship tests reject orphan references.
select
    {% for column in grain %}facts.{{ adapter.quote(column) }}{% if not loop.last %}, {% endif %}{% endfor %},
    count() as joined_rows
from {{ model }} as facts
{% for dimension in dimensions %}
left join {{ dimension.to }} as dimension_{{ loop.index }}
    on facts.{{ adapter.quote(dimension.field) }} = dimension_{{ loop.index }}.{{ adapter.quote(dimension.target_field) }}
{% endfor %}
group by {% for column in grain %}facts.{{ adapter.quote(column) }}{% if not loop.last %}, {% endif %}{% endfor %}
having joined_rows != 1
settings join_use_nulls = 1
{% endtest %}
