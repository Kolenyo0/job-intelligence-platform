with ranked_postings as (
    select
        *,
        row_number() over (
            partition by source, source_id
            order by
                ingested_at desc nulls last,
                created_at desc nulls last,
                company_name asc nulls last,
                job_title asc nulls last,
                location asc nulls last,
                remote asc nulls last,
                job_types asc nulls last    
        ) as posting_rank
    from {{ ref('stg_job_postings') }}
)

select
    source,
    source_id,
    company_name,
    job_title,
    remote,
    location,
    job_types,
    created_at,
    ingested_at
from ranked_postings
-- where posting_rank = 1
