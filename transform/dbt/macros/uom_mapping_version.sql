{# One explicit version per run; allow no interpolation outside its identifier format. #}
{% macro uom_mapping_version_literal() %}
    {% set version = var('uom_mapping_version') %}
    {% if version is not string or modules.re.fullmatch('uom_mapping_v[1-9][0-9]*_[0-9]{4}-[0-9]{2}-[0-9]{2}', version) is none %}
        {{ exceptions.raise_compiler_error('uom_mapping_version must name one published mapping version') }}
    {% endif %}
    {{ return("'" ~ version ~ "'") }}
{% endmacro %}
