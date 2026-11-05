select
    nullif(btrim(source), '') as source,
    nullif(btrim(source_id), '') as source_id,
    nullif(btrim(company_name), '') as company_name,
    nullif(btrim(job_title), '') as job_title,
    remote,
    nullif(btrim(location), '') as location,
    case
        when type is null then null
        else array(
            select nullif(btrim(job_type), '')
            from unnest(type) with ordinality as job_types(job_type, position)
            where nullif(btrim(job_type), '') is not null
            order by position
        )
    end as job_types,
    created_at,
    ingested_at
from {{ source('ingestion', 'job_postings') }}
