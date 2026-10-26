-- ============================================================
-- 03_views.sql  Stage 3 SQL analysis views (vw_ prefix)
-- All use suspect drugs only (drugcharacterization = 1) for
-- drug-reaction analysis; concomitant/interacting drugs are
-- context, not the signal source.
-- ============================================================
USE faers;
GO

-- Top drugs by report count (suspect only)
IF OBJECT_ID('dbo.vw_top_drugs', 'V') IS NOT NULL DROP VIEW dbo.vw_top_drugs;
GO
CREATE VIEW dbo.vw_top_drugs AS
SELECT
    d.drug_name,
    d.generic_name,
    d.manufacturer_name,
    COUNT(*)                                              AS report_count,
    SUM(CAST(fr.is_serious AS INT))                       AS serious_count,
    CAST(SUM(CAST(fr.is_serious AS INT)) AS FLOAT)
      / NULLIF(COUNT(*), 0) * 100                        AS serious_pct
FROM dbo.fact_drug fd
JOIN dbo.dim_drug  d  ON fd.drug_key_dim  = d.drug_key
JOIN dbo.fact_report fr ON fd.report_key  = fr.report_key
WHERE fd.is_suspect = 1
GROUP BY d.drug_name, d.generic_name, d.manufacturer_name;
GO

-- Top reactions
IF OBJECT_ID('dbo.vw_top_reactions', 'V') IS NOT NULL DROP VIEW dbo.vw_top_reactions;
GO
CREATE VIEW dbo.vw_top_reactions AS
SELECT
    r.reaction_meddra_apt,
    COUNT(*)                                              AS report_count,
    SUM(CAST(fr.is_serious AS INT))                       AS serious_count,
    CAST(SUM(CAST(fr.is_serious AS INT)) AS FLOAT)
      / NULLIF(COUNT(*), 0) * 100                        AS serious_pct
FROM dbo.fact_reaction rxn
JOIN dbo.dim_reaction  r  ON rxn.reaction_key_dim = r.reaction_key
JOIN dbo.fact_report   fr ON rxn.report_key       = fr.report_key
GROUP BY r.reaction_meddra_apt;
GO

-- Seriousness rate by age group
IF OBJECT_ID('dbo.vw_serious_by_age', 'V') IS NOT NULL DROP VIEW dbo.vw_serious_by_age;
GO
CREATE VIEW dbo.vw_serious_by_age AS
SELECT
    a.age_group_label,
    a.age_min_years,
    a.age_max_years,
    COUNT(*)                                              AS report_count,
    SUM(CAST(fr.is_serious AS INT))                       AS serious_count,
    CAST(SUM(CAST(fr.is_serious AS INT)) AS FLOAT)
      / NULLIF(COUNT(*), 0) * 100                        AS serious_pct
FROM dbo.fact_report fr
JOIN dbo.dim_age_group a ON fr.age_group_key = a.age_group_key
GROUP BY a.age_group_label, a.age_min_years, a.age_max_years;
GO

-- Seriousness rate by sex
IF OBJECT_ID('dbo.vw_serious_by_sex', 'V') IS NOT NULL DROP VIEW dbo.vw_serious_by_sex;
GO
CREATE VIEW dbo.vw_serious_by_sex AS
SELECT
    ISNULL(fr.sex_code, 'unknown')                       AS sex_code,
    COUNT(*)                                              AS report_count,
    SUM(CAST(fr.is_serious AS INT))                       AS serious_count,
    CAST(SUM(CAST(fr.is_serious AS INT)) AS FLOAT)
      / NULLIF(COUNT(*), 0) * 100                        AS serious_pct
FROM dbo.fact_report fr
GROUP BY fr.sex_code;
GO

-- Seriousness rate by country (top reporters)
IF OBJECT_ID('dbo.vw_serious_by_country', 'V') IS NOT NULL DROP VIEW dbo.vw_serious_by_country;
GO
CREATE VIEW dbo.vw_serious_by_country AS
SELECT
    c.iso2_code,
    COUNT(*)                                              AS report_count,
    SUM(CAST(fr.is_serious AS INT))                       AS serious_count,
    CAST(SUM(CAST(fr.is_serious AS INT)) AS FLOAT)
      / NULLIF(COUNT(*), 0) * 100                        AS serious_pct
FROM dbo.fact_report fr
JOIN dbo.dim_country c ON fr.country_key = c.country_key
WHERE c.iso2_code <> 'XX'
GROUP BY c.iso2_code;
GO

-- Seriousness rate by reporter qualification
IF OBJECT_ID('dbo.vw_serious_by_reporter', 'V') IS NOT NULL DROP VIEW dbo.vw_serious_by_reporter;
GO
CREATE VIEW dbo.vw_serious_by_reporter AS
SELECT
    ISNULL(rp.qualification, 'unknown')                  AS qualification,
    COUNT(*)                                              AS report_count,
    SUM(CAST(fr.is_serious AS INT))                       AS serious_count,
    CAST(SUM(CAST(fr.is_serious AS INT)) AS FLOAT)
      / NULLIF(COUNT(*), 0) * 100                        AS serious_pct
FROM dbo.fact_report fr
JOIN dbo.dim_reporter rp ON fr.reporter_key = rp.reporter_key
GROUP BY rp.qualification;
GO

-- Outcome distribution
IF OBJECT_ID('dbo.vw_outcomes', 'V') IS NOT NULL DROP VIEW dbo.vw_outcomes;
GO
CREATE VIEW dbo.vw_outcomes AS
SELECT
    ISNULL(outcome_code, 'unknown')                      AS outcome_code,
    COUNT(*)                                              AS report_count,
    CAST(COUNT(*) AS FLOAT)
      / (SELECT COUNT(*) FROM dbo.fact_reaction) * 100   AS share_pct
FROM dbo.fact_reaction
GROUP BY outcome_code;
GO

-- Manufacturer quality analytics: volume + seriousness rate
IF OBJECT_ID('dbo.vw_manufacturer_quality', 'V') IS NOT NULL DROP VIEW dbo.vw_manufacturer_quality;
GO
CREATE VIEW dbo.vw_manufacturer_quality AS
SELECT
    ISNULL(d.manufacturer_name, 'unknown')               AS manufacturer_name,
    COUNT(DISTINCT fd.report_key)                         AS report_count,
    SUM(CAST(fr.is_serious AS INT))                       AS serious_count,
    CAST(SUM(CAST(fr.is_serious AS INT)) AS FLOAT)
      / NULLIF(COUNT(DISTINCT fd.report_key), 0) * 100   AS serious_pct
FROM dbo.fact_drug fd
JOIN dbo.dim_drug    d  ON fd.drug_key_dim = d.drug_key
JOIN dbo.fact_report fr ON fd.report_key   = fr.report_key
WHERE fd.is_suspect = 1
GROUP BY d.manufacturer_name;
GO

-- Dosage form x administration route quality analytics
IF OBJECT_ID('dbo.vw_dosage_route_quality', 'V') IS NOT NULL DROP VIEW dbo.vw_dosage_route_quality;
GO
CREATE VIEW dbo.vw_dosage_route_quality AS
SELECT
    ISNULL(d.dosage_form,  'unknown')                    AS dosage_form,
    ISNULL(d.route,        'unknown')                    AS route,
    COUNT(DISTINCT fd.report_key)                         AS report_count,
    SUM(CAST(fr.is_serious AS INT))                       AS serious_count,
    CAST(SUM(CAST(fr.is_serious AS INT)) AS FLOAT)
      / NULLIF(COUNT(DISTINCT fd.report_key), 0) * 100   AS serious_pct
FROM dbo.fact_drug fd
JOIN dbo.dim_drug    d  ON fd.drug_key_dim = d.drug_key
JOIN dbo.fact_report fr ON fd.report_key   = fr.report_key
WHERE fd.is_suspect = 1
GROUP BY d.dosage_form, d.route;
GO

PRINT 'Stage 3 views created.';
