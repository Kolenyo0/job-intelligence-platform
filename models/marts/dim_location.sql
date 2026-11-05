with location_entities as (
    select
        case
            when nullif(lower(btrim(location)), '') is null then 'null:'
            else 'value:' || lower(btrim(location))
        end as location_identity,
        coalesce(min(location), 'Unknown') as location_name
    from {{ ref('int_job_postings') }}
    group by 1
)

select
    md5('location|' || location_identity) as location_key,
    location_name
from location_entities
