-- ============================================================
-- 01_create_database.sql
-- Creates the faers database (idempotent).
-- Run in SSMS with Windows Authentication.
-- ============================================================
IF DB_ID('faers') IS NULL
    CREATE DATABASE faers;
GO
USE faers;
GO

-- Schemas: stg = staging (raw, one row per source element),
--           dbo = star-schema facts and dimensions.
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'stg')
    EXEC ('CREATE SCHEMA stg');
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'dbo')
    EXEC ('CREATE SCHEMA dbo');
GO

-- ============================================================
-- STAGING: mirrors the openFDA JSON structure exactly.
-- Composite key (safetyreportid, safetyreportversion) makes
-- re-runs idempotent: DELETE by batch_id before reload.
-- ============================================================

IF OBJECT_ID('stg.reactions', 'U') IS NULL
CREATE TABLE stg.reactions (
    safetyreportid     VARCHAR(20)  NOT NULL,
    safetyreportversion VARCHAR(10)  NOT NULL,
    reactionmeddrapt    VARCHAR(255),
    reactionmeddraversionpt VARCHAR(20),
    reactionoutcome     VARCHAR(10),
    batch_id            INT          NOT NULL,
    loaded_at           DATETIME2    NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT pk_stg_reactions PRIMARY KEY (safetyreportid, safetyreportversion, reactionmeddrapt)
);
GO

IF OBJECT_ID('stg.drugs', 'U') IS NULL
CREATE TABLE stg.drugs (
    safetyreportid          VARCHAR(20)  NOT NULL,
    safetyreportversion     VARCHAR(10)  NOT NULL,
    medicinalproduct        VARCHAR(512),
    drugcharacterization    VARCHAR(10),
    drugauthorizationnumb    VARCHAR(50),
    drugseparatedosagenumb   VARCHAR(50),
    drugdosageform          VARCHAR(255),
    drugadministrationroute VARCHAR(50),
    drugindication          VARCHAR(512),
    activesubstancename     VARCHAR(512),
    openfda_brand_name      VARCHAR(255),
    openfda_generic_name    VARCHAR(512),
    openfda_manufacturer_name VARCHAR(255),
    batch_id                INT          NOT NULL,
    loaded_at               DATETIME2    NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT pk_stg_drugs PRIMARY KEY (safetyreportid, safetyreportversion, medicinalproduct, activesubstancename)
);
GO

IF OBJECT_ID('stg.reports', 'U') IS NULL
CREATE TABLE stg.reports (
    safetyreportid             VARCHAR(20)  NOT NULL,
    safetyreportversion        VARCHAR(10)  NOT NULL,
    companynumb                VARCHAR(100),
    primarysourcecountry       VARCHAR(10),
    occurcountry               VARCHAR(10),
    transmissiondateformat     VARCHAR(10),
    transmissiondate           VARCHAR(20),
    reporttype                 VARCHAR(10),
    serious                    VARCHAR(10),
    seriousnessdeath           VARCHAR(10),
    seriousnesslifethreatening VARCHAR(10),
    seriousnesshospitalization  VARCHAR(10),
    seriousnessdisabling       VARCHAR(10),
    seriousnesscongenitalanomali VARCHAR(10),
    seriousnessother           VARCHAR(10),
    receivedateformat          VARCHAR(10),
    receivedate                VARCHAR(20),
    receiptdateformat          VARCHAR(10),
    receiptdate                VARCHAR(20),
    fulfillexpeditecriteria    VARCHAR(10),
    duplicate                  VARCHAR(10),
    patientsex                 VARCHAR(10),
    patientagegroup            VARCHAR(50),
    patientonsetage            VARCHAR(20),
    patientonsetageunit        VARCHAR(10),
    patientweight              VARCHAR(20),
    primarysource_reportercountry VARCHAR(10),
    primarysource_qualification   VARCHAR(10),
    sender_sendertype          VARCHAR(10),
    sender_senderorganization  VARCHAR(255),
    receiver_receivertype      VARCHAR(10),
    receiver_receiverorganization VARCHAR(255),
    batch_id                   INT          NOT NULL,
    loaded_at                  DATETIME2    NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT pk_stg_reports PRIMARY KEY (safetyreportid, safetyreportversion)
);
GO

-- Quarantine: rows rejected during cleaning, with a reason code.
IF OBJECT_ID('stg.quarantine', 'U') IS NULL
CREATE TABLE stg.quarantine (
    safetyreportid     VARCHAR(20),
    safetyreportversion VARCHAR(10),
    element_type       VARCHAR(20)  NOT NULL,  -- report | drug | reaction
    reason_code        VARCHAR(50)  NOT NULL,
    reason_detail      VARCHAR(512),
    raw_json           VARCHAR(MAX),
    batch_id           INT          NOT NULL,
    loaded_at          DATETIME2    NOT NULL DEFAULT SYSDATETIME()
);
GO

-- Data quality results per batch.
IF OBJECT_ID('stg.data_quality_log', 'U') IS NULL
CREATE TABLE stg.data_quality_log (
    batch_id       INT          NOT NULL,
    check_name     VARCHAR(100) NOT NULL,
    before_count   INT,
    after_count    INT,
    note           VARCHAR(512),
    logged_at      DATETIME2    NOT NULL DEFAULT SYSDATETIME()
);
GO

PRINT 'Database faers and staging tables created.';