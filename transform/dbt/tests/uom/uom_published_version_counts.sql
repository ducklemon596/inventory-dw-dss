-- Immutable research snapshots, not universal counts for newly published versions.
with expected as (
    select 'uom_mapping_v1_2026-11-08' as mapping_version, 190 as pairs, 182 as skus,
        73 as approved, 87 as candidate, 30 as quarantined
    union all
    select 'uom_mapping_v2_2026-11-08', 207, 197, 87, 89, 31
), actual as (
    select mapping_version, count() as pairs, uniqExact(product_id) as skus,
        countIf(approval_status = 'approved') as approved,
        countIf(approval_status = 'candidate') as candidate,
        countIf(approval_status = 'quarantined') as quarantined
    from {{ ref('uom_conversion_mapping') }} group by mapping_version
)
select actual.mapping_version
from actual left join expected on actual.mapping_version = expected.mapping_version
where expected.mapping_version is null or actual.pairs != expected.pairs
    or actual.skus != expected.skus or actual.approved != expected.approved
    or actual.candidate != expected.candidate or actual.quarantined != expected.quarantined
settings join_use_nulls = 1
