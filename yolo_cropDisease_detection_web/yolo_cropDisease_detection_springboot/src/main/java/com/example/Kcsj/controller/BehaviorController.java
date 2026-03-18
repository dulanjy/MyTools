package com.example.Kcsj.controller;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.example.Kcsj.entity.BehaviorRecord;
import com.example.Kcsj.mapper.BehaviorMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.*;

@RestController
@RequestMapping("/behavior")
public class BehaviorController {

    @Autowired
    private BehaviorMapper behaviorMapper;

    @GetMapping("/stats")
    public Map<String, Object> getStats() {
        List<BehaviorRecord> records = behaviorMapper.selectList(new QueryWrapper<BehaviorRecord>().orderByAsc("record_time"));
        
        Map<String, Object> result = new HashMap<>();
        result.put("code", 200);
        result.put("msg", "success");
        result.put("data", records);
        return result;
    }

    @PostMapping("/save")
    public Map<String, Object> saveRecord(@RequestBody BehaviorRecord record) {
        if (record.getRecordTime() == null) {
            record.setRecordTime(new Date());
        }
        behaviorMapper.insert(record);
        
        Map<String, Object> result = new HashMap<>();
        result.put("code", 200);
        result.put("msg", "success");
        return result;
    }
}
