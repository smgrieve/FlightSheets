-- MySQL dump 10.13  Distrib 8.0.41, for Linux (x86_64)
--
-- Host: localhost    Database: hscflightprod
-- ------------------------------------------------------
-- Server version	8.0.41-0ubuntu0.24.04.1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `aircraft`
--

DROP TABLE IF EXISTS `aircraft`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `aircraft` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `annual_due_date` date DEFAULT NULL,
  `total_flight_time` decimal(10,2) DEFAULT NULL,
  `total_flights` int DEFAULT '0',
  `rental_rate` decimal(10,2) NOT NULL DEFAULT '0.00',
  PRIMARY KEY (`id`),
  KEY `idx_aircraft_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `flights`
--

DROP TABLE IF EXISTS `flights`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `flights` (
  `id` int NOT NULL AUTO_INCREMENT,
  `aircraft` varchar(100) NOT NULL,
  `instructor` varchar(100) NOT NULL,
  `pilot` varchar(100) NOT NULL,
  `charge_to` varchar(100) NOT NULL,
  `takeoff_time` datetime NOT NULL,
  `landing_time` datetime DEFAULT NULL,
  `flight_time` time DEFAULT NULL,
  `release_altitude` int DEFAULT NULL,
  `incomplete` tinyint(1) DEFAULT '0',
  `comments` text,
  `user_id` text,
  `user_update` text,
  `towplane` varchar(100) DEFAULT NULL,
  `tow_pilot` varchar(255) DEFAULT NULL,
  `cost` decimal(10,2) DEFAULT '0.00',
  `tow_cost` decimal(10,2) DEFAULT '0.00',
  `total_cost` decimal(10,2) DEFAULT '0.00',
  PRIMARY KEY (`id`),
  KEY `aircraft` (`aircraft`),
  KEY `instructor` (`instructor`),
  KEY `idx_flight_time` (`flight_time`),
  KEY `idx_cost` (`cost`),
  KEY `idx_takeoff_time_aircraft` (`takeoff_time`,`aircraft`),
  KEY `idx_takeoff_aircraft` (`takeoff_time`,`aircraft`),
  KEY `idx_takeoff_time_aircraft_composite` (`takeoff_time`,`aircraft`),
  CONSTRAINT `flights_ibfk_1` FOREIGN KEY (`aircraft`) REFERENCES `aircraft` (`name`) ON DELETE CASCADE,
  CONSTRAINT `flights_ibfk_2` FOREIGN KEY (`instructor`) REFERENCES `instructors` (`name`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=194 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `hourly_rates`
--

DROP TABLE IF EXISTS `hourly_rates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `hourly_rates` (
  `id` int NOT NULL AUTO_INCREMENT,
  `rate` decimal(6,2) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `instructors`
--

DROP TABLE IF EXISTS `instructors`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `instructors` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_instructors_name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `members`
--

DROP TABLE IF EXISTS `members`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `members` (
  `Active Status` text,
  `Customer` text,
  `FirstName` text,
  `LastName` text,
  `MainPhone` text,
  `MainEmail` text,
  `Bill to 1` text,
  `Bill to 2` text,
  `Bill to 3` text,
  `member_id` int DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tow_pilots`
--

DROP TABLE IF EXISTS `tow_pilots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tow_pilots` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `active` tinyint(1) DEFAULT '1',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tow_plane_usage`
--

DROP TABLE IF EXISTS `tow_plane_usage`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tow_plane_usage` (
  `id` int NOT NULL AUTO_INCREMENT,
  `tow_plane_id` int DEFAULT NULL,
  `date_of_usage` date DEFAULT NULL,
  `number_of_tows` int DEFAULT NULL,
  `refuel_times` int DEFAULT NULL,
  `tach_start` decimal(10,2) DEFAULT NULL,
  `tach_end` decimal(10,2) DEFAULT NULL,
  `next_oil_change_tach` decimal(10,2) DEFAULT NULL,
  `last_oil_change_tach` decimal(10,2) DEFAULT NULL,
  `gallons_of_fuel` decimal(10,2) DEFAULT NULL,
  `oil_added` decimal(10,2) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `tow_plane_id` (`tow_plane_id`),
  CONSTRAINT `tow_plane_usage_ibfk_1` FOREIGN KEY (`tow_plane_id`) REFERENCES `towplanes` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `tow_rates`
--

DROP TABLE IF EXISTS `tow_rates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tow_rates` (
  `id` int NOT NULL AUTO_INCREMENT,
  `base_fee` decimal(10,2) NOT NULL DEFAULT '40.00',
  `rate_per_100ft` decimal(10,2) NOT NULL DEFAULT '1.00',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `towplane`
--

DROP TABLE IF EXISTS `towplane`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `towplane` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `towplanes`
--

DROP TABLE IF EXISTS `towplanes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `towplanes` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `annual_due_date` date DEFAULT NULL,
  `last_oil_change_tach` decimal(10,2) DEFAULT NULL,
  `next_oil_change_due` decimal(10,2) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) NOT NULL,
  `password` varchar(255) NOT NULL,
  `is_adult` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `volunteer_hours`
--

DROP TABLE IF EXISTS `volunteer_hours`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `volunteer_hours` (
  `id` int NOT NULL AUTO_INCREMENT,
  `volunteer_id` int DEFAULT NULL,
  `date_worked` date DEFAULT NULL,
  `hours` decimal(4,2) DEFAULT NULL,
  `approved` tinyint(1) DEFAULT '0',
  `approver_id` int DEFAULT NULL,
  `work_type_id` int DEFAULT NULL,
  `comments` text,
  PRIMARY KEY (`id`),
  KEY `volunteer_id` (`volunteer_id`),
  KEY `work_type_id` (`work_type_id`),
  KEY `approver_id` (`approver_id`),
  CONSTRAINT `volunteer_hours_ibfk_1` FOREIGN KEY (`volunteer_id`) REFERENCES `volunteers` (`id`),
  CONSTRAINT `volunteer_hours_ibfk_2` FOREIGN KEY (`approver_id`) REFERENCES `volunteers` (`id`),
  CONSTRAINT `volunteer_hours_ibfk_3` FOREIGN KEY (`work_type_id`) REFERENCES `work_types` (`id`),
  CONSTRAINT `volunteer_hours_ibfk_4` FOREIGN KEY (`approver_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `volunteers`
--

DROP TABLE IF EXISTS `volunteers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `volunteers` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `work_types`
--

DROP TABLE IF EXISTS `work_types`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `work_types` (
  `id` int NOT NULL AUTO_INCREMENT,
  `description` varchar(255) NOT NULL,
  `value` decimal(10,2) NOT NULL DEFAULT '0.00',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-01-31  9:58:47
