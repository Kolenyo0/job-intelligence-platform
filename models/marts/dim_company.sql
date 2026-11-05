with company_entities as (
    select
        case
            when nullif(lower(btrim(company_name)), '') is null then 'null:'
            else 'value:' || lower(btrim(company_name))
        end as company_identity,
        coalesce(min(company_name), 'Unknown') as company_name
    from {{ ref('int_job_postings') }}
    group by 1
)       

select
    md5('company|' || company_identity) as company_key,
    company_name
from company_entities
