package com.example.Kcsj.controller;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.example.Kcsj.common.Result;
import com.example.Kcsj.entity.BehaviorRecord;
import com.example.Kcsj.mapper.BehaviorMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Date;
import java.util.List;

@RestController
@ConditionalOnProperty(name = "app.db.enabled", havingValue = "true")
@RequestMapping("/behavior")
public class BehaviorController {

    @Autowired
    private BehaviorMapper behaviorMapper;

    @GetMapping("/stats")
    public Result<List<BehaviorRecord>> getStats() {
        List<BehaviorRecord> records = behaviorMapper.selectList(
                new QueryWrapper<BehaviorRecord>().orderByAsc("record_time")
        );
        return Result.success(records);
    }

    @PostMapping("/save")
    public Result<Void> saveRecord(@RequestBody BehaviorRecord record) {
        if (record.getRecordTime() == null) {
            record.setRecordTime(new Date());
        }
        behaviorMapper.insert(record);
        return Result.success();
    }
}
