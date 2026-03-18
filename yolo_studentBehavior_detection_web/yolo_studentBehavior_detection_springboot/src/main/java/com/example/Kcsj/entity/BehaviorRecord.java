package com.example.Kcsj.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.fasterxml.jackson.annotation.JsonFormat;
import lombok.Data;

import java.util.Date;

@Data
@TableName("student_behavior_records")
public class BehaviorRecord {
    @TableId(value = "id", type = IdType.AUTO)
    private Integer id;

    private String classroomId;

    @JsonFormat(pattern = "yyyy-MM-dd HH:mm:ss", timezone = "GMT+8")
    private Date recordTime;

    private Integer studentCount;
    private Integer focusScore;
    private Integer activityScore;
    private String interactionLevel;

    private String metricsJson;
    private String spatialJson;
    private String risksJson;
    private String suggestionsJson;
}
