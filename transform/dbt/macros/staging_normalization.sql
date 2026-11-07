{# Missing markers are field-specific; business codes are never globally remapped. #}
{# ------------------------------------------------------------------------ #}
{# 01. Text whitespace and missing-value markers #}
{# ------------------------------------------------------------------------ #}
{% macro stg_text(value, missing=[]) -%}
    {%- set trimmed = "replaceRegexpAll(toString(" ~ value ~ "), '^[\\\\s\\\\x{00A0}]+|[\\\\s\\\\x{00A0}]+$', '')" -%}
    {%- if missing %}
    if(lowerUTF8({{ trimmed }}) in ({% for token in missing %}'{{ token }}'{% if not loop.last %}, {% endif %}{% endfor %}),
       CAST(NULL AS Nullable(String)), nullIf({{ trimmed }}, ''))
    {%- else %}
    nullIf({{ trimmed }}, '')
    {%- endif -%}
{%- endmacro %}

{# ------------------------------------------------------------------------ #}
{# 02. Integer syntax, positivity and overflow #}
{# ------------------------------------------------------------------------ #}
{% macro stg_integer(value, target, positive=false) -%}
    {%- set base = target[9:-1] if target.startswith('Nullable(') else target -%}
    CAST(if(isNull({{ value }}), NULL,
        accurateCast(ifNull(if(isNull({{ value }}), '0', if(match({{ value }}, '{% if positive %}^0*[1-9][0-9]*${% else %}^[0-9]+${% endif %}'),
            {{ value }}, 'INVALID_{{ value }}')), '0'), '{{ base }}')) AS {{ target }})
{%- endmacro %}

{# ------------------------------------------------------------------------ #}
{# 03. Decimal precision, scale and percentage bounds #}
{# ------------------------------------------------------------------------ #}
{% macro stg_decimal(value, target, precision=18, scale=6, percentage=false) -%}
    {%- set base = target[9:-1] if target.startswith('Nullable(') else target -%}
    {%- set number = "replaceAll(trimBoth(replaceRegexpOne(" ~ value ~ ", '%$', '')), ',', '.')" if percentage else value -%}
    {%- set fraction = "replaceRegexpOne(extract(" ~ number ~ ", '[.]([0-9]+)$'), '0+$', '')" -%}
    {%- set integer = "replaceRegexpOne(extract(" ~ number ~ ", '^[+-]?([0-9]+)'), '^0+', '')" -%}
    {# Parse a non-nullable value FIRST: casting bad text directly to Nullable may silently return NULL. #}
    CAST(if(isNull({{ value }}), NULL,
        CAST(ifNull(if(isNull({{ value }}), '0', if(match({{ number }}, '^[+-]?[0-9]+([.][0-9]+)?$')
           and length({{ fraction }}) <= {{ scale }}
           and length({{ integer }}) <= {{ precision - scale }}
           {% if percentage %}
           and toDecimal128OrNull({{ number }}, {{ scale }}) between 0 and 100
           {% endif %},
           {{ number }}, 'INVALID_{{ value }}')), '0') AS {{ base }})) AS {{ target }})
{%- endmacro %}

{# ------------------------------------------------------------------------ #}
{# 04. Calendar date format, bounds and round-trip validation #}
{# ------------------------------------------------------------------------ #}
{% macro stg_date(value, target) -%}
    {%- set base = target[9:-1] if target.startswith('Nullable(') else target -%}
    CAST(if(isNull({{ value }}), NULL,
        CAST(ifNull(if(isNull({{ value }}), '1970-01-01', if(match({{ value }}, '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
           and {{ value }} between '1900-01-01' and '2299-12-31'
           and toString(toDate32OrNull({{ value }})) = {{ value }},
           {{ value }}, 'INVALID_{{ value }}')), '1970-01-01') AS {{ base }})) AS {{ target }})
{%- endmacro %}

{# ------------------------------------------------------------------------ #}
{# 05. Timestamp format, microseconds and calendar validation #}
{# ------------------------------------------------------------------------ #}
{% macro stg_timestamp(value, target) -%}
    {%- set base = target[9:-1] if target.startswith('Nullable(') else target -%}
    {%- set timestamp = "replaceAll(" ~ value ~ ", 'T', ' ')" -%}
    CAST(if(isNull({{ value }}), NULL,
        CAST(ifNull(if(isNull({{ value }}), '1970-01-01 00:00:00', if(match({{ timestamp }}, '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]{1,6})?$')
           and substring({{ timestamp }}, 1, 10) between '1900-01-01' and '2299-12-31'
           and toString(toDateTime64OrNull({{ timestamp }}, 6)) =
               concat(substring({{ timestamp }}, 1, 19), '.', rightPad(extract({{ timestamp }}, '[.]([0-9]+)$'), 6, '0')),
           {{ timestamp }}, 'INVALID_{{ value }}')), '1970-01-01 00:00:00') AS {{ base }})) AS {{ target }})
{%- endmacro %}

{# ------------------------------------------------------------------------ #}
{# 06. Categorical normalization and explicit allowed labels #}
{# ------------------------------------------------------------------------ #}
{% macro stg_domain(value, target, allowed) -%}
    {%- set canonical = "upperUTF8(replaceRegexpAll(" ~ value ~ ", '[\\\\s\\\\x{00A0}]+', ' '))" -%}
    CAST(if(isNull({{ value }}), NULL,
        CAST(CAST(ifNull({{ canonical }}, '{{ allowed[0] }}') AS Enum8(
            {% for label in allowed %}'{{ label }}' = {{ loop.index }}{% if not loop.last %}, {% endif %}{% endfor %}
        )) AS String)) AS {{ target }})
{%- endmacro %}
