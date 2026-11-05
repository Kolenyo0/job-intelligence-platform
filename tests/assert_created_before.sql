-- tests/assert_created_before_ingested.sql

select
    source,
    source_id,
    created_at,
    ingested_at
from {{ ref('fact_job_posting') }}
where created_at > ingested_at