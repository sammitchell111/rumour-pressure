"""Warehouse DDL. Timestamps are stored as naive TIMESTAMP holding UTC."""

DDL = """
CREATE TABLE IF NOT EXISTS markets (
    market_id       VARCHAR PRIMARY KEY,
    venue           VARCHAR NOT NULL,
    question        VARCHAR NOT NULL,
    resolution_text VARCHAR NOT NULL,
    url             VARCHAR NOT NULL,
    close_time      TIMESTAMP,
    entity_keys     VARCHAR[]
);

CREATE TABLE IF NOT EXISTS prices (
    market_id VARCHAR   NOT NULL,
    ts_utc    TIMESTAMP NOT NULL,
    price     DOUBLE    NOT NULL,
    volume    DOUBLE,
    n_trades  BIGINT,
    PRIMARY KEY (market_id, ts_utc)
);

CREATE TABLE IF NOT EXISTS attention (
    source  VARCHAR   NOT NULL,
    entity  VARCHAR   NOT NULL,
    ts_utc  TIMESTAMP NOT NULL,
    metric  VARCHAR   NOT NULL,
    value   DOUBLE    NOT NULL,
    PRIMARY KEY (source, entity, metric, ts_utc)
);

CREATE TABLE IF NOT EXISTS posts (
    post_id      VARCHAR PRIMARY KEY,
    source       VARCHAR   NOT NULL,
    ts_utc       TIMESTAMP NOT NULL,
    channel      VARCHAR   NOT NULL,
    author_hash  VARCHAR,
    text         VARCHAR   NOT NULL,
    url          VARCHAR   NOT NULL,
    collected_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS stance (
    post_id        VARCHAR   NOT NULL,
    market_id      VARCHAR   NOT NULL,
    label          VARCHAR   NOT NULL,
    confidence     DOUBLE    NOT NULL,
    model          VARCHAR   NOT NULL,
    prompt_version VARCHAR   NOT NULL,
    classified_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (post_id, market_id, model, prompt_version)
);

CREATE TABLE IF NOT EXISTS jumps (
    market_id   VARCHAR   NOT NULL,
    ts_start    TIMESTAMP NOT NULL,
    ts_end      TIMESTAMP NOT NULL,
    delta       DOUBLE    NOT NULL,
    residual    DOUBLE    NOT NULL,
    params_hash VARCHAR   NOT NULL,
    volume      DOUBLE,
    n_trades    BIGINT,
    PRIMARY KEY (market_id, ts_start, params_hash)
);

CREATE TABLE IF NOT EXISTS logger_gaps (
    source    VARCHAR   NOT NULL,
    gap_start TIMESTAMP NOT NULL,
    gap_end   TIMESTAMP,
    reason    VARCHAR,
    PRIMARY KEY (source, gap_start)
);
"""
