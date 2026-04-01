package com.example.Kcsj.controller;
import cn.hutool.core.util.StrUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.example.Kcsj.common.Result;
import com.example.Kcsj.entity.CameraRecords;
import com.example.Kcsj.mapper.CameraRecordsMapper;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.List;

@RestController
@ConditionalOnProperty(name = "app.db.enabled", havingValue = "true")
@RequestMapping("/cameraRecords")
public class CameraRecordsController {
    @Resource
    CameraRecordsMapper cameraRecordsMapper;

    @GetMapping("/all")
    public Result<?> GetAll() {
        return Result.success(cameraRecordsMapper.selectList(null));
    }
    @GetMapping("/{id}")
    public Result<?> getById(@PathVariable int id) {
        System.out.println(id);
        return Result.success(cameraRecordsMapper.selectById(id));
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
        LambdaQueryWrapper<CameraRecords> wrapper = Wrappers.<CameraRecords>lambdaQuery();
        wrapper.orderByDesc(CameraRecords::getStartTime);
        if (StrUtil.isNotBlank(search)) {
            wrapper.like(CameraRecords::getUsername, search);
        }
        if (StrUtil.isNotBlank(search1)) {
            wrapper.like(CameraRecords::getKind, search1);
        }
        if (StrUtil.isNotBlank(search2)) {
            wrapper.like(CameraRecords::getWeight, search2);
        }
        if (StrUtil.isNotBlank(search3)) {
            wrapper.like(CameraRecords::getConf, search3);
        }
        if (StrUtil.isNotBlank(startTimeFrom)) {
            wrapper.ge(CameraRecords::getStartTime, startTimeFrom);
        }
        if (StrUtil.isNotBlank(startTimeTo)) {
            wrapper.le(CameraRecords::getStartTime, startTimeTo);
        }
        Page<CameraRecords> Page = cameraRecordsMapper.selectPage(new Page<>(pageNum, pageSize), wrapper);
        return Result.success(Page);
    }

    @DeleteMapping("/{id}")
    public Result<?> delete(@PathVariable int id) {
        cameraRecordsMapper.deleteById(id);
        return Result.success();
    }

    @PostMapping("/batchDelete")
    public Result<?> batchDelete(@RequestBody List<Integer> ids) {
        if (ids == null || ids.isEmpty()) {
            return Result.success();
        }
        cameraRecordsMapper.deleteBatchIds(ids);
        return Result.success();
    }

    @PostMapping("/update")
    public Result<?> updates(@RequestBody CameraRecords cameraRecords) {
        cameraRecordsMapper.updateById(cameraRecords);
        return Result.success();
    }


    @PostMapping
    public Result<?> save(@RequestBody CameraRecords cameraRecords) {
        System.out.println(cameraRecords);
        cameraRecordsMapper.insert(cameraRecords);
        return Result.success();
    }
}
