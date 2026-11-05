with postings as (
    select
        source,
        source_id,
        company_name,
        job_title,
        location,
        remote,
        job_types,
        created_at,
        ingested_at,
        md5(
            'company|' ||
            case
                when nullif(lower(btrim(company_name)), '') is null then 'null:'
                else 'value:' || lower(btrim(company_name))
            end
        ) as company_key,
        md5(
            'role|' ||
            case
                when nullif(lower(btrim(job_title)), '') is null then 'null:'
                else 'value:' || lower(btrim(job_title))
            end
        ) as role_key,
        md5(
            'location|' ||
            case
                when nullif(lower(btrim(location)), '') is null then 'null:'
                else 'value:' || lower(btrim(location))
            end
        ) as location_key,
        md5(
            'job|' || source || '|' || source_id
        ) as job_key
    from {{ ref('int_job_postings') }}
)

select
    postings.source,
    postings.source_id,
    dim_company.company_key,
    dim_role.role_key,
    dim_location.location_key,
    postings.remote,
    postings.job_types,
    postings.created_at,
    postings.ingested_at
from postings
inner join {{ ref('dim_company') }} as dim_company
    on postings.company_key = dim_company.company_key
inner join {{ ref('dim_role') }} as dim_role
    on postings.role_key = dim_role.role_key
inner join {{ ref('dim_location') }} as dim_location
   on postings.location_key = dim_location.location_key
