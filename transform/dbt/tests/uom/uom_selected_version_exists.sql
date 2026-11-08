-- Empty/unpublished version is an error, including when no sales exist.
select {{ uom_mapping_version_literal() }} as missing_mapping_version
from {{ ref('uom_conversion_mapping') }}
having countIf(mapping_version = {{ uom_mapping_version_literal() }}) = 0
