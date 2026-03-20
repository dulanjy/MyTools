package com.example.Kcsj.common.auth;

import com.alibaba.fastjson.JSON;
import com.example.Kcsj.common.Result;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

@Component
public class AuthInterceptor implements HandlerInterceptor {
    private final TokenService tokenService;

    public AuthInterceptor(TokenService tokenService) {
        this.tokenService = tokenService;
    }

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        if ("OPTIONS".equalsIgnoreCase(request.getMethod())) {
            return true;
        }

        String uri = request.getRequestURI();
        if (isExcluded(uri)) {
            return true;
        }

        AuthUser authUser = tokenService.verifyToken(request.getHeader("Authorization"));
        if (authUser == null) {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setCharacterEncoding("UTF-8");
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write(JSON.toJSONString(Result.error(401, "unauthorized")));
            return false;
        }

        AuthContext.setCurrentUser(authUser);
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) {
        AuthContext.clear();
    }

    private boolean isExcluded(String uri) {
        if (uri == null || uri.isEmpty()) {
            return true;
        }
        return uri.startsWith("/user/login")
                || uri.startsWith("/user/signIn")
                || uri.startsWith("/user/register")
                || uri.startsWith("/files/")
                || uri.equals("/error");
    }
}
