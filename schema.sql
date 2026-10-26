-- =============================================================================
-- BloodLink — Standalone Clean Database Schema (schema.sql)
-- =============================================================================
-- Purpose:
--   Provisions the complete database structure for a fresh installation.
--   Contains all 7 application tables, relational constraints, foreign keys,
--   and initial institutional reference data (hospitals).
--
-- Security Guarantee:
--   Contains ZERO personal user records, actual passwords, or password hashes.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS `blood_donation` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `blood_donation`;

SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------------------------
-- 1. Table: users
-- Core authentication and role-based access control (ADMIN, DONOR, RECIPIENT)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `user_id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(100) NOT NULL,
  `email` VARCHAR(150) NOT NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  `role` VARCHAR(20) NOT NULL,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 2. Table: hospitals
-- Reference directory of healthcare facilities for admissions and blood banks
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `hospitals`;
CREATE TABLE `hospitals` (
  `hospital_id` INT NOT NULL AUTO_INCREMENT,
  `hospital_name` VARCHAR(150) NOT NULL,
  `address` VARCHAR(200) NOT NULL,
  `city` VARCHAR(100) NOT NULL,
  `phone` VARCHAR(15) DEFAULT NULL,
  `emergency_available` TINYINT(1) DEFAULT 1,
  `blood_bank_available` TINYINT(1) DEFAULT 1,
  PRIMARY KEY (`hospital_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 3. Table: donors
-- Donor profiles, blood group attributes, availability, and privacy consent
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `donors`;
CREATE TABLE `donors` (
  `donor_id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT DEFAULT NULL,
  `name` VARCHAR(100) NOT NULL,
  `age` INT NOT NULL,
  `gender` VARCHAR(20) DEFAULT NULL,
  `blood_group` VARCHAR(5) NOT NULL,
  `phone` VARCHAR(15) NOT NULL,
  `location` VARCHAR(100) NOT NULL,
  `availability` TINYINT(1) DEFAULT 1,
  `last_donation_date` DATE DEFAULT NULL,
  `weight` DECIMAL(5,2) DEFAULT NULL,
  `medical_status` VARCHAR(100) DEFAULT 'Healthy',
  `contact_consent` TINYINT(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`donor_id`),
  KEY `fk_donors_user` (`user_id`),
  CONSTRAINT `fk_donors_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 4. Table: recipients
-- Recipient and patient profiles requiring blood transfusions
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `recipients`;
CREATE TABLE `recipients` (
  `recipient_id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT DEFAULT NULL,
  `name` VARCHAR(100) NOT NULL,
  `age` INT NOT NULL,
  `gender` VARCHAR(20) DEFAULT NULL,
  `blood_group` VARCHAR(5) NOT NULL,
  `phone` VARCHAR(15) NOT NULL,
  `location` VARCHAR(100) NOT NULL,
  `hospital_id` INT DEFAULT NULL,
  `units_required` INT DEFAULT 1,
  `emergency_level` VARCHAR(20) DEFAULT 'NORMAL',
  PRIMARY KEY (`recipient_id`),
  KEY `fk_recipients_user` (`user_id`),
  KEY `hospital_id` (`hospital_id`),
  CONSTRAINT `fk_recipients_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 5. Table: emergency_requests
-- Broadcasted emergency blood requirements with urgency and fulfillment status
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `emergency_requests`;
CREATE TABLE `emergency_requests` (
  `request_id` INT NOT NULL AUTO_INCREMENT,
  `recipient_id` INT DEFAULT NULL,
  `hospital_id` INT DEFAULT NULL,
  `blood_group_required` VARCHAR(5) NOT NULL,
  `units_required` INT NOT NULL,
  `emergency_level` VARCHAR(20) NOT NULL,
  `request_status` VARCHAR(20) DEFAULT 'ACTIVE',
  `request_date` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`request_id`),
  KEY `recipient_id` (`recipient_id`),
  KEY `hospital_id` (`hospital_id`),
  CONSTRAINT `emergency_requests_ibfk_1` FOREIGN KEY (`recipient_id`) REFERENCES `recipients` (`recipient_id`) ON DELETE CASCADE,
  CONSTRAINT `emergency_requests_ibfk_2` FOREIGN KEY (`hospital_id`) REFERENCES `hospitals` (`hospital_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 6. Table: campaigns
-- Community blood donation collection drives managed by administrators
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `campaigns`;
CREATE TABLE `campaigns` (
  `campaign_id` INT NOT NULL AUTO_INCREMENT,
  `campaign_name` VARCHAR(150) NOT NULL,
  `description` TEXT DEFAULT NULL,
  `location` VARCHAR(150) NOT NULL,
  `start_date` DATETIME NOT NULL,
  `end_date` DATETIME NOT NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'PLANNED',
  `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`campaign_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------------------------------------------
-- 7. Table: donation_requests
-- Direct donation offers connecting voluntary donors to emergency requests
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS `donation_requests`;
CREATE TABLE `donation_requests` (
  `request_id` INT NOT NULL AUTO_INCREMENT,
  `recipient_id` INT NOT NULL,
  `donor_id` INT NOT NULL,
  `emergency_request_id` INT DEFAULT NULL,
  `hospital_id` INT DEFAULT NULL,
  `blood_group_required` VARCHAR(5) NOT NULL,
  `units_required` INT NOT NULL DEFAULT 1,
  `urgency_level` VARCHAR(20) NOT NULL DEFAULT 'HIGH',
  `clinical_notes` VARCHAR(255) DEFAULT NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  `recipient_consent_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `donor_contact_consent_at` TIMESTAMP NULL DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `responded_at` TIMESTAMP NULL DEFAULT NULL,
  PRIMARY KEY (`request_id`),
  KEY `fk_dr_hospital` (`hospital_id`),
  KEY `idx_dr_recipient_status` (`recipient_id`, `status`),
  KEY `idx_dr_donor_status` (`donor_id`, `status`),
  KEY `idx_dr_emergency` (`emergency_request_id`),
  CONSTRAINT `fk_dr_recipient` FOREIGN KEY (`recipient_id`) REFERENCES `recipients` (`recipient_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_dr_donor` FOREIGN KEY (`donor_id`) REFERENCES `donors` (`donor_id`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_dr_emergency` FOREIGN KEY (`emergency_request_id`) REFERENCES `emergency_requests` (`request_id`) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT `fk_dr_hospital` FOREIGN KEY (`hospital_id`) REFERENCES `hospitals` (`hospital_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;

-- -----------------------------------------------------------------------------
-- Initial Reference Data: hospitals (DEMO / SAMPLE DATA ONLY)
-- Fictional placeholder healthcare facilities provided strictly for development,
-- local testing, and UI dropdown population.
-- None of these entries represent genuine verified facilities, and phone
-- numbers are non-operational dummy numbers.
-- Replace with actual verified institution data for production environments.
-- -----------------------------------------------------------------------------
INSERT INTO `hospitals` (`hospital_id`, `hospital_name`, `address`, `city`, `phone`, `emergency_available`, `blood_bank_available`) VALUES
(1, 'City Care Hospital (Sample)', '100 Demonstration Road', 'Pune', '02000000001', 1, 1),
(2, 'LifeLine Hospital (Sample)', '200 Sample Avenue', 'Pune', '02000000002', 1, 1),
(3, 'Central Care Hospital (Sample)', '300 Test Boulevard', 'Pune', '02000000003', 1, 1),
(4, 'Metro Health Clinic (Sample)', '400 Mock Street', 'Pune', '02000000004', 1, 1),
(5, 'Sunrise Hospital (Sample)', '500 Prototype Way', 'Pimpri', '02000000005', 1, 1)
ON DUPLICATE KEY UPDATE `hospital_name` = VALUES(`hospital_name`);
