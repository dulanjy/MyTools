package com.example.Kcsj.controller;

import cn.hutool.core.util.StrUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.example.Kcsj.common.Result;
import com.example.Kcsj.entity.VideoRecords;
import com.example.Kcsj.mapper.VideoRecordsMapper;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.List;

@RestController
@ConditionalOnProperty(name = "app.db.enabled", havingValue = "true")
@RequestMapping("/videoRecords")
public class VideoRecordsController {
    @Resource
    VideoRecordsMapper videoRecordsMapper;

    @GetMapping("/all")
    public Result<?> GetAll() {
        return Result.success(videoRecordsMapper.selectList(null));
    }
    @GetMapping("/{id}")
    public Result<?> getById(@PathVariable int id) {
        System.out.println(id);
        return Result.success(videoRecordsMapper.selectById(id));
    }

    @GetMapping
    public Result<?> findPage(@RequestParam(defaultValue = "1") Integer pageNum,
                              @RequestParam(defaultValue = "10") Integer pageSize,
                              @RequestParam(defaultValue = "") String search,
                              @RequestParam(defaultValue = "") String search1,
                              @RequestParam(defaultValue = "") String search3,
                              @RequestParam(defaultValue = "") String search2,
                              @RequestParam(defaultValue = "") String startTimeFrom,
                              @RequestParam(defaultValue = "") String startTimeTo) {
        LambdaQueryWrapper<VideoRecords> wrapper = Wrappers.<VideoRecords>lambdaQuery();
        wrapper.orderByDesc(VideoRecords::getStartTime);
        if (StrUtil.isNotBlank(search)) {
            wrapper.like(VideoRecords::getUsername, search);
        }
        if (StrUtil.isNotBlank(search1)) {
            wrapper.like(VideoRecords::getKind, search1);
        }
        if (StrUtil.isNotBlank(search2)) {
            wrapper.like(VideoRecords::getWeight, search2);
        }
        if (StrUtil.isNotBlank(search3)) {
            wrapper.like(VideoRecords::getConf, search3);
        }
        if (StrUtil.isNotBlank(startTimeFrom)) {
            wrapper.ge(VideoRecords::getStartTime, startTimeFrom);
        }
        if (StrUtil.isNotBlank(startTimeTo)) {
            wrapper.le(VideoRecords::getStartTime, startTimeTo);
        }
        Page<VideoRecords> Page = videoRecordsMapper.selectPage(new Page<>(pageNum, pageSize), wrapper);
        return Result.success(Page);
    }

    @DeleteMapping("/{id}")
    public Result<?> delete(@PathVariable int id) {
        videoRecordsMapper.deleteById(id);
        return Result.success();
    }

    @PostMapping("/batchDelete")
    public Result<?> batchDelete(@RequestBody List<Integer> ids) {
        if (ids == null || ids.isEmpty()) {
            return Result.success();
        }
        videoRecordsMapper.deleteBatchIds(ids);
        return Result.success();
    }

    @PostMapping("/update")
    public Result<?> updates(@RequestBody VideoRecords videoRecords) {
        videoRecordsMapper.updateById(videoRecords);
        return Result.success();
    }


    @PostMapping
    public Result<?> save(@RequestBody VideoRecords videoRecords) {
        System.out.println(videoRecords);
        videoRecordsMapper.insert(videoRecords);
        return Result.success();
    }
}
