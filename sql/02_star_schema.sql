-- ============================================================
-- 02_star_schema.sql
-- Star schema built from stg.* staging tables.
-- Idempotent: DROP IF EXISTS before CREATE.
-- ============================================================
USE faers;
GO

-- ------------------------------------------------------------
-- RESET EXISTING STAR SCHEMA
-- Facts must be dropped before dimensions because their foreign keys
-- reference the dimension tables.
-- ------------------------------------------------------------

IF OBJECT_ID('dbo.fact_reaction', 'U') IS NOT NULL DROP TABLE dbo.fact_reaction;
IF OBJECT_ID('dbo.fact_drug', 'U') IS NOT NULL DROP TABLE dbo.fact_drug;
IF OBJECT_ID('dbo.fact_report', 'U') IS NOT NULL DROP TABLE dbo.fact_report;
GO

-- ------------------------------------------------------------
-- DIMENSIONS
-- ------------------------------------------------------------

IF OBJECT_ID('dbo.dim_date', 'U') IS NOT NULL DROP TABLE dbo.dim_date;
CREATE TABLE dbo.dim_date (
    date_key         INT IDENTITY(1,1) PRIMARY KEY,   -- YYYYMMDD integer
    full_date        DATE          NOT NULL,
    year             INT           NOT NULL,
    quarter          INT           NOT NULL,
    month            INT           NOT NULL,
    month_name       VARCHAR(20)   NOT NULL,
    day_of_week      INT           NOT NULL,
    is_weekend       BIT           NOT NULL DEFAULT 0
);
GO

IF OBJECT_ID('dbo.dim_country', 'U') IS NOT NULL DROP TABLE dbo.dim_country;
CREATE TABLE dbo.dim_country (
    country_key     INT IDENTITY(1,1) PRIMARY KEY,
    iso2_code       VARCHAR(2)    NOT NULL,
    country_name    VARCHAR(100)  NOT NULL,
    region          VARCHAR(50),
    UNIQUE (iso2_code)
);
GO

IF OBJECT_ID('dbo.dim_age_group', 'U') IS NOT NULL DROP TABLE dbo.dim_age_group;
CREATE TABLE dbo.dim_age_group (
    age_group_key   INT IDENTITY(1,1) PRIMARY KEY,
    age_group_code  VARCHAR(20)   NOT NULL,   -- raw patientagegroup value
    age_group_label VARCHAR(50)   NOT NULL,
    age_min_years   INT,
    age_max_years   INT,
    UNIQUE (age_group_code)
);
GO

IF OBJECT_ID('dbo.dim_drug', 'U') IS NOT NULL DROP TABLE dbo.dim_drug;
CREATE TABLE dbo.dim_drug (
    drug_key        INT IDENTITY(1,1) PRIMARY KEY,
    -- Standardised drug identity (openfda generic/substance first, fallback
    -- trimmed uppercase medicinalproduct). Stored denormalised for reporting.
    drug_name       VARCHAR(512)  NOT NULL,
    generic_name    VARCHAR(512),
    substance_name  VARCHAR(512),
    brand_name      VARCHAR(255),
    manufacturer_name VARCHAR(255),
    dosage_form     VARCHAR(255),
    route           VARCHAR(255),
    is_suspect      BIT           NOT NULL DEFAULT 0,
    UNIQUE (drug_name)
);
GO

IF OBJECT_ID('dbo.dim_reaction', 'U') IS NOT NULL DROP TABLE dbo.dim_reaction;
CREATE TABLE dbo.dim_reaction (
    reaction_key    INT IDENTITY(1,1) PRIMARY KEY,
    reaction_meddra_apt VARCHAR(255) NOT NULL,  -- MedDRA PT
    reaction_meddra_version_pt VARCHAR(20),
    UNIQUE (reaction_meddra_apt)
);
GO

IF OBJECT_ID('dbo.dim_reporter', 'U') IS NOT NULL DROP TABLE dbo.dim_reporter;
CREATE TABLE dbo.dim_reporter (
    reporter_key    INT IDENTITY(1,1) PRIMARY KEY,
    reporter_type_code VARCHAR(10),
    reporter_type_label VARCHAR(50),
    organization   VARCHAR(255),
    country        VARCHAR(10),
    qualification  VARCHAR(10),
    UNIQUE (reporter_type_code, organization, country, qualification)
);
GO

-- ------------------------------------------------------------
-- FACTS
-- ------------------------------------------------------------

CREATE TABLE dbo.fact_report (
    report_key      INT IDENTITY(1,1) PRIMARY KEY,
    safetyreportid  VARCHAR(20)   NOT NULL,
    safetyreportversion VARCHAR(10) NOT NULL,
    report_type     VARCHAR(10),
    is_serious      BIT           NOT NULL DEFAULT 0,
    is_duplicate    BIT           NOT NULL DEFAULT 0,
    date_key        INT          NOT NULL,
    receipt_date_key INT         NOT NULL,
    receive_date_key INT         NOT NULL,
    transmission_date_key INT     NOT NULL,
    country_key     INT          NOT NULL,
    occur_country_key INT         NOT NULL,
    reporter_key    INT          NOT NULL,
    age_group_key   INT          NOT NULL,
    sex_code        VARCHAR(10),
    onset_age_years DECIMAL(8,2),
    weight_kg       DECIMAL(8,2),
    companynumb     VARCHAR(100),
    CONSTRAINT fk_fact_report_date FOREIGN KEY (date_key) REFERENCES dbo.dim_date(date_key),
    CONSTRAINT fk_fact_report_receipt FOREIGN KEY (receipt_date_key) REFERENCES dbo.dim_date(date_key),
    CONSTRAINT fk_fact_report_receive FOREIGN KEY (receive_date_key) REFERENCES dbo.dim_date(date_key),
    CONSTRAINT fk_fact_report_transmission FOREIGN KEY (transmission_date_key) REFERENCES dbo.dim_date(date_key),
    CONSTRAINT fk_fact_report_country FOREIGN KEY (country_key) REFERENCES dbo.dim_country(country_key),
    CONSTRAINT fk_fact_report_occur FOREIGN KEY (occur_country_key) REFERENCES dbo.dim_country(country_key),
    CONSTRAINT fk_fact_report_reporter FOREIGN KEY (reporter_key) REFERENCES dbo.dim_reporter(reporter_key),
    CONSTRAINT fk_fact_report_age FOREIGN KEY (age_group_key) REFERENCES dbo.dim_age_group(age_group_key)
);
GO

CREATE TABLE dbo.fact_drug (
    drug_key        INT IDENTITY(1,1) PRIMARY KEY,
    safetyreportid  VARCHAR(20)   NOT NULL,
    safetyreportversion VARCHAR(10) NOT NULL,
    report_key      INT          NOT NULL,
    drug_key_dim    INT          NOT NULL,
    is_suspect      BIT           NOT NULL DEFAULT 0,
    drugcharacterization VARCHAR(10),
    drugauthorizationnumb VARCHAR(50),
    drugindication  VARCHAR(512),
    CONSTRAINT fk_fact_drug_report FOREIGN KEY (report_key) REFERENCES dbo.fact_report(report_key),
    CONSTRAINT fk_fact_drug_drug FOREIGN KEY (drug_key_dim) REFERENCES dbo.dim_drug(drug_key)
);
GO

CREATE TABLE dbo.fact_reaction (
    reaction_key    INT IDENTITY(1,1) PRIMARY KEY,
    safetyreportid  VARCHAR(20)   NOT NULL,
    safetyreportversion VARCHAR(10) NOT NULL,
    report_key      INT          NOT NULL,
    reaction_key_dim INT         NOT NULL,
    outcome_code    VARCHAR(10),
    CONSTRAINT fk_fact_reaction_report FOREIGN KEY (report_key) REFERENCES dbo.fact_report(report_key),
    CONSTRAINT fk_fact_reaction_reaction FOREIGN KEY (reaction_key_dim) REFERENCES dbo.dim_reaction(reaction_key)
);
GO

-- ------------------------------------------------------------
-- Indexes
-- ------------------------------------------------------------
CREATE INDEX ix_fact_report_reportid ON dbo.fact_report(safetyreportid, safetyreportversion);
CREATE INDEX ix_fact_drug_report ON dbo.fact_drug(report_key);
CREATE INDEX ix_fact_drug_drug ON dbo.fact_drug(drug_key_dim);
CREATE INDEX ix_fact_reaction_report ON dbo.fact_reaction(report_key);
CREATE INDEX ix_fact_reaction_reaction ON dbo.fact_reaction(reaction_key_dim);
GO

PRINT 'Star schema created.';