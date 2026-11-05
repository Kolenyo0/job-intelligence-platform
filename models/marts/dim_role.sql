with role_entities as (
    select
        case
            when nullif(lower(btrim(job_title)), '') is null then 'null:'
            else 'value:' || lower(btrim(job_title))
        end as role_identity,
        coalesce(min(job_title), 'Unknown') as job_title
    from {{ ref('int_job_postings') }}
    group by 1
)

select
    md5('role|' || role_identity) as role_key,
    job_title
from role_entities
