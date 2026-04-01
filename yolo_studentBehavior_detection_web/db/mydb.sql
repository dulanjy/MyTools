-- MySQL dump 10.13  Distrib 8.4.6, for Win64 (x86_64)
--
-- Host: localhost    Database: cropdisease
-- ------------------------------------------------------
-- Server version	8.4.6

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
-- Table structure for table `camerarecords`
--

DROP TABLE IF EXISTS `camerarecords`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `camerarecords` (
  `id` int NOT NULL AUTO_INCREMENT,
  `weight` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `conf` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `start_time` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `out_video` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `kind` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=34 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `camerarecords`
--

LOCK TABLES `camerarecords` WRITE;
/*!40000 ALTER TABLE `camerarecords` DISABLE KEYS */;
INSERT INTO `camerarecords` VALUES (33,'rice_best.pt','0.45','admin','2025-01-14 16:22:31','http://localhost:9999/files/d7846c7eba244350bdebe55e09c200e3_output.mp4','rice');
/*!40000 ALTER TABLE `camerarecords` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `imgrecords`
--

DROP TABLE IF EXISTS `imgrecords`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `imgrecords` (
  `id` int NOT NULL AUTO_INCREMENT,
  `input_img` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `out_img` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `confidence` mediumtext COMMENT 'JSON array or summary object of detection confidences',
  `all_time` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `conf` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `weight` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `start_time` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `label` mediumtext COMMENT 'JSON array of detection labels',
  `kind` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=219 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `imgrecords`
--

LOCK TABLES `imgrecords` WRITE;
/*!40000 ALTER TABLE `imgrecords` DISABLE KEYS */;
INSERT INTO `imgrecords` VALUES (209,'http://localhost:9999/files/8a43338e7f564978b360c555d10974e3_Corn_Blight-21-_jpg.rf.90d948f720fc87791e00c7f8800027f3.jpg','http://localhost:9999/files/14c4e3edd5f349258b31e013ee70b5b0_result.jpg','[0.744063675403595]','1.646s','0.54','corn_best.pt','dulan','2025-11-13 11:27:01','[\"blight（疫病）\"]','corn'),(210,'http://localhost:9999/files/5f1b9cf815c746e5be2cb6cf2cfc75f5_test1.jpg','http://localhost:9999/files/ff9b2ce989544b318d9b569550cb027c_result.jpg','[0.7360418438911438, 0.7001059055328369, 0.6990247964859009, 0.5766220688819885]','2.243s','0.57','best_per_counts.pt','dulan','2025-11-13 20:03:38','[\"head\", \"head\", \"head\", \"head\"]','head'),(211,'http://localhost:9999/files/d15e16ea9daa48af83507c6c731c9930_00000010_jpg.rf.307ff8ffed24b178c5ffe98342cab32c.jpg','http://localhost:9999/files/46687379610f4db7b33f6ec5822c9884_result.jpg','[0.799207329750061, 0.759503185749054, 0.7535097002983093, 0.7396593689918518, 0.7296307682991028, 0.7292976975440979, 0.7086260318756104, 0.6865995526313782, 0.6669760942459106]','1.612s','0.55','best_per_counts.pt','dulan','2025-11-17 11:14:38','[\"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\"]','head'),(217,'http://localhost:9999/files/c63a71625431464eb38089c949c4ffa8_0000003_jpg.rf.44c4cb7c59816df9822cda6c8e8b5f76.jpg','http://localhost:9999/files/175aa95008434d7caa3ae5ba657daf0b_result.jpg','[0.7955667972564697, 0.7416948676109314, 0.7359275221824646, 0.7256119847297668, 0.7101054191589355, 0.6959189772605896, 0.6871861219406128, 0.6753515601158142, 0.6724489331245422, 0.6668618321418762, 0.6658559441566467, 0.6642022132873535, 0.6592988967895508, 0.6422028541564941, 0.6405649781227112, 0.6372474431991577, 0.6342212557792664, 0.627220094203949, 0.6257139444351196, 0.6225582957267761, 0.6184996366500854, 0.6067383289337158, 0.5999879837036133, 0.5994899868965149, 0.5984484553337097, 0.5938497185707092, 0.5913877487182617, 0.580451488494873, 0.5790717601776123, 0.5780029892921448, 0.5778799057006836, 0.5718197226524353, 0.5710166692733765, 0.5541434288024902, 0.5487197637557983, 0.5447162389755249, 0.5372845530509949, 0.5336856245994568, 0.5298789143562317, 0.5291867256164551, 0.5285484194755554, 0.528028130531311, 0.5250461101531982]','0.835s','0.52','best_per_counts.pt','dulan','2025-11-18 08:44:33','[\"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\"]','head'),(218,'http://127.0.0.1:9999/files/afb34bded4c647839874bba87cbceaa4_1252031_png.rf.afb6dd5266b7603f57ab781d8e793908.jpg','http://127.0.0.1:9999/files/9a11e69acd1e4a9ab35ca5f4f63af8da_result.jpg','[0.7298817038536072, 0.708473265171051, 0.6684701442718506, 0.6522004008293152, 0.6424224376678467, 0.6169800162315369, 0.597561776638031, 0.5833088159561157, 0.5820697546005249, 0.5819352269172668, 0.579297661781311, 0.5715087652206421, 0.571397602558136, 0.5644295811653137, 0.5330165028572083, 0.5314855575561523, 0.502062201499939, 0.5001907348632812, 0.49863699078559875, 0.49389010667800903]','2.502s','0.49','best_per_counts.pt','dulan','2025-11-19 11:37:43','[\"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\", \"head\"]','head');
/*!40000 ALTER TABLE `imgrecords` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `student_behavior_records`
--

DROP TABLE IF EXISTS `student_behavior_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_behavior_records` (
  `id` int NOT NULL AUTO_INCREMENT,
  `classroom_id` varchar(50) DEFAULT NULL,
  `record_time` datetime DEFAULT NULL,
  `student_count` int DEFAULT '0',
  `focus_score` int DEFAULT '0',
  `activity_score` int DEFAULT '0',
  `interaction_level` varchar(20) DEFAULT NULL,
  `metrics_json` json DEFAULT NULL COMMENT '存储metrics对象',
  `spatial_json` json DEFAULT NULL COMMENT '存储spatial对象',
  `risks_json` json DEFAULT NULL,
  `suggestions_json` json DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `student_behavior_records`
--

LOCK TABLES `student_behavior_records` WRITE;
/*!40000 ALTER TABLE `student_behavior_records` DISABLE KEYS */;
INSERT INTO `student_behavior_records` VALUES (1,NULL,'2025-11-21 09:11:17',20,0,0,NULL,NULL,NULL,NULL,NULL),(2,'101','2025-11-21 09:22:36',15,85,0,'Normal','{\"reading\": 10, \"writing\": 5}','{\"grid3x3\": [[1, 2, 1], [2, 5, 2], [1, 1, 1]]}','[\"有人玩手机\"]','[]'),(3,'101','2025-11-21 09:24:31',15,85,0,'Normal','{\"reading\": 10, \"writing\": 5}','{\"grid3x3\": [[1, 2, 1], [2, 5, 2], [1, 1, 1]]}','[\"有人玩手机\"]','[]'),(4,'Class-Default','2025-11-21 11:48:59',12,100,52,'high','{\"focus_score\": 100, \"reading_rate\": 0, \"writing_rate\": 75, \"sleeping_rate\": 0, \"activity_score\": 52, \"head_down_rate\": 0, \"distracted_rate\": 0, \"hand_raise_rate\": 25, \"phone_usage_rate\": 0, \"interaction_level\": \"high\", \"looking_around_rate\": 0}','{\"grid3x3\": [[0, 4, 0], [6, 6, 4], [0, 2, 2]], \"image_size\": {\"width\": 640, \"height\": 640}}','[]','[\"设计小组讨论或举手问答环节，提高互动密度。\"]'),(5,'Class-Default','2025-11-21 11:49:53',228,72,10,'low','{\"focus_score\": 72, \"reading_rate\": 20, \"writing_rate\": 0, \"sleeping_rate\": 0, \"activity_score\": 10, \"head_down_rate\": 38, \"distracted_rate\": 38, \"hand_raise_rate\": 0, \"phone_usage_rate\": 7, \"interaction_level\": \"low\", \"looking_around_rate\": 1}','{\"grid3x3\": [[78, 192, 46], [22, 46, 52], [2, 8, 10]], \"image_size\": {\"width\": 640, \"height\": 640}}','[\"手机数量较多（15），可能影响部分学生注意力。\", \"低头/阅读行为较集中，可能削弱与教师的互动与反馈。\"]','[\"提醒规范手机使用，必要时设置收纳或定时检查，强化课堂专注度。\", \"增加抬头交流的提问/点名频率，穿插短时任务促进眼神交流。\"]'),(6,'Class-Default','2025-11-21 11:50:24',22,56,2,'low','{\"focus_score\": 56, \"reading_rate\": 5, \"writing_rate\": 0, \"sleeping_rate\": 0, \"activity_score\": 2, \"head_down_rate\": 50, \"distracted_rate\": 50, \"hand_raise_rate\": 0, \"phone_usage_rate\": 18, \"interaction_level\": \"low\", \"looking_around_rate\": 0}','{\"grid3x3\": [[0, 0, 0], [2, 6, 2], [12, 6, 16]], \"image_size\": {\"width\": 640, \"height\": 640}}','[\"手机数量较多（4），可能影响部分学生注意力。\", \"低头/阅读行为较集中，可能削弱与教师的互动与反馈。\"]','[\"提醒规范手机使用，必要时设置收纳或定时检查，强化课堂专注度。\", \"增加抬头交流的提问/点名频率，穿插短时任务促进眼神交流。\", \"设计小组讨论或举手问答环节，提高互动密度。\"]'),(7,'Class-Default','2025-11-21 11:50:33',22,56,2,'low','{\"focus_score\": 56, \"reading_rate\": 5, \"writing_rate\": 0, \"sleeping_rate\": 0, \"activity_score\": 2, \"head_down_rate\": 50, \"distracted_rate\": 50, \"hand_raise_rate\": 0, \"phone_usage_rate\": 18, \"interaction_level\": \"low\", \"looking_around_rate\": 0}','{\"grid3x3\": [[0, 0, 0], [2, 6, 2], [12, 6, 16]], \"image_size\": {\"width\": 640, \"height\": 640}}','[\"手机数量较多（4），可能影响部分学生注意力。\", \"低头/阅读行为较集中，可能削弱与教师的互动与反馈。\"]','[\"提醒规范手机使用，必要时设置收纳或定时检查，强化课堂专注度。\", \"增加抬头交流的提问/点名频率，穿插短时任务促进眼神交流。\", \"设计小组讨论或举手问答环节，提高互动密度。\"]');
/*!40000 ALTER TABLE `student_behavior_records` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user`
--

DROP TABLE IF EXISTS `user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `password` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `sex` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `email` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `tel` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `role` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `avatar` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `time` datetime DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=MyISAM AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC COMMENT='Table ''.\\demo\\user'' is marked as crashed and should be repaired';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user`
--

LOCK TABLES `user` WRITE;
/*!40000 ALTER TABLE `user` DISABLE KEYS */;
INSERT INTO `user` VALUES (1,'admin','admin','张三','男','123@qq.com','1234567889','admin','https://wpimg.wallstcn.com/f778738c-e4f8-4870-b634-56703b4acafe.gif',NULL),(2,'123','123','张三','男','123@qq.com','1234567889','common','https://wpimg.wallstcn.com/f778738c-e4f8-4870-b634-56703b4acafe.gif',NULL),(3,'dulan','12345','tangchangjie','男','123@qq.com','12345678910','common','http://localhost:9999/files/0027f4900ee343a49b2b27e97f56e674_20200115132208_cwqad.gif','2025-09-22 21:31:50'),(4,'copilot_test_001','123456','张三','男','123@qq.com','1234567889','common','https://wpimg.wallstcn.com/f778738c-e4f8-4870-b634-56703b4acafe.gif','2025-09-22 21:34:37'),(5,'proxy30d198','123456','张三','男','123@qq.com','1234567889','common','https://wpimg.wallstcn.com/f778738c-e4f8-4870-b634-56703b4acafe.gif','2025-09-22 22:22:24'),(6,'proxyf32104','123456','张三','男','123@qq.com','1234567889','common','https://wpimg.wallstcn.com/f778738c-e4f8-4870-b634-56703b4acafe.gif','2025-09-22 22:29:25');
/*!40000 ALTER TABLE `user` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `videorecords`
--

DROP TABLE IF EXISTS `videorecords`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `videorecords` (
  `id` int NOT NULL AUTO_INCREMENT,
  `input_video` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `out_video` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `username` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `start_time` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `conf` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `weight` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `kind` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  PRIMARY KEY (`id`) USING BTREE
) ENGINE=InnoDB AUTO_INCREMENT=60 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `videorecords`
--

LOCK TABLES `videorecords` WRITE;
/*!40000 ALTER TABLE `videorecords` DISABLE KEYS */;
INSERT INTO `videorecords` VALUES (59,'http://localhost:9999/files/2959be5a3711409ba0d9ba23275b4acd_QQ2025114-14418-HD.mp4','http://localhost:9999/files/f11c80bc1b2944538fad29cabd835586_output.mp4','admin','2025-01-14 16:21:41','0.41','corn_best.pt','corn');
/*!40000 ALTER TABLE `videorecords` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-11-22 11:06:13
