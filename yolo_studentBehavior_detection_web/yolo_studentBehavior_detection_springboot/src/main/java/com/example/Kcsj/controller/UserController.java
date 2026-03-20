package com.example.Kcsj.controller;

import cn.hutool.core.util.StrUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.example.Kcsj.common.Result;
import com.example.Kcsj.common.auth.AuthContext;
import com.example.Kcsj.common.auth.AuthUser;
import com.example.Kcsj.common.auth.TokenService;
import com.example.Kcsj.entity.User;
import com.example.Kcsj.mapper.UserMapper;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Date;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

@RestController
@ConditionalOnProperty(name = "app.db.enabled", havingValue = "true")
@RequestMapping("/user")
public class UserController {
    @Resource
    private UserMapper userMapper;

    @Resource
    private TokenService tokenService;

    @GetMapping
    public Result<?> findPage(@RequestParam(defaultValue = "1") Integer pageNum,
                              @RequestParam(defaultValue = "10") Integer pageSize,
                              @RequestParam(defaultValue = "") String search) {
        Result<?> denied = requireAdmin();
        if (denied != null) {
            return denied;
        }

        LambdaQueryWrapper<User> wrapper = Wrappers.<User>lambdaQuery();
        wrapper.orderByDesc(User::getId);
        if (StrUtil.isNotBlank(search)) {
            wrapper.like(User::getUsername, search);
        }
        Page<User> userPage = userMapper.selectPage(new Page<>(pageNum, pageSize), wrapper);
        return Result.success(userPage);
    }

    @GetMapping("/{username}")
    public Result<?> getByUsername(@PathVariable String username) {
        AuthUser authUser = AuthContext.getCurrentUser();
        if (authUser == null) {
            return Result.error(401, "unauthorized");
        }
        if (!isAdmin(authUser) && !Objects.equals(authUser.getUsername(), username)) {
            return Result.error(403, "forbidden");
        }
        return Result.success(userMapper.selectByUsername(username));
    }

    @GetMapping("/all")
    public Result<?> getAll() {
        Result<?> denied = requireAdmin();
        if (denied != null) {
            return denied;
        }
        return Result.success(userMapper.selectList(null));
    }

    @PostMapping({"/login", "/signIn"})
    public Result<?> login(@RequestBody User userParam) {
        try {
            if (userParam == null || StrUtil.isBlank(userParam.getUsername()) || StrUtil.isBlank(userParam.getPassword())) {
                return Result.error(-1, "username and password are required");
            }

            User user = userMapper.selectByUsername(userParam.getUsername());
            if (user == null) {
                return Result.error(-1, "user not found");
            }
            if (!Objects.equals(userParam.getPassword(), user.getPassword())) {
                return Result.error(-1, "wrong password");
            }

            String token = tokenService.issueToken(user.getUsername(), user.getRole());
            user.setPassword(null);

            Map<String, Object> payload = new HashMap<>();
            payload.put("token", token);
            payload.put("user", user);
            return Result.success(payload);
        } catch (Exception e) {
            return Result.error(-1, "login failed: " + e.getMessage());
        }
    }

    @PostMapping({"/logout", "/signOut"})
    public Result<?> logout() {
        // Stateless token auth: sign-out is handled client-side by removing token.
        return Result.success();
    }

    @PostMapping("/register")
    public Result<?> register(@RequestBody User user) {
        try {
            if (user == null || StrUtil.isBlank(user.getUsername()) || StrUtil.isBlank(user.getPassword())) {
                return Result.error(-1, "username and password are required");
            }

            User existing = userMapper.selectOne(Wrappers.<User>lambdaQuery().eq(User::getUsername, user.getUsername()));
            if (existing != null) {
                return Result.error(-1, "username already exists");
            }

            User user1 = new User();
            user1.setUsername(user.getUsername());
            user1.setPassword(user.getPassword());
            user1.setName("user");
            user1.setSex("unknown");
            user1.setRole("common");
            user1.setEmail("123@qq.com");
            user1.setTime(new Date());
            user1.setTel("1234567889");
            user1.setAvatar("https://wpimg.wallstcn.com/f778738c-e4f8-4870-b634-56703b4acafe.gif");

            userMapper.insert(user1);
            return Result.success();
        } catch (Exception e) {
            return Result.error(-1, "register failed: " + e.getMessage());
        }
    }

    @PostMapping("/update")
    public Result<?> updates(@RequestBody User user) {
        if (user == null) {
            return Result.error(-1, "empty payload");
        }

        AuthUser authUser = AuthContext.getCurrentUser();
        if (authUser == null) {
            return Result.error(401, "unauthorized");
        }

        if (!isAdmin(authUser)) {
            User existing = userMapper.selectByUsername(authUser.getUsername());
            if (existing == null) {
                return Result.error(404, "user not found");
            }
            if (StrUtil.isNotBlank(user.getUsername()) && !Objects.equals(user.getUsername(), authUser.getUsername())) {
                return Result.error(403, "forbidden");
            }
            user.setId(existing.getId());
            user.setUsername(existing.getUsername());
            user.setRole(existing.getRole());
        }

        userMapper.updateById(user);
        return Result.success();
    }

    @DeleteMapping("/{id}")
    public Result<?> delete(@PathVariable int id) {
        Result<?> denied = requireAdmin();
        if (denied != null) {
            return denied;
        }
        userMapper.deleteById(id);
        return Result.success();
    }

    @PostMapping
    public Result<?> save(@RequestBody User user) {
        Result<?> denied = requireAdmin();
        if (denied != null) {
            return denied;
        }
        userMapper.insert(user);
        return Result.success();
    }

    private Result<?> requireAdmin() {
        AuthUser authUser = AuthContext.getCurrentUser();
        if (authUser == null) {
            return Result.error(401, "unauthorized");
        }
        if (!isAdmin(authUser)) {
            return Result.error(403, "forbidden");
        }
        return null;
    }

    private boolean isAdmin(AuthUser authUser) {
        return authUser != null && "admin".equals(authUser.getRole());
    }
}
