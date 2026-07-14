-- Phase 6: RBAC permission model
-- Migration 003: requirement_users table for role-based access control
-- Applies after 002_requirement_program.sql (user_version 2 -> 3)

CREATE TABLE IF NOT EXISTS requirement_users (
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    project_id TEXT,
    display_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, project_id)
);

CREATE INDEX IF NOT EXISTS idx_requirement_users_user
    ON requirement_users(user_id);
CREATE INDEX IF NOT EXISTS idx_requirement_users_project
    ON requirement_users(project_id);
