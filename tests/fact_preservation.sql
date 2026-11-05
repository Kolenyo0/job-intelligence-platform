-- tests/assert_fact_preserves_job_count.sql

with int_count as (
    select count(*) as row_count
    from {{ ref('int_job_postings') }}
),

fact_count as (
    select count(*) as row_count
    from {{ ref('fact_job_posting') }}
)

select
    int_count.row_count as int_rows,
    fact_count.row_count as fact_rows
from int_count
cross join fact_count
where int_count.row_count <> fact_count.row_count