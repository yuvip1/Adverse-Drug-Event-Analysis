-- ============================================================
-- 04_signal_views.sql  Stage 6: disproportionality signal detection
-- Builds the 2x2 contingency building blocks for every
-- suspect-drug x reaction pair observed in the star schema.
--
-- Cell meanings (reports are the analysis unit):
--   pair_count      = a   reports with BOTH drug d and reaction r
--   drug_total      = a+b reports with drug d (any reaction)
--   reaction_total  = a+c reports with reaction r (any drug)
--   n_total         = a+b+c+d total reports (passed in by caller)
--   b = drug_total - a, c = reaction_total - a,
--   d = n_total - drug_total - reaction_total + a
--
-- PRR / ROR / chi-square are computed in src/signal_analysis.py because the
-- confidence-interval and Yates-correction arithmetic is clearer in
-- Python and keeps the view a pure aggregation.
-- ============================================================
USE faers;
GO

IF OBJECT_ID('dbo.vw_drug_reaction_pairs', 'V') IS NOT NULL DROP VIEW dbo.vw_drug_reaction_pairs;
GO
CREATE VIEW dbo.vw_drug_reaction_pairs AS
WITH suspect AS (
    -- Suspect / interacting drugs only (drugcharacterization = 1).
    -- Concomitant medications (2) are context, not the signal source.
    SELECT DISTINCT report_key, drug_key_dim
    FROM dbo.fact_drug
    WHERE is_suspect = 1
),
rxn AS (
    SELECT DISTINCT report_key, reaction_key_dim
    FROM dbo.fact_reaction
),
drug_totals AS (
    SELECT drug_key_dim, COUNT(DISTINCT report_key) AS drug_total
    FROM suspect
    GROUP BY drug_key_dim
),
rxn_totals AS (
    SELECT reaction_key_dim, COUNT(DISTINCT report_key) AS reaction_total
    FROM rxn
    GROUP BY reaction_key_dim
)
SELECT
    d.drug_key,
    r.reaction_key,
    d.drug_name,
    d.generic_name,
    d.manufacturer_name,
    d.dosage_form,
    d.route,
    r.reaction_meddra_apt,
    COUNT(DISTINCT s.report_key) AS pair_count, -- a
    dt.drug_total,                      -- a + b
    rt.reaction_total                    -- a + c
FROM suspect s
JOIN rxn         ON s.report_key       = rxn.report_key
JOIN dbo.dim_drug    d  ON s.drug_key_dim   = d.drug_key
JOIN dbo.dim_reaction r  ON rxn.reaction_key_dim = r.reaction_key
JOIN drug_totals dt ON dt.drug_key_dim   = s.drug_key_dim
JOIN rxn_totals rt ON rt.reaction_key_dim = rxn.reaction_key_dim
GROUP BY d.drug_key, r.reaction_key, d.drug_name, d.generic_name,
         d.manufacturer_name, d.dosage_form, d.route, r.reaction_meddra_apt,
         dt.drug_total, rt.reaction_total;
GO

PRINT 'Stage 6 signal views created.';